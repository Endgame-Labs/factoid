"""Variants for `factoid eval --vary`."""


# Issue #25: resolve compares what reports say, not whether both were said, by default since 0.1.27.
# Run with --vary resolve_answers=@evals.variants:RESOLVE_DEFAULT,@evals.variants:RESOLVE_SAID.
from factoid.fact import RESOLVE_ANSWERS as _RESOLVE

RESOLVE_SAID = dict(_RESOLVE)  # the default since 0.1.27
RESOLVE_DEFAULT = {**_RESOLVE, "unrelated": _RESOLVE["unrelated"].split(" When the facts report")[0]}  # before 0.1.27
