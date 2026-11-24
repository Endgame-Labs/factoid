"""Variants for `factoid eval --vary`."""


# Issue #25: resolve compares what reports say, not whether both were said. Run with
# --vary resolve_answers=@evals.variants:RESOLVE_DEFAULT,@evals.variants:RESOLVE_SAID.
from factoid.fact import RESOLVE_ANSWERS as _RESOLVE

RESOLVE_DEFAULT = dict(_RESOLVE)
RESOLVE_SAID = {**_RESOLVE, "unrelated": _RESOLVE["unrelated"] + (
    " When the facts report what someone said, compare what was said, not whether it was said: a later statement "
    "that changes an earlier one is not unrelated because both statements were made.")}
