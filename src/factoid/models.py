"""Models, providers, keys, and the call log.

Every model name is `provider/model`, so Factoid knows which key a workload needs. Calls go through `ModelClient`,
which logs them, counts tokens and time, and replays identical requests from a cache. The cache key is the exact
request, so changing a prompt, a question, or a model is a miss.

Base URLs: a provider's `<PROVIDER>_BASE_URL` environment variable wins; otherwise Factoid calls the vendor's API. A
call needs the provider's key, or a base URL (such as a gateway that adds credentials itself). The key is sent when it
is set.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .judge import Choice, Judgments, Noul, Question, Score, ScoreAnswer
from .steps import current_step

__all__ = [
    "PROVIDERS",
    "WORKLOADS",
    "CallLog",
    "Meter",
    "Model",
    "ModelClient",
    "ModelError",
    "Provider",
    "check_models",
    "keys_file",
    "load_keys",
]


class ModelError(RuntimeError):
    """A model call failed, or a workload has no usable model."""


@dataclass(frozen=True)
class Provider:
    name: str
    vendor_url: str
    key_env: str
    kinds: tuple[str, ...]  # which workloads it can serve
    key_url: str = ""  # where a person gets a key
    access: str = ""  # how to get access, when a key is not self-serve

    @property
    def base_url_env(self) -> str:
        return f"{self.name.upper()}_BASE_URL"

    def base_url(self) -> str:
        override = os.environ.get(self.base_url_env, "").strip()
        return override.rstrip("/") if override else self.vendor_url

    def api_key(self) -> str | None:
        load_keys()
        value = os.environ.get(self.key_env, "").strip()
        return value or None

    def ready(self) -> bool:
        """A key is set, or a base URL is, for a gateway that adds credentials itself."""
        load_keys()
        return bool(self.api_key() or os.environ.get(self.base_url_env, "").strip())

    def missing_key(self) -> str:
        return (f"no {self.key_env} is set. Set one with `factoid keys set {self.name}`, or set {self.base_url_env} "
                f"to a gateway that adds credentials itself.")

    def headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = self.api_key()
        if key:
            headers["authorization"] = f"Bearer {key}"
        return headers


PROVIDERS: dict[str, Provider] = {
    "typesafe": Provider(
        "typesafe",
        "https://api.typesafe.ai",
        "TYPESAFE_API_KEY",
        ("choose",),
        key_url="https://console.typesafe.ai/keys",
    ),
    "fireworks": Provider(
        "fireworks",
        "https://api.fireworks.ai/inference/v1",
        "FIREWORKS_API_KEY",
        ("choose", "generate", "embed", "rerank"),
        key_url="https://app.fireworks.ai/settings/users/api-keys",
    ),
    "openai": Provider(
        "openai",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        ("choose", "generate", "embed"),
        key_url="https://platform.openai.com/api-keys",
    ),
    "openrouter": Provider(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        ("generate",),
        key_url="https://openrouter.ai/settings/keys",
    ),
}

#: What each workload is for, in the words `factoid keys` and `factoid models` use.
WORKLOADS = {
    "choose": "the decision model: classify, evaluate facts, assess, link, and resolve",
    "generate": "extract facts and describe chunks",
    "embed": "search",
    "rerank": "reorder search results (optional)",
}

#: The generation steps that can have their own model. Each counts as the `generate` workload.
GENERATION_STEPS = ("situate", "extract", "repair", "discover")


def workload_kind(workload: str) -> str:
    """The workload a models key stands for: a generation step counts as `generate`."""
    return "generate" if workload in GENERATION_STEPS else workload


def check_models(models: dict[str, Model]) -> list[str]:
    """Problems with a models setting: unknown providers, and providers that cannot serve a workload."""
    problems = []
    for workload, model in models.items():
        if model is None:
            continue
        provider = PROVIDERS.get(model.provider_name)
        if provider is None:
            problems.append(f"{workload}: unknown provider {model.provider_name!r} in {model.name!r} "
                            f"(known: {', '.join(PROVIDERS)})")
            continue
        kind = workload_kind(workload)
        if kind in WORKLOADS and kind not in provider.kinds:
            able = [p.name for p in PROVIDERS.values() if kind in p.kinds]
            problems.append(f"{workload}: {provider.name} cannot serve the {kind} workload "
                            f"(providers that can: {', '.join(able)})")
    return problems


def factoid_home() -> Path:
    return Path(os.environ.get("FACTOID_HOME", Path.home() / ".factoid"))


def keys_file(project: Path | None = None, *, create_id: bool = False) -> Path | None:
    """`~/.factoid/.env`, or a project's own keys at `~/.factoid/projects/<id>/.env` (None when the project has no id
    yet; `create_id` gives it one)."""
    if project is None:
        return factoid_home() / ".env"
    from .project_id import project_id

    pid = project_id(project, create=create_id)
    return factoid_home() / "projects" / pid / ".env" if pid else None


def legacy_keys_file(project: Path) -> Path:
    """Where `keys set --project` stored keys before 0.1.1: inside the project. Still read, below the project's keys."""
    return project / ".factoid" / ".env"


_keys_loaded = False
#: Which file each loaded key came from. A key missing here came from the real environment.
KEY_SOURCES: dict[str, Path] = {}


def load_keys(project: Path | None = None) -> None:
    """Load keys from `~/.factoid/.env` and the project's keys. A real environment variable wins, then the project's
    keys (`~/.factoid/projects/<id>/.env`), then a project's old in-tree `.factoid/.env`, then the home file."""
    global _keys_loaded
    if _keys_loaded and project is None:
        return
    files = [keys_file()]  # lowest first
    if project is not None:
        files += [legacy_keys_file(project), keys_file(project)]
    for rank, path in enumerate(files):
        if path is None or not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            # A value from a lower file gives way to a higher one; one from the real environment never does.
            source = KEY_SOURCES.get(name)
            lower = source is not None and source in files[:rank]
            if name not in os.environ or lower:
                os.environ[name] = value.strip().strip("'\"")
                KEY_SOURCES[name] = path
    _keys_loaded = True


@dataclass(frozen=True)
class Model:
    """A pinned model for one workload, named `provider/model`."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    price_in: float | None = None  # dollars per million input tokens, when known
    price_out: float | None = None

    def __init__(self, name: str, price_in: float | None = None, price_out: float | None = None, *,
                 api_key: str | Callable[[], str] | None = None, base_url: str | None = None, **params: Any):
        """`params` go into each request body. `api_key` (a string, or a function that returns one, called for each
        request) and `base_url` replace the provider's key and address from the environment; they never enter a
        request body, the call cache key, or this model's repr."""
        if "/" not in name:
            raise ValueError(f"model {name!r} must be named provider/model")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "price_in", price_in)
        object.__setattr__(self, "price_out", price_out)
        object.__setattr__(self, "_api_key", api_key)
        object.__setattr__(self, "_base_url", base_url.rstrip("/") if base_url else None)

    def api_key(self) -> str | None:
        """The key given in code, else the provider's key from the environment."""
        given = self._api_key() if callable(self._api_key) else self._api_key
        return (given or "").strip() or self.provider.api_key()

    def base_url(self) -> str:
        return self._base_url or self.provider.base_url()

    def headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = self.api_key()
        if key:
            headers["authorization"] = f"Bearer {key}"
        return headers

    def ready(self) -> bool:
        return bool(self._api_key or self._base_url or self.provider.ready())

    @property
    def provider_name(self) -> str:
        return self.name.split("/", 1)[0]

    @property
    def model_id(self) -> str:
        return self.name.split("/", 1)[1]

    @property
    def provider(self) -> Provider:
        try:
            return PROVIDERS[self.provider_name]
        except KeyError:
            raise ModelError(f"unknown provider {self.provider_name!r} in {self.name!r}") from None

    def wire_id(self) -> str:
        """The model id the provider's API expects."""
        # "glm-5p3-flash" is short for a Fireworks model; "nomic-ai/nomic-embed-text-v1.5" is another org's, as is.
        if self.provider_name == "fireworks" and "/" not in self.model_id:
            return f"accounts/fireworks/models/{self.model_id}"
        return self.model_id

    def __hash__(self) -> int:
        return hash((self.name, json.dumps(self.params, sort_keys=True)))


class CallLog:
    """A SQLite cache of model calls. Identical requests replay their stored response."""

    #: What `put` keeps: "full" (requests and responses, which replay), "metadata" (the key, model, step, and tokens,
    #: with no text, so nothing replays), or "none" (nothing).
    MODES = ("full", "metadata", "none")

    def __init__(self, path: Path | None, mode: str = "full"):
        if mode not in self.MODES:
            raise ValueError(f"call_log must be one of {', '.join(self.MODES)}, not {mode!r}")
        self.path = path
        self.mode = mode
        self._lock = threading.Lock()
        if path is None:
            self._db = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.execute("pragma journal_mode=wal")
        self._db.execute(
            """create table if not exists calls (
                key text primary key, workload text, model text, request text, response text,
                input_tokens integer, output_tokens integer, seconds real, created_at real, factoid text)"""
        )
        columns = [row[1] for row in self._db.execute("pragma table_info(calls)")]
        if "factoid" not in columns:  # caches from before 0.1.1
            self._db.execute("alter table calls add column factoid text")
        if "step" not in columns:  # caches from before 0.1.10
            self._db.execute("alter table calls add column step text")
        self._db.commit()
        from .version import describe

        self.factoid = describe()

    @staticmethod
    def key(workload: str, model: str, request: dict[str, Any]) -> str:
        # Keys are sorted, so the order of a decision request's questions is added: order can change the answers.
        order = list(request["questions"]) if isinstance(request.get("questions"), dict) else None
        blob = json.dumps([workload, model, request, *([order] if order else [])], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        found = self.get_with_version(key)
        return found[0] if found else None

    def get_with_version(self, key: str) -> tuple[dict[str, Any], str | None] | None:
        """The stored response, and the Factoid (version and commit) that stored it, or None before 0.1.1."""
        with self._lock:
            row = self._db.execute("select response, factoid from calls where key = ?", (key,)).fetchone()
        return (json.loads(row[0]), row[1]) if row and row[0] is not None else None

    def put(self, key: str, workload: str, model: str, request: dict[str, Any], response: dict[str, Any],
            input_tokens: int, output_tokens: int, seconds: float, step: str | None = None) -> None:
        if self.mode == "none":
            return
        bodies = self.mode == "full"
        with self._lock:
            self._db.execute(
                "insert or replace into calls (key, workload, model, request, response, input_tokens, output_tokens, "
                "seconds, created_at, factoid, step) values (?,?,?,?,?,?,?,?,?,?,?)",
                (key, workload, model, json.dumps(request) if bodies else None,
                 json.dumps(response) if bodies else None, input_tokens, output_tokens, seconds, time.time(),
                 self.factoid, step),
            )
            self._db.commit()

    def recent(self, limit: int = 20, step: str | None = None) -> list[dict[str, Any]]:
        """The latest calls, newest first: when, the workload and step, the model, tokens, and the request."""
        sql = ("select created_at, workload, step, model, input_tokens, output_tokens, seconds, request from calls"
               + (" where step = ?" if step else "") + " order by created_at desc limit ?")
        with self._lock:
            rows = self._db.execute(sql, (step, limit) if step else (limit,)).fetchall()
        keys = ("created_at", "workload", "step", "model", "input_tokens", "output_tokens", "seconds", "request")
        return [{**dict(zip(keys, row)), "request": json.loads(row[7]) if row[7] else None} for row in rows]


@dataclass
class Meter:
    """Counts calls, cache hits, tokens, time, and cost, per workload."""

    rows: dict[str, dict[str, float]] = field(default_factory=dict)
    #: The same counts by the step that made each call, such as "evaluate" or "resolve".
    steps: dict[str, dict[str, float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, workload: str, *, hit: bool, input_tokens: int, output_tokens: int, seconds: float,
            cost: float | None, older: bool = False, step: str | None = None) -> None:
        """`older`: a cache hit saved by a different Factoid (another version or commit)."""
        with self._lock:
            row = self.steps.setdefault(step or workload, {"calls": 0, "cache_hits": 0, "input_tokens": 0,
                                                           "output_tokens": 0})
            row["calls"] += 1
            row["cache_hits"] += int(hit)
            row["input_tokens"] += input_tokens
            row["output_tokens"] += output_tokens
            row = self.rows.setdefault(workload, {"calls": 0, "cache_hits": 0, "older_hits": 0, "input_tokens": 0,
                                                  "output_tokens": 0, "seconds": 0.0, "cost": 0.0,
                                                  "priced": 1})
            row["calls"] += 1
            row["cache_hits"] += int(hit)
            row["older_hits"] = row.get("older_hits", 0) + int(hit and older)
            row["input_tokens"] += input_tokens
            row["output_tokens"] += output_tokens
            row["seconds"] += seconds
            if cost is None:
                row["priced"] = 0
            else:
                row["cost"] += cost

    def total(self) -> dict[str, float]:
        keys = ("calls", "cache_hits", "older_hits", "input_tokens", "output_tokens", "seconds", "cost")
        return {k: sum(r.get(k, 0) for r in self.rows.values()) for k in keys}


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds to wait from a Retry-After header, when the provider sends one."""
    value = response.headers.get("retry-after")
    try:
        return min(120.0, max(0.0, float(value))) if value else None
    except ValueError:
        return None


def _cost(model: Model, input_tokens: int, output_tokens: int) -> float | None:
    if model.price_in is None or model.price_out is None:
        return None
    return (input_tokens * model.price_in + output_tokens * model.price_out) / 1e6


class ModelClient:
    """Sends requests for the four workloads, through the cache and the meter."""

    def __init__(self, models: dict[str, Model], log: CallLog, meter: Meter | None = None,
                 replay: bool = True, timeout: float = 180.0, attempts: int = 12, deadline: float | None = None):
        self.models = models
        self.log = log
        self.meter = meter or Meter()
        self.replay = replay
        self.timeout, self.attempts, self.deadline = timeout, max(1, attempts), deadline
        # A short connect timeout, so a wrong base URL fails in seconds.
        self._http = httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))
        self._reachable: set[str] = set()  # providers that have answered, whose connect errors are retried

    # -- plumbing ---------------------------------------------------------------------------------------------

    def model(self, workload: str) -> Model:
        model = self.models.get(workload)
        if model is None:
            raise ModelError(f"no model is set for the {workload!r} workload; set it in settings.py")
        problems = check_models({workload: model})
        if problems:
            raise ModelError(f"{problems[0]}; change it in settings.py")
        return model

    def _post(self, workload: str, model: Model, url_path: str, body: dict[str, Any],
              cache_kind: str | None = None) -> tuple[dict[str, Any], bool]:
        # The cache key is the kind of call and the exact request; the workload only labels usage and cost.
        key = CallLog.key(cache_kind or workload, model.name, body)
        if self.replay:
            found = self.log.get_with_version(key)
            if found is not None:
                cached, saved_by = found
                self.meter.add(workload, hit=True, input_tokens=0, output_tokens=0, seconds=0.0, cost=0.0,
                               older=saved_by != self.log.factoid, step=current_step())
                return cached, True
        provider = model.provider
        if not model.ready():
            raise ModelError(f"{model.name}: {provider.missing_key()}")
        url = model.base_url() + url_path
        started = time.monotonic()
        response = None
        attempts = self.attempts

        def left() -> float:
            return float("inf") if self.deadline is None else self.deadline - (time.monotonic() - started)

        def wait(seconds: float, why: str) -> None:
            if seconds >= left():
                raise ModelError(f"{model.name}: gave up after {attempt + 1} tries in "
                                 f"{time.monotonic() - started:.0f}s (model_deadline): {why}")
            time.sleep(seconds)

        for attempt in range(attempts):
            try:
                response = self._http.post(url, headers=model.headers(), json=body,
                                           timeout=httpx.Timeout(max(0.1, min(self.timeout, left())), connect=10.0))
            except httpx.TransportError as err:
                # A host that has never answered is probably a wrong base URL: say so at once. A connect error
                # from a host that has answered before is a blip, and is retried.
                if provider.name not in self._reachable and isinstance(err, (httpx.ConnectError,
                                                                             httpx.ConnectTimeout)):
                    raise ModelError(f"{model.name}: could not connect to {model.base_url()} ({err})") from err
                if attempt == attempts - 1:
                    raise ModelError(f"{model.name}: {err}") from err
                wait(min(60, 2 ** attempt), str(err))
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                wait(_retry_after(response) or min(60, 2 ** attempt) * (0.5 + random.random()),
                     f"HTTP {response.status_code}")
                continue
            break
        assert response is not None
        self._reachable.add(provider.name)
        if response.status_code >= 400:
            hint = ""
            if response.status_code in (401, 403) and not model.api_key():
                hint = f" ({provider.base_url_env} is set and no key is; {provider.missing_key()})"
            elif response.status_code in (400, 401, 403) and model._api_key:
                hint = " (check the api_key given to this Model in code)"
            elif response.status_code in (400, 401, 403) and provider.api_key():
                hint = f" (check the key in {provider.key_env}: `factoid keys set {provider.name}` replaces it)"
            raise ModelError(f"{model.name}: HTTP {response.status_code}: {response.text[:500]}{hint}")
        data = response.json()
        seconds = time.monotonic() - started
        usage = data.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        self.log.put(key, workload, model.name, body, data, tokens_in, tokens_out, seconds, step=current_step())
        self.meter.add(workload, hit=False, input_tokens=tokens_in, output_tokens=tokens_out, seconds=seconds,
                       step=current_step(),
                       cost=_cost(model, tokens_in, tokens_out))
        return data, False

    # -- choose: the decision model -------------------------------------------------------------------------

    def ask(self, state: Any, questions: dict[str, Question]) -> Judgments:
        """Ask every question about one `state` in one request. Identical questions are asked once."""
        if not questions:
            return Judgments({})
        model = self.model("choose")
        by_key: dict[str, Question] = {}
        names_for: dict[str, list[str]] = {}
        for name, question in questions.items():
            key = question.key()
            by_key[key] = question
            names_for.setdefault(key, []).append(name)
        if model.provider_name == "openai":
            answers = self._ask_decisions(model, state, by_key)
        else:
            # TypeSafe's Jev and Fireworks' Rune both speak System One.
            path = "/v1/systemone" if model.provider_name == "typesafe" else "/systemone"
            body = {
                "model": model.wire_id(),
                "state": state,
                # In the order the caller listed them, which only changes when the code does. Sorting by key (a
                # hash) moved a question when its wording changed, and its neighbours' scores moved with it.
                "questions": {key: q.wire() for key, q in by_key.items()},
                **model.params,
            }
            data, _ = self._post("choose", model, path, body)
            answers = data.get("answers") or {}
        out: dict[str, Any] = {}
        for key, question in by_key.items():
            raw = answers.get(key)
            if raw is None:
                raise ModelError(f"{model.name}: no answer for question {question.instructions!r}")
            value = _answer(question, raw)
            for name in names_for[key]:
                out[name] = value
        return Judgments(out)

    def _ask_decisions(self, model: Model, state: Any, by_key: dict[str, Question]) -> dict[str, Any]:
        """Ask through OpenAI's Decisions API, and return the answers in System One's shape, keyed like `by_key`."""
        keys = list(by_key)  # the caller's order, as for System One
        if isinstance(state, (dict, list)):
            content: Any = [{"type": "input_json", "data": state}]
        else:
            content = str(state)
        body = {
            "model": model.wire_id(),
            "input": [{"role": "user", "content": content}],
            "questions": [_decisions_question(key, by_key[key]) for key in keys],
            **model.params,
        }
        data, _ = self._post("choose", model, "/decisions", body)
        answers: dict[str, Any] = {}
        for index, raw in enumerate(data.get("answers") or []):
            key = raw.get("name") or (keys[index] if index < len(keys) else None)
            if key is None:
                continue
            if raw.get("type") == "refusal":
                raise ModelError(f"{model.name}: refused to answer {by_key[key].instructions!r}")
            answers[key] = _from_decisions(raw)
        return answers

    # -- generate -------------------------------------------------------------------------------------------

    def model_for(self, step: str | None) -> tuple[str, Model]:
        """The model for a generation step (situate, extract, repair, discover), or `generate` when it has none."""
        if step and step in self.models:
            problems = check_models({step: self.models[step]})
            if problems:
                raise ModelError(f"{problems[0]}; change it in settings.py")
            return step, self.models[step]
        return "generate", self.model("generate")

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 4000,
                 system: str | None = None, step: str | None = None) -> str:
        workload, model = self.model_for(step)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        if model.provider_name == "openai":
            # OpenAI's reasoning models reject max_tokens and any temperature but the default.
            body: dict[str, Any] = {"model": model.wire_id(), "messages": messages,
                                    "max_completion_tokens": max_tokens, **model.params}
        else:
            body = {"model": model.wire_id(), "messages": messages, "max_tokens": max_tokens, "temperature": 0,
                    **model.params}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data, _ = self._post(step or workload, model, "/chat/completions", body, cache_kind="generate")
        choices = data.get("choices") or []
        if not choices:
            raise ModelError(f"{model.name}: no choices in response")
        return choices[0]["message"].get("content") or ""

    # -- embed ----------------------------------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.model("embed")
        out: list[list[float]] = []
        for start in range(0, len(texts), 64):
            batch = texts[start:start + 64]
            body = {"model": model.wire_id(), "input": batch, **model.params}
            data, _ = self._post("embed", model, "/embeddings", body)
            rows = sorted(data["data"], key=lambda r: r["index"])
            out.extend(r["embedding"] for r in rows)
        return out

    # -- rerank ---------------------------------------------------------------------------------------------

    def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        model = self.models.get("rerank")
        if model is None or not documents:
            return None
        body = {"model": model.wire_id(), "query": query, "documents": documents, **model.params}
        data, _ = self._post("rerank", model, "/rerank", body)
        scores = [0.0] * len(documents)
        for row in data.get("data") or data.get("results") or []:
            scores[row["index"]] = float(row.get("relevance_score", row.get("score", 0.0)))
        return scores


def _decisions_question(key: str, question: Question) -> dict[str, Any]:
    """One question in the shape of OpenAI's Decisions API."""
    if isinstance(question, Noul):
        instructions = question.instructions
        if (question.true, question.false) != ("Yes.", "No."):
            instructions += f"\nAnswer yes when: {question.true}\nAnswer no when: {question.false}"
        return {"type": "predicate", "name": key, "instructions": instructions}
    if isinstance(question, Choice):
        return {"type": "choice", "name": key, "instructions": question.instructions,
                "choices": [{"value": value, "description": description} for value, description in question.options]}
    if isinstance(question, Score):
        return {"type": "score", "name": key, "instructions": question.instructions,
                "levels": [{"label": str(n), "description": level} for n, level in enumerate(question.levels)]}
    raise ModelError(f"unknown question type {question.type!r}")


def _from_decisions(raw: dict[str, Any]) -> dict[str, Any]:
    """A Decisions API answer in System One's shape, which `_answer` reads."""
    kind = raw.get("type")
    if kind == "predicate":
        return {"noul": raw.get("probability")}
    if kind == "choice":
        return {"probabilities": {str(p["value"]): p["probability"] for p in raw.get("probabilities") or []}}
    if kind == "score":
        return {"score": raw.get("score"),
                "probabilities": {str(p["value"]): p["probability"] for p in raw.get("probabilities") or []}}
    return raw


def _answer(question: Question, raw: dict[str, Any]) -> Any:
    if isinstance(question, Noul):
        return float(raw.get("noul") or 0.0)
    if isinstance(question, Choice):
        probabilities = raw.get("probabilities") or {}
        return {name: float(probabilities.get(name, 0.0)) for name, _ in question.options}
    if isinstance(question, Score):
        probabilities = {int(k): float(v) for k, v in (raw.get("probabilities") or {}).items()}
        return ScoreAnswer(float(raw.get("score") or 0.0), probabilities)
    raise ModelError(f"unknown question type {question.type!r}")
