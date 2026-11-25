"""The search index contract: what every `Index` does, run against LocalIndex and, when `FACTOID_TEST_POSTGRES_URL` is
set, PostgresIndex (with pgvector)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from factoid.search import LocalIndex

PG_URL = os.environ.get("FACTOID_TEST_POSTGRES_URL", "")
BACKENDS = ["local", pytest.param("postgres", marks=pytest.mark.skipif(
    not PG_URL, reason="set FACTOID_TEST_POSTGRES_URL to run the index contract against Postgres"))]


@pytest.fixture(params=BACKENDS)
def index(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    if request.param == "local":
        yield LocalIndex(tmp_path / "index.db")
        return
    import psycopg

    from factoid.postgres import PostgresIndex

    schema = f"factoid_test_{uuid.uuid4().hex[:12]}"
    index = PostgresIndex(PG_URL, schema=schema)
    try:
        yield index
    finally:
        index.close()
        with psycopg.connect(PG_URL, autocommit=True) as conn:
            conn.execute(f'drop schema if exists "{schema}" cascade')


def _unit(*xs: float) -> list[float]:
    v = np.asarray(xs, dtype=np.float64)
    return (v / np.linalg.norm(v)).tolist()


def test_upsert_delete_and_vectors(index):
    index.upsert("facts", [{"id": "a", "text": "Vega pays Orion", "vector": [1.0, 0.0, 0.0]},
                           {"id": "b", "text": "Orion ships", "vector": [0.0, 1.0, 0.0]},
                           {"id": "c", "text": "no vector"}])
    index.upsert("other", [{"id": "a", "text": "elsewhere", "vector": [0.0, 0.0, 1.0]}])
    assert index.vectors("facts", ["a", "c", "zz"]) == {"a": [1.0, 0.0, 0.0]}
    index.upsert("facts", [{"id": "a", "text": "Vega pays Orion", "vector": [0.5, 0.5, 0.0]},
                           {"id": "a", "text": "Vega pays Orion twice", "vector": [0.0, 0.0, 2.0]}])
    assert index.vectors("facts", ["a"]) == {"a": [0.0, 0.0, 2.0]}  # the last one named holds
    index.delete("facts", ["a", "missing"])
    index.delete("facts", [])
    assert index.vectors("facts", ["a", "b"]) == {"b": [0.0, 1.0, 0.0]}
    assert index.vectors("other", ["a"]) == {"a": [0.0, 0.0, 1.0]}  # namespaces are apart
    assert index.bm25("facts", "Vega", 5) == []
    assert index.nearest("empty", [1.0, 0.0, 0.0], 3) == []


def test_bm25_finds_words_and_ranks_the_closer_text_first(index):
    index.upsert("facts", [
        {"id": "a", "text": "Vega pays Orion monthly"},
        {"id": "b", "text": "Orion ships the parts to Vega and Vega pays for shipping"},
        {"id": "c", "text": "Nothing about them"},
        {"id": "d", "text": "The lease ends in March"},
    ])
    found = index.bm25("facts", "Vega pays", 10)
    assert set(found) == {"a", "b"}
    assert index.bm25("facts", "lease, March!", 10) == ["d"]
    assert index.bm25("facts", "LEASE", 10) == ["d"]  # case does not matter
    assert index.bm25("facts", "?!", 10) == []
    assert len(index.bm25("facts", "Vega Orion lease", 1)) == 1


def test_filters_match_any_value(index):
    index.upsert("facts", [
        {"id": "a", "text": "Vega pays", "vector": [1.0, 0.0], "entity_ids": ["e1", "e2"], "class": "Term",
         "document_id": "d1"},
        {"id": "b", "text": "Vega ships", "vector": [0.9, 0.1], "entity_ids": ["e2"], "class": "Fact",
         "document_id": "d2"},
        {"id": "c", "text": "Vega leases", "vector": [0.8, 0.2], "entity_ids": [], "class": "Fact",
         "document_id": "d1"},
    ])
    for search in (lambda f: index.bm25("facts", "Vega", 10, f), lambda f: index.nearest("facts", [1.0, 0.0], 10, f)):
        assert set(search({"entity_ids": ["e1"]})) == {"a"}
        assert set(search({"entity_ids": ["e2", "e9"]})) == {"a", "b"}
        assert set(search({"entity_ids": "e2"})) == {"a", "b"}  # one wanted value, a list held
        assert set(search({"class": ["Fact"]})) == {"b", "c"}
        assert set(search({"class": "Term"})) == {"a"}
        assert set(search({"document_id": ["d1"], "class": ["Fact"]})) == {"c"}
        assert search({"traits": ["x"]}) == []  # a row without the attribute does not pass


def test_nearest_ranks_by_cosine_then_id(index):
    index.upsert("v", [{"id": "far", "text": "t", "vector": _unit(0, 1, 0)},
                       {"id": "near", "text": "t", "vector": _unit(1, 0.1, 0)},
                       {"id": "t2", "text": "t", "vector": [2.0, 1.0, 0.0]},
                       {"id": "t1", "text": "t", "vector": [2.0, 1.0, 0.0]}])  # a tie, so by id
    assert index.nearest("v", [1.0, 0.0, 0.0], 4) == ["near", "t1", "t2", "far"]
    assert index.nearest("v", [1.0, 0.0, 0.0], 0) == ["near"]  # at least one row
    with pytest.raises(ValueError):
        index.upsert("v", [{"id": "short", "text": "t", "vector": [1.0, 0.0]}])
        index.nearest("v", [1.0, 0.0, 0.0], 3)


def test_hybrid_fuses_both_rankings(index):
    words = "the cutover date for the rollout is set for some day in January"
    index.upsert("h", [{"id": "words", "text": words, "vector": [0.0, 1.0]},
                       {"id": "meaning", "text": "the switch moves to next year", "vector": [1.0, 0.0]},
                       {"id": "both", "text": "cutover moves to January", "vector": [0.9, 0.1]}])
    hits = index.hybrid("h", "cutover January", [1.0, 0.0], 3)
    assert hits[0][0] == "both" and {h[0] for h in hits} == {"words", "meaning", "both"}
    assert {h[0] for h in index.hybrid("h", "cutover January", None, 3)} == {"words", "both"}  # words only
