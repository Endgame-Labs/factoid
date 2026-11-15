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
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .fact_evals import JevFloors, Nli

if TYPE_CHECKING:
    from .app import Factoid, IngestResult
    from .document import Document
    from .project import Project

__all__ = [
    "Suite",
    "Variant",
    "RunResult",
    "run_suite",
    "parse_vary",
    "load_suites",
    "prf",
    "aupr",
    "precision_at_recall",
]


class Suite:
    """A labeled eval suite. Subclass it in `evals/` and implement `documents` and `score`."""

    name = "suite"
    description = ""

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


FACT_EVAL_CHAINS: dict[str, Any] = {
    "none": [],
    "nli": [Nli()],
    "jev_floors": [JevFloors()],
    "default": [Nli(), JevFloors()],
}


def _value(raw: str) -> Any:
    lowered = raw.lower()
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


def parse_vary(specs: list[str]) -> list[Variant]:
    """`["situate=on,off"]` becomes one variant per value. Several `--vary` options multiply."""
    variants = [Variant("default")]
    for spec in specs:
        key, _, values = spec.partition("=")
        if not key or not values:
            raise ValueError(f"--vary {spec!r}: want key=value1,value2")
        next_variants = []
        for variant in variants:
            for raw in values.split(","):
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
            value = FACT_EVAL_CHAINS[raw] if key == "fact_evals" and raw in FACT_EVAL_CHAINS else _value(raw)
            touched = False
            for klass in classes:
                if hasattr(klass, key):
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
        results = []
        latencies = []
        started = time.monotonic()
        for document in suite.documents(limit=limit):
            t0 = time.monotonic()
            result = app.ingest(document)
            latencies.append(time.monotonic() - t0)
            results.append(result)
            if log:
                log(f"  {variant.name}: {document.title or document.id}: {len(result.facts)} facts, "
                    f"{len(result.rejected)} rejected, {latencies[-1]:.1f}s")
        wall = time.monotonic() - started
        metrics = suite.score(app, results)
        usage = {"by_workload": app.meter.rows, "total": app.meter.total(), "wall_seconds": round(wall, 2)}
        app.close()
    latency = {}
    if latencies:
        ordered = sorted(latencies)
        latency = {"p50_doc_s": round(statistics.median(ordered), 2),
                   "p95_doc_s": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 2)}
    out = RunResult(suite.name, variant, metrics, usage, latency, len(results),
                    sum(len(r.facts) for r in results), sum(len(r.rejected) for r in results), folder)
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "scorecard.json").write_text(json.dumps(scorecard(out), indent=2, default=str))
    return out


def scorecard(result: RunResult) -> dict[str, Any]:
    return {
        "suite": result.suite,
        "variant": result.variant.name,
        "overrides": result.variant.overrides,
        "documents": result.documents,
        "facts": result.facts,
        "rejected": result.rejected,
        "metrics": result.metrics,
        "latency": result.latency,
        "usage": result.usage,
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
