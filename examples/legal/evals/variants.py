"""Variants for `factoid eval --vary`. `--vary models=@evals.variants:RUNE` runs the suites with Rune for `choose`."""

from legal.settings import Project

from factoid import Model

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
