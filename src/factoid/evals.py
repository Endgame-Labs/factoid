"""Evals: benchmarks decide algorithms.

A suite is a `Suite` subclass in the project's `evals/` package. It yields documents and scores a run. `factoid eval`
runs each suite, and `--vary key=a,b` runs the same documents under each value and compares quality, cost, and
latency. Every variant gets a fresh store; all variants share the project's call cache, so a re-run replays.
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .fact_evals import DecisionFloors, Nli

if TYPE_CHECKING:
    from .app import Factoid, IngestResult
    from .document import Document
    from .project import Project

__all__ = [
    "RunResult",
    "Suite",
    "Variant",
    "aupr",
    "load_suites",
    "parse_vary",
    "precision_at_recall",
    "prf",
    "run_suite",
]


class Suite:
    """A labeled eval suite. Subclass it in `evals/` and implement `documents` and `score`."""

    name = "suite"
    description = ""
    #: Documents ingested at once. Above 1, documents must be independent of each other.
    parallel = 1

    def documents(self, limit: int | None = None) -> Iterable[Document]:
        raise NotImplementedError

    def score(self, app: Factoid, results: list[IngestResult]) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class Variant:
    name: str
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    suite: str
    variant: Variant
    metrics: dict[str, Any]
    usage: dict[str, Any]
    latency: dict[str, float]
    documents: int
    facts: int
    rejected: int
    path: Path | None = None
    rejected_by_reason: dict[str, int] = field(default_factory=dict)
    samples: dict[str, list[str]] = field(default_factory=dict)
    skipped_evals: dict[str, int] = field(default_factory=dict)  # fact evals that did not run, and on how many facts


FACT_EVAL_CHAINS: dict[str, Any] = {
    "none": [],
    "nli": [Nli()],
    "decision_floors": [DecisionFloors()],
    "default": [Nli(), DecisionFloors()],
}


def _value(raw: str) -> Any:
    """A `--vary` value: on/off, none, a number, `@module:name` for an object the project defines, or a string."""
    if raw.startswith("@"):
        return _import(raw[1:])
    lowered = raw.lower()
    if lowered in ("none", "null"):
        return None
    if lowered in ("true", "on", "yes"):
        return True
    if lowered in ("false", "off", "no"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _import(spec: str) -> Any:
    module, _, name = spec.partition(":")
    if not module or not name:
        raise ValueError(f"--vary @{spec}: want @module:name")
    value: Any = importlib.import_module(module)
    for part in name.split("."):
        value = getattr(value, part)
    return value


def _split_values(values: str) -> list[str]:
    """Split on commas that are not inside parentheses."""
    out, depth, current = [], 0, ""
    for char in values:
        if char == "," and depth == 0:
            out.append(current)
            current = ""
            continue
        depth += char == "("
        depth -= char == ")"
        current += char
    out.append(current)
    return [v.strip() for v in out if v.strip()]


def fact_eval_chain(raw: str) -> list[Any]:
    """`none`, `nli`, `decision_floors`, `default`, `decision_floors(atomic=0.3;grounded=0.4)`, or `@module:name`."""
    if raw.startswith("@"):
        return list(_import(raw[1:]))
    if raw in FACT_EVAL_CHAINS:
        return FACT_EVAL_CHAINS[raw]
    if raw.startswith("decision_floors(") and raw.endswith(")"):
        floors = {}
        for pair in raw[len("decision_floors("):-1].split(";"):
            if pair.strip():
                key, _, value = pair.partition("=")
                floors[key.strip()] = float(value)
        return [Nli(), DecisionFloors(**floors)]
    raise ValueError(f"unknown fact eval chain {raw!r}")


def parse_vary(specs: list[str]) -> list[Variant]:
    """`["situate=on,off"]` becomes one variant per value. Several `--vary` options multiply."""
    variants = [Variant("default")]
    for spec in specs:
        key, _, values = spec.partition("=")
        if not key or not values:
            raise ValueError(f"--vary {spec!r}: want key=value1,value2")
        next_variants = []
        for variant in variants:
            for raw in _split_values(values):
                name = f"{key}={raw}" if variant.name == "default" else f"{variant.name} {key}={raw}"
                next_variants.append(Variant(name, {**variant.overrides, key: raw}))
        variants = next_variants
    return variants


@contextmanager
def applied(project: Project, overrides: dict[str, Any]) -> Iterator[None]:
    """Set each override on every project class that has the attribute, and restore afterwards."""
    saved: list[tuple[type, str, Any, bool]] = []
    classes = [*project.documents, *project.facts, *project.entities, project.settings]
    try:
        for key, raw in overrides.items():
            value = fact_eval_chain(raw) if key == "fact_evals" else _value(raw)
            touched = False
            for klass in classes:
                if hasattr(klass, key):
                    current_value = getattr(klass, key)
                    if callable(current_value) and not isinstance(current_value, type) and isinstance(value, str):
                        raise ValueError(f"--vary {key}: {klass.__name__}.{key} is a method, and {raw!r} would "
                                         f"replace it; --vary sets settings, and a strategy is a value defined in "
                                         f"Python (--vary {key}=@module:NAME)")
                    saved.append((klass, key, klass.__dict__.get(key), key in klass.__dict__))
                    setattr(klass, key, value)
                    touched = True
            if not touched:
                raise ValueError(f"--vary {key}: no project class has a setting named {key!r}")
        yield
    finally:
        for klass, key, old, had in reversed(saved):
            if had:
                setattr(klass, key, old)
            else:
                delattr(klass, key)


def run_suite(project: Project, suite: Suite, variant: Variant, *, limit: int | None = None,
              run_dir: Path | None = None, replay: bool = True, log: Any = None) -> RunResult:
    from .runtime import use

    folder = run_dir / _slug(variant.name) if run_dir else None
    data_dir = project.settings.data_path(project.root)
    with applied(project, variant.overrides):
        app = project.app(data_dir=folder, calls_path=data_dir / "calls.db", replay=replay,
                          in_memory=folder is None)
        use(app)
        latencies: list[float] = []

        def one(document: Document) -> IngestResult:
            use(app)
            t0 = time.monotonic()
            result = app.ingest(document)
            latencies.append(time.monotonic() - t0)
            if log:
                label = getattr(document, "title", None) or getattr(document, "uri", None) or document.id
                log(f"  {variant.name}: {label}: {len(result.facts)} facts, {len(result.rejected)} rejected, "
                    f"{latencies[-1]:.1f}s")
            return result

        started = time.monotonic()
        documents = list(suite.documents(limit=limit))
        if suite.parallel > 1:
            with ThreadPoolExecutor(max_workers=suite.parallel) as pool:
                results = list(pool.map(one, documents))
        else:
            results = [one(d) for d in documents]
        wall = time.monotonic() - started
        metrics = suite.score(app, results)
        skipped_evals = dict(app.skipped_evals)
        usage = {"by_workload": app.meter.rows, "total": app.meter.total(), "wall_seconds": round(wall, 2)}
        app.close()
    latency = {}
    if latencies:
        ordered = sorted(latencies)
        latency = {"p50_doc_s": round(statistics.median(ordered), 2),
                   "p95_doc_s": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 2)}
    reasons: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for r in results:
        for rejected in r.rejected:
            for reason in rejected.reasons or ["unknown"]:
                reasons[reason] = reasons.get(reason, 0) + 1
                samples.setdefault(reason, [])
                if len(samples[reason]) < 5:
                    samples[reason].append(rejected.text)
    out = RunResult(suite.name, variant, metrics, usage, latency, len(results),
                    sum(len(r.facts) for r in results), sum(len(r.rejected) for r in results), folder,
                    dict(sorted(reasons.items(), key=lambda kv: -kv[1])), samples, skipped_evals)
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "scorecard.json").write_text(json.dumps(scorecard(out), indent=2, default=str))
        # Every rejected fact with its scores and quotes, for reviewing what the fact evals turned away.
        with open(folder / "rejected.jsonl", "w") as f:
            for r in results:
                for rejected in r.rejected:
                    f.write(json.dumps({"document": r.document.title or r.document.id, "text": rejected.text,
                                        "reasons": rejected.reasons, "scores": rejected.scores,
                                        "quotes": rejected.quotes, "repairs": rejected.repairs},
                                       default=str) + "\n")
    return out


def scorecard(result: RunResult) -> dict[str, Any]:
    return {
        "suite": result.suite,
        "variant": result.variant.name,
        "overrides": result.variant.overrides,
        "documents": result.documents,
        "facts": result.facts,
        "rejected": result.rejected,
        "rejected_by_reason": result.rejected_by_reason,
        "metrics": result.metrics,
        "latency": result.latency,
        "usage": result.usage,
        "rejected_samples": result.samples,
        "skipped_fact_evals": result.skipped_evals,
    }


def load_suites(project: Project) -> dict[str, type[Suite]]:
    """Every `Suite` subclass in the project's `evals/` folder."""
    folder = project.root / "evals"
    found: dict[str, type[Suite]] = {}
    if not folder.is_dir():
        return found
    if str(project.root) not in sys.path:
        sys.path.insert(0, str(project.root))
    for path in sorted(folder.rglob("*.py")):
        if path.name.startswith("_") or "test" in path.stem:
            continue
        name = "evals." + ".".join(path.relative_to(folder).with_suffix("").parts)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, Suite) and value is not Suite \
                    and value.__module__ == name:
                found[value.name] = value
    return found


# -- metrics ------------------------------------------------------------------------------------------------


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn}


def _curve(scores: list[float], labels: list[bool]) -> list[tuple[float, float]]:
    """(recall, precision) points, best precision for each recall."""
    positives = sum(labels)
    if positives == 0:
        return []
    pairs = sorted(zip(scores, labels), key=lambda p: -p[0])
    tp = fp = 0
    points = []
    for _, label in pairs:
        if label:
            tp += 1
        else:
            fp += 1
        points.append((tp / positives, tp / (tp + fp)))
    best, out = 0.0, []
    for recall, precision in reversed(points):
        best = max(best, precision)
        out.append((recall, best))
    return list(reversed(out))


def aupr(scores: list[float], labels: list[bool]) -> float:
    """Area under the precision-recall curve (step interpolation)."""
    curve = _curve(scores, labels)
    area, last_recall = 0.0, 0.0
    for recall, precision in curve:
        area += (recall - last_recall) * precision
        last_recall = recall
    return round(area, 4)


def precision_at_recall(scores: list[float], labels: list[bool], recall: float) -> float:
    curve = _curve(scores, labels)
    reachable = [p for r, p in curve if r >= recall]
    return round(max(reachable), 4) if reachable else 0.0


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "=-_." else "_" for c in name) or "default"
