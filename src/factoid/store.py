"""The system of record: current state in SQLite, plus an event log in the same database.

Current state is the source of truth. Each change also writes an event (`added`, `restated`, `superseded`, `ended`,
`corrected`, `contradicted`, `settled`, `replaced`, `retracted`, `restored`, `revised`, `linked`, `merged`, or `split`),
so a reader can see where a fact came from and how it changed. The log is not replayed.
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
create table if not exists revisions (
    document_id text not null, n integer not null, text text not null, metadata text, source_datetime text,
    saved_at text not null, primary key (document_id, n)
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
create table if not exists export_cursors (
    name text primary key, seq integer not null, at text not null
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
        if "attrs" not in columns:  # stores made before quotes carried attrs
            self.db.execute("alter table quotes add column attrs text")
        if "revision" not in {row[1] for row in self.db.execute("pragma table_info(facts)")}:
            self.db.execute("alter table facts add column revision integer")  # stores made before revisions
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
            self.event(db, "document.saved", doc["id"], uri=doc.get("uri"))

    def archive_revision(self, document_id: str) -> bool:
        """Keep a document's stored text as a numbered revision before a new version replaces it. Facts record the
        revision they came from, so the quotes of a replaced fact still point at the text they quote."""
        with self.tx() as db:
            row = db.execute("select text, metadata, source_datetime from documents where id = ?",
                             (document_id,)).fetchone()
            if row is None:
                return False
            n = db.execute("select count(*) from revisions where document_id = ?", (document_id,)).fetchone()[0]
            db.execute("insert into revisions values (?,?,?,?,?,?)",
                       (document_id, n, row["text"], row["metadata"], row["source_datetime"], _now()))
            self.event(db, "document.revised", document_id, revision=n + 1)
            return True

    def document_text(self, document_id: str, revision: int | None = None) -> str | None:
        """A document's text: the current version, or an earlier revision by number (0 is the first)."""
        if revision is not None:
            row = self.one("select text from revisions where document_id = ? and n = ?", (document_id, revision))
            if row is not None:
                return row["text"]
        row = self.one("select text from documents where id = ?", (document_id,))
        return row["text"] if row else None

    def standing_facts(self, document_id: str) -> dict[str, str]:
        """A document's facts that still stand (current or contradicted), as ids by text."""
        rows = self.query("select id, text from facts where document_id = ? and status in ('current', 'contradicted')",
                          (document_id,))
        return {row["text"]: row["id"] for row in rows}

    def replace_fact(self, fact_id: str, by: str | None, reason: str) -> None:
        """A newer version of the fact's document no longer states it: changed (`by` the fact that says it now) or
        dropped. Apart from `retracted`, which a person sets."""
        with self.tx() as db:
            db.execute("update facts set status = 'replaced', updated_at = ? where id = ?", (_now(), fact_id))
            self.event(db, "fact.replaced", fact_id, reason=reason, **({"by": by} if by else {}))
            if by:
                db.execute("insert or replace into relations values (?,?,?,?)", (by, fact_id, "replaces", _now()))

    # -- facts ----------------------------------------------------------------------------------------------

    def save_fact(self, row: dict[str, Any], quotes: list[dict[str, Any]], mentions: list[dict[str, Any]]) -> None:
        stamp = _now()
        with self.tx() as db:
            before = db.execute("select created_at from facts where id = ?", (row["id"],)).fetchone()
            db.execute(
                """insert or replace into facts (id, class, text, document_id, chunk_id, status, traits,
                trait_scores, valid_from, expires, valid_until, lifetime, source_datetime, extracted_at, scores,
                fingerprint, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["id"], row["class"], row["text"], row["document_id"], row.get("chunk_id"),
                 row.get("status", "current"), json.dumps(row.get("traits") or []),
                 json.dumps(row.get("trait_scores") or {}), row.get("valid_from"), row.get("expires"),
                 row.get("valid_until"), json.dumps(row.get("lifetime")) if row.get("lifetime") else None,
                 row.get("source_datetime"), row["extracted_at"], json.dumps(row.get("scores") or {}),
                 row.get("fingerprint"), before["created_at"] if before else stamp, stamp),
            )
            db.execute("update facts set revision = (select count(*) from revisions where document_id = ?) "
                       "where id = ?", (row["document_id"], row["id"]))
            db.execute("delete from quotes where fact_id = ?", (row["id"],))
            db.execute("delete from mentions where fact_id = ?", (row["id"],))
            db.executemany(
                "insert into quotes (fact_id, document_id, passage_n, start, \"end\", text, speaker, said_at, section, "
                "attrs) values (?,?,?,?,?,?,?,?,?,?)",
                [(row["id"], q["document_id"], q["passage_n"], q["start"], q["end"], q["text"], q.get("speaker"),
                  q.get("said_at"), q.get("section"), json.dumps(q["attrs"]) if q.get("attrs") else None)
                 for q in quotes],
            )
            db.executemany(
                "insert into mentions values (?,?,?,?,?,?,?)",
                [(row["id"], m["text"], m.get("kind"), m.get("role", "about"), m.get("entity_id"), m.get("method"),
                  m.get("confidence")) for m in mentions],
            )
            restated = row.get("restated")
            self.event(db, "fact.restated" if restated else "fact.added", row["id"], text=row["text"],
                       document=row["document_id"], **({"reason": restated} if restated else {}))
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
            self.event(db, "fact.updated", fact_id, **fields)

    def relate(self, fact_id: str, other_id: str, relation: str) -> None:
        with self.tx() as db:
            db.execute("insert or ignore into relations values (?,?,?,?)", (fact_id, other_id, relation, _now()))

    def settle(self, fact_id: str, other_id: str, *, dropped: str | None = None, **data: Any) -> bool:
        """Settle the open contradiction between two facts: its `contradicts` relation becomes `settled`, `dropped`
        (if any) is retracted, and a side still marked `contradicted` goes back to `current` unless another open
        contradiction holds it. Each side gets a `fact.settled` event. False when the pair has no open contradiction."""
        pair = "((fact_id = ? and other_id = ?) or (fact_id = ? and other_id = ?))"
        ids = (fact_id, other_id, other_id, fact_id)
        with self.tx() as db:
            found = db.execute(f"select 1 from relations where relation = 'contradicts' and {pair}", ids).fetchone()
            if found is None:
                return False
            db.execute(f"update or replace relations set relation = 'settled', at = ? "
                       f"where relation = 'contradicts' and {pair}", (_now(), *ids))
            for side in (fact_id, other_id):
                row = db.execute("select status from facts where id = ?", (side,)).fetchone()
                status = row["status"] if row else None
                if side == dropped:
                    status = "retracted"
                elif status == "contradicted":
                    still = db.execute("select 1 from relations where relation = 'contradicts' and "
                                       "(fact_id = ? or other_id = ?)", (side, side)).fetchone()
                    status = "contradicted" if still else "current"
                if row is not None:
                    db.execute("update facts set status = ?, updated_at = ? where id = ?", (status, _now(), side))
                self.event(db, "fact.settled", side, status=status,
                           other=other_id if side == fact_id else fact_id, **data)
        return True

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
                self.event(db, "entity.aliased", entity_id, alias=alias)

    def save_entity_key(self, key: str, value: str, entity_id: str) -> None:
        with self.tx() as db:
            db.execute("insert or ignore into entity_keys values (?,?,?)", (key, _norm(value), entity_id))

    def merge_entities(self, keep: str, gone: str, reason: str) -> list[str]:
        """Fold `gone` into `keep`: its mentions, keys, and names. Returns the ids of the facts that moved."""
        with self.tx() as db:
            facts = [r["fact_id"] for r in db.execute("select distinct fact_id from mentions where entity_id = ?",
                                                      (gone,))]
            db.execute("update entities set merged_into = ? where id = ?", (keep, gone))
            db.execute("update mentions set entity_id = ? where entity_id = ?", (keep, gone))
            db.execute("update or ignore entity_keys set entity_id = ? where entity_id = ?", (keep, gone))
            self.event(db, "entity.merged", keep, merged=gone, reason=reason)
            return facts

    def update_entity(self, entity_id: str, *, name: str, aliases: list[str], props: dict[str, Any],
                      reason: str = "") -> None:
        with self.tx() as db:
            db.execute("update entities set name = ?, aliases = ?, props = ? where id = ?",
                       (name, json.dumps(aliases), json.dumps(props, default=str), entity_id))
            self.event(db, "entity.updated", entity_id, name=name, aliases=aliases, props=props,
                       **({"reason": reason} if reason else {}))

    def move_mentions(self, source: str, target: str, fact_ids: list[str], reason: str) -> list[str]:
        """Move the links from `source` to `target` on the given facts (a split). Returns the facts that moved."""
        with self.tx() as db:
            moved = [r["fact_id"] for r in db.execute(
                f"select distinct fact_id from mentions where entity_id = ? and fact_id in "
                f"({','.join('?' * len(fact_ids))})", (source, *fact_ids))] if fact_ids else []
            for fact_id in moved:
                db.execute("update mentions set entity_id = ? where entity_id = ? and fact_id = ?",
                           (target, source, fact_id))
            self.event(db, "entity.split", source, into=target, facts=moved, reason=reason)
            return moved


    # -- export cursors ---------------------------------------------------------------------------------------

    def last_event(self) -> int:
        row = self.one("select max(seq) seq from events")
        return int(row["seq"] or 0) if row else 0

    def cursor(self, name: str) -> int:
        """The last event an export was sent, or 0 for one never run."""
        row = self.one("select seq from export_cursors where name = ?", (name,))
        return int(row["seq"]) if row else 0

    def set_cursor(self, name: str, seq: int) -> None:
        with self.tx() as db:
            db.execute("insert or replace into export_cursors values (?,?,?)", (name, seq, _now()))


def _norm(value: str) -> str:
    return " ".join(str(value).lower().split())


def now_stamp() -> str:
    return _now()



