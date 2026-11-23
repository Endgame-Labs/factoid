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
