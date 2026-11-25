"""Fact evals: each decides one thing, whether a candidate fact is good enough to keep.

The default chain is `[Nli, DecisionFloors]`. It runs in order and rejects a candidate at the first failure. Custom fact
evals run on top of the default chain:

    fact_evals = [*Fact.fact_evals, CitesSourceEval]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from .judge import Judgments, Noul
from .runtime import current

if TYPE_CHECKING:
    from .fact import Fact

__all__ = [
    "DEFAULT_FLOORS",
    "DEFAULT_TARGETS",
    "MODEL_FLOORS",
    "MODEL_TARGETS",
    "QUESTIONS",
    "DecisionFloors",
    "EvalResult",
    "FactEval",
    "Nli",
]


@dataclass
class EvalResult:
    passed: bool
    scores: dict[str, float] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    #: Questions the fact passed but scored below their target on: worth one repair, keeping the fact if it fails.
    short: list[str] = field(default_factory=list)
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
    "grounded": 0.45,
    "attribution": 0.3,
    "self_contained": 0.1,  # a strict question: below its target a fact is repaired, not dropped
    "atomic": 0.25,
    "useful": 0.45,
    "distinct": 0.2,  # dropping a fact as a repeat needs the same confidence as a duplicate in resolve
}

#: Starting targets: a passing fact below its target gets one repair, and keeps its old wording if the repair misses.
DEFAULT_TARGETS: dict[str, float] = {"self_contained": 0.5}

#: Floors and targets for decision models whose probabilities run on a different scale from Jev's, which the defaults
#: were set on. Each entry replaces the defaults for that model, except where a project sets its own value. Rune's
#: were matched to Jev's pass rates on the same 1,450 fact eval requests from the example apps (2026-11-17): Rune
#: ranks facts much like Jev, but scores "atomic" lower and "self_contained" higher.
MODEL_FLOORS: dict[str, dict[str, float]] = {
    "fireworks/rune": {"grounded": 0.25, "self_contained": 0.05, "atomic": 0.08, "useful": 0.25, "distinct": 0.05},
}
MODEL_TARGETS: dict[str, dict[str, float]] = {
    "fireworks/rune": {"self_contained": 0.95},
}

QUESTIONS: dict[str, Noul] = {
    "grounded": Noul(
        "Do the cited passages support the claim the fact makes? Judge the claim only. Names and dates that resolve "
        "a reference in the passages ('he', 'the plane', 'yesterday') may come from text_before_passages or the "
        "document's details, and words that name the document, its section, or its parties may come from elsewhere "
        "in the document, so do not count them against the fact.",
        true="The passages support the claim.",
        false="The fact claims something the passages do not say, or changes what they say.",
    ),
    "attribution": Noul(
        "Does the fact report the passages' claim with the same speaker, about the same subject, and with the same "
        "certainty? If a passage shows who said it, the fact must not credit the words to anyone else. If the "
        "passages have no speaker, as in narration, a report, or a contract clause, the fact need not name one. A "
        "condition, hedge, plan, belief, or negation in the passages must stay in the fact. Context the fact adds, "
        "such as the document's name, the parties, the event, or the date, is fine.",
        true="The speaker (or no speaker), the subject, and the certainty all match the passages.",
        false="The fact credits the claim to the wrong person, changes who or what it is about, or turns a "
              "condition, hedge, or negation into a plain claim.",
    ),
    "self_contained": Noul(
        "Can a reader who has not seen the source understand the fact on its own? The fact must name or describe, "
        "well enough to identify, every person, organization, place, document, and event it refers to. It fails if "
        "it has a pronoun or a description ('he', 'the company', 'the president', 'this Agreement', 'the case') "
        "whose referent the fact itself does not give, or a time relative to an unstated date ('yesterday', 'last "
        "week'). Text the source itself omits or redacts, such as [***], does not count against the fact.",
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
        "definitions of ordinary words, and filler are not useful, and neither are remarks about the document or "
        "conversation itself, such as greetings, thanks, and what comes next.",
        true="Worth keeping.",
        false="Not worth keeping.",
    ),
    "distinct": Noul(
        "Is the fact different from every stored fact listed in similar_stored_facts? A fact from a different source "
        "or date that gives a new or changed value is different. If none are listed, answer yes.",
        true="It states something no listed fact states.",
        false="A listed fact already states the same claim.",
    ),
}


class DecisionFloors(FactEval):
    """Yes-or-no questions in one decision-model call. Each probability has a floor, and all must pass.

    Change a floor, reword a question, add one, or drop one, per fact class or per document class:

        DecisionFloors(grounded=0.3)
        DecisionFloors(questions={"useful": Noul("Would a researcher look this up?"), "atomic": None})
        DecisionFloors(questions={"on_topic": Noul("Is the fact about the program's topic?")}, on_topic=0.5)

    A target sits above a floor. A fact that passes the floor but scores below the target gets one repair. The repair
    replaces it only when every repaired sentence passes and scores higher on each question it fell short on;
    otherwise the fact is kept as it was. So a strict question can push for explicit facts without throwing useful
    ones away:

        DecisionFloors(self_contained=0.2, targets={"self_contained": 0.5})

    A question with a floor of 0 never rejects; with a target, it only asks for repairs.

    A subclass can set `questions`, `floors`, and `targets` as class attributes instead.

    The defaults were set on Jev. For another decision model, `model_floors` and `model_targets` hold its own values,
    keyed by model name; they apply to every floor and target the project has not set itself.
    """

    name = "decision_floors"
    questions: ClassVar[dict[str, Noul]] = QUESTIONS
    floors: dict[str, float] = DEFAULT_FLOORS
    targets: dict[str, float] = DEFAULT_TARGETS
    model_floors: ClassVar[dict[str, dict[str, float]]] = MODEL_FLOORS
    model_targets: ClassVar[dict[str, dict[str, float]]] = MODEL_TARGETS
    #: Failures a rewording or a split can fix. A fact that fails only these gets one repair, however low the score:
    #: the repair sees the text before the quote, so it can name what "he" or "this aircraft" refers to.
    repairable = ("self_contained", "atomic", "attribution")
    #: Also repair a fact that fails "grounded", by trimming it to what its passages say. On by default since the
    #: evals showed it helps (decision 129, issue #6).
    repair_grounded: bool = True
    #: A "useful" failure within this margin rides along with a repairable one, since splitting a compound fact often
    #: makes each part useful.
    repair_margin = 0.2

    def __init__(self, questions: dict[str, Noul | None] | None = None, targets: dict[str, float] | None = None,
                 repair_grounded: bool | None = None, **floors: float):
        if repair_grounded is not None:
            self.repair_grounded = repair_grounded
        merged: dict[str, Noul | None] = {**type(self).questions, **(questions or {})}
        self.questions = {k: q for k, q in merged.items() if q is not None}
        unknown = set(floors) - set(self.questions)
        if unknown:
            raise ValueError(f"floors for questions that are not asked: {sorted(unknown)}")
        self.floors = {k: v for k, v in {**type(self).floors, **floors}.items() if k in self.questions}
        missing = set(self.questions) - set(self.floors)
        if missing:
            raise ValueError(f"questions with no floor: {sorted(missing)}")
        self._changed = {k: q for k, q in merged.items() if QUESTIONS.get(k) is not q}
        # The project owns a floor or target it set: by argument, or by a subclass value that differs from the
        # default. Model values apply to the rest.
        self._own_floors = set(floors) | {k for k, v in type(self).floors.items() if DEFAULT_FLOORS.get(k) != v}
        self._own_targets = set(targets or {}) | {
            k for k, v in type(self).targets.items() if DEFAULT_TARGETS.get(k) != v}
        self.targets = {k: v for k, v in {**type(self).targets, **(targets or {})}.items() if k in self.questions}
        for name, target in self.targets.items():
            if target < self.floors[name]:
                raise ValueError(f"target for {name!r} ({target}) is below its floor ({self.floors[name]})")

    def floors_for(self, model: str | None) -> tuple[dict[str, float], dict[str, float]]:
        """The floors and targets for a decision model: its own values where it has them and the project has not
        set one."""
        floors = {**self.floors, **{k: v for k, v in self.model_floors.get(model or "", {}).items()
                                    if k in self.floors and k not in self._own_floors}}
        targets = {**self.targets, **{k: v for k, v in self.model_targets.get(model or "", {}).items()
                                      if k in self.targets and k not in self._own_targets}}
        return floors, {k: max(v, floors[k]) for k, v in targets.items()}

    def check(self, fact: Fact) -> EvalResult:
        app = current()
        state: dict[str, Any] = fact.eval_state()
        asked: dict[str, Any] = dict(self.questions)
        early = getattr(type(fact), "assess_with_evaluate", True)
        if early:  # one request instead of two: the assess questions ride along, prefixed so names cannot clash
            asked.update({f"assess.{k}": q for k, q in type(fact).assess_questions().items()})
        judgments = app.client.ask(state, asked)
        if early:
            fact.assessed_early = (fact.text, Judgments({k: judgments[f"assess.{k}"]
                                                         for k in type(fact).assess_questions()}))
        scores = {name: float(judgments[name]) for name in self.questions}
        model = app.client.models.get("choose")
        floors, targets = self.floors_for(getattr(model, "name", model))
        failed = [name for name, floor in floors.items() if scores[name] < floor]
        repairable = (*self.repairable, "grounded") if self.repair_grounded else self.repairable
        near = bool(failed) and any(name in repairable for name in failed) and all(
            name in repairable or (name == "useful" and scores[name] >= floors[name] - self.repair_margin)
            for name in failed
        )
        short = [name for name, target in targets.items() if floors[name] <= scores[name] < target]
        return EvalResult(passed=not failed, scores=scores, failed=failed, short=[] if failed else short,
                          near_miss=near)

    def __repr__(self) -> str:
        parts = [f"{k}={v}" for k, v in self.floors.items() if DEFAULT_FLOORS.get(k) != v]
        parts += [] if self.repair_grounded else ["repair_grounded=False"]
        parts += [f"target {k}={v}" for k, v in self.targets.items() if DEFAULT_TARGETS.get(k) != v]
        for name, question in self._changed.items():
            parts.append(f"{name}: dropped" if question is None else
                         f"{name}: {json.dumps(question.wire(), sort_keys=True)}")
        return f"{type(self).name}({', '.join(parts)})" if parts else type(self).name
