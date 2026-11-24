"""Variants for `factoid eval --vary`."""


# Issue #24: a rule that keeps a reference the text leaves open, in the repair prompt's references block. Run with
# --vary repair_prompt=@evals.variants:DEFAULT_REPAIR,@evals.variants:KEEP_OPEN to score both on the same code.
DEFAULT_REPAIR = '{% extends "factoid/repair.md.j2" %}'
KEEP_OPEN = (
    '{% extends "factoid/repair.md.j2" %}{% block references %}{{ super() }}Keep a reference the text leaves open as '
    'worded, such as "its" when the text does not say which thing it means. Never guess what it refers to.\n'
    '{% endblock %}'
)


# Decision models side by side (decision 135's follow-up): Jev 1.13 (the default), Jev 1.14, and Rune, which makes the
# project Fireworks only. Run with --vary models=@evals.variants:JEV_113,@evals.variants:JEV_114,@evals.variants:RUNE.
from app.settings import Project as _Project  # noqa: E402

from factoid import Model as _Model  # noqa: E402

JEV_113 = {**_Project.models, "choose": _Model("typesafe/jev-1.13.0")}
JEV_114 = {**_Project.models, "choose": _Model("typesafe/jev-1.14.0")}
RUNE = {**_Project.models, "choose": _Model("fireworks/rune")}


# Issue #25: resolve compares what reports say, not whether both were said, by default since 0.1.27.
# Run with --vary resolve_answers=@evals.variants:RESOLVE_DEFAULT,@evals.variants:RESOLVE_SAID.
from factoid.fact import RESOLVE_ANSWERS as _RESOLVE  # noqa: E402

RESOLVE_SAID = dict(_RESOLVE)  # the default since 0.1.27
RESOLVE_DEFAULT = {**_RESOLVE, "unrelated": _RESOLVE["unrelated"].split(" When the facts report")[0]}  # before 0.1.27
