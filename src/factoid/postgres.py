"""The system of record in Postgres, for many processes writing at once or a hosted deployment.

    from factoid.stores import Postgres

    class Project(Settings):
        store = Postgres()  # the URL comes from FACTOID_POSTGRES_URL, or libpq's PGHOST, PGUSER, PGPASSWORD, ...

Install it with `factoid[postgres]` (psycopg 3). `PostgresStore` has the same methods as the SQLite `Store` and keeps
the same tables, in one Postgres schema per project (`factoid` unless the setting names another).

Many writers at once: every write transaction first takes a transaction-level advisory lock for the schema, so writes
from all processes apply one at a time, as they do in SQLite. Writes are short (one fact, one entity, or one
document's rows; model calls happen outside them), so ingest from many processes still runs in parallel where the time
goes. Because events are numbered under that lock, an event with a lower `seq` always commits before one with a higher
`seq`, and an export that read up to event N never misses an event below N that committed later. Reads take no lock.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from .store import Store

__all__ = ["PostgresStore"]

_T = 'text collate "C"'  # byte order, as SQLite sorts text

SCHEMA = f"""
create table if not exists documents (
    id {_T} primary key, class {_T} not null, uri {_T}, title {_T}, source_datetime {_T}, metadata {_T},
    text {_T} not null, content_hash {_T}, ingested_at {_T} not null
);
create table if not exists revisions (
    document_id {_T} not null, n integer not null, text {_T} not null, metadata {_T}, source_datetime {_T},
    saved_at {_T} not null, primary key (document_id, n)
);
create table if not exists passages (
    document_id {_T} not null, n integer not null, start integer not null, "end" integer not null,
    speaker {_T}, said_at {_T}, primary key (document_id, n)
);
create table if not exists chunks (
    id {_T} primary key, document_id {_T} not null, n integer not null, first_passage integer not null,
    last_passage integer not null, text {_T} not null, situation {_T}
);
create index if not exists chunks_document on chunks(document_id);
create table if not exists facts (
    id {_T} primary key, class {_T} not null, text {_T} not null, document_id {_T} not null, chunk_id {_T},
    status {_T} not null default 'current', traits {_T} not null default '{{}}',
    trait_scores {_T} not null default '{{}}', valid_from {_T}, expires {_T}, valid_until {_T}, lifetime {_T},
    source_datetime {_T}, extracted_at {_T} not null, scores {_T} not null default '{{}}', fingerprint {_T},
    created_at {_T} not null, updated_at {_T} not null, revision integer,
    rowid bigint generated always as identity
);
create index if not exists facts_document on facts(document_id);
create index if not exists facts_status on facts(status);
create table if not exists quotes (
    fact_id {_T} not null, document_id {_T} not null, passage_n integer not null, start integer not null,
    "end" integer not null, text {_T} not null, speaker {_T}, said_at {_T}, section {_T}, attrs {_T},
    rowid bigint generated always as identity
);
create index if not exists quotes_fact on quotes(fact_id);
create table if not exists mentions (
    fact_id {_T} not null, text {_T} not null, kind {_T}, role {_T} not null default 'about', entity_id {_T},
    method {_T}, confidence double precision, rowid bigint generated always as identity
);
create index if not exists mentions_fact on mentions(fact_id);
create index if not exists mentions_entity on mentions(entity_id);
create table if not exists entities (
    id {_T} primary key, class {_T} not null, kind {_T}, name {_T} not null, aliases {_T} not null default '[]',
    props {_T} not null default '{{}}', created_at {_T} not null, merged_into {_T},
    rowid bigint generated always as identity
);
create index if not exists entities_name on entities(lower(name));
create table if not exists entity_keys (
    key {_T} not null, value {_T} not null, entity_id {_T} not null, primary key (key, value)
);
create table if not exists relations (
    fact_id {_T} not null, other_id {_T} not null, relation {_T} not null, at {_T} not null,
    rowid bigint generated always as identity, primary key (fact_id, other_id, relation)
);
create index if not exists relations_other on relations(other_id);
create table if not exists events (
    seq bigint generated always as identity primary key, at {_T} not null, type {_T} not null,
    subject {_T} not null, data {_T} not null default '{{}}'
);
create index if not exists events_subject on events(subject);
create table if not exists export_cursors (
    name {_T} primary key, seq bigint not null, at {_T} not null
);
"""

_SCHEMA_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def _sql(sql: str) -> str:
    """`?` placeholders to psycopg's `%s`. The framework's SQL has no `?` inside string literals."""
    return sql.replace("%", "%%").replace("?", "%s")


def _key(*parts: str) -> int:
    """A 64-bit advisory lock key for these names."""
    return int.from_bytes(hashlib.sha256(":".join(("factoid", *parts)).encode()).digest()[:8], "big", signed=True)


class _Db:
    """A psycopg connection that takes the `?` placeholders the store's SQL uses."""

    def __init__(self, conn: Any):
        self.conn = conn

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> Any:
        params = tuple(params) if params is not None else ()
        return self.conn.execute(_sql(sql), params) if params else self.conn.execute(sql)

    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        if rows:
            with self.conn.cursor() as cur:
                cur.executemany(_sql(sql), rows)


class PostgresStore(Store):
    """The store in a Postgres schema. One connection per process, shared by its threads under a lock."""

    def __init__(self, url: str = "", *, schema: str = "factoid"):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as err:
            raise RuntimeError("the Postgres store needs psycopg: install factoid[postgres], or add psycopg[binary] "
                               "to the project's dependencies") from err
        if not _SCHEMA_NAME.fullmatch(schema):
            raise ValueError(f"schema must be a lowercase name of letters, digits, and _; got {schema!r}")
        self.path = None
        self.url = url
        self.schema = schema
        self._lock = threading.RLock()
        self._write_key = _key("write", schema)
        self._conn = psycopg.connect(url, autocommit=True, row_factory=dict_row,
                                     application_name="factoid")
        self.db = _Db(self._conn)
        with self._conn.transaction():
            # Two processes creating the same tables at once would collide, so they take turns.
            self._conn.execute("select pg_advisory_xact_lock(%s)", (self._write_key,))
            self._conn.execute(f'create schema if not exists "{schema}"')
            self._conn.execute(f'set search_path to "{schema}"')
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def tx(self) -> Iterator[Any]:
        with self._lock, self._conn.transaction():
            self._conn.execute("select pg_advisory_xact_lock(%s)", (self._write_key,))
            yield self.db

    def query(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[Any]:
        with self._lock:
            return self.db.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any | None:
        with self._lock:
            return self.db.execute(sql, params).fetchone()

    def _replace(self, db: Any, table: str, columns: Iterable[str], key: Iterable[str],
                 rows: list[tuple[Any, ...]]) -> None:
        columns, key = tuple(columns), tuple(key)
        where = " and ".join(f"{k} = ?" for k in key)
        at = [columns.index(k) for k in key]
        db.executemany(f"delete from {table} where {where}", [tuple(row[i] for i in at) for row in rows])
        db.executemany(f"insert into {table} ({', '.join(columns)}) values ({','.join('?' * len(columns))})", rows)

    def _insert_ignore(self, db: Any, table: str, columns: Iterable[str], rows: list[tuple[Any, ...]]) -> None:
        columns = tuple(columns)
        db.executemany(f"insert into {table} ({', '.join(columns)}) values ({','.join('?' * len(columns))}) "
                       "on conflict do nothing", rows)

    def _has_trait(self, column: str) -> str:
        return f"{column}::jsonb @> jsonb_build_array(?::text)"

    @contextmanager
    def exporting(self, name: str) -> Iterator[None]:
        """Two runs of one export, in any processes, take turns: a session advisory lock on a connection of its own,
        so the store's shared connection stays free while a run waits."""
        import psycopg

        with self._export_lock(name), psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute("select pg_advisory_lock(%s)", (_key("export", self.schema, name),))
            try:
                yield
            finally:
                conn.execute("select pg_advisory_unlock(%s)", (_key("export", self.schema, name),))
