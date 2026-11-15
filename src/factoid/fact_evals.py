"""Fact evals: each decides one thing, whether a candidate fact is good enough to keep.

The default chain is `[Nli, JevFloors]`. It runs in order and rejects a candidate at the first failure. Custom fact
evals run on top of the default chain:

    fact_evals = [*Fact.fact_evals, CitesSourceEval]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .judge import Noul
from .runtime import current

if TYPE_CHECKING:
    from .fact import Fact

__all__ = ["EvalResult", "FactEval", "Nli", "JevFloors", "DEFAULT_FLOORS"]


@dataclass
class EvalResult:
    passed: bool
    scores: dict[str, float] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    near_miss: bool = False
    skipped: bool = False
    note: str = ""


class FactEval:
    """Base class for a fact eval. Subclass it and implement `check`."""

    name = "fact_eval"

    def check(self, fact: Fact) -> EvalResult:
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.name


class Nli(FactEval):
    """A small entailment model checks that the cited passages entail the sentence. Cheap, so it runs first.

    It runs when the project sets an `nli` model. With none set, it is skipped and the run says so.
    """

    name = "nli"
    floor = 0.5

    def check(self, fact: Fact) -> EvalResult:
        app = current()
        if "nli" not in app.client.models:
            return EvalResult(passed=True, skipped=True, note="no nli model is set; skipped")
        raise NotImplementedError("nli models are not wired up yet")


#: Starting floors. They are fixed values until calibration from labeled data is built.
DEFAULT_FLOORS: dict[str, float] = {
    "grounded": 0.6,
    "attribution": 0.55,
    "self_contained": 0.55,
    "atomic": 0.45,
    "useful": 0.45,
    "distinct": 0.3,
}

QUESTIONS: dict[str, Noul] = {
    "grounded": Noul(
        "Do the cited passages support everything the fact states? The fact may name the document, the people, "
        "and the companies from the document's title and context, since a fact must name what its passage only "
        "refers to.",
        true="Every claim in the fact is supported by the cited passages.",
        false="The fact states something the cited passages do not support.",
    ),
    "attribution": Noul(
        "Does the fact keep who said it, and whether it was certain, conditional, hedged, or negated, the same as "
        "the cited passages?",
        true="Attribution and certainty match the passages.",
        false="The fact changes who said it, or makes a hedge, condition, or negation into a plain claim.",
    ),
    "self_contained": Noul(
        "Can a reader understand the fact on its own? It must name its subject and the people, companies, and "
        "documents it refers to, with no unresolved pronouns and no references like 'this Agreement' or 'the Party'.",
        true="The fact is understandable alone.",
        false="The fact needs context it does not give.",
    ),
    "atomic": Noul(
        "Does the fact state one claim, rather than several joined together?",
        true="One claim.",
        false="Several claims.",
    ),
    "useful": Noul(
        "Is the fact worth keeping: a specific claim someone might later look up? Boilerplate, headings, "
        "definitions of ordinary words, and filler are not useful.",
        true="Worth keeping.",
        false="Not worth keeping.",
    ),
    "distinct": Noul(
        "Is the fact different from every stored fact listed in similar_stored_facts? If none are listed, answer yes.",
        true="It states something no listed fact states.",
        false="A listed fact already states the same claim.",
    ),
}


class JevFloors(FactEval):
    """Six yes-or-no questions in one decision-model call. Each probability has a floor, and all six must pass."""

    name = "jev_floors"
    #: A failure within this margin of its floor, on a question a rewording can fix, is a near miss.
    repair_margin = 0.2
    repairable = ("self_contained", "atomic", "attribution")

    def __init__(self, **floors: float):
        unknown = set(floors) - set(DEFAULT_FLOORS)
        if unknown:
            raise ValueError(f"unknown floors: {sorted(unknown)}")
        self.floors = {**DEFAULT_FLOORS, **floors}

    def check(self, fact: Fact) -> EvalResult:
        app = current()
        state: dict[str, Any] = fact.eval_state()
        judgments = app.client.ask(state, dict(QUESTIONS))
        scores = {name: float(judgments[name]) for name in QUESTIONS}
        failed = [name for name, floor in self.floors.items() if scores[name] < floor]
        near = bool(failed) and all(
            name in self.repairable and scores[name] >= self.floors[name] - self.repair_margin for name in failed
        )
        return EvalResult(passed=not failed, scores=scores, failed=failed, near_miss=near)

    def __repr__(self) -> str:
        changed = {k: v for k, v in self.floors.items() if DEFAULT_FLOORS[k] != v}
        return f"jev_floors({changed})" if changed else "jev_floors"
