"""Test doubles: a scripted decision model, generator, and embedder, so tests make no network calls."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from factoid import Factoid, Settings
from factoid.judge import Choice, Judgments, Noul, Question, Score, ScoreAnswer
from factoid.models import Meter


class FakeClient:
    """Answers Nouls with `noul(question, state)`, Choices with `choice(question, state)`, and returns canned text."""

    def __init__(self) -> None:
        self.models: dict[str, Any] = {"choose": "fake", "generate": "fake", "embed": "fake"}
        self.meter = Meter()
        self.asked: list[tuple[Any, dict[str, Question]]] = []
        self.prompts: list[str] = []
        self.noul: Callable[[Noul, Any], float] = (
            lambda q, s: 0.1 if "specific named thing" in q.instructions and str(s.get("mention", "")).lower()
            in ("agreement", "the agreement", "amendment") else 0.9)
        self.choice: Callable[[Choice, Any, str], dict[str, float]] = self._default_choice
        self.generator: Callable[[str], str] = lambda prompt: json.dumps({"facts": []})

    @staticmethod
    def _default_choice(q: Choice, state: Any, name: str) -> dict[str, float]:
        options = [k for k, _ in q.options]
        if name == "expires":
            return {k: (0.9 if k == "estimated" else 0.05) for k in options}
        if name == "lifetime":
            return {k: (0.8 if k == "a few years" else 0.2 / (len(options) - 1)) for k in options}
        if re.fullmatch(r"F\d+", name):
            return {k: (0.9 if k == "unrelated" else 0.02) for k in options}
        return {k: 1.0 / len(options) for k in options}

    def ask(self, state: Any, questions: dict[str, Question]) -> Judgments:
        self.asked.append((state, questions))
        out: dict[str, Any] = {}
        for name, q in questions.items():
            if isinstance(q, Noul):
                out[name] = self.noul(q, state)
            elif isinstance(q, Choice):
                out[name] = self.choice(q, state, name)
            elif isinstance(q, Score):
                out[name] = ScoreAnswer(1.0, {0: 0.0, 1: 1.0})
        return Judgments(out)

    def generate(self, prompt: str, *, json_mode: bool = False, **_: Any) -> str:
        self.prompts.append(prompt)
        return self.generator(prompt)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vector = [0.0] * 64
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
            out.append(vector)
        return out

    def rerank(self, query: str, documents: list[str]) -> None:
        return None


@pytest.fixture
def fake() -> FakeClient:
    return FakeClient()


@pytest.fixture
def make_app(fake: FakeClient) -> Iterator[Callable[..., Factoid]]:
    """Apps in memory. With `FACTOID_TEST_STORE=postgres` (and `FACTOID_TEST_POSTGRES_URL`), each app's store is a
    fresh Postgres schema instead, so the whole suite can run against the Postgres store."""
    schemas: list[tuple[Any, str]] = []

    def build(**kwargs: Any) -> Factoid:
        app = Factoid(Settings, in_memory=True, **kwargs)
        app.client = fake  # type: ignore[assignment]
        if os.environ.get("FACTOID_TEST_STORE") == "postgres":
            from factoid.postgres import PostgresStore

            schema = f"factoid_test_{uuid.uuid4().hex[:12]}"
            app.store = PostgresStore(os.environ["FACTOID_TEST_POSTGRES_URL"], schema=schema)
            schemas.append((app.store, schema))
        return app

    yield build
    for store, schema in schemas:
        store.close()
        import psycopg

        with psycopg.connect(os.environ["FACTOID_TEST_POSTGRES_URL"], autocommit=True) as conn:
            conn.execute(f'drop schema if exists "{schema}" cascade')
