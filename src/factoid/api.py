"""Reads and writes as plain JSON-ready dicts, shared by `factoid serve` (HTTP) and `factoid mcp`.

Each function takes the project's app and returns lists and dicts of strings, numbers, and booleans, with dates as
ISO 8601 strings, so a server can send the result as it is.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from .runtime import stored_name

__all__ = ["NotFound", "contradictions", "entities", "entity", "fact", "facts", "ingest", "search", "settle", "stats"]


class NotFound(LookupError):
    """No fact, entity, or class by that name or id."""


def search(app: Any, query: str, *, about: str | None = None, as_of: str | None = None, top_k: int = 10,
           chunks: bool = False, min_score: float | None = None) -> list[dict[str, Any]]:
    """Facts that match `query`, best first. `about` limits them to one entity (a name, key, or id); `as_of` weights
    them by how likely each was still true on that date (a bare date is midnight UTC), and includes superseded facts
    that were true then."""
    entity = _entity(app, about) if about else None
    if as_of and len(as_of) == 10:  # a bare date, such as 2026-06-01, means midnight UTC
        as_of += "T00:00:00Z"
    top_k = max(1, min(int(top_k), 100))
    if chunks:
        return [_plain(r) for r in app.search_chunks(query, about=entity, top_k=top_k)]
    hits = app.search_facts(query, about=entity, as_of=as_of, top_k=top_k,
                            min_score=float(min_score) if min_score is not None else None)
    return [{**_fact(app, h.fact), "score": round(h.score, 6), "validity": round(h.validity, 4),
             "contradicted_by": h.contradiction_ids} for h in hits]


def fact(app: Any, fact_id: str) -> dict[str, Any]:
    """One fact with its quotes, mentions, relations to other facts, and history."""
    found = app.load_fact(fact_id)
    if found is None:
        raise NotFound(f"no fact {fact_id}")
    out = _fact(app, found)
    out["relations"] = [{"fact_id": r["fact_id"], "relation": r["relation"], "other_id": r["other_id"]}
                        for r in app.store.relations(found.id)]
    out["events"] = [{"seq": r["seq"], "at": r["at"], "type": r["type"], "data": json.loads(r["data"] or "{}")}
                     for r in app.store.events_for(found.id)]
    return out


def facts(app: Any, *, document: str | None = None, trait: str | None = None, status: str = "current",
          limit: int = 50) -> list[dict[str, Any]]:
    """Facts in the order they were added. `document` is a document's id, title, or file name; `status` is one
    status or `all`; `limit` 0 means every fact."""
    rows = app.store.fact_list(status=status, document=document, trait=trait, limit=limit)
    return [{"id": r["id"], "class": r["class"], "text": r["text"], "status": r["status"],
             "traits": json.loads(r["traits"] or "[]"),
             "document": {"id": r["document_id"], "title": r["title"], "uri": r["uri"]}}
            for r in rows]


def entities(app: Any, *, class_name: str | None = None, name: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
    """Entities with their fact counts, most facts first. `name` matches part of a name or another name."""
    rows = app.store.entity_list(class_name=class_name, name=name, limit=limit)
    return [{"id": r["id"], "class": r["class"], "kind": r["kind"], "name": r["name"],
             "aliases": json.loads(r["aliases"] or "[]"), "facts": r["facts"]} for r in rows]


def entity(app: Any, name_or_id: str, *, limit: int = 50) -> dict[str, Any]:
    """One entity (by id, key, name, or other name), its current facts, newest first, and the entities it appears
    with most."""
    found = _entity(app, name_or_id)
    out: dict[str, Any] = {"id": found.id, "class": stored_name(type(found)), "kind": found.kind,
                           "name": found.name, "aliases": list(found.aliases)}
    out["facts"] = [_fact(app, f) for f in app.entity_facts(found)[:limit]]
    out["related"] = [{"id": r["entity"].id, "name": r["entity"].name, "co_mentions": r["co_mentions"],
                       "weight": r["weight"]} for r in app.related_entities(found)[:20]]
    return out


def contradictions(app: Any, *, include_stale: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    """Open contradictions, newest first: both facts in full, when the pair was found, and whether either fact has
    passed its `valid_until` (stale)."""
    return [{"fact": _fact(app, c.fact), "other": _fact(app, c.other), "at": c.at, "stale": c.stale}
            for c in app.contradictions(include_stale=include_stale, limit=max(0, int(limit)))]


def settle(app: Any, fact_id: str, other_id: str, *, keep: str, reason: str = "",
           by: str | None = None) -> dict[str, Any]:
    """Settle an open contradiction: `keep` is one of the two fact ids (the other is retracted) or `both`. Returns
    both facts as they stand after."""
    try:
        app.settle_contradiction(fact_id, other_id, keep=keep, reason=reason or "", by=by)
    except LookupError as err:
        raise NotFound(str(err)) from err
    return {"kept": keep, "facts": [fact(app, fact_id), fact(app, other_id)]}


def stats(app: Any) -> dict[str, Any]:
    """Counts of documents, facts, and entities by class and status."""
    return _plain(app.stats())


def ingest(app: Any, text: str, *, document_type: str | None = None, uri: str | None = None,
           title: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ingest one document's text and return the facts kept and rejected. `document_type` names a document class in
    the project; without it, the project's classifiers pick one."""
    klass = None
    if document_type:
        klass = next((k for k in app.document_classes if stored_name(k) == document_type), None)
        if klass is None:
            names = ", ".join(stored_name(k) for k in app.document_classes) or "none"
            raise NotFound(f"no document class {document_type}; the project has: {names}")
    result = app.ingest_text(text, document_type=klass, metadata=metadata, uri=uri, title=title)
    return {"document": {"id": result.document.id, "class": stored_name(type(result.document)),
                         "uri": result.document.uri, "title": result.document.title},
            "unchanged": result.unchanged, "facts": [_fact(app, f) for f in result.facts],
            "rejected": [{"text": r.text, "reasons": list(r.reasons)} for r in result.rejected],
            "duplicates": result.duplicates}


# -- shapes -------------------------------------------------------------------------------------------------


def _entity(app: Any, name_or_id: str) -> Any:
    from .entity import Entity

    found = app.load_entity(name_or_id) or Entity.find(name_or_id)
    if found is None:
        raise NotFound(f"no entity named {name_or_id!r}")
    return found


def events(app: Any, *, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    """Events after sequence number `after`, oldest first. Pass the last `seq` back to read on."""
    return app.events(after, limit)


def document(app: Any, document_id: str) -> dict[str, Any]:
    found = app.document(document_id)
    if found is None:
        raise NotFound(f"no document {document_id}")
    return found


def _fact(app: Any, f: Any) -> dict[str, Any]:
    """A fact as a dict. A quote the store keeps no text for, and `Document.fetch_text` cannot supply, has text None
    and its offsets."""
    app.fill_quotes(f)
    doc = app.document(f.document_id) if f.document_id else None
    return {
        "id": f.id, "class": stored_name(type(f)), "text": f.text, "status": f.status, "traits": f.trait_names,
        "valid_from": _iso(f.valid_from), "valid_until": _iso(f.valid_until), "expires": f.expires,
        "still_valid": round(f.valid_at(), 4),
        "document": {"id": f.document_id, "title": app.document_title(f.document_id),
                     **({k: doc[k] for k in ("uri", "source_datetime", "metadata")} if doc else {})},
        "quotes": [{"document_id": q.document_id, "passage": q.passage_n, "section": q.section, "text": q.text,
                    "start": q.start, "end": q.end, "speaker": q.speaker, "said_at": q.said_at,
                    **({"attrs": q.attrs} if q.attrs else {})}
                   for q in f.quotes],
        "mentions": [{"text": m.text, "role": m.role, "entity_id": m.entity_id} for m in f.mentions],
    }


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def _plain(value: Any) -> Any:
    """Dates to ISO strings, recursively, so `json.dumps` takes the result."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return _iso(value)
