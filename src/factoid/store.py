"""The system of record: current state in SQLite, plus an event log in the same database.

Current state is the source of truth. Each change also writes an event (`added`, `superseded`, `ended`, `corrected`,
`contradicted`, `retracted`, `restored`, `linked`, `merged`, or `split`), so a reader can see where a fact came from
and how it changed. The log is not replayed.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

__all__ = ["Store"]

SCHEMA = """
create table if not exists documents (
    id text primary key, class text not null, uri text, title text, source_datetime text, metadata text,
    text text not null, content_hash text, ingested_at text not null
);
create table if not exists passages (
    document_id text not null, n integer not null, start integer not null, "end" integer not null,
    speaker text, said_at text, primary key (document_id, n)
);
create table if not exists chunks (
    id text primary key, document_id text not null, n integer not null, first_passage integer not null,
    last_passage integer not null, text text not null, situation text
);
create table if not exists facts (
    id text primary key, class text not null, text text not null, document_id text not null, chunk_id text,
    status text not null default 'current', traits text not null default '{}', trait_scores text not null default '{}',
    valid_from text, expires text, valid_until text, lifetime text, source_datetime text, extracted_at text not null,
    scores text not null default '{}', fingerprint text, created_at text not null, updated_at text not null
);
create index if not exists facts_document on facts(document_id);
create index if not exists facts_status on facts(status);
create table if not exists quotes (
    fact_id text not null, document_id text not null, passage_n integer not null, start integer not null,
    "end" integer not null, text text not null, speaker text, said_at text, section text
);
create index if not exists quotes_fact on quotes(fact_id);
create table if not exists mentions (
    fact_id text not null, text text not null, kind text, role text not null default 'about', entity_id text,
    method text, confidence real
);
create index if not exists mentions_fact on mentions(fact_id);
create index if not exists mentions_entity on mentions(entity_id);
create table if not exists entities (
    id text primary key, class text not null, kind text, name text not null, aliases text not null default '[]',
    props text not null default '{}', created_at text not null, merged_into text
);
create index if not exists entities_name on entities(lower(name));
create table if not exists entity_keys (
    key text not null, value text not null, entity_id text not null, primary key (key, value)
);
create table if not exists relations (
    fact_id text not null, other_id text not null, relation text not null, at text not null,
    primary key (fact_id, other_id, relation)
);
create table if not exists events (
    seq integer primary key autoincrement, at text not null, type text not null, subject text not null,
    data text not null default '{}'
);
"""


def _now() -> str:
    from .dates import format_datetime, now

    return format_datetime(now())


class Store:
    """SQLite store. One writer per process; WAL mode on."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.RLock()
        if path is None:
            self.db = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute("pragma journal_mode=wal")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        columns = {row[1] for row in self.db.execute("pragma table_info(quotes)")}
        if "section" not in columns:  # stores made before quotes carried sections
            self.db.execute("alter table quotes add column section text")
        self.db.commit()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def query(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.db.execute(sql, params).fetchone()

    def event(self, db: sqlite3.Connection, type_: str, subject: str, **data: Any) -> None:
        db.execute("insert into events (at, type, subject, data) values (?,?,?,?)",
                   (_now(), type_, subject, json.dumps(data, default=str)))

    # -- documents ------------------------------------------------------------------------------------------

    def has_document(self, document_id: str, content_hash: str, class_name: str | None = None,
                     metadata: dict[str, Any] | None = None) -> bool:
        """True when this document is stored with the same text (and, if given, the same class and metadata)."""
        row = self.one("select class, metadata, content_hash from documents where id = ?", (document_id,))
        if row is None or row["content_hash"] != content_hash:
            return False
        if class_name is not None and row["class"] != class_name:
            return False
        return metadata is None or json.loads(row["metadata"] or "{}") == json.loads(json.dumps(metadata, default=str))

    def finish_document(self, document_id: str, content_hash: str) -> None:
        """Record that a document's ingest finished, so an unchanged re-ingest can skip it. A run that fails halfway
        leaves no hash, and the next run ingests the document again."""
        with self.tx() as db:
            db.execute("update documents set content_hash = ? where id = ?", (content_hash, document_id))

    def save_document(self, doc: dict[str, Any], passages: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> None:
        with self.tx() as db:
            db.execute("delete from passages where document_id = ?", (doc["id"],))
            db.execute("delete from chunks where document_id = ?", (doc["id"],))
            db.execute(
                "insert or replace into documents values (?,?,?,?,?,?,?,?,?)",
                (doc["id"], doc["class"], doc.get("uri"), doc.get("title"), doc.get("source_datetime"),
                 json.dumps(doc.get("metadata") or {}, default=str), doc["text"], doc.get("content_hash"), _now()),
            )
            db.executemany(
                "insert into passages values (?,?,?,?,?,?)",
                [(doc["id"], p["n"], p["start"], p["end"], p.get("speaker"), p.get("said_at")) for p in passages],
            )
            db.executemany(
                "insert into chunks values (?,?,?,?,?,?,?)",
                [(c["id"], doc["id"], c["n"], c["first_passage"], c["last_passage"], c["text"], c.get("situation"))
                 for c in chunks],
            )

    def retire_document_facts(self, document_id: str) -> dict[str, str]:
        """When a document is re-ingested, its old facts are retracted. Returns their ids by text, so a fact that
        comes back with the same sentence keeps its id."""
        with self.tx() as db:
            rows = db.execute("select id, text from facts where document_id = ? and status != 'retracted'",
                              (document_id,)).fetchall()
            for row in rows:
                db.execute("update facts set status = 'retracted', updated_at = ? where id = ?", (_now(), row["id"]))
                self.event(db, "fact.retracted", row["id"], reason="document re-ingested")
            return {row["text"]: row["id"] for row in rows}

    # -- facts ----------------------------------------------------------------------------------------------

    def save_fact(self, row: dict[str, Any], quotes: list[dict[str, Any]], mentions: list[dict[str, Any]]) -> None:
        stamp = _now()
        with self.tx() as db:
            db.execute(
                """insert or replace into facts (id, class, text, document_id, chunk_id, status, traits,
                trait_scores, valid_from, expires, valid_until, lifetime, source_datetime, extracted_at, scores,
                fingerprint, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["id"], row["class"], row["text"], row["document_id"], row.get("chunk_id"),
                 row.get("status", "current"), json.dumps(row.get("traits") or []),
                 json.dumps(row.get("trait_scores") or {}), row.get("valid_from"), row.get("expires"),
                 row.get("valid_until"), json.dumps(row.get("lifetime")) if row.get("lifetime") else None,
                 row.get("source_datetime"), row["extracted_at"], json.dumps(row.get("scores") or {}),
                 row.get("fingerprint"), stamp, stamp),
            )
            db.execute("delete from quotes where fact_id = ?", (row["id"],))
            db.execute("delete from mentions where fact_id = ?", (row["id"],))
            db.executemany(
                "insert into quotes values (?,?,?,?,?,?,?,?,?)",
                [(row["id"], q["document_id"], q["passage_n"], q["start"], q["end"], q["text"], q.get("speaker"),
                  q.get("said_at"), q.get("section")) for q in quotes],
            )
            db.executemany(
                "insert into mentions values (?,?,?,?,?,?,?)",
                [(row["id"], m["text"], m.get("kind"), m.get("role", "about"), m.get("entity_id"), m.get("method"),
                  m.get("confidence")) for m in mentions],
            )
            restored = row.get("restored")
            self.event(db, "fact.restored" if restored else "fact.added", row["id"], text=row["text"],
                       document=row["document_id"], **({"reason": restored} if restored else {}))
            for m in mentions:
                if m.get("entity_id"):
                    self.event(db, "entity.linked", m["entity_id"], fact=row["id"], method=m.get("method"))

    def set_status(self, fact_id: str, status: str, event: str, **data: Any) -> None:
        with self.tx() as db:
            db.execute("update facts set status = ?, updated_at = ? where id = ?", (status, _now(), fact_id))
            self.event(db, f"fact.{event}", fact_id, **data)

    def set_fields(self, fact_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{name} = ?" for name in fields)
        with self.tx() as db:
            db.execute(f"update facts set {cols}, updated_at = ? where id = ?", (*fields.values(), _now(), fact_id))

    def relate(self, fact_id: str, other_id: str, relation: str) -> None:
        with self.tx() as db:
            db.execute("insert or ignore into relations values (?,?,?,?)", (fact_id, other_id, relation, _now()))

    def fact_row(self, fact_id: str) -> sqlite3.Row | None:
        return self.one("select * from facts where id = ?", (fact_id,))

    def quotes(self, fact_id: str) -> list[sqlite3.Row]:
        return self.query("select * from quotes where fact_id = ? order by passage_n", (fact_id,))

    def mentions(self, fact_id: str) -> list[sqlite3.Row]:
        return self.query("select * from mentions where fact_id = ?", (fact_id,))

    def relations(self, fact_id: str) -> list[sqlite3.Row]:
        return self.query("select * from relations where fact_id = ? or other_id = ?", (fact_id, fact_id))

    def events_for(self, subject: str) -> list[sqlite3.Row]:
        return self.query("select * from events where subject = ? order by seq", (subject,))

    # -- entities -------------------------------------------------------------------------------------------

    def save_entity(self, row: dict[str, Any], keys: dict[str, str]) -> None:
        with self.tx() as db:
            db.execute(
                "insert or replace into entities (id, class, kind, name, aliases, props, created_at) "
                "values (?,?,?,?,?,?,?)",
                (row["id"], row["class"], row.get("kind"), row["name"], json.dumps(row.get("aliases") or []),
                 json.dumps(row.get("props") or {}, default=str), row.get("created_at") or _now()),
            )
            for key, value in keys.items():
                db.execute("insert or ignore into entity_keys values (?,?,?)", (key, _norm(value), row["id"]))
            self.event(db, "entity.created", row["id"], name=row["name"], cls=row["class"], kind=row.get("kind"))

    def entity_by_key(self, key: str, value: str) -> str | None:
        row = self.one("select entity_id from entity_keys where key = ? and value = ?", (key, _norm(value)))
        return row["entity_id"] if row else None

    def entities_named(self, name: str) -> list[sqlite3.Row]:
        name = _norm(name)
        rows = self.query("select * from entities where merged_into is null and lower(name) = ?", (name,))
        if rows:
            return rows
        return [r for r in self.query("select * from entities where merged_into is null and aliases like ?",
                                      (f"%{name}%",))
                if name in [_norm(a) for a in json.loads(r["aliases"])]]

    def entity_row(self, entity_id: str) -> sqlite3.Row | None:
        row = self.one("select * from entities where id = ?", (entity_id,))
        while row is not None and row["merged_into"]:
            row = self.one("select * from entities where id = ?", (row["merged_into"],))
        return row

    def add_alias(self, entity_id: str, alias: str) -> None:
        row = self.entity_row(entity_id)
        if row is None:
            return
        aliases = json.loads(row["aliases"])
        if _norm(alias) != _norm(row["name"]) and _norm(alias) not in [_norm(a) for a in aliases]:
            aliases.append(alias)
            with self.tx() as db:
                db.execute("update entities set aliases = ? where id = ?", (json.dumps(aliases), entity_id))

    def save_entity_key(self, key: str, value: str, entity_id: str) -> None:
        with self.tx() as db:
            db.execute("insert or ignore into entity_keys values (?,?,?)", (key, _norm(value), entity_id))

    def merge_entities(self, keep: str, gone: str, reason: str) -> None:
        with self.tx() as db:
            db.execute("update entities set merged_into = ? where id = ?", (keep, gone))
            db.execute("update mentions set entity_id = ? where entity_id = ?", (keep, gone))
            db.execute("update entity_keys set entity_id = ? where entity_id = ?", (keep, gone))
            self.event(db, "entity.merged", keep, merged=gone, reason=reason)


def _norm(value: str) -> str:
    return " ".join(str(value).lower().split())


def now_stamp() -> str:
    return _now()



