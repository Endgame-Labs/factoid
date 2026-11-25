"""The system of record: current state, plus an event log in the same database.

Current state is the source of truth. Each change also writes an event (`added`, `restated`, `superseded`, `ended`,
`corrected`, `contradicted`, `settled`, `replaced`, `retracted`, `restored`, `revised`, `linked`, `merged`, or `split`),
so a reader can see where a fact came from and how it changed. The log is not replayed.

`Store` keeps it in SQLite. `factoid.postgres.PostgresStore` keeps it in Postgres with the same methods. No other
module writes SQL: every read and write the framework makes is a named method here. `query` and `one` stay for
project code and tests that want a read the methods do not cover; their SQL uses `?` placeholders on every backend.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
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

#: Statuses of a fact that still stands.
STANDING = "('current', 'contradicted')"

_QUOTE_COLUMNS = ("fact_id", "document_id", "passage_n", "start", '"end"', "text", "speaker", "said_at", "section",
                  "attrs")
_MENTION_COLUMNS = ("fact_id", "text", "kind", "role", "entity_id", "method", "confidence")


def _now() -> str:
    from .dates import format_datetime, now

    return format_datetime(now())


class Store:
    """SQLite store. One writer per process; WAL mode on.

    Backends differ only in how they connect, in `tx`, and in the few statements SQL dialects spell differently
    (`_replace`, `_insert_ignore`, and `_has_trait`)."""

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

    def close(self) -> None:
        self.db.close()

    # -- the SQL every method goes through -----------------------------------------------------------------------

    @contextmanager
    def tx(self) -> Iterator[Any]:
        """One write transaction. Yields a connection with `execute` and `executemany`, for this module only.

        It takes SQLite's write lock at the start (`begin immediate`), so a write that reads first (a fact's
        created_at, an entity's aliases) sees no change from another process before it writes."""
        with self._lock:
            if not self.db.in_transaction:
                self.db.execute("begin immediate")
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def query(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        """Rows for a read with `?` placeholders. Each row reads by column name (`row["id"]`) and turns into a dict."""
        with self._lock:
            return self.db.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any | None:
        with self._lock:
            return self.db.execute(sql, params).fetchone()

    def event(self, db: Any, type_: str, subject: str, **data: Any) -> None:
        db.execute("insert into events (at, type, subject, data) values (?,?,?,?)",
                   (_now(), type_, subject, json.dumps(data, default=str)))

    def _replace(self, db: Any, table: str, columns: Iterable[str], key: Iterable[str],
                 rows: list[tuple[Any, ...]]) -> None:
        """Insert rows, first removing any row with the same key (SQLite's `insert or replace`)."""
        columns = tuple(columns)
        db.executemany(f"insert or replace into {table} ({', '.join(columns)}) values ({_marks(len(columns))})", rows)

    def _insert_ignore(self, db: Any, table: str, columns: Iterable[str], rows: list[tuple[Any, ...]]) -> None:
        """Insert rows, skipping any whose key is already stored."""
        columns = tuple(columns)
        db.executemany(f"insert or ignore into {table} ({', '.join(columns)}) values ({_marks(len(columns))})", rows)

    def _has_trait(self, column: str) -> str:
        """SQL that is true when the JSON list in `column` holds the `?` parameter."""
        return f"exists (select 1 from json_each({column}) t where t.value = ?)"

    def _in(self, sql: str, ids: list[str], before: tuple[Any, ...] = (), after: tuple[Any, ...] = (),
            size: int = 500) -> list[Any]:
        """Run `sql`, whose `{ids}` stands for a list of `?`, over `ids` in parts."""
        out: list[Any] = []
        for start in range(0, len(ids), size):
            part = ids[start:start + size]
            out.extend(self.query(sql.format(ids=_marks(len(part))), (*before, *part, *after)))
        return out

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
            self._replace(
                db, "documents",
                ("id", "class", "uri", "title", "source_datetime", "metadata", "text", "content_hash", "ingested_at"),
                ("id",),
                [(doc["id"], doc["class"], doc.get("uri"), doc.get("title"), doc.get("source_datetime"),
                  json.dumps(doc.get("metadata") or {}, default=str), doc["text"], doc.get("content_hash"), _now())],
            )
            db.executemany(
                'insert into passages (document_id, n, start, "end", speaker, said_at) values (?,?,?,?,?,?)',
                [(doc["id"], p["n"], p["start"], p["end"], p.get("speaker"), p.get("said_at")) for p in passages],
            )
            db.executemany(
                "insert into chunks (id, document_id, n, first_passage, last_passage, text, situation) "
                "values (?,?,?,?,?,?,?)",
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
            n = db.execute("select count(*) as n from revisions where document_id = ?", (document_id,)).fetchone()["n"]
            db.execute("insert into revisions (document_id, n, text, metadata, source_datetime, saved_at) "
                       "values (?,?,?,?,?,?)",
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

    def document_row(self, document_id: str) -> Any | None:
        """A document's id, class, uri, title, source_datetime, metadata (JSON), and ingested_at, without its text."""
        return self.one("select id, class, uri, title, source_datetime, metadata, ingested_at from documents "
                        "where id = ?", (document_id,))

    def revision_count(self, document_id: str) -> int:
        """How many earlier versions of a document are kept."""
        return int(self.one("select count(*) as n from revisions where document_id = ?", (document_id,))["n"])

    def document_rows(self, ids: list[str]) -> list[Any]:
        """Whole document rows, text included, for these ids (in no set order)."""
        return self._in("select * from documents where id in ({ids})", ids)

    def all_document_ids(self) -> list[str]:
        return [r["id"] for r in self.query("select id from documents order by ingested_at, id")]

    def chunk_row(self, chunk_id: str) -> Any | None:
        return self.one("select * from chunks where id = ?", (chunk_id,))

    def documents_mentioning(self, entity_id: str) -> list[str]:
        """The documents with a fact linked to this entity."""
        return [r["document_id"] for r in self.query(
            "select distinct f.document_id from facts f join mentions m on m.fact_id = f.id where m.entity_id = ?",
            (entity_id,))]

    def standing_facts(self, document_id: str) -> dict[str, str]:
        """A document's facts that still stand (current or contradicted), as ids by text."""
        rows = self.query(f"select id, text from facts where document_id = ? and status in {STANDING} order by rowid",
                          (document_id,))
        return {row["text"]: row["id"] for row in rows}

    def replace_fact(self, fact_id: str, by: str | None, reason: str) -> None:
        """A newer version of the fact's document no longer states it: changed (`by` the fact that says it now) or
        dropped. Apart from `retracted`, which a person sets."""
        with self.tx() as db:
            db.execute("update facts set status = 'replaced', updated_at = ? where id = ?", (_now(), fact_id))
            self.event(db, "fact.replaced", fact_id, reason=reason, **({"by": by} if by else {}))
            if by:
                self._replace(db, "relations", ("fact_id", "other_id", "relation", "at"),
                              ("fact_id", "other_id", "relation"), [(by, fact_id, "replaces", _now())])

    # -- facts ----------------------------------------------------------------------------------------------

    def save_fact(self, row: dict[str, Any], quotes: list[dict[str, Any]], mentions: list[dict[str, Any]]) -> None:
        stamp = _now()
        with self.tx() as db:
            before = db.execute("select created_at from facts where id = ?", (row["id"],)).fetchone()
            self._replace(
                db, "facts",
                ("id", "class", "text", "document_id", "chunk_id", "status", "traits", "trait_scores", "valid_from",
                 "expires", "valid_until", "lifetime", "source_datetime", "extracted_at", "scores", "fingerprint",
                 "created_at", "updated_at"),
                ("id",),
                [(row["id"], row["class"], row["text"], row["document_id"], row.get("chunk_id"),
                  row.get("status", "current"), json.dumps(row.get("traits") or []),
                  json.dumps(row.get("trait_scores") or {}), row.get("valid_from"), row.get("expires"),
                  row.get("valid_until"), json.dumps(row.get("lifetime")) if row.get("lifetime") else None,
                  row.get("source_datetime"), row["extracted_at"], json.dumps(row.get("scores") or {}),
                  row.get("fingerprint"), before["created_at"] if before else stamp, stamp)],
            )
            db.execute("update facts set revision = (select count(*) from revisions where document_id = ?) "
                       "where id = ?", (row["document_id"], row["id"]))
            db.execute("delete from quotes where fact_id = ?", (row["id"],))
            db.execute("delete from mentions where fact_id = ?", (row["id"],))
            self._write_quotes(db, row["id"], quotes)
            db.executemany(
                f"insert into mentions ({', '.join(_MENTION_COLUMNS)}) values ({_marks(len(_MENTION_COLUMNS))})",
                [(row["id"], m["text"], m.get("kind"), m.get("role", "about"), m.get("entity_id"), m.get("method"),
                  m.get("confidence")) for m in mentions],
            )
            restated = row.get("restated")
            self.event(db, "fact.restated" if restated else "fact.added", row["id"], text=row["text"],
                       document=row["document_id"], **({"reason": restated} if restated else {}))
            for m in mentions:
                if m.get("entity_id"):
                    self.event(db, "entity.linked", m["entity_id"], fact=row["id"], method=m.get("method"))

    def _write_quotes(self, db: Any, fact_id: str, quotes: list[dict[str, Any]]) -> None:
        db.executemany(
            f"insert into quotes ({', '.join(_QUOTE_COLUMNS)}) values ({_marks(len(_QUOTE_COLUMNS))})",
            [(fact_id, q["document_id"], q["passage_n"], q["start"], q["end"], q["text"], q.get("speaker"),
              q.get("said_at"), q.get("section"), json.dumps(q["attrs"]) if q.get("attrs") else None)
             for q in quotes],
        )

    def add_quotes(self, fact_id: str, quotes: list[dict[str, Any]]) -> None:
        """Add quotes to a stored fact, as when a duplicate confirms it. Writes no event."""
        with self.tx() as db:
            self._write_quotes(db, fact_id, quotes)

    def add_mentions(self, mentions: list[dict[str, Any]]) -> None:
        """Add linked mentions to stored facts (each dict has `fact_id`, `text`, `kind`, `role`, `entity_id`,
        `method`, and `confidence`), with an `entity.linked` event each, in one transaction."""
        with self.tx() as db:
            for m in mentions:
                db.execute(
                    f"insert into mentions ({', '.join(_MENTION_COLUMNS)}) values ({_marks(len(_MENTION_COLUMNS))})",
                    (m["fact_id"], m["text"], m.get("kind"), m.get("role", "about"), m["entity_id"], m.get("method"),
                     m.get("confidence")))
                self.event(db, "entity.linked", m["entity_id"], fact=m["fact_id"], method=m.get("method"))

    def set_status(self, fact_id: str, status: str, event: str, **data: Any) -> None:
        with self.tx() as db:
            db.execute("update facts set status = ?, updated_at = ? where id = ?", (status, _now(), fact_id))
            self.event(db, f"fact.{event}", fact_id, **data)

    def set_fields(self, fact_id: str, **fields: Any) -> None:
        if not fields:
            return
        if not all(name.isidentifier() for name in fields):
            raise ValueError(f"not column names: {sorted(fields)}")
        cols = ", ".join(f"{name} = ?" for name in fields)
        with self.tx() as db:
            db.execute(f"update facts set {cols}, updated_at = ? where id = ?", (*fields.values(), _now(), fact_id))
            self.event(db, "fact.updated", fact_id, **fields)

    def relate(self, fact_id: str, other_id: str, relation: str) -> None:
        with self.tx() as db:
            self._insert_ignore(db, "relations", ("fact_id", "other_id", "relation", "at"),
                                [(fact_id, other_id, relation, _now())])

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
            # A pair settled before and contradicted again keeps one `settled` row, the newer one.
            db.execute(f"delete from relations where relation = 'settled' and {pair}", ids)
            db.execute(f"update relations set relation = 'settled', at = ? where relation = 'contradicts' and {pair}",
                       (_now(), *ids))
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

    def fact_row(self, fact_id: str) -> Any | None:
        return self.one("select * from facts where id = ?", (fact_id,))

    def fact_rows(self, ids: list[str]) -> list[Any]:
        """Whole fact rows for these ids (in no set order)."""
        return self._in("select * from facts where id in ({ids})", ids)

    def quotes(self, fact_id: str) -> list[Any]:
        return self.query("select * from quotes where fact_id = ? order by passage_n, rowid", (fact_id,))

    def mentions(self, fact_id: str) -> list[Any]:
        return self.query("select * from mentions where fact_id = ? order by rowid", (fact_id,))

    def quotes_of(self, fact_ids: list[str]) -> list[Any]:
        """The quotes of these facts, in the order they were saved."""
        rows = self._in("select *, rowid as _n from quotes where fact_id in ({ids})", fact_ids)
        return sorted(rows, key=lambda r: r["_n"])

    def mentions_of(self, fact_ids: list[str]) -> list[Any]:
        """The mentions of these facts, in the order they were saved."""
        rows = self._in("select *, rowid as _n from mentions where fact_id in ({ids})", fact_ids)
        return sorted(rows, key=lambda r: r["_n"])

    def relations(self, fact_id: str) -> list[Any]:
        return self.query("select * from relations where fact_id = ? or other_id = ? order by rowid",
                          (fact_id, fact_id))

    def contradiction_relations(self) -> list[Any]:
        """Every `contradicts` relation, newest first."""
        return self.query("select * from relations where relation = 'contradicts' order by at desc, rowid desc")

    def events_for(self, subject: str) -> list[Any]:
        return self.query("select * from events where subject = ? order by seq", (subject,))

    def events_after(self, after: int = 0, *, until: int | None = None, limit: int | None = None) -> list[Any]:
        """Events with seq after `after` (and up to `until`), oldest first: seq, at, type, subject, and data (JSON)."""
        sql, params = "select seq, at, type, subject, data from events where seq > ?", [int(after)]
        if until is not None:
            sql += " and seq <= ?"
            params.append(int(until))
        sql += " order by seq"
        if limit is not None:
            sql += " limit ?"
            params.append(int(limit))
        return self.query(sql, params)

    def fact_ids(self, *, document_id: str | None = None, status: str | None = None,
                 classes: list[str] | None = None) -> list[str]:
        """Fact ids, in the order they were saved, by document, status, and class names."""
        if classes is not None and not classes:
            return []
        sql, params = "select id from facts where 1 = 1", []
        if classes is not None:
            sql += f" and class in ({_marks(len(classes))})"
            params += classes
        if document_id:
            sql += " and document_id = ?"
            params.append(document_id)
        if status:
            sql += " and status = ?"
            params.append(status)
        return [r["id"] for r in self.query(sql + " order by rowid", params)]

    def all_fact_ids(self) -> list[str]:
        return [r["id"] for r in self.query("select id from facts order by created_at, id")]

    def standing_fact_ids_about(self, entity_ids: list[str], *, outside: str) -> list[str]:
        """Facts that still stand, from documents other than `outside`, linked to any of these entities."""
        if not entity_ids:
            return []
        return [r["id"] for r in self.query(
            f"select f.id from facts f join mentions m on m.fact_id = f.id where m.entity_id in "
            f"({_marks(len(entity_ids))}) and f.document_id != ? and f.status in {STANDING} "
            "group by f.id order by min(m.rowid)",
            (*entity_ids, outside))]

    def fact_ids_about(self, entity_id: str, *, role: str | None = None, include_retired: bool = False,
                       since: str | None = None) -> list[str]:
        """Facts linked to an entity, newest first (by valid_from, source date, or extraction time)."""
        sql = "select f.id, max(coalesce(f.valid_from, f.source_datetime, f.extracted_at)) as t " \
              "from facts f join mentions m on m.fact_id = f.id where m.entity_id = ?"
        params: list[Any] = [entity_id]
        if role:
            sql += " and m.role = ?"
            params.append(role)
        if not include_retired:
            sql += f" and f.status in {STANDING}"
        if since:
            sql += " and coalesce(f.valid_from, f.source_datetime, f.extracted_at) >= ?"
            params.append(since)
        sql += " group by f.id order by t desc, f.id"
        return [r["id"] for r in self.query(sql, params)]

    def linked_fact_ids(self, entity_id: str) -> list[str]:
        """Every fact with a mention linked to this entity."""
        return [r["fact_id"] for r in self.query(
            "select fact_id from mentions where entity_id = ? group by fact_id order by min(rowid)", (entity_id,))]

    def unlinked_fact_ids(self, since: str | None = None) -> list[str]:
        """Facts that still stand and have a mention linked to no entity."""
        sql = ("select f.id from facts f join mentions m on m.fact_id = f.id "
               f"where m.entity_id is null and f.status in {STANDING}")
        params: list[Any] = []
        if since:
            sql += " and f.extracted_at >= ?"
            params.append(since)
        return [r["id"] for r in self.query(sql + " group by f.id order by min(m.rowid)", params)]

    def co_mentions(self, entity_id: str) -> list[Any]:
        """(other, fact_id) for each other entity linked in a fact that still stands with this one."""
        return self.query(
            "select m2.entity_id as other, f.id as fact_id from mentions m1 join mentions m2 "
            "on m1.fact_id = m2.fact_id and m2.entity_id != m1.entity_id join facts f on f.id = m1.fact_id "
            f"where m1.entity_id = ? and m2.entity_id is not null and f.status in {STANDING} order by m2.rowid",
            (entity_id,))

    def fact_list(self, *, status: str = "current", document: str | None = None, trait: str | None = None,
                  limit: int = 0) -> list[Any]:
        """Facts in the order they were added, with their document's title and uri. `status` is one status or `all`;
        `document` is a document's id, title, uri, or file name; `limit` 0 means every fact."""
        sql = ("select f.id, f.class, f.text, f.status, f.traits, f.document_id, d.title, d.uri from facts f "
               "left join documents d on d.id = f.document_id where 1 = 1")
        params: list[Any] = []
        if status != "all":
            sql += " and f.status = ?"
            params.append(status)
        if document:
            sql += " and (d.id = ? or d.title = ? or d.uri = ? or lower(d.uri) like lower(?))"
            params += [document, document, document, f"%/{document}"]
        if trait:
            sql += f" and {self._has_trait('f.traits')}"
            params.append(trait)
        sql += " order by f.created_at, f.rowid"
        if limit:
            sql += " limit ?"
            params.append(int(limit))
        return self.query(sql, params)

    def sample_facts(self) -> list[Any]:
        """Current facts of readable length (60 to 220 characters), those with a trait first: class, text,
        document_id, and traits."""
        return self.query("select class, text, document_id, traits from facts where status = 'current' "
                          "and length(text) between 60 and 220 order by traits = '[]', document_id, id")

    def counts(self) -> dict[str, Any]:
        """The counts `Factoid.stats` reports that come straight from the store."""
        q = self.query
        live = "status in ('current', 'contradicted', 'superseded', 'ended')"
        return {
            "documents": q("select count(*) as n from documents")[0]["n"],
            "documents_by_class": {r["class"]: r["n"] for r in q(
                "select class, count(*) as n from documents group by class order by n desc, class")},
            "facts": {r["status"]: r["n"] for r in q(
                "select status, count(*) as n from facts group by status order by status")},
            "facts_by_class": {r["class"]: r["n"] for r in q(
                f"select class, count(*) as n from facts where {live} group by class order by n desc, class")},
            "entities_by_class": {r["class"]: r["n"] for r in q(
                "select class, count(*) as n from entities where merged_into is null group by class "
                "order by n desc, class")},
            "facts_with_no_trait": q(f"select count(*) as n from facts where status in {STANDING} "
                                     "and traits = '[]'")[0]["n"],
            "unlinked_mentions": q("select count(*) as n from mentions where entity_id is null")[0]["n"],
            "entities": q("select count(*) as n from entities where merged_into is null")[0]["n"],
            "single_fact_entities": q(
                "select count(*) as n from (select entity_id from mentions where entity_id is not null "
                "group by entity_id having count(distinct fact_id) = 1) as single")[0]["n"],
        }

    # -- entities -------------------------------------------------------------------------------------------

    def save_entity(self, row: dict[str, Any], keys: dict[str, str]) -> None:
        with self.tx() as db:
            self._replace(
                db, "entities", ("id", "class", "kind", "name", "aliases", "props", "created_at"), ("id",),
                [(row["id"], row["class"], row.get("kind"), row["name"], json.dumps(row.get("aliases") or []),
                  json.dumps(row.get("props") or {}, default=str), row.get("created_at") or _now())],
            )
            self._insert_ignore(db, "entity_keys", ("key", "value", "entity_id"),
                                [(key, _norm(value), row["id"]) for key, value in keys.items()])
            self.event(db, "entity.created", row["id"], name=row["name"], cls=row["class"], kind=row.get("kind"))

    def entity_by_key(self, key: str, value: str) -> str | None:
        row = self.one("select entity_id from entity_keys where key = ? and value = ?", (key, _norm(value)))
        return row["entity_id"] if row else None

    def entities_named(self, name: str) -> list[Any]:
        name = _norm(name)
        rows = self.query("select * from entities where merged_into is null and lower(name) = ? order by rowid",
                          (name,))
        if rows:
            return rows
        return [r for r in self.query("select * from entities where merged_into is null and lower(aliases) like ? "
                                      "order by rowid", (f"%{name}%",))
                if name in [_norm(a) for a in json.loads(r["aliases"])]]

    def entity_row(self, entity_id: str) -> Any | None:
        row = self.one("select * from entities where id = ?", (entity_id,))
        while row is not None and row["merged_into"]:
            row = self.one("select * from entities where id = ?", (row["merged_into"],))
        return row

    def entity_rows(self, ids: list[str]) -> list[Any]:
        """Whole entity rows for these ids, merged ones included (in no set order)."""
        return self._in("select * from entities where id in ({ids})", ids)

    def all_entity_ids(self) -> list[str]:
        return [r["id"] for r in self.query("select id from entities order by created_at, id")]

    def entities_of_classes(self, class_names: list[str]) -> list[Any]:
        """id and props (JSON) of every unmerged entity of these classes."""
        if not class_names:
            return []
        return self.query(f"select id, props from entities where merged_into is null and class in "
                          f"({_marks(len(class_names))}) order by rowid", class_names)

    def entity_list(self, *, class_name: str | None = None, name: str | None = None, by: str = "facts",
                    limit: int = 0) -> list[Any]:
        """Unmerged entities with how many facts each is linked to: id, class, kind, name, aliases (JSON), and facts.
        `name` matches part of a name or another name. `by` orders them: `facts` (most first) or `name`."""
        sql = ("select e.id, e.class, e.kind, e.name, e.aliases, count(distinct m.fact_id) as facts from entities e "
               "left join mentions m on m.entity_id = e.id where e.merged_into is null")
        params: list[Any] = []
        if class_name:
            sql += " and e.class = ?"
            params.append(class_name)
        if name:
            sql += " and (lower(e.name) like ? or lower(e.aliases) like ?)"
            params += [f"%{name.lower()}%"] * 2
        sql += " group by e.id" + (" order by e.name, e.id" if by == "name" else " order by facts desc, e.name, e.id")
        if limit:
            sql += " limit ?"
            params.append(int(limit))
        return self.query(sql, params)

    def kind_counts(self) -> list[Any]:
        """Untyped entities by kind: kind, entities, and facts, most facts first."""
        return self.query(
            "select e.kind, count(distinct e.id) as entities, count(distinct m.fact_id) as facts from entities e "
            "left join mentions m on m.entity_id = e.id where e.class = 'Entity' and e.merged_into is null "
            "group by e.kind order by facts desc, e.kind")

    def top_entities(self) -> list[Any]:
        """Unmerged entities with how many facts each is linked to, most first: class, name, and n."""
        return self.query("select e.class, e.name, count(distinct m.fact_id) as n from entities e join mentions m "
                          "on m.entity_id = e.id where e.merged_into is null group by e.id order by n desc, e.name")

    def add_alias(self, entity_id: str, alias: str) -> None:
        with self.tx() as db:
            row = self.entity_row(entity_id)  # read inside the transaction, so two writers cannot lose an alias
            if row is None:
                return
            aliases = json.loads(row["aliases"])
            if _norm(alias) != _norm(row["name"]) and _norm(alias) not in [_norm(a) for a in aliases]:
                aliases.append(alias)
                db.execute("update entities set aliases = ? where id = ?", (json.dumps(aliases), entity_id))
                self.event(db, "entity.aliased", entity_id, alias=alias)

    def save_entity_key(self, key: str, value: str, entity_id: str) -> None:
        with self.tx() as db:
            self._insert_ignore(db, "entity_keys", ("key", "value", "entity_id"), [(key, _norm(value), entity_id)])

    def merge_entities(self, keep: str, gone: str, reason: str) -> list[str]:
        """Fold `gone` into `keep`: its mentions, keys, and names. Returns the ids of the facts that moved."""
        with self.tx() as db:
            facts = [r["fact_id"] for r in db.execute("select distinct fact_id from mentions where entity_id = ?",
                                                      (gone,)).fetchall()]
            db.execute("update entities set merged_into = ? where id = ?", (keep, gone))
            db.execute("update mentions set entity_id = ? where entity_id = ?", (keep, gone))
            db.execute("update entity_keys set entity_id = ? where entity_id = ?", (keep, gone))
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
                f"({_marks(len(fact_ids))})", (source, *fact_ids)).fetchall()] if fact_ids else []
            for fact_id in moved:
                db.execute("update mentions set entity_id = ? where entity_id = ? and fact_id = ?",
                           (target, source, fact_id))
            self.event(db, "entity.split", source, into=target, facts=moved, reason=reason)
            return moved

    # -- export cursors ---------------------------------------------------------------------------------------

    def last_event(self) -> int:
        row = self.one("select max(seq) as seq from events")
        return int(row["seq"] or 0) if row else 0

    def cursor(self, name: str) -> int:
        """The last event an export was sent, or 0 for one never run."""
        row = self.one("select seq from export_cursors where name = ?", (name,))
        return int(row["seq"]) if row else 0

    def set_cursor(self, name: str, seq: int) -> None:
        """Move an export's cursor. It only moves forward, so a slower run that finishes last cannot move it back."""
        with self.tx() as db:
            row = db.execute("select seq from export_cursors where name = ?", (name,)).fetchone()
            seq = max(int(seq), int(row["seq"])) if row else int(seq)
            self._replace(db, "export_cursors", ("name", "seq", "at"), ("name",), [(name, seq, _now())])

    @contextmanager
    def exporting(self, name: str) -> Iterator[None]:
        """Held while one export runs, so two runs of the same export in this process take turns."""
        with self._export_lock(name):
            yield

    def _export_lock(self, name: str) -> threading.Lock:
        where = str(self.path) if self.path is not None else id(self)
        with _EXPORT_LOCKS_LOCK:
            return _EXPORT_LOCKS.setdefault((where, name), threading.Lock())


_EXPORT_LOCKS: dict[tuple[Any, str], threading.Lock] = {}
_EXPORT_LOCKS_LOCK = threading.Lock()


def _marks(n: int) -> str:
    return ",".join("?" * n)


def _norm(value: str) -> str:
    return " ".join(str(value).lower().split())


def now_stamp() -> str:
    return _now()
