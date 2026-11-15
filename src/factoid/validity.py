"""Time on a fact: `valid_from`, `expires`, `valid_until`, and `lifetime`.

- `expires = "never"`: true for good, as history or as an invariant.
- `expires = "estimated"`: true until something changes it. `lifetime` is a distribution over ranges, and Factoid
  computes the chance the fact is still true at a given time.
- `expires = "at_deadline"`: settled by `valid_until`. What a passed deadline means is not settled (SPEC, Open), so
  validity after the deadline is reported as one half.

The clock for an estimated lifetime starts at the most recent time the fact was seen to be true.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

__all__ = ["EXPIRES", "LIFETIME_RANGES", "validity"]

EXPIRES: dict[str, str] = {
    "never": "True for good: something that happened, a choice that was made, or something that can never change, "
             "such as a signing, a past payment, or a founding date.",
    "estimated": "True until something changes it, at a time nobody can name now, such as a status, a role, a price, "
                 "a contract term, an obligation, or a policy.",
    "at_deadline": "Settled by a stated date, such as a plan, a promise with a due date, or an expected outcome "
                   "with a date.",
}

LIFETIME_RANGES: dict[str, timedelta] = {
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
    "quarter": timedelta(days=91),
    "year": timedelta(days=365),
    "a few years": timedelta(days=3 * 365),
    "longer": timedelta(days=25 * 365),
}


def validity(
    at: datetime,
    *,
    valid_from: datetime | None,
    expires: str | None,
    valid_until: datetime | None,
    lifetime: dict[str, float] | None,
    seen_at: datetime | None,
    ranges: dict[str, timedelta] = LIFETIME_RANGES,
) -> float:
    """The probability a fact is still true at `at`."""
    if valid_from is not None and at < valid_from:
        return 0.0
    if valid_until is not None and at >= valid_until:
        return 0.5 if expires == "at_deadline" else 0.0
    if expires in (None, "never", "at_deadline"):
        return 1.0
    start = max(t for t in (seen_at, valid_from) if t is not None) if (seen_at or valid_from) else None
    if start is None or not lifetime:
        return 1.0
    elapsed = max(0.0, (at - start).total_seconds())
    total = sum(lifetime.values()) or 1.0
    p = 0.0
    for name, weight in lifetime.items():
        span = ranges.get(name)
        if span is None:
            continue
        p += (weight / total) * math.exp(-elapsed / span.total_seconds())
    return p
