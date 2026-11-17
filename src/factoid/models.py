"""Models, providers, keys, and the call log.

Every model name is `provider/model`, so Factoid knows which key a workload needs. Calls go through `ModelClient`,
which logs them, counts tokens and time, and replays identical requests from a cache. The cache key is the exact
request, so changing a prompt, a question, or a model is a miss.

Base URLs: a provider's `<PROVIDER>_BASE_URL` environment variable wins. Otherwise, with a key set, Factoid calls the
vendor's API. With no key, it tries the exe.dev integration host for that provider, which injects credentials; off
exe.dev that host does not answer, and the error says to set a key.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .judge import Choice, Judgments, Noul, Question, Score, ScoreAnswer

__all__ = [
    "Model",
    "Provider",
    "PROVIDERS",
    "ModelError",
    "CallLog",
    "Meter",
    "ModelClient",
    "load_keys",
    "keys_file",
]


class ModelError(RuntimeError):
    """A model call failed, or a workload has no usable model."""


@dataclass(frozen=True)
class Provider:
    name: str
    vendor_url: str
    integration_url: str
    key_env: str
    kinds: tuple[str, ...]  # which workloads it can serve

    def base_url(self) -> str:
        override = os.environ.get(f"{self.name.upper()}_BASE_URL")
        if override:
            return override.rstrip("/")
        if self.api_key():
            return self.vendor_url
        return self.integration_url

    def api_key(self) -> str | None:
        load_keys()
        value = os.environ.get(self.key_env, "").strip()
        return value or None

    def uses_integration(self) -> bool:
        """No key and no base URL override: calls go to the exe.dev integration host."""
        return not os.environ.get(f"{self.name.upper()}_BASE_URL") and not self.api_key()

    def missing_key(self) -> str:
        return (f"no {self.key_env} is set, so Factoid tried the exe.dev integration host ({self.integration_url}), "
                f"which only answers on exe.dev. Set a key with `factoid keys set {self.name}`.")

    def headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = self.api_key()
        if key and not os.environ.get(f"{self.name.upper()}_BASE_URL"):
            headers["authorization"] = f"Bearer {key}"
        return headers


PROVIDERS: dict[str, Provider] = {
    "typesafe": Provider(
        "typesafe", "https://api.typesafe.ai", "https://typesafe.int.exe.xyz", "TYPESAFE_API_KEY", ("choose",)
    ),
    "fireworks": Provider(
        "fireworks",
        "https://api.fireworks.ai/inference/v1",
        "https://fireworks.int.exe.xyz/inference/v1",
        "FIREWORKS_API_KEY",
        ("generate", "embed", "rerank"),
    ),
    "openai": Provider(
        "openai", "https://api.openai.com/v1", "https://openai.int.exe.xyz/v1", "OPENAI_API_KEY", ("generate", "embed")
    ),
    "openrouter": Provider(
        "openrouter",
        "https://openrouter.ai/api/v1",
        "https://openrouter.int.exe.xyz/api/v1",
        "OPENROUTER_API_KEY",
        ("generate",),
    ),
}


def keys_file(project: Path | None = None) -> Path:
    if project is not None:
        return project / ".factoid" / ".env"
    return Path(os.environ.get("FACTOID_HOME", Path.home() / ".factoid")) / ".env"


_keys_loaded = False


def load_keys(project: Path | None = None) -> None:
    """Load keys from `~/.factoid/.env` and the project's `.factoid/.env`. Real environment variables win."""
    global _keys_loaded
    if _keys_loaded and project is None:
        return
    for path in (keys_file(), keys_file(project) if project else None):
        if path is None or not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            os.environ.setdefault(name.strip(), value.strip().strip("'\""))
    _keys_loaded = True


@dataclass(frozen=True)
class Model:
    """A pinned model for one workload, named `provider/model`."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    price_in: float | None = None  # dollars per million input tokens, when known
    price_out: float | None = None

    def __init__(self, name: str, price_in: float | None = None, price_out: float | None = None, **params: Any):
        if "/" not in name:
            raise ValueError(f"model {name!r} must be named provider/model")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "price_in", price_in)
        object.__setattr__(self, "price_out", price_out)

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

    def __init__(self, path: Path | None):
        self.path = path
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
                input_tokens integer, output_tokens integer, seconds real, created_at real)"""
        )
        self._db.commit()

    @staticmethod
    def key(workload: str, model: str, request: dict[str, Any]) -> str:
        blob = json.dumps([workload, model, request], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("select response from calls where key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, workload: str, model: str, request: dict[str, Any], response: dict[str, Any],
            input_tokens: int, output_tokens: int, seconds: float) -> None:
        with self._lock:
            self._db.execute(
                "insert or replace into calls values (?,?,?,?,?,?,?,?,?)",
                (key, workload, model, json.dumps(request), json.dumps(response), input_tokens, output_tokens,
                 seconds, time.time()),
            )
            self._db.commit()


@dataclass
class Meter:
    """Counts calls, cache hits, tokens, time, and cost, per workload."""

    rows: dict[str, dict[str, float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, workload: str, *, hit: bool, input_tokens: int, output_tokens: int, seconds: float,
            cost: float | None) -> None:
        with self._lock:
            row = self.rows.setdefault(workload, {"calls": 0, "cache_hits": 0, "input_tokens": 0,
                                                  "output_tokens": 0, "seconds": 0.0, "cost": 0.0,
                                                  "priced": 1})
            row["calls"] += 1
            row["cache_hits"] += int(hit)
            row["input_tokens"] += input_tokens
            row["output_tokens"] += output_tokens
            row["seconds"] += seconds
            if cost is None:
                row["priced"] = 0
            else:
                row["cost"] += cost

    def total(self) -> dict[str, float]:
        keys = ("calls", "cache_hits", "input_tokens", "output_tokens", "seconds", "cost")
        return {k: sum(r[k] for r in self.rows.values()) for k in keys}


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
                 replay: bool = True, timeout: float = 180.0):
        self.models = models
        self.log = log
        self.meter = meter or Meter()
        self.replay = replay
        self._http = httpx.Client(timeout=timeout)

    # -- plumbing ---------------------------------------------------------------------------------------------

    def model(self, workload: str) -> Model:
        model = self.models.get(workload)
        if model is None:
            raise ModelError(f"no model is set for the {workload!r} workload; set it in settings.py")
        return model

    def _post(self, workload: str, model: Model, url_path: str, body: dict[str, Any],
              cache_kind: str | None = None) -> tuple[dict[str, Any], bool]:
        # The cache key is the kind of call and the exact request; the workload only labels usage and cost.
        key = CallLog.key(cache_kind or workload, model.name, body)
        if self.replay:
            cached = self.log.get(key)
            if cached is not None:
                usage = cached.get("usage") or {}
                self.meter.add(workload, hit=True, input_tokens=0, output_tokens=0, seconds=0.0, cost=0.0)
                _ = usage
                return cached, True
        provider = model.provider
        url = provider.base_url() + url_path
        started = time.monotonic()
        response = None
        attempts = 12  # rate limits during a big eval can last minutes; give up only after about ten
        for attempt in range(attempts):
            try:
                response = self._http.post(url, headers=provider.headers(), json=body)
            except httpx.TransportError as err:
                if provider.uses_integration() and isinstance(err, httpx.ConnectError):
                    raise ModelError(f"{model.name}: {provider.missing_key()}") from err
                if attempt == attempts - 1:
                    raise ModelError(f"{model.name}: {err}") from err
                time.sleep(min(60, 2 ** attempt))
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(_retry_after(response) or min(60, 2 ** attempt) * (0.5 + random.random()))
                continue
            break
        assert response is not None
        if response.status_code >= 400:
            hint = ""
            if provider.uses_integration() and response.status_code in (401, 403, 404):
                hint = f" ({provider.missing_key()})"
            elif response.status_code in (400, 401, 403) and provider.api_key():
                hint = f" (check the key in {provider.key_env}: `factoid keys set {provider.name}` replaces it)"
            raise ModelError(f"{model.name}: HTTP {response.status_code}: {response.text[:500]}{hint}")
        data = response.json()
        seconds = time.monotonic() - started
        usage = data.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        self.log.put(key, workload, model.name, body, data, tokens_in, tokens_out, seconds)
        self.meter.add(workload, hit=False, input_tokens=tokens_in, output_tokens=tokens_out, seconds=seconds,
                       cost=_cost(model, tokens_in, tokens_out))
        return data, False

    # -- choose: the decision model -------------------------------------------------------------------------

    def ask(self, state: Any, questions: dict[str, Question]) -> Judgments:
        """Ask every question about one `state` in one request. Identical questions are asked once."""
        if not questions:
            return Judgments({})
        model = self.model("choose")
        if model.provider_name != "typesafe":
            raise ModelError(f"{model.name}: only Jev (typesafe/...) is supported for the choose workload so far")
        by_key: dict[str, Question] = {}
        names_for: dict[str, list[str]] = {}
        for name, question in questions.items():
            key = question.key()
            by_key[key] = question
            names_for.setdefault(key, []).append(name)
        body = {
            "model": model.model_id,
            "state": state,
            "questions": {key: q.wire() for key, q in sorted(by_key.items())},
            **model.params,
        }
        data, _ = self._post("choose", model, "/v1/systemone", body)
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

    # -- generate -------------------------------------------------------------------------------------------

    def model_for(self, step: str | None) -> tuple[str, Model]:
        """The model for a generation step (situate, extract, repair, discover), or `generate` when it has none."""
        if step and step in self.models:
            return step, self.models[step]
        return "generate", self.model("generate")

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 4000,
                 system: str | None = None, step: str | None = None) -> str:
        workload, model = self.model_for(step)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {"model": model.wire_id(), "messages": messages, "max_tokens": max_tokens,
                                "temperature": 0, **model.params}
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
