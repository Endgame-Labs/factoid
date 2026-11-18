from pathlib import Path

import pyarrow.parquet as pq
from test_pipeline import Contract, build

from factoid.exports import TURBOPUFFER_SCHEMA, Parquet, Turbopuffer, export

FIRST = ("Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
         "Orion may not assign the supply agreement to anyone without Vega's written consent.")
AMENDMENT = "Amendment 2 raises Vega's liability cap to Orion to $2M from January 1, 2027."


def _ingest(app, text, uri, signed):
    return app.ingest_text(text, document_type=Contract, metadata={"signed_at": signed}, uri=uri)


def _read(folder: Path) -> list[tuple[str, list[dict]]]:
    return [(f.name, pq.read_table(f).to_pylist()) for f in sorted(folder.glob("*.parquet"))]


def test_parquet_sends_changes_since_the_cursor_and_rebuilds_with_full(make_app, fake, tmp_path):
    app = build(make_app, fake)
    first = _ingest(app, FIRST, "supply.txt", "2025-03-01T00:00:00Z")
    cap, consent = first.facts
    exports = {"warehouse": Parquet(str(tmp_path / "out"), vectors=True)}

    [result] = export(app, exports)
    assert len(result.batch.facts) == 2 and not result.skipped
    [(name, facts)] = _read(tmp_path / "out" / "facts")
    assert name.startswith("0000000000-")
    row = next(f for f in facts if f["id"] == cap.id)
    # Mentions and quotes are nested in the fact's row; the vector is a float list with its model.
    assert {m["text"] for m in row["mentions"]} == {"Vega", "Orion"} and row["quotes"][0]["text"]
    assert len(row["vector"]) == 64 and row["embedding_model"] and row["status"] == "current"
    assert row["valid_from"] is None or row["valid_from"].tzinfo is not None
    assert len(_read(tmp_path / "out" / "entities")[0][1]) == 2
    assert _read(tmp_path / "out" / "documents")[0][1][0]["uri"] == "supply.txt"

    [again] = export(app, exports)
    assert again.skipped  # nothing changed since the cursor

    _ingest(app, AMENDMENT, "amendment2.txt", "2026-10-03T00:00:00Z")
    [second] = export(app, exports)
    files = _read(tmp_path / "out" / "facts")
    assert len(files) == 2
    changed = {f["id"]: f for f in files[1][1]}
    # The superseded cap is sent again with its new status and end date; the untouched consent fact is not.
    assert changed[cap.id]["status"] == "superseded" and changed[cap.id]["valid_until"].year == 2027
    assert consent.id not in changed and len(changed) == 2
    events = [e for _, rows in _read(tmp_path / "out" / "events") for e in rows]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))  # every event once, in order

    [full] = export(app, exports, full=True)
    assert full.batch.full
    [(_, facts)] = _read(tmp_path / "out" / "facts")
    assert len(facts) == 3 and {f["exported_through"] for f in facts} == {second.batch.end}


def test_each_sink_keeps_its_own_cursor(make_app, fake, tmp_path):
    app = build(make_app, fake)
    _ingest(app, FIRST, "supply.txt", "2025-03-01T00:00:00Z")
    exports = {"a": Parquet(str(tmp_path / "a")), "b": Parquet(str(tmp_path / "b"))}
    export(app, exports, ["a"])
    _ingest(app, AMENDMENT, "amendment2.txt", "2026-10-03T00:00:00Z")
    a, b = export(app, exports)
    assert len(a.batch.facts) == 2 and len(b.batch.facts) == 3  # b catches up from the start
    assert "vector" not in pq.read_table(next((tmp_path / "b" / "facts").glob("*.parquet"))).column_names


def test_turbopuffer_sink_writes_one_row_per_fact(make_app, fake, monkeypatch):
    app = build(make_app, fake)
    first = _ingest(app, FIRST, "supply.txt", "2025-03-01T00:00:00Z")
    posts, deletes = [], []

    class Client:
        base_url = "https://tp.example"
        _http = type("H", (), {"delete": lambda self, url, headers: (deletes.append(url),
                                                                     type("R", (), {"status_code": 200})())[1]})()

        def _headers(self):
            return {}

        def _post(self, path, body):
            posts.append((path, body))
            return {}

    monkeypatch.setattr(Turbopuffer, "_client", lambda self: Client())
    exports = {"search": Turbopuffer(namespace="acme-facts")}
    export(app, exports)
    [(path, body)] = posts
    assert path == "/v2/namespaces/acme-facts" and body["schema"] == TURBOPUFFER_SCHEMA
    rows = {r["id"]: r for r in body["upsert_rows"]}
    row = rows[first.facts[0].id]
    assert set(row) == {"id", "vector", "text", "class", "traits", "status", "valid_from", "valid_until",
                        "document_id", "entity_ids"}
    assert len(row["vector"]) == 64 and len(row["entity_ids"]) == 2 and row["status"] == "current"
    assert not deletes
    export(app, exports, full=True)
    assert deletes == ["https://tp.example/v2/namespaces/acme-facts"]
