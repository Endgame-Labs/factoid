from __future__ import annotations

from datetime import UTC, datetime

import pytest

from factoid import Choice, Noul, ProseDocument, Skip, judge
from factoid.dates import DateError, format_datetime, parse_datetime
from factoid.judge import questions_of
from factoid.steps import SKIPPED, describe_steps, run_step


def test_dates_accept_documented_inputs() -> None:
    expected = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    assert parse_datetime("2026-11-15T12:00:00Z") == expected
    assert parse_datetime("2026-11-15T07:00:00-05:00") == expected
    seconds = int(expected.timestamp())
    assert parse_datetime(seconds) == expected
    assert parse_datetime(seconds * 1000) == expected
    assert parse_datetime(seconds * 1_000_000) == expected
    assert parse_datetime(expected) == expected
    assert format_datetime(expected) == "2026-11-15T12:00:00.000000Z"


def test_dates_reject_naive() -> None:
    with pytest.raises(DateError):
        parse_datetime("2026-11-15T12:00:00")
    with pytest.raises(DateError):
        parse_datetime(datetime(2026, 1, 1))


def test_judge_collects_questions() -> None:
    class Contract(ProseDocument):
        """A contract."""

        @classmethod
        @judge(is_contract=Noul("Is this a contract?"), status=Choice("State?", ["signed", "draft"]))
        def classify(cls, raw, judgments):
            return judgments.is_contract > 0.9

    asked = questions_of(Contract.classify)
    assert set(asked) == {"is_contract", "status"}
    assert Noul("Is this a contract?").key() == asked["is_contract"].key()


def test_steps_run_hooks_and_skip() -> None:
    calls = []

    class Thing:
        STEPS = ("work",)

        def before_work(self, x):
            calls.append(("before", x))
            if x < 0:
                raise Skip

        def work(self, x):
            return x * 2

        def after_work(self, x, result):
            calls.append(("after", result))
            return result + 1 if x == 5 else None

    assert run_step(Thing(), "work", 2) == 4
    assert run_step(Thing(), "work", 5) == 11
    assert run_step(Thing(), "work", -1) is SKIPPED
    assert calls[0] == ("before", 2)
    rows = describe_steps(Thing)
    assert rows[0]["step"] == "work" and len(rows[0]["hooks"]) == 2


def test_chunking_keeps_passages_whole() -> None:
    class Memo(ProseDocument):
        """A memo."""

        chunk_size = 120
        chunk_overlap = "20%"

    text = "\n\n".join(f"Paragraph {i} says something about Orion and Vega." for i in range(8))
    doc = Memo(text)
    passages = doc.segment()
    assert len(passages) == 8
    chunks = doc.chunk(passages)
    owned = [p.n for c in chunks for p in c.passages]
    assert owned == list(range(1, 9))
    assert all(len(c.text) <= 120 for c in chunks)
    assert chunks[1].context_passages and chunks[1].context_passages[-1].n == chunks[0].passages[-1].n


def test_chunk_overlap_rejects_floats() -> None:
    with pytest.raises(TypeError):
        class Bad(ProseDocument):
            """Bad."""

            chunk_overlap = 0.2  # type: ignore[assignment]
