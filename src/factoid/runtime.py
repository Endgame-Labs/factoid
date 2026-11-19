"""The active Factoid app, class registries, and the model-call helpers every class has.

Subclassing a base class is the declaration: `__init_subclass__` records each subclass in its base's registry.
Classes defined inside the `factoid` package itself (such as `ProseDocument`) are bases, not candidates.
"""

from __future__ import annotations

import contextvars
import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from .judge import Choice, Judgments, Noul, Question, Score

if TYPE_CHECKING:
    from .app import Factoid

__all__ = ["ModelCalls", "NoApp", "Registered", "active", "current", "use"]

_current: contextvars.ContextVar[Factoid | None] = contextvars.ContextVar("factoid_app", default=None)
_global: list[Factoid] = []


class NoApp(RuntimeError):
    """A read or a model call needs an active Factoid app."""


def current() -> Factoid:
    app = _current.get() or (_global[-1] if _global else None)
    if app is None:
        raise NoApp("no active Factoid app: create one with Factoid(...) or run inside a project")
    return app


def use(app: Factoid) -> None:
    """Make `app` the active app here, and the fallback for threads that have none (the last one created wins)."""
    _global.append(app)
    _current.set(app)


@contextmanager
def active(app: Factoid) -> Iterator[Factoid]:
    """Make `app` the active app inside the block, in this thread only."""
    token = _current.set(app)
    try:
        yield app
    finally:
        _current.reset(token)


def activates(method: Callable[..., Any]) -> Callable[..., Any]:
    """Run an app method with its app active, so classes it calls read the right store and models."""
    @functools.wraps(method)
    def wrapper(self: Factoid, *args: Any, **kwargs: Any) -> Any:
        if _current.get() is self:
            return method(self, *args, **kwargs)
        with active(self):
            return method(self, *args, **kwargs)
    return wrapper


class Registered:
    """Keeps a registry of subclasses defined outside the factoid package."""

    _registry: dict[str, type]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "_registry" in cls.__dict__:  # a new base starts its own registry
            return
        if cls.__module__.split(".")[0] == "factoid":
            return
        cls._registry[cls.__qualname__] = cls

    @classmethod
    def registered(cls) -> list[type]:
        return [klass for klass in cls._registry.values() if issubclass(klass, cls)]

    @classmethod
    def description(cls) -> str:
        return " ".join((cls.__doc__ or cls.__name__).split())


class ModelCalls:
    """Model calls a step can make through `self` or `cls`. Factoid logs, prices, budgets, and replays them."""

    def state(self) -> Any:
        """What the decision model sees about this item. Override to change the view."""
        return {"text": str(self)}

    def generate(self, prompt: Any, *, json_mode: bool = False, step: str | None = None, **context: Any) -> str:
        """Generate text. `step` picks that step's model (such as "situate"), falling back to `generate`."""
        from .templates import Template, render

        text = render(prompt, **context) if (context or isinstance(prompt, Template)) else str(prompt)
        return current().client.generate(text, json_mode=json_mode, step=step)

    def ask(self, **questions: Question) -> Judgments:
        return current().client.ask(self.state(), questions)

    def decide(self, prompt: str) -> float:
        """The probability that the answer is yes."""
        return self.ask(q=Noul(prompt)).q

    def choose(self, prompt: str, options: dict[str, str] | list[str]) -> dict[str, float]:
        """A probability for each option."""
        return self.ask(q=Choice(prompt, options)).q

    def score(self, prompt: str, rubric: list[str]) -> Any:
        """A rubric level, as a `ScoreAnswer` that compares like a float."""
        return self.ask(q=Score(prompt, rubric)).q
