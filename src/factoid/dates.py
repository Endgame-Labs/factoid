"""Document dates: one accepted set of inputs, one stored form.

`source_datetime` accepts ISO-8601 strings with a timezone offset or `Z`, epoch seconds, milliseconds, or
microseconds (the unit is inferred from the size of the number), and timezone-aware `datetime` values. It is stored
as an ISO-8601 UTC string with microseconds.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["DateError", "parse_datetime", "format_datetime", "now"]


class DateError(ValueError):
    """A date that Factoid does not accept."""


def parse_datetime(value: object) -> datetime:
    """Return a UTC `datetime` for an accepted input, or raise `DateError`."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise DateError(f"datetime {value!r} has no timezone")
        return value.astimezone(UTC)
    if isinstance(value, bool):
        raise DateError(f"{value!r} is not a date")
    if isinstance(value, (int, float)):
        seconds = float(value)
        magnitude = abs(seconds)
        if magnitude >= 1e14:
            seconds /= 1e6  # microseconds
        elif magnitude >= 1e11:
            seconds /= 1e3  # milliseconds
        return datetime.fromtimestamp(seconds, UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as err:
            raise DateError(f"{value!r} is not an ISO-8601 date") from err
        if parsed.tzinfo is None:
            raise DateError(f"{value!r} has no timezone offset or Z")
        return parsed.astimezone(UTC)
    raise DateError(f"{value!r} is not a date")


def format_datetime(value: datetime) -> str:
    """ISO-8601 in UTC with microseconds and a `Z` suffix."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def now() -> datetime:
    return datetime.now(UTC)
