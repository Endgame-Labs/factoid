"""The store contract: every `Store` behavior, run against each backend.

SQLite always runs. Postgres runs when `FACTOID_TEST_POSTGRES_URL` names a database to test against; each test gets a
schema of its own and drops it after. For example:

    docker run -d --name factoid-pg-test -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 postgres:17
    FACTOID_TEST_POSTGRES_URL=postgresql://postgres:test@127.0.0.1:55432/postgres uv run pytest
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from factoid.store import Store

PG_URL = os.environ.get("FACTOID_TEST_POSTGRES_URL", "")
BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(
    not PG_URL, reason="set FACTOID_TEST_POSTGRES_URL to run the store contract against Postgres"))]


def _drop(schema: str) -> None:
    import psycopg

    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f'drop schema if exists "{schema}" cascade')


@pytest.fixture(params=BACKENDS)
def opener(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Callable[[], Any]]:
    """Opens a store on one backend; each call is a new connection to the same data, as another process would be."""
    opened: list[Any] = []
    if request.param == "sqlite":
        def open_store() -> Any:
            opened.append(Store(tmp_path / "store.db"))
            return opened[-1]
        yield open_store
    else:
        from factoid.postgres import PostgresStore

        schema = f"factoid_test_{uuid.uuid4().hex[:12]}"

        def open_store() -> Any:
            opened.append(PostgresStore(PG_URL, schema=schema))
            return opened[-1]
        try:
            yield open_store
        finally:
            for store in opened:
                store.close()
            _drop(schema)
        return
    for store in opened:
        store.close()


@pytest.fixture
def store(opener: Callable[[], Any]) -> Any:
    return opener()


def _doc(store: Any, id_: str = "doc_1", text: str = "Vega pays Orion. Orion ships.", **extra: Any) -> None:
    store.save_document(
        {"id": id_, "class": "Contract", "uri": f"files/{id_}.txt", "title": extra.get("title", id_.upper()),
         "source_datetime": "2025-01-01T00:00:00.000000Z", "metadata": {"k": 1}, "text": text,
         "content_hash": None},
        [{"n": 0, "start": 0, "end": 16, "speaker": None, "said_at": None},
         {"n": 1, "start": 17, "end": len(text), "speaker": "A", "said_at": None}],
        [{"id": f"{id_}_c0", "n": 0, "first_passage": 0, "last_passage": 1, "text": text, "situation": "s"}],
    )


def _fact(store: Any, id_: str, text: str, *, document_id: str = "doc_1", status: str = "current",
          traits: list[str] | None = None, entities: list[str | None] | None = None, **row: Any) -> None:
    store.save_fact(
        {"id": id_, "class": row.pop("cls", "Fact"), "text": text, "document_id": document_id,
         "chunk_id": f"{document_id}_c0", "status": status, "traits": traits or [], "trait_scores": {},
         "extracted_at": row.pop("extracted_at", "2025-02-01T00:00:00.000000Z"), "scores": {"x": 1}, **row},
        [{"document_id": document_id, "passage_n": 1, "start": 17, "end": 29, "text": "Orion ships.",
          "speaker": "A", "section": "1.2", "attrs": {"page": 2}},
         {"document_id": document_id, "passage_n": 0, "start": 0, "end": 16, "text": "Vega pays Orion."}],
        [{"text": f"name {e}", "kind": "org", "role": "about", "entity_id": e, "method": "key", "confidence": 0.5}
         for e in (entities or [])],
    )


def _entity(store: Any, id_: str, name: str, *, cls: str = "Company", kind: str | None = None,
            aliases: list[str] | None = None, keys: dict[str, str] | None = None) -> None:
    store.save_entity({"id": id_, "class": cls, "kind": kind, "name": name, "aliases": aliases or [],
                       "props": {"tier": 1}}, keys or {})


def _types(store: Any, subject: str) -> list[str]:
    return [e["type"] for e in store.events_for(subject)]


# -- documents --------------------------------------------------------------------------------------------------


def test_documents_save_read_and_finish(store):
    _doc(store)
    assert store.document_text("doc_1") == "Vega pays Orion. Orion ships."
    row = store.document_row("doc_1")
    assert row["class"] == "Contract" and row["uri"] == "files/doc_1.txt" and json.loads(row["metadata"]) == {"k": 1}
    assert "text" not in dict(row)
    assert store.chunk_row("doc_1_c0")["situation"] == "s"
    assert not store.has_document("doc_1", "h1")
    store.finish_document("doc_1", "h1")
    assert store.has_document("doc_1", "h1") and store.has_document("doc_1", "h1", "Contract", {"k": 1})
    assert not store.has_document("doc_1", "h1", "Memo") and not store.has_document("doc_1", "h1", None, {"k": 2})
    assert store.document_row("nope") is None and store.document_text("nope") is None
    _doc(store)  # saved again: replaced, not added
    assert [d["id"] for d in store.document_rows(["doc_1", "nope"])] == ["doc_1"]
    assert store.all_document_ids() == ["doc_1"]
    assert _types(store, "doc_1") == ["document.saved", "document.saved"]


def test_revisions_are_numbered_and_facts_record_theirs(store):
    assert store.archive_revision("doc_1") is False
    _doc(store, text="first text")
    _fact(store, "f1", "Vega pays Orion.")
    assert store.fact_row("f1")["revision"] == 0
    assert store.archive_revision("doc_1") and store.archive_revision("doc_1")
    assert store.revision_count("doc_1") == 2
    _doc(store, text="second text")
    _fact(store, "f2", "Orion ships.")
    assert store.fact_row("f2")["revision"] == 2
    assert store.document_text("doc_1", 0) == "first text" and store.document_text("doc_1") == "second text"
    assert store.document_text("doc_1", 9) == "second text"
    assert [e["data"] for e in store.events_for("doc_1") if e["type"] == "document.revised"] == \
        ['{"revision": 1}', '{"revision": 2}']


# -- facts ------------------------------------------------------------------------------------------------------


def test_facts_save_with_quotes_mentions_and_events(store):
    _doc(store)
    _entity(store, "e1", "Vega")
    _fact(store, "f1", "Vega pays Orion.", entities=["e1", None], valid_from="2025-01-01T00:00:00.000000Z",
          lifetime={"a few years": 1.0})
    row = store.fact_row("f1")
    assert row["text"] == "Vega pays Orion." and row["status"] == "current" and json.loads(row["traits"]) == []
    assert json.loads(row["lifetime"]) == {"a few years": 1.0} and row["valid_from"].startswith("2025")
    first_created = row["created_at"]
    quotes = store.quotes("f1")
    assert [q["passage_n"] for q in quotes] == [0, 1] and json.loads(quotes[1]["attrs"]) == {"page": 2}
    assert quotes[0]["attrs"] is None and quotes[1]["section"] == "1.2" and quotes[1]["end"] == 29
    assert [(m["entity_id"], m["confidence"]) for m in store.mentions("f1")] == [("e1", 0.5), (None, 0.5)]
    _fact(store, "f1", "Vega pays Orion.", entities=["e1"], restated="new version")
    assert store.fact_row("f1")["created_at"] == first_created and len(store.mentions("f1")) == 1
    assert _types(store, "f1") == ["fact.added", "fact.restated"]
    assert [e["data"] for e in store.events_for("e1")].count(json.dumps({"fact": "f1", "method": "key"})) == 2
    store.add_quotes("f1", [{"document_id": "doc_1", "passage_n": 5, "start": 0, "end": 1, "text": "V"}])
    assert [q["passage_n"] for q in store.quotes("f1")][-1] == 5
    assert store.fact_row("nope") is None and store.fact_rows(["f1", "nope"])[0]["id"] == "f1"
    assert [q["text"] for q in store.quotes_of(["f1"])] == ["Orion ships.", "Vega pays Orion.", "V"]
    assert [m["entity_id"] for m in store.mentions_of(["f1", "nope"])] == ["e1"]


def test_status_fields_relations_and_replacement(store):
    _doc(store)
    for i in range(3):
        _fact(store, f"f{i}", f"fact {i}")
    store.set_status("f0", "superseded", "superseded", by="f1")
    store.set_fields("f1", valid_until="2026-01-01T00:00:00.000000Z")
    store.set_fields("f1")  # nothing to change
    with pytest.raises(ValueError):
        store.set_fields("f1", **{"x = 1; drop table facts; --": 1})
    store.relate("f1", "f0", "supersedes")
    store.relate("f1", "f0", "supersedes")  # once only
    store.replace_fact("f2", "f1", "changed")
    store.replace_fact("f2", "f1", "changed")  # the relation is replaced, not added
    store.replace_fact("f0", None, "dropped")
    assert store.fact_row("f0")["status"] == "replaced" and store.fact_row("f2")["status"] == "replaced"
    assert store.fact_row("f1")["valid_until"] == "2026-01-01T00:00:00.000000Z"
    assert sorted((r["fact_id"], r["relation"], r["other_id"]) for r in store.relations("f1")) == \
        [("f1", "replaces", "f2"), ("f1", "supersedes", "f0")]
    assert _types(store, "f0") == ["fact.added", "fact.superseded", "fact.replaced"]
    assert json.loads(store.events_for("f2")[-1]["data"]) == {"reason": "changed", "by": "f1"}
    assert _types(store, "f1")[-1] == "fact.updated"


def test_contradictions_settle(store):
    _doc(store)
    for id_ in ("a", "b", "c"):
        _fact(store, id_, f"fact {id_}", status="contradicted")
    store.relate("a", "b", "contradicts")
    store.relate("c", "a", "contradicts")
    assert [(r["fact_id"], r["other_id"]) for r in store.contradiction_relations()] == [("c", "a"), ("a", "b")]
    assert store.settle("a", "zzz") is False
    assert store.settle("b", "a", dropped="b", how="picked") is True
    assert store.fact_row("b")["status"] == "retracted"
    assert store.fact_row("a")["status"] == "contradicted"  # c still contradicts it
    assert store.settle("b", "a") is False
    store.relate("a", "b", "contradicts")  # contradicted again, then settled again: one settled row
    assert store.settle("a", "b")
    assert [r["relation"] for r in store.relations("b")] == ["settled"]
    assert store.fact_row("a")["status"] == "contradicted"
    assert [r["fact_id"] for r in store.contradiction_relations()] == ["c"]
    assert _types(store, "b").count("fact.settled") == 2


def test_fact_queries(store):
    _doc(store, "doc_1", title="Supply")
    _doc(store, "doc_2", title="Lease")
    _entity(store, "e1", "Vega")
    _entity(store, "e2", "Orion")
    _fact(store, "f1", "Vega pays Orion monthly under the supply agreement, in dollars, by wire.",
          traits=["payment"], entities=["e1", "e2"], valid_from="2025-03-01T00:00:00.000000Z", cls="Term")
    _fact(store, "f2", "Orion ships.", entities=["e2", None], valid_from="2025-05-01T00:00:00.000000Z")
    _fact(store, "f3", "Vega leases.", document_id="doc_2", entities=["e1"], status="contradicted",
          valid_from="2025-04-01T00:00:00.000000Z")
    _fact(store, "f4", "Old news.", document_id="doc_2", entities=["e1"], status="superseded",
          extracted_at="2020-01-01T00:00:00.000000Z")
    assert store.fact_ids() == ["f1", "f2", "f3", "f4"]
    assert store.fact_ids(document_id="doc_2", status="contradicted") == ["f3"]
    assert store.fact_ids(classes=["Term"]) == ["f1"] and store.fact_ids(classes=[]) == []
    assert store.all_fact_ids() == ["f1", "f2", "f3", "f4"]
    assert store.standing_facts("doc_2") == {"Vega leases.": "f3"}
    assert store.standing_fact_ids_about(["e1", "e2"], outside="doc_2") == ["f1", "f2"]
    assert store.standing_fact_ids_about(["e1"], outside="doc_1") == ["f3"]
    assert store.fact_ids_about("e1") == ["f3", "f1"]  # newest first
    assert store.fact_ids_about("e1", include_retired=True) == ["f3", "f1", "f4"]
    assert store.fact_ids_about("e1", since="2025-03-15T00:00:00.000000Z") == ["f3"]
    assert store.fact_ids_about("e2", role="subject") == []
    assert store.linked_fact_ids("e1") == ["f1", "f3", "f4"]
    assert store.unlinked_fact_ids() == ["f2"] and store.unlinked_fact_ids("2099-01-01") == []
    assert store.documents_mentioning("e2") == ["doc_1"]
    assert sorted((r["other"], r["fact_id"]) for r in store.co_mentions("e1")) == [("e2", "f1")]
    listed = store.fact_list()
    assert [r["id"] for r in listed] == ["f1", "f2"] and listed[0]["title"] == "Supply"
    assert [r["id"] for r in store.fact_list(status="all", limit=3)] == ["f1", "f2", "f3"]
    assert [r["id"] for r in store.fact_list(status="all", document="Lease")] == ["f3", "f4"]
    assert [r["id"] for r in store.fact_list(status="all", document="doc_2.txt")] == ["f3", "f4"]
    assert [r["id"] for r in store.fact_list(trait="payment")] == ["f1"]
    assert store.fact_list(trait="pay") == []
    assert [r["text"][:4] for r in store.sample_facts()] == ["Vega"]  # 60 to 220 characters, current
    counts = store.counts()
    assert counts["documents"] == 2 and counts["documents_by_class"] == {"Contract": 2}
    assert counts["facts"] == {"contradicted": 1, "current": 2, "superseded": 1}
    assert counts["facts_by_class"] == {"Fact": 3, "Term": 1} and counts["entities"] == 2
    assert counts["facts_with_no_trait"] == 2 and counts["unlinked_mentions"] == 1
    assert counts["single_fact_entities"] == 0 and counts["entities_by_class"] == {"Company": 2}


# -- entities ---------------------------------------------------------------------------------------------------


def test_entities_keys_names_and_aliases(store):
    _entity(store, "e1", "Vega Corp", aliases=["Vega"], keys={"domain": " Vega.COM "})
    _entity(store, "e2", "Orion", cls="Entity", kind="org")
    _entity(store, "e3", "orion", cls="Entity", kind="org")
    assert store.entity_by_key("domain", "vega.com") == "e1" and store.entity_by_key("domain", "x") is None
    assert [r["id"] for r in store.entities_named("  ORION ")] == ["e2", "e3"]
    assert [r["id"] for r in store.entities_named("vega")] == ["e1"]  # by alias
    assert store.entities_named("veg") == []
    store.add_alias("e1", "VEGA")  # the same name, once
    store.add_alias("e1", "Vega Corp")
    store.add_alias("e1", "V.C.")
    store.add_alias("nope", "x")
    assert json.loads(store.entity_row("e1")["aliases"]) == ["Vega", "V.C."]
    store.save_entity_key("email", "a@vega.com", "e1")
    store.save_entity_key("email", "a@vega.com", "e2")  # a key belongs to its first entity
    assert store.entity_by_key("email", "A@vega.com") == "e1"
    store.update_entity("e2", name="Orion Ltd", aliases=["Orion"], props={"tier": 2}, reason="fix")
    assert store.entity_row("e2")["name"] == "Orion Ltd"
    assert [r["id"] for r in store.entities_of_classes(["Company"])] == ["e1"]
    assert [r["id"] for r in store.entity_rows(["e1", "e2", "x"])] == ["e1", "e2"] or \
        sorted(r["id"] for r in store.entity_rows(["e1", "e2", "x"])) == ["e1", "e2"]
    assert store.all_entity_ids() == ["e1", "e2", "e3"]
    assert _types(store, "e1") == ["entity.created", "entity.aliased"]
    assert _types(store, "e2") == ["entity.created", "entity.updated"]


def test_entity_lists_and_counts(store):
    _doc(store)
    _entity(store, "e1", "Vega", aliases=["Big V"])
    _entity(store, "e2", "Acme", cls="Entity", kind="org")
    _entity(store, "e3", "Bolt", cls="Entity", kind="tool")
    _fact(store, "f1", "x", entities=["e1", "e2"])
    _fact(store, "f2", "y", entities=["e1"])
    assert [(r["id"], r["facts"]) for r in store.entity_list()] == [("e1", 2), ("e2", 1), ("e3", 0)]
    assert [r["name"] for r in store.entity_list(by="name")] == ["Acme", "Bolt", "Vega"]
    assert [r["id"] for r in store.entity_list(class_name="Entity", limit=1)] == ["e2"]
    assert [r["id"] for r in store.entity_list(name="big")] == ["e1"]
    assert [(r["kind"], r["entities"], r["facts"]) for r in store.kind_counts()] == [("org", 1, 1), ("tool", 1, 0)]
    assert [(r["name"], r["n"]) for r in store.top_entities()] == [("Vega", 2), ("Acme", 1)]
    assert store.counts()["single_fact_entities"] == 1


def test_merge_and_split(store):
    _doc(store)
    _entity(store, "keep", "Vega", keys={"domain": "vega.com"})
    _entity(store, "gone", "Vega Inc", keys={"domain": "vegainc.com"})
    _fact(store, "f1", "x", entities=["gone"])
    _fact(store, "f2", "y", entities=["gone"])
    assert store.merge_entities("keep", "gone", "same company") == ["f1", "f2"]
    assert store.entity_row("gone")["id"] == "keep"  # follows the merge
    assert store.entity_by_key("domain", "vegainc.com") == "keep"
    assert store.linked_fact_ids("keep") == ["f1", "f2"] and store.entity_list()[0]["facts"] == 2
    _entity(store, "new", "Vega Labs")
    assert store.move_mentions("keep", "new", ["f2", "f9"], "different") == ["f2"]
    assert store.move_mentions("keep", "new", [], "nothing") == []
    assert store.linked_fact_ids("new") == ["f2"]
    assert _types(store, "keep")[-3:] == ["entity.merged", "entity.split", "entity.split"]


def test_add_mentions_links_facts_with_events(store):
    _doc(store)
    _entity(store, "e1", "Vega")
    _fact(store, "f1", "x")
    store.add_mentions([{"fact_id": "f1", "text": "Vega", "kind": "org", "role": "about", "entity_id": "e1",
                         "method": "claim", "confidence": 0.9}])
    store.add_mentions([])
    assert [(m["entity_id"], m["method"]) for m in store.mentions("f1")] == [("e1", "claim")]
    assert json.loads(store.events_for("e1")[-1]["data"]) == {"fact": "f1", "method": "claim"}


# -- events and export cursors ---------------------------------------------------------------------------------


def test_events_and_cursors(store):
    assert store.last_event() == 0 and store.cursor("w") == 0
    _doc(store)
    _fact(store, "f1", "x")
    last = store.last_event()
    assert last == 2
    assert [e["seq"] for e in store.events_after(0)] == [1, 2]
    assert [e["type"] for e in store.events_after(1)] == ["fact.added"]
    assert [e["seq"] for e in store.events_after(0, until=1)] == [1]
    assert [e["seq"] for e in store.events_after(0, limit=1)] == [1]
    store.set_cursor("w", 2)
    store.set_cursor("w", 1)  # a slower run cannot move it back
    assert store.cursor("w") == 2 and store.cursor("other") == 0
    with store.exporting("w"):
        pass


def test_query_and_one_take_question_marks(store):
    _doc(store)
    assert store.one("select count(*) as n from documents where id = ?", ("doc_1",))["n"] == 1
    assert [dict(r)["id"] for r in store.query("select id from documents where title like '%OC%'")] == ["doc_1"]
    assert store.one("select id from documents where id = ?", ("x",)) is None


def test_a_failed_write_leaves_nothing(store):
    _doc(store)
    with pytest.raises(KeyError):
        store.save_fact({"id": "f1", "class": "Fact", "text": "x", "document_id": "doc_1", "extracted_at": "t"},
                        [{"document_id": "doc_1"}], [])  # a quote missing its fields fails halfway
    assert store.fact_row("f1") is None and store.events_for("f1") == []
    _fact(store, "f1", "x")  # and the store still works
    assert store.fact_row("f1") is not None


# -- many writers ------------------------------------------------------------------------------------------------


def test_many_writers_number_events_in_commit_order(opener):
    """Writers on their own connections (as separate processes are) while a reader keeps reading the log the way an
    export does: every event up to the last one it sees is already there, so an export never skips one."""
    setup = opener()
    _doc(setup)
    writers, per_writer = 6, 15
    stores = [opener() for _ in range(writers)]
    reader = opener()
    done = threading.Event()
    problems: list[str] = []

    def write(n: int) -> None:
        try:
            for i in range(per_writer):
                _fact(stores[n], f"f{n}_{i}", f"fact {n} {i}")
                stores[n].add_alias("e_shared", f"alias {n} {i}")
        except Exception as err:  # pragma: no cover - reported below
            problems.append(repr(err))

    def read() -> None:
        while not done.is_set():
            last = reader.last_event()
            seqs = [e["seq"] for e in reader.events_after(0, until=last)]
            if seqs != list(range(1, last + 1)):
                problems.append(f"read up to {last} but saw {len(seqs)} events")
                return

    _entity(setup, "e_shared", "Shared")
    threads = [threading.Thread(target=write, args=(n,)) for n in range(writers)]
    watcher = threading.Thread(target=read)
    watcher.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    done.set()
    watcher.join()
    assert problems == []
    total = 2 + writers * per_writer * 2  # document and entity, then a fact and an alias each time
    assert setup.last_event() == total
    assert [e["seq"] for e in setup.events_after(0)] == list(range(1, total + 1))
    # Every alias survived: each was added inside the write that read the list, so none overwrote another.
    assert len(json.loads(setup.entity_row("e_shared")["aliases"])) == writers * per_writer


def test_export_runs_take_turns(opener):
    first, second = opener(), opener()
    order: list[str] = []
    inside = threading.Event()

    def run() -> None:
        with first.exporting("w"):
            order.append("first in")
            inside.set()
            threading.Event().wait(0.3)
            order.append("first out")

    t = threading.Thread(target=run)
    t.start()
    inside.wait(5)
    with second.exporting("w"):
        order.append("second in")
    t.join()
    assert order == ["first in", "first out", "second in"]
