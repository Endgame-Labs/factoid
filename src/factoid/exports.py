"""Exports: where a project's facts go for other systems to use.

A project declares its exports by name in `settings.py`:

    from factoid.exports import Parquet, Turbopuffer

    class Project(Settings):
        exports = {
            "warehouse": Parquet("s3://bucket/facts/"),
            "search": Turbopuffer(namespace="acme-facts"),
        }

`factoid export` sends each export what changed since its cursor, the last event it was sent, read from the event log.
`--full` sends everything again. A superseded or retracted fact is sent again with its new status, never deleted.
Credentials come from the environment: AWS's usual variables and files for S3, and `TURBOPUFFER_API_KEY` or
`TURBOPUFFER_BASE_URL` for turbopuffer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["Batch", "Export", "ExportResult", "Parquet", "Turbopuffer", "changes", "export"]


@dataclass
class Batch:
    """What one run sends an export: the rows that changed between two events, as plain dicts."""

    start: int  # the export's cursor before this run; 0 for a first or full run
    end: int  # the last event included
    full: bool  # --full: the export replaces what it holds
    facts: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    vectors: dict[str, list[float]] = field(default_factory=dict)  # fact vectors by id, for exports that want them
    embedding_model: str = ""
    root: Any = None  # the project folder, which relative export paths are under

    def empty(self) -> bool:
        return not (self.facts or self.entities or self.documents or self.events)


@dataclass
class ExportResult:
    name: str
    batch: Batch
    skipped: bool = False  # nothing changed since the cursor


class Export:
    """A destination for facts. Subclasses implement `send`."""

    #: Whether `export` should look up each fact's vector for this export.
    wants_vectors: bool = False

    def send(self, batch: Batch) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        return type(self).__name__


# -- reading changes from the store ------------------------------------------------------------------------


def changes(app: Any, since: int, until: int, full: bool = False) -> Batch:
    """The facts, entities, documents, and events that changed after event `since`, up to event `until`.
    With `since` 0, everything. `full` marks a batch that replaces what the export holds."""
    store = app.store
    events = [dict(r) for r in store.events_after(since, until=until)]
    if since == 0:
        fact_ids, entity_ids, document_ids = store.all_fact_ids(), store.all_entity_ids(), store.all_document_ids()
    else:
        facts: dict[str, None] = {}
        entities: dict[str, None] = {}
        documents: dict[str, None] = {}
        for event in events:
            kind, subject = event["type"], event["subject"]
            data = json.loads(event["data"] or "{}")
            if kind.startswith("fact."):
                facts[subject] = None
            elif kind.startswith("entity."):
                entities[subject] = None
                if kind == "entity.linked" and data.get("fact"):
                    facts[data["fact"]] = None
                if kind == "entity.merged":
                    if data.get("merged"):
                        entities[data["merged"]] = None
                    # The merge moved mentions to the kept entity, so its facts changed too.
                    for fact_id in store.linked_fact_ids(subject):
                        facts[fact_id] = None
            elif kind.startswith("document."):
                documents[subject] = None
        fact_ids, entity_ids, document_ids = list(facts), list(entities), list(documents)
    batch = Batch(start=since, end=until, full=full, events=[_event_row(e) for e in events])
    batch.facts = _fact_rows(store, fact_ids)
    batch.entities = _rows(store.entity_rows, entity_ids, _entity_row)
    batch.documents = _rows(store.document_rows, document_ids, _document_row)
    return batch


def _rows(read: Any, ids: list[str], shape: Any) -> list[dict[str, Any]]:
    out = []
    for part in _parts(ids):
        by_id = {r["id"]: r for r in read(part)}
        out.extend(shape(by_id[i]) for i in part if i in by_id)
    return out


def _parts(ids: list[str], size: int = 500) -> list[list[str]]:
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def _fact_rows(store: Any, ids: list[str]) -> list[dict[str, Any]]:
    out = []
    for part in _parts(ids):
        rows = {r["id"]: r for r in store.fact_rows(part)}
        mentions: dict[str, list[dict[str, Any]]] = {}
        for m in store.mentions_of(part):
            mentions.setdefault(m["fact_id"], []).append(
                {"entity_id": m["entity_id"], "role": m["role"], "text": m["text"], "kind": m["kind"]})
        quotes: dict[str, list[dict[str, Any]]] = {}
        for q in store.quotes_of(part):
            quotes.setdefault(q["fact_id"], []).append(
                {"document_id": q["document_id"], "passage": q["passage_n"], "section": q["section"],
                 "text": q["text"] or None})  # None when the store keeps no document text
        for id_ in part:
            row = rows.get(id_)
            if row is None:
                continue
            traits = json.loads(row["traits"] or "[]")
            out.append({
                "id": row["id"], "class": row["class"], "text": row["text"], "status": row["status"],
                "document_id": row["document_id"], "chunk_id": row["chunk_id"],
                "traits": traits if isinstance(traits, list) else list(traits),
                "trait_scores": row["trait_scores"], "valid_from": _time(row["valid_from"]),
                "expires": row["expires"], "valid_until": _time(row["valid_until"]), "lifetime": row["lifetime"],
                "source_datetime": _time(row["source_datetime"]), "extracted_at": _time(row["extracted_at"]),
                "created_at": _time(row["created_at"]), "updated_at": _time(row["updated_at"]),
                "entity_ids": sorted({m["entity_id"] for m in mentions.get(id_, []) if m["entity_id"]}),
                "mentions": mentions.get(id_, []), "quotes": quotes.get(id_, []),
            })
    return out


def _entity_row(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "class": row["class"], "kind": row["kind"], "name": row["name"],
            "aliases": json.loads(row["aliases"] or "[]"), "props": row["props"],
            "created_at": _time(row["created_at"]), "merged_into": row["merged_into"]}


def _document_row(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "class": row["class"], "uri": row["uri"], "title": row["title"],
            "source_datetime": _time(row["source_datetime"]), "metadata": row["metadata"], "text": row["text"] or None,
            "ingested_at": _time(row["ingested_at"])}


def _event_row(row: dict[str, Any]) -> dict[str, Any]:
    return {"seq": row["seq"], "at": _time(row["at"]), "type": row["type"], "subject": row["subject"],
            "data": row["data"]}


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    from .dates import parse_datetime

    return parse_datetime(value)


# -- running an export ------------------------------------------------------------------------------------


def export(app: Any, exports: dict[str, Export], names: list[str] | None = None,
           full: bool = False) -> list[ExportResult]:
    """Send each named export (or every export) what changed since its cursor, and move the cursor once it is sent.
    An export that fails keeps its cursor, so the next run sends the same changes again."""
    chosen = names or list(exports)
    unknown = [n for n in chosen if n not in exports]
    if unknown:
        raise KeyError(f"unknown exports {unknown}; settings.py declares {sorted(exports)}")
    results = []
    for name in chosen:
        # Two runs of one export (two processes, say) take turns, so the second sends only what the first did not.
        with app.store.exporting(name):
            results.append(_export_one(app, name, exports[name], full))
    return results


def _export_one(app: Any, name: str, target: Export, full: bool) -> ExportResult:
    until = app.store.last_event()
    since = 0 if full else app.store.cursor(name)
    if since >= until and not full:
        return ExportResult(name, Batch(start=since, end=until, full=False), skipped=True)
    batch = changes(app, since, until, full)
    batch.root = getattr(app, "root", None)
    if target.wants_vectors and batch.facts:
        batch.vectors, batch.embedding_model = _vectors(app, batch.facts)
    target.send(batch)
    app.store.set_cursor(name, until)
    return ExportResult(name, batch)


def _vectors(app: Any, facts: list[dict[str, Any]]) -> tuple[dict[str, list[float]], str]:
    """Each fact's vector from the search index, embedding any the index does not hold."""
    ids = [f["id"] for f in facts]
    found = app.index.vectors(app.ns("facts"), ids)
    missing = [f for f in facts if f["id"] not in found]
    for part in [missing[i:i + 100] for i in range(0, len(missing), 100)]:
        for fact, vector in zip(part, app.client.embed([f["text"] for f in part])):
            found[fact["id"]] = list(vector)
    model = app.settings.all_models().get("embed")
    return found, model.name if model is not None else ""


# -- Parquet -----------------------------------------------------------------------------------------------


class Parquet(Export):
    """Parquet files in a local folder or on S3 (`s3://bucket/path/`): `facts`, `entities`, `documents`, and `events`.
    A relative folder is under the project folder. For an S3-compatible store such as R2 or MinIO, set
    `AWS_ENDPOINT_URL`; `AWS_PROFILE` picks a profile.

    Each run writes one file per table that changed, named by the events it covers, such as
    `facts/0000000041-0000000097.parquet`. A row that changed again appears in a later file, so the current version
    of a fact or entity is its row with the highest `exported_through`. `--full` removes this export's earlier files and
    writes every row again. Mentions and quotes are nested list columns in `facts`. With `vectors=True`, `facts` also
    gets `vector` (a list of 32-bit floats) and `embedding_model`.
    """

    def __init__(self, path: str, vectors: bool = False):
        self.path = path.rstrip("/")
        self.wants_vectors = vectors

    def describe(self) -> str:
        return f"Parquet({self.path})"

    def send(self, batch: Batch) -> None:
        pa, pq, fs, root = self._open(batch.root)
        tables = {"facts": batch.facts, "entities": batch.entities, "documents": batch.documents,
                  "events": batch.events}
        for table, rows in tables.items():
            folder = f"{root}/{table}"
            if batch.full:
                _clear(fs, folder)
            if not rows:
                continue
            fs.create_dir(folder, recursive=True)
            if table != "events":
                rows = [{**r, "exported_through": batch.end} for r in rows]
            if table == "facts" and self.wants_vectors:
                rows = [{**r, "vector": batch.vectors.get(r["id"]), "embedding_model": batch.embedding_model}
                        for r in rows]
            data = pa.Table.from_pylist(rows, schema=_schema(pa, table, self.wants_vectors))
            pq.write_table(data, f"{folder}/{batch.start:010d}-{batch.end:010d}.parquet", filesystem=fs)

    def _open(self, project_root: Any = None) -> tuple[Any, Any, Any, str]:
        try:
            import pyarrow as pa
            import pyarrow.fs as pafs
            import pyarrow.parquet as pq
        except ImportError as err:
            raise RuntimeError("the Parquet export needs pyarrow: install factoid[parquet], or add pyarrow to the "
                               "project's dependencies") from err
        if "://" in self.path:
            fs, root = pafs.FileSystem.from_uri(self.path)
        else:
            from pathlib import Path

            local = Path(self.path).expanduser()
            if not local.is_absolute() and project_root is not None:
                local = Path(project_root) / local
            local = local.resolve()
            fs, root = pafs.LocalFileSystem(), str(local)
        return pa, pq, fs, root


def _clear(fs: Any, folder: str) -> None:
    """Remove the Parquet files this export wrote in one table's folder, and nothing else."""
    import pyarrow.fs as pafs

    for info in fs.get_file_info(pafs.FileSelector(folder, allow_not_found=True)):
        name = info.path.rsplit("/", 1)[-1]
        if info.type == pafs.FileType.File and name.endswith(".parquet") and name[:10].isdigit():
            fs.delete_file(info.path)


def _schema(pa: Any, table: str, vectors: bool) -> Any:
    ts = pa.timestamp("us", tz="UTC")
    text = pa.string()
    if table == "facts":
        mention = pa.struct([("entity_id", text), ("role", text), ("text", text), ("kind", text)])
        quote = pa.struct([("document_id", text), ("passage", pa.int64()), ("section", text), ("text", text)])
        fields = [("id", text), ("class", text), ("text", text), ("status", text), ("document_id", text),
                  ("chunk_id", text), ("traits", pa.list_(text)), ("trait_scores", text), ("valid_from", ts),
                  ("expires", text), ("valid_until", ts), ("lifetime", text), ("source_datetime", ts),
                  ("extracted_at", ts), ("created_at", ts), ("updated_at", ts), ("entity_ids", pa.list_(text)),
                  ("mentions", pa.list_(mention)), ("quotes", pa.list_(quote)), ("exported_through", pa.int64())]
        if vectors:
            fields += [("vector", pa.list_(pa.float32())), ("embedding_model", text)]
    elif table == "entities":
        fields = [("id", text), ("class", text), ("kind", text), ("name", text), ("aliases", pa.list_(text)),
                  ("props", text), ("created_at", ts), ("merged_into", text), ("exported_through", pa.int64())]
    elif table == "documents":
        fields = [("id", text), ("class", text), ("uri", text), ("title", text), ("source_datetime", ts),
                  ("metadata", text), ("text", text), ("ingested_at", ts), ("exported_through", pa.int64())]
    else:
        fields = [("seq", pa.int64()), ("at", ts), ("type", text), ("subject", text), ("data", text)]
    return pa.schema(fields)


# -- turbopuffer -------------------------------------------------------------------------------------------


class Turbopuffer(Export):
    """A turbopuffer namespace, or one on a turbopuffer-compatible service, for an app to search.

    One row per fact, keyed by its id: its vector, `text` (with a BM25 index), `class`, `traits`, `status`,
    `valid_from`, `valid_until`, `document_id`, and `entity_ids`. This is separate from the index Factoid searches
    itself. `--full` deletes the namespace and writes every fact again.
    """

    wants_vectors = True

    def __init__(self, namespace: str, base_url: str | None = None):
        self.namespace = namespace
        self.base_url = base_url

    def describe(self) -> str:
        return f"Turbopuffer({self.namespace})"

    def _client(self) -> Any:
        from .search import Turbopuffer as Client

        return Client(base_url=self.base_url)

    def send(self, batch: Batch) -> None:
        client = self._client()
        path = f"/v2/namespaces/{self.namespace}"
        if batch.full:
            response = client._http.delete(f"{client.base_url}{path}", headers=client._headers())
            if response.status_code not in (200, 202, 404):
                raise RuntimeError(f"turbopuffer delete {self.namespace}: HTTP {response.status_code}: "
                                   f"{response.text[:300]}")
        rows = [self.row(fact, batch.vectors.get(fact["id"])) for fact in batch.facts]
        for start in range(0, len(rows), 200):
            client._post(path, {"upsert_rows": rows[start:start + 200], "distance_metric": "cosine_distance",
                                "schema": TURBOPUFFER_SCHEMA})

    @staticmethod
    def row(fact: dict[str, Any], vector: list[float] | None) -> dict[str, Any]:
        if vector is None:
            raise RuntimeError(f"no vector for fact {fact['id']}")
        return {"id": fact["id"], "vector": list(vector), "text": fact["text"], "class": fact["class"],
                "traits": fact["traits"], "status": fact["status"], "valid_from": _iso(fact["valid_from"]),
                "valid_until": _iso(fact["valid_until"]), "document_id": fact["document_id"],
                "entity_ids": fact["entity_ids"]}


#: Types for the attributes turbopuffer cannot infer from a first row, such as an empty list or a missing date.
TURBOPUFFER_SCHEMA = {
    "text": {"type": "string", "full_text_search": True},
    "traits": {"type": "[]string"},
    "entity_ids": {"type": "[]string"},
    "valid_from": {"type": "datetime"},
    "valid_until": {"type": "datetime"},
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    from .dates import format_datetime

    return format_datetime(value)
