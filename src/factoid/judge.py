"""The decision model judges, code decides.

A step declares atomic questions with `@judge(...)`. Factoid asks every question for one item in one request to the
decision model, and passes the answers to the step as `judgments`. Code then decides with thresholds it controls.

    @classmethod
    @judge(is_contract=Noul("Is this a contract?"))
    def classify(cls, raw, judgments):
        return judgments.is_contract > 0.9
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Question", "Noul", "Choice", "Score", "ScoreAnswer", "Judgments", "judge", "questions_of"]


@dataclass(frozen=True)
class Question:
    """One typed question for the decision model."""

    instructions: str

    type: str = field(default="", init=False)

    def wire(self) -> dict[str, Any]:
        raise NotImplementedError

    def key(self) -> str:
        """Identical questions share a key, so they are asked once."""
        blob = json.dumps(self.wire(), sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Noul(Question):
    """A yes-or-no question answered with the probability of yes."""

    true: str = "Yes."
    false: str = "No."
    type: str = field(default="noul", init=False)

    def wire(self) -> dict[str, Any]:
        return {"type": "noul", "instructions": self.instructions, "criteria": {"true": self.true, "false": self.false}}


@dataclass(frozen=True, init=False)
class Choice(Question):
    """One of several options, answered with a probability per option."""

    options: tuple[tuple[str, str], ...] = ()
    type: str = field(default="choice", init=False)

    def __init__(self, instructions: str, options: Mapping[str, str] | list[str] | tuple[str, ...]):
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(self, "type", "choice")
        if isinstance(options, Mapping):
            pairs = tuple((str(k), str(v)) for k, v in options.items())
        else:
            pairs = tuple((str(o), str(o)) for o in options)
        if len(pairs) < 2:
            raise ValueError("a Choice needs at least two options")
        object.__setattr__(self, "options", pairs)

    def wire(self) -> dict[str, Any]:
        return {"type": "choice", "instructions": self.instructions, "criteria": dict(self.options)}


@dataclass(frozen=True, init=False)
class Score(Question):
    """A rubric level, answered with a probability per level and an expected score."""

    levels: tuple[str, ...] = ()
    type: str = field(default="score", init=False)

    def __init__(self, instructions: str, levels: list[str] | tuple[str, ...]):
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(self, "type", "score")
        if len(levels) < 2:
            raise ValueError("a Score needs at least two levels")
        object.__setattr__(self, "levels", tuple(levels))

    def wire(self) -> dict[str, Any]:
        return {"type": "score", "instructions": self.instructions, "criteria": list(self.levels)}


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    probabilities: dict[int, float]

    def __float__(self) -> float:
        return self.score

    def __gt__(self, other: float) -> bool:
        return self.score > other

    def __lt__(self, other: float) -> bool:
        return self.score < other

    def __ge__(self, other: float) -> bool:
        return self.score >= other

    def __le__(self, other: float) -> bool:
        return self.score <= other


class Judgments:
    """The answers to one item's questions, by name.

    A Noul answer is a float (the probability of yes). A Choice answer is a dict of option to probability. A Score
    answer is a `ScoreAnswer`, which compares like a float.
    """

    def __init__(self, answers: Mapping[str, Any]):
        self._answers = dict(answers)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._answers[name]
        except KeyError:
            raise AttributeError(f"no judgment named {name!r}; asked: {sorted(self._answers)}") from None

    def __getitem__(self, name: str) -> Any:
        return self._answers[name]

    def __contains__(self, name: str) -> bool:
        return name in self._answers

    def get(self, name: str, default: Any = None) -> Any:
        return self._answers.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._answers)

    def __repr__(self) -> str:
        return f"Judgments({self._answers!r})"


def judge(**questions: Question) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare the questions a step asks. Stacked decorators add to the set."""
    for name, question in questions.items():
        if not isinstance(question, Question):
            raise TypeError(f"@judge({name}=...) must be a Noul, Choice, or Score")

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        target = func.__func__ if isinstance(func, (classmethod, staticmethod)) else func
        existing = dict(getattr(target, "__judge__", {}))
        existing.update(questions)
        target.__judge__ = existing  # type: ignore[attr-defined]
        return func

    return decorate


def questions_of(method: Any) -> dict[str, Question]:
    """The questions a step method declared with `@judge`, or an empty dict."""
    target = getattr(method, "__func__", method)
    return dict(getattr(target, "__judge__", {}))
