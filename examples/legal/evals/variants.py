"""Variants for `factoid eval --vary`. `--vary models=@evals.variants:RUNE` runs the suites with Rune for `choose`."""

from app.settings import Project

from factoid import DecisionFloors, Model, Nli

RUNE = {**Project.models, "choose": Model("fireworks/rune")}

# Resolve wordings tried on Rune (SPEC decision 94). Rune read "replaces a value the stored fact gave" as true of any
# stored fact that mentions what changed, such as an appointment "within the Territory" when the Territory changed.
from factoid.fact import RESOLVE_ANSWERS  # noqa: E402

STATES_VALUE = {
    **RESOLVE_ANSWERS,
    "supersedes": "The stored fact itself states a value (a term, amount, date, party, place, or rule), and the new "
                  "fact gives a different value for that same thing, which replaces it from then on.",
    "unrelated": "The facts are about different things, or both can be true at once: a rule and an exception to it, "
                 "terms that apply in different cases, or a stored fact that only refers to or depends on something "
                 "the new fact changes without stating its value.",
}


# Decision 87's experiment (issue #6): a fact that fails "grounded" is trimmed to what its passages say, not dropped.
GROUNDED_REPAIR = [Nli(), DecisionFloors(repair_grounded=True)]


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


# Issue #25: resolve compares what reports say, not whether both were said. Run with
# --vary resolve_answers=@evals.variants:RESOLVE_DEFAULT,@evals.variants:RESOLVE_SAID.
from factoid.fact import RESOLVE_ANSWERS as _RESOLVE  # noqa: E402

RESOLVE_DEFAULT = dict(_RESOLVE)
RESOLVE_SAID = {**_RESOLVE, "unrelated": _RESOLVE["unrelated"] + (
    " When the facts report what someone said, compare what was said, not whether it was said: a later statement "
    "that changes an earlier one is not unrelated because both statements were made.")}


# Issue #26: redaction markers shown as "[redacted]" in resolve. Run with
# --vary redaction_markers=@evals.variants:NO_MARKERS,@evals.variants:MARKERS.
NO_MARKERS: list[str] = []
MARKERS = ["[*]", "[***]"]
