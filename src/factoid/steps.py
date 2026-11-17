"""Steps are methods, with `before_` and `after_` hooks.

Every pipeline step is a classmethod or an instance method. Factoid runs a step through `run_step`, which always
calls `before_<step>` and `after_<step>`. They do nothing unless a class defines them.

- `before_<step>(*args)` can raise `Skip` to skip the step for this item.
- `after_<step>(*args, result=...)` can return a replacement, or `None` to keep the result.
"""

from __future__ import annotations

import inspect
from typing import Any

__all__ = ["SKIPPED", "Skip", "describe_steps", "run_step"]


class Skip(Exception):
    """Raised by a `before_` hook to skip a step for one item."""


class _Skipped:
    def __repr__(self) -> str:
        return "SKIPPED"

    def __bool__(self) -> bool:
        return False


SKIPPED = _Skipped()


def run_step(target: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    """Run `target.<name>(*args, **kwargs)` between its `before_` and `after_` hooks."""
    before = getattr(target, f"before_{name}", None)
    if before is not None:
        try:
            before(*args, **kwargs)
        except Skip:
            return SKIPPED
    result = getattr(target, name)(*args, **kwargs)
    after = getattr(target, f"after_{name}", None)
    if after is not None:
        replaced = after(*args, result=result, **kwargs)
        if replaced is not None:
            return replaced
    return result


def describe_steps(cls: type) -> list[dict[str, Any]]:
    """Each step on a class: its name, kind, the class that defines it, and the hooks defined for it."""
    rows = []
    for name in getattr(cls, "STEPS", ()):
        owner = next((klass for klass in cls.__mro__ if name in vars(klass)), None)
        raw = inspect.getattr_static(cls, name, None)
        if isinstance(raw, classmethod):
            kind = "classmethod"
        elif isinstance(raw, property):
            kind = "property"
        elif callable(raw):
            kind = "method"
        else:
            kind = f"setting={raw!r}"
        hooks = []
        for prefix in ("before_", "after_"):
            hook_owner = next((k for k in cls.__mro__ if f"{prefix}{name}" in vars(k)), None)
            if hook_owner is not None:
                hooks.append(f"{prefix}{name} ({hook_owner.__name__})")
        rows.append({
            "step": name,
            "kind": kind,
            "defined_in": owner.__name__ if owner else "?",
            "hooks": hooks,
        })
    return rows
