"""`Settings.keep_document_text = False`: the store keeps offsets and hashes, not the document's text (issue #22)."""

import json

import pyarrow.parquet as pq
import pytest
from test_pipeline import Contract, build, extractor

from factoid import Fact, Settings, api
from factoid.exports import Parquet, export
from factoid.search import LocalIndex

META = {"signed_at": "2025-03-01T00:00:00Z"}
CAP = "Vega's liability to Orion is capped at $1M under the supply agreement."
ASSIGN = "Orion may not assign the supply agreement to anyone without Vega's written consent."
DELIVER = "Vega will deliver the goods to Orion every month under the supply agreement."
SOURCES: dict[str, str] = {}


class NoText(Settings):
    keep_document_text = False
    call_log = "metadata"


class FetchedContract(Contract):
    """A contract whose text its source can supply again."""

    @classmethod
    def fetch_text(cls, uri):
        return SOURCES.get(uri)


def _app(make_app, fake, keep=False, documents=(Contract,)):
    settings = Settings if keep else NoText
    return build(lambda **kw: make_app(settings, **{**kw, "documents": list(documents)}), fake)


def _ingest(app, text, document_type=Contract, uri="supply.txt"):
    return app.ingest_text(text, document_type=document_type, metadata=META, uri=uri)


def _stored_texts(app) -> list[str]:
    """Every text the store and the chunk index keep for documents, chunks, revisions, and quotes."""
    q = app.store.query
    out = [r["text"] for table in ("documents", "chunks", "revisions", "quotes")
           for r in q(f"select text from {table}")]
    if isinstance(app.index, LocalIndex):
        out += [r[0] for r in app.index.db.execute("select text from rows where ns = 'chunks'")]
        out += [r[0] for r in app.index.db.execute("select text from fts where ns = 'chunks'")]
    else:  # PostgresIndex, under FACTOID_TEST_SEARCH=postgres
        out += [r[0] for r in app.index._db().execute("select text from index_rows where ns = %s",
                                                      (app.ns("chunks"),)).fetchall()]
    return out


def _facts(app) -> list[tuple]:
    return sorted((f.text, f.status, tuple(f.trait_names), tuple(sorted(e.name for e in f.entities)),
                   tuple((q.passage_n, q.start, q.end) for q in f.quotes))
                  for f in app.list_facts())


def test_no_document_or_quote_text_is_stored_and_the_facts_are_the_same(make_app, fake, capsys):
    kept = _app(make_app, fake, keep=True)
    _ingest(kept, CAP + "\n\n" + ASSIGN)
    _ingest(kept, CAP + "\n\n" + ASSIGN + "\n\n" + DELIVER)
    with kept.active():
        expected = _facts(kept)

    app = _app(make_app, fake)
    first = _ingest(app, CAP + "\n\n" + ASSIGN)
    second = _ingest(app, CAP + "\n\n" + ASSIGN + "\n\n" + DELIVER)  # a new version: the old one is a revision
    assert app.store.revision_count(first.document.id) == 1
    quoted = {q.text for f in first.facts + second.facts for q in f.quotes}
    assert quoted >= {CAP, ASSIGN, DELIVER}
    stored = _stored_texts(app)
    assert stored and set(stored) == {""}
    assert app.store.document_text(first.document.id) is None
    with app.active():
        assert _facts(app) == expected
        assert all(q.text is None and q.text_hash for f in app.list_facts() for q in f.quotes)
    row = app.store.document_row(first.document.id)
    assert row["uri"] == "supply.txt" and row["content_hash"] == second.document.content_hash
    chunks = app.search_chunks("liability")  # found by vector only
    assert chunks and all(c["text"] is None for c in chunks)
    assert "warning" not in capsys.readouterr().err  # call_log is "metadata"


def test_a_full_call_log_warns_once_at_start(make_app, capsys):
    class FullLog(NoText):
        call_log = "full"

    classes = {"documents": [Contract], "entities": [], "facts": [Fact]}
    make_app(FullLog, **classes)
    err = capsys.readouterr().err
    assert err.count("warning:") == 1 and "call_log" in err
    make_app(NoText, **classes)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("keep", [True, False])
def test_reingest_keeps_old_ids_by_quote_hashes(make_app, fake, keep):
    app = _app(make_app, fake, keep=keep)
    first = _ingest(app, CAP + "\n\n" + ASSIGN)
    old = {f.text: f.id for f in first.facts}

    def reworded(prompt):  # the same passages, extracted in other words
        facts = json.loads(extractor(prompt))["facts"]
        for fact in facts:
            fact["text"] = fact["text"].replace("capped at", "limited to").replace("anyone", "any party")
        return json.dumps({"facts": facts})

    fake.generator = reworded
    second = _ingest(app, CAP + "\n\n" + ASSIGN + "\n\n" + DELIVER)
    by_text = {f.text: f.id for f in second.facts}
    assert by_text[CAP.replace("capped at", "limited to")] == old[CAP]
    assert by_text[ASSIGN.replace("anyone", "any party")] == old[ASSIGN]
    assert {Fact.get(i).status for i in old.values()} == {"current"}


def test_fetch_text_fills_quotes_when_the_hash_matches(make_app, fake):
    text = CAP + "\n\n" + ASSIGN
    app = _app(make_app, fake, documents=[FetchedContract])
    result = _ingest(app, text, document_type=FetchedContract, uri="fetched.txt")
    fact_id = next(f.id for f in result.facts if f.text == CAP)

    SOURCES.clear()  # the source has nothing
    quotes = api.fact(app, fact_id)["quotes"]
    assert [(q["text"], q["start"], q["end"]) for q in quotes] == [(None, 0, len(CAP))]

    SOURCES["fetched.txt"] = text
    quotes = api.fact(app, fact_id)["quotes"]
    assert [q["text"] for q in quotes] == [CAP]

    SOURCES["fetched.txt"] = text.replace("$1M", "$9M")  # the source changed since the ingest
    assert [q["text"] for q in api.fact(app, fact_id)["quotes"]] == [None]
    SOURCES.clear()


def test_parquet_writes_null_quote_and_document_text(make_app, fake, tmp_path):
    app = _app(make_app, fake)
    _ingest(app, CAP + "\n\n" + ASSIGN)
    export(app, {"warehouse": Parquet(str(tmp_path / "out"))})
    facts = [r for f in sorted((tmp_path / "out" / "facts").glob("*.parquet")) for r in pq.read_table(f).to_pylist()]
    assert len(facts) == 2 and {q["text"] for f in facts for q in f["quotes"]} == {None}
    assert all(f["text"] for f in facts)
    documents = pq.read_table(next((tmp_path / "out" / "documents").glob("*.parquet"))).to_pylist()
    assert [d["text"] for d in documents] == [None] and documents[0]["uri"] == "supply.txt"
