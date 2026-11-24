"""Traits: project-defined tags on facts.

A trait is a `FactTrait` subclass. The docstring is the definition the decision model reads. With no `decide`, the
trait is one yes-or-no question built from the docstring, compared with `threshold`. A `decide` method gets that
answer as `judgments.<trait name>` plus any factor questions it declares with `@judge`.

    class LiabilityCap(FactTrait):
        \"\"\"A limit on how much a party can owe.\"\"\"
        threshold = 0.8
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

from .judge import Judgments, Noul, Question, questions_of
from .runtime import Registered

if TYPE_CHECKING:
    from .fact import Fact

__all__ = ["MODEL_TRAIT", "FactTrait", "snake"]


#: The trait bar for decision models whose probabilities sit closer to 1 than Jev's. Rune answers yes at 0.85 or more
#: for many facts without the trait; at 0.85 it keeps Jev's recall on CUAD with better precision (SPEC decision 143).
MODEL_TRAIT: dict[str, float] = {"fireworks/rune": 0.85}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class FactTrait(Registered):
    """Base class for traits. Subclass it and write a docstring."""

    _registry: ClassVar[list[type]] = []

    #: The probability the yes-or-no answer must reach. None takes the decision model's value from `MODEL_TRAIT`, else
    #: 0.5. A `decide` that reads `cls.threshold` should set it, or call `cls.bar()`.
    threshold: ClassVar[float | None] = None
    #: Example fact sentences that have the trait. They are shown to the model with the definition.
    examples: ClassVar[list[str]] = []
    #: Sentences that look close but do not have the trait.
    counterexamples: ClassVar[list[str]] = []
    #: Replaces the default question wording, when set.
    question: ClassVar[str | None] = None

    @classmethod
    def key(cls) -> str:
        """The trait's name in judgments and storage, such as `liability_cap`."""
        return snake(cls.__name__)

    @classmethod
    def base_question(cls) -> Noul:
        if cls.question:
            return Noul(cls.question)
        lines = [f"Does this fact have the trait \"{cls.__name__}\"? Definition: {cls.description()}"]
        if cls.examples:
            lines.append("Examples that have it: " + " | ".join(cls.examples))
        if cls.counterexamples:
            lines.append("Examples that do not: " + " | ".join(cls.counterexamples))
        return Noul("\n".join(lines), true="The fact has this trait.", false="The fact does not have this trait.")

    @classmethod
    def questions(cls) -> dict[str, Question]:
        """Every question this trait needs: its own yes-or-no question and any `@judge` factor questions."""
        asked: dict[str, Question] = {cls.key(): cls.base_question()}
        asked.update(questions_of(cls.decide))
        return asked

    @classmethod
    def bar(cls) -> float:
        """`threshold` for the decision model: the class's own value, else the model's, else 0.5."""
        if cls.threshold is not None:
            return cls.threshold
        from .runtime import current

        model = current().client.models.get("choose")
        return MODEL_TRAIT.get(getattr(model, "name", model) or "", 0.5)

    @classmethod
    def decide(cls, fact: Fact, judgments: Judgments) -> bool | float:
        """True when the fact has the trait. Override to add factor questions and logic."""
        return judgments[cls.key()] >= cls.bar()

    @classmethod
    def call_hook(cls, name: str, fact: Fact, *args: Any) -> None:
        hook = getattr(cls, name, None)
        if hook is not None:
            hook(fact, *args)
