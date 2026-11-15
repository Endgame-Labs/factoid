"""The Factoid app: classes, settings, a store, an index, and the model client, in one object.

    factoid = Factoid(settings=Settings, documents=[DealMemo], entities=[Company])
    factoid.ingest_text("Orion's lease in Austin ends in March 2027.", document_type=DealMemo)
    hits = Fact.search("Orion lease")
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from .dates import format_datetime, now, parse_datetime
from .document import Document, ProseDocument, Raw, classify_raw
from .entity import Entity
from .fact import Fact, Mention, Quote
from .judge import Noul
from .models import CallLog, Meter, ModelClient
from .runtime import use
from .search import Index, LocalIndex
from .settings import Settings
from .steps import SKIPPED, run_step
from .validity import LIFETIME_RANGES

__all__ = ["Factoid", "IngestResult", "SearchHit", "Rejected"]

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class Rejected:
    text: str
    reasons: list[str]
    scores: dict[str, Any] = field(default_factory=dict)
    document_id: str | None = None


@dataclass
class IngestResult:
    document: Document
    facts: list[Fact]
    rejected: list[Rejected]
    duplicates: int = 0


@dataclass
class SearchHit:
    fact: Fact
    score: float
    validity: float
    contradictions: list[Fact] = field(default_factory=list)
    contradiction_ids: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"<SearchHit {self.score:.3f} {self.fact.text!r}>"


class Factoid:
    """One project's classes, settings, store, index, and models."""

    placeholder_floor = 0.5

    def __init__(
        self,
        settings: type[Settings] = Settings,
        *,
        documents: Iterable[type[Document]] | None = None,
        entities: Iterable[type[Entity]] | None = None,
        facts: Iterable[type[Fact]] | None = None,
        root: Path | str | None = None,
        project_id: str | None = None,
        in_memory: bool = False,
        replay: bool | None = None,
        data_dir: Path | str | None = None,
        calls_path: Path | str | None = None,
    ):
        self.settings = settings
        self.root = Path(root) if root else Path.cwd()
        self.project_id = project_id or self.root.name or "factoid"
        data = Path(data_dir) if data_dir else settings.data_path(self.root)
        self.data_dir = None if in_memory else data
        store_path = data / "store.db"
        if settings.store is not None and data_dir is None:
            store_path = settings.store.resolve(self.root)
        self.store = _store(None if in_memory else store_path)
        self.calls = CallLog(Path(calls_path) if calls_path else None if in_memory else data / "calls.db")
        self.meter = Meter()
        self.client = ModelClient(settings.all_models(), self.calls, self.meter,
                                  replay=settings.replay if replay is None else replay)
        self.index: Index = settings.search or LocalIndex(None if in_memory else data / "index.db")
        self.document_classes = list(documents) if documents is not None else list(Document.registered())
        self.entity_classes = list(entities) if entities is not None else list(Entity.registered())
        fact_classes = list(facts) if facts is not None else list(Fact.registered())
        self.fact_classes: list[type[Fact]] = fact_classes or [Fact]
        self.document_entities: dict[str, dict[str, str]] = {}
        self.placeholders: set[str] = set()
        self._name_checks: dict[str, bool] = {}
        self.rejected: list[Rejected] = []
        self._pool = ThreadPoolExecutor(max_workers=max(1, settings.concurrency))
        use(self)

    # -- plumbing -------------------------------------------------------------------------------------------

    def ns(self, name: str) -> str:
        if isinstance(self.index, LocalIndex):
            return name
        return f"{self.project_id}-{name}"

    def map(self, fn: Callable[[T], R], items: Iterable[T]) -> list[R]:
        items = list(items)
        if len(items) <= 1:
            return [fn(item) for item in items]
        return list(self._pool.map(fn, items))

    def entity_class(self, name: str) -> type[Entity]:
        for klass in self.entity_classes:
            if klass.__qualname__ == name:
                return klass
        return Entity._registry.get(name, Entity)  # type: ignore[return-value]

    def fact_class(self, name: str) -> type[Fact]:
        for klass in self.fact_classes:
            if klass.__qualname__ == name:
                return klass
        return Fact._registry.get(name, Fact)  # type: ignore[return-value]

    def document_class(self, name: str) -> type[Document]:
        for klass in self.document_classes:
            if klass.__qualname__ == name or klass.__name__ == name:
                return klass
        raise KeyError(f"no document class named {name!r}")

    def close(self) -> None:
        self._pool.shutdown(wait=True)

    # -- ingest ---------------------------------------------------------------------------------------------

    def classify(self, raw: Raw) -> tuple[type[Document] | None, dict[str, Any]]:
        classes = [k for k in self.document_classes if k not in (Document, ProseDocument)]
        return classify_raw(raw, classes, self.client.ask)

    def ingest(self, item: Document | Raw | str | Path, *, document_type: type[Document] | None = None,
               metadata: dict[str, Any] | None = None) -> IngestResult:
        """Ingest a document instance, a raw document, or a file path."""
        if isinstance(item, (str, Path)) and Path(item).exists():
            path = Path(item)
            meta = dict(metadata or {})
            sidecar = path.with_name(path.name + ".meta.json")
            if sidecar.is_file():
                meta = {**json.loads(sidecar.read_text()), **meta}
            item = Raw(path.read_text(errors="replace"), meta, uri=str(path), title=meta.get("title", path.stem))
        if isinstance(item, Raw):
            klass = document_type
            if klass is None:
                klass, _ = self.classify(item)
                if klass is None:
                    if len(self.document_classes) == 0:
                        klass = ProseDocument
                    else:
                        raise ValueError(f"no document class claims {item.uri or 'this document'}")
            item = klass(item.text, metadata=item.metadata, uri=item.uri, title=item.title)
        if not isinstance(item, Document):
            raise TypeError(f"cannot ingest {item!r}")
        before = len(self.rejected)
        self._duplicates = 0
        facts = run_step(item, "ingest", self)
        facts = [] if facts is SKIPPED else facts
        return IngestResult(item, facts, self.rejected[before:], self._duplicates)

    def ingest_text(self, text: str, *, document_type: type[Document] | None = None,
                    metadata: dict[str, Any] | None = None, uri: str | None = None,
                    title: str | None = None) -> IngestResult:
        return self.ingest(Raw(text, dict(metadata or {}), uri=uri, title=title), document_type=document_type)

    def index_chunks(self, document: Document, chunks: list[Any]) -> None:
        if not chunks:
            return
        texts = [(f"{c.situation}\n\n" if c.situation else "") + c.text for c in chunks]
        vectors = self.client.embed(texts)
        self.index.upsert(self.ns("chunks"), [
            {"id": c.id, "text": t, "vector": v, "document_id": document.id}
            for c, t, v in zip(chunks, texts, vectors)
        ])

    def process_candidates(self, document: Document, candidates: list[Fact]) -> list[Fact]:
        """Classify, validate, evaluate, repair, assess, link, resolve, and save each candidate fact."""
        if not candidates:
            return []
        classes = list(getattr(document, "fact_classes", None) or self.fact_classes)
        candidates = self.map(lambda f: self._classify_fact(f, classes), candidates)
        kept = []
        for fact in candidates:
            if fact is SKIPPED:
                continue
            problems = run_step(fact, "validate")
            if problems:
                self.rejected.append(Rejected(fact.text, [f"validate: {p}" for p in problems],
                                              document_id=document.id))
                continue
            kept.append(fact)
        vectors = self.client.embed([f.text for f in kept]) if kept else []
        for fact, vector in zip(kept, vectors):
            fact.vector = vector
            fact.similar = self._similar_facts(fact, vector, limit=3)
        evaluated = self.map(self._evaluate, kept)
        passed = [f for group in evaluated for f in group]
        self.map(lambda f: run_step(f, "assess"), passed)
        saved = []
        for fact in passed:
            run_step(fact, "link")
            outcome = run_step(fact, "resolve")
            outcome = [] if outcome is SKIPPED else outcome
            duplicate = next((other for answer, other, _ in outcome if answer == "duplicate"), None)
            if duplicate is not None:
                self._confirm(duplicate, fact)
                self._duplicates += 1
                continue
            for answer, other, _ in outcome:
                step = {"supersedes": "supersede", "ends": "end", "corrects": "correct",
                        "contradicts": "contradict"}[answer]
                run_step(fact, step, other)
            run_step(fact, "save")
            saved.append(fact)
        return saved

    def replace_sections(self, document: Document, replaced: list[Any], facts: list[Fact]) -> int:
        """Retire the older facts that a section replaced as a whole made out of date.

        Scope: earlier documents that share an entity with the facts quoting the replacing passage (or, when none was
        kept, with the new section's facts), and older facts that quote the named section. Within that scope, the
        decision model confirms each one: an older fact is superseded only by a new fact from the same section that
        it judges replaces what the older fact says, so a sibling clause the amendment did not touch stays current.
        A section deleted with no replacement text ends its older facts."""
        mine = document.dated()
        retired = 0

        def in_section(fact: Fact, section: str) -> bool:
            return any(q.section and (q.section == section or q.section.startswith(section + "."))
                       for q in fact.quotes)

        for passage, sections in replaced:
            instruction = [f for f in facts if any(q.passage_n == passage.n for q in f.quotes)]
            deleted_only = re.search(r"deleted\s+in\s+(?:its|their)\s+entirety", passage.text, re.I) is not None \
                and re.search(r"replaced|as follows|to read", passage.text, re.I) is None
            for section in sections:
                same = [f for f in facts if f.status == "current" and in_section(f, section) and f not in instruction]
                candidates = same or instruction
                scope = instruction or same
                entity_ids = sorted({m.entity_id for f in scope for m in f.mentions if m.entity_id})
                if not entity_ids:
                    continue
                marks = ",".join("?" * len(entity_ids))
                rows = self.store.query(
                    f"select distinct f.id from facts f join mentions m on m.fact_id = f.id "
                    f"where m.entity_id in ({marks}) and f.document_id != ? "
                    "and f.status in ('current', 'contradicted')", (*entity_ids, document.id))
                for row in rows:
                    old = self.load_fact(row["id"])
                    if old is None or not in_section(old, section):
                        continue
                    theirs = old.valid_from or old.source_datetime
                    if mine is not None and theirs is not None and theirs >= mine:
                        continue
                    if deleted_only and instruction:
                        run_step(instruction[0], "end", old)
                        retired += 1
                        continue
                    best = self._replacing_fact(old, candidates, section)
                    if best is not None:
                        run_step(best, "supersede", old)
                        retired += 1
        return retired

    def _replacing_fact(self, old: Fact, candidates: list[Fact], section: str) -> Fact | None:
        """The new fact the decision model judges replaces `old`, or None."""
        if not candidates:
            return None
        candidates = candidates[:12]
        keys = [f"N{i + 1}" for i in range(len(candidates))]
        state = {"section": section, "old_fact": old.text, "new_facts": {k: f.text for k, f in zip(keys, candidates)}}
        questions = {k: Noul(f"Section {section} was replaced as a whole. Does new fact {k} replace what the old fact "
                             "says: the same term, right, duty, amount, or rule, now worded or set differently?")
                     for k in keys}
        judgments = self.client.ask(state, questions)
        best = max(keys, key=lambda k: judgments[k])
        threshold = type(old).replace_threshold
        return candidates[keys.index(best)] if judgments[best] >= threshold else None

    def _classify_fact(self, fact: Fact, classes: list[type[Fact]]) -> Fact:
        if len(classes) == 1:
            chosen = classes[0]
        else:
            questions = classes[0].class_question(classes)
            for klass in classes:
                questions.update(_judge_questions(klass.classify))
            judgments = self.client.ask(fact.state(), questions)
            scores = {}
            for klass in classes:
                answer = run_step(klass, "classify", fact, judgments)
                scores[klass] = 1.0 if answer is True else 0.0 if answer in (False, None, SKIPPED) else float(answer)
            chosen = max(scores, key=scores.get)
        if type(fact) is chosen:
            return fact
        return _recast(fact, chosen)

    def _evaluate(self, fact: Fact) -> list[Fact]:
        """The facts to keep from one candidate: itself, its repair (a rewording or a split), or none."""
        result = run_step(fact, "evaluate")
        if result is SKIPPED:
            return [fact]
        if result.passed:
            self._record(fact, result)
            return [fact]
        if result.near_miss and type(fact).repair_enabled:
            texts = run_step(fact, "repair", result)
            if texts and texts is not SKIPPED:
                kept = []
                for text in texts:
                    candidate = fact.copy(" ".join(text.split()))
                    second = run_step(candidate, "evaluate")
                    if second is SKIPPED or second.passed:
                        candidate.scores["repaired_from"] = fact.text
                        if second is not SKIPPED:
                            self._record(candidate, second)
                        kept.append(candidate)
                if kept:
                    vectors = self.client.embed([c.text for c in kept])
                    for candidate, vector in zip(kept, vectors):
                        candidate.vector = vector
                    return kept
        self._record(fact, result)
        self.rejected.append(Rejected(fact.text, result.failed, result.scores, fact.document_id))
        return []

    def _record(self, fact: Fact, result: Any) -> None:
        fact.scores.update(result.scores)
        if result.note:
            fact.scores["note"] = result.note

    def _confirm(self, existing: Fact, new: Fact) -> None:
        """A duplicate confirms a stored fact: its quotes are added, which restarts the clock."""
        with self.store.tx() as db:
            for q in new.quotes:
                db.execute("insert into quotes values (?,?,?,?,?,?,?,?,?)",
                           (existing.id, q.document_id, q.passage_n, q.start, q.end, q.text, q.speaker, q.said_at,
                            q.section))

    # -- saving and loading ---------------------------------------------------------------------------------

    def fingerprint(self, fact: Fact) -> str:
        klass = type(fact)
        doc_class = type(fact.document) if fact.document is not None else None
        parts = [
            json.dumps({k: v.wire() for k, v in klass.assess_questions().items()}, sort_keys=True),
            repr(klass.fact_evals),
            str(getattr(getattr(doc_class, "extract_prompt", None), "source", getattr(doc_class, "extract_prompt",
                                                                                      ""))),
            str(getattr(doc_class, "guidance", "")) + klass.guidance,
        ]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]

    def save_fact(self, fact: Fact) -> None:
        row = {
            "id": fact.id, "class": type(fact).__qualname__, "text": fact.text, "document_id": fact.document_id,
            "chunk_id": fact.chunk_id, "status": fact.status, "traits": fact.trait_names,
            "trait_scores": fact.trait_scores, "valid_from": _fmt(fact.valid_from), "expires": fact.expires,
            "valid_until": _fmt(fact.valid_until), "lifetime": fact.lifetime,
            "source_datetime": _fmt(fact.source_datetime), "extracted_at": _fmt(fact.extracted_at),
            "scores": fact.scores, "fingerprint": self.fingerprint(fact),
        }
        quotes = [vars(q) for q in fact.quotes]
        mentions = [{k: v for k, v in vars(m).items() if k != "keys"} for m in fact.mentions]
        self.store.save_fact(row, quotes, mentions)
        vector = getattr(fact, "vector", None) or self.client.embed([fact.text])[0]
        self.index.upsert(self.ns("facts"), [{
            "id": fact.id, "text": fact.text, "vector": vector, "class": type(fact).__qualname__,
            "entity_ids": sorted({m.entity_id for m in fact.mentions if m.entity_id}) or ["-"],
            "traits": fact.trait_names or ["-"], "document_id": fact.document_id,
        }])

    def load_fact(self, fact_id: str) -> Fact | None:
        row = self.store.fact_row(fact_id)
        if row is None:
            return None
        klass = self.fact_class(row["class"])
        fact = klass.__new__(klass)
        Fact.__init__(
            fact, row["text"], id=row["id"], document_id=row["document_id"], chunk_id=row["chunk_id"],
            status=row["status"], traits=json.loads(row["traits"]), trait_scores=json.loads(row["trait_scores"]),
            valid_from=_parse(row["valid_from"]), expires=row["expires"], valid_until=_parse(row["valid_until"]),
            lifetime=json.loads(row["lifetime"]) if row["lifetime"] else None,
            source_datetime=_parse(row["source_datetime"]), extracted_at=_parse(row["extracted_at"]),
            scores=json.loads(row["scores"]),
            quotes=[Quote(r["document_id"], r["passage_n"], r["start"], r["end"], r["text"], r["speaker"],
                          r["said_at"], r["section"]) for r in self.store.quotes(fact_id)],
            mentions=[Mention(r["text"], r["kind"], r["role"], r["entity_id"], r["method"], r["confidence"])
                      for r in self.store.mentions(fact_id)],
        )
        return fact

    def save_entity(self, entity: Entity, keys: dict[str, str]) -> None:
        self.store.save_entity({"id": entity.id, "class": type(entity).__qualname__, "kind": entity.kind,
                                "name": entity.name, "aliases": entity.aliases, "props": entity.props}, keys)
        self.index.upsert(self.ns("entities"), [{"id": entity.id, "text": " ".join([entity.name, *entity.aliases]),
                                                 "class": type(entity).__qualname__}])

    def add_alias(self, entity_id: str, alias: str) -> None:
        """Record another name for an entity, and make it findable by that name.

        Only a specific name becomes an alias of the entity. A generic defined term, such as "the Agreement" or
        "Amendment", stays an alias within its own document, or it would link other documents' mentions here."""
        if not self.is_specific_name(alias):
            return
        self.store.add_alias(entity_id, alias)
        row = self.store.entity_row(entity_id)
        if row is not None:
            names = [row["name"], *json.loads(row["aliases"])]
            self.index.upsert(self.ns("entities"), [{"id": row["id"], "text": " ".join(names), "class": row["class"]}])

    def is_specific_name(self, name: str) -> bool:
        key = " ".join(name.lower().split())
        if key not in self._name_checks:
            from .entity import PLACEHOLDER_QUESTION

            answer = self.client.ask({"mention": name}, {"named": PLACEHOLDER_QUESTION})["named"]
            self._name_checks[key] = answer >= self.placeholder_floor
        return self._name_checks[key]

    def load_entity(self, entity_id: str) -> Entity | None:
        row = self.store.entity_row(entity_id)
        if row is None:
            return None
        klass = self.entity_class(row["class"])
        entity = klass.__new__(klass)
        entity.id, entity.name, entity.kind = row["id"], row["name"], row["kind"]
        entity.aliases = json.loads(row["aliases"])
        entity.props = json.loads(row["props"])
        return entity

    def document_title(self, document_id: str | None) -> str | None:
        if not document_id:
            return None
        row = self.store.one("select title, uri from documents where id = ?", (document_id,))
        return (row["title"] or row["uri"]) if row else None

    def similar_entities(self, text: str, limit: int = 5) -> list[Any]:
        ids = self.index.bm25(self.ns("entities"), text, limit)
        rows = [self.store.entity_row(i) for i in ids]
        seen, out = set(), []
        for row in rows:
            if row is not None and row["id"] not in seen:
                seen.add(row["id"])
                out.append(row)
        return out

    def claim(self, entity: Entity, limit: int = 8) -> int:
        """Search stored facts for a new entity's names, and confirm each hit with the decision model."""
        ids = self.index.bm25(self.ns("facts"), entity.name, limit)
        linked = {r["fact_id"] for r in self.store.query("select fact_id from mentions where entity_id = ?",
                                                         (entity.id,))}
        facts = [f for f in (self.load_fact(i) for i in ids if i not in linked) if f is not None
                 and f.status not in ("retracted", "corrected")]
        if not facts:
            return 0
        keys = [f"F{i + 1}" for i in range(len(facts))]
        state = {"entity": {"name": entity.name, "kind": entity.kind},
                 "facts": {k: f.text for k, f in zip(keys, facts)}}
        questions = {k: Noul(f"Is fact {k} about {entity.name}?") for k in keys}
        judgments = self.client.ask(state, questions)
        claimed = 0
        with self.store.tx() as db:
            for key, fact in zip(keys, facts):
                if judgments[key] >= entity.link_threshold:
                    db.execute("insert into mentions values (?,?,?,?,?,?,?)",
                               (fact.id, entity.name, entity.kind, "about", entity.id, "claim",
                                round(judgments[key], 4)))
                    self.store.event(db, "entity.linked", entity.id, fact=fact.id, method="claim")
                    claimed += 1
        return claimed

    # -- reads ----------------------------------------------------------------------------------------------

    def _similar_facts(self, fact: Fact, vector: list[float], limit: int) -> list[Fact]:
        hits = self.index.hybrid(self.ns("facts"), fact.text, vector, limit)
        out = []
        for fact_id, _ in hits:
            other = self.load_fact(fact_id)
            if other is not None and other.status in ("current", "contradicted"):
                out.append(other)
        return out

    def related_facts(self, fact: Fact, limit: int = 5) -> list[Fact]:
        """Stored current facts that share an entity with `fact`, most similar first."""
        entity_ids = sorted({m.entity_id for m in fact.mentions if m.entity_id})
        if not entity_ids:
            return []
        vector = getattr(fact, "vector", None)
        hits = self.index.hybrid(self.ns("facts"), fact.text, vector, limit * 3, filters={"entity_ids": entity_ids})
        out = []
        same_document = 0
        for fact_id, _ in hits:
            if fact_id == fact.id:
                continue
            other = self.load_fact(fact_id)
            if other is None or other.status not in ("current", "contradicted"):
                continue
            if other.document_id == fact.document_id:
                # Most changes come from other documents, so a document's own facts get at most half the slots.
                if same_document >= limit // 2:
                    continue
                same_document += 1
            out.append(other)
            if len(out) >= limit:
                break
        return out

    def search_facts(self, query: str, *, about: Entity | list[Entity] | None = None,
                     traits: list[Any] | None = None, as_of: str | datetime | None = None,
                     valid_at: str | datetime | None = None, freshness: bool | str = True,
                     contradictions: int | bool = 3, top_k: int = 10, include_retired: bool = False,
                     fact_class: type[Fact] | None = None) -> list[SearchHit]:
        filters: dict[str, Any] = {}
        if about is not None:
            about_list = about if isinstance(about, list) else [about]
            filters["entity_ids"] = [e.id for e in about_list]
        if traits:
            filters["traits"] = [t if isinstance(t, str) else t.key() for t in traits]
        if fact_class is not None:
            filters["class"] = [k.__qualname__ for k in self.fact_classes if issubclass(k, fact_class)] or \
                [fact_class.__qualname__]
        vector = self.client.embed([query])[0]
        fused = self.index.hybrid(self.ns("facts"), query, vector, max(50, top_k * 5), filters or None)
        moment = parse_datetime(as_of) if as_of is not None else now()
        hits: list[SearchHit] = []
        for fact_id, score in fused:
            fact = self.load_fact(fact_id)
            if fact is None:
                continue
            if not include_retired and fact.status not in ("current", "contradicted"):
                # with as_of, a superseded or ended fact still counts if it was valid then
                if as_of is None or fact.status not in ("superseded", "ended") or fact.valid_until is None:
                    continue
            p = fact.valid_at(moment)
            if valid_at is not None and fact.valid_at(parse_datetime(valid_at)) < 0.5:
                continue
            weight = 1.0 if freshness in (False, "any") else (0.25 + 0.75 * p)
            hits.append(SearchHit(fact, score * weight, p))
        hits.sort(key=lambda h: -h.score)
        if self.client.models.get("rerank") and hits:
            head = hits[:50]
            scores = self.client.rerank(query, [h.fact.text for h in head])
            if scores:
                for hit, s in zip(head, scores):
                    weight = 1.0 if freshness in (False, "any") else (0.25 + 0.75 * hit.validity)
                    hit.score = s * weight
                hits = sorted(head, key=lambda h: -h.score)  # reranked scores are not comparable to the rest
        hits = hits[:top_k]
        if contradictions is not False:
            limit = int(contradictions)
            for hit in hits:
                others = [r["other_id"] if r["fact_id"] == hit.fact.id else r["fact_id"]
                          for r in self.store.relations(hit.fact.id) if r["relation"] == "contradicts"]
                hit.contradiction_ids = others
                hit.contradictions = [f for f in (self.load_fact(i) for i in others[:limit]) if f is not None]
        return hits

    def search_chunks(self, query: str, *, about: Entity | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        filters = None
        if about is not None:
            docs = [r["document_id"] for r in self.store.query(
                "select distinct f.document_id from facts f join mentions m on m.fact_id = f.id "
                "where m.entity_id = ?", (about.id,))]
            if not docs:
                return []
            filters = {"document_id": docs}
        vector = self.client.embed([query])[0]
        out = []
        for chunk_id, score in self.index.hybrid(self.ns("chunks"), query, vector, top_k, filters):
            row = self.store.one("select * from chunks where id = ?", (chunk_id,))
            if row is not None:
                out.append({"id": row["id"], "document_id": row["document_id"], "text": row["text"],
                            "situation": row["situation"], "score": score})
        return out

    def entity_facts(self, entity: Entity, *, traits: list[Any] | None = None, since: str | None = None,
                     role: str | None = None, include_retired: bool = False) -> list[Fact]:
        sql = ("select distinct f.id from facts f join mentions m on m.fact_id = f.id where m.entity_id = ?")
        params: list[Any] = [entity.id]
        if role:
            sql += " and m.role = ?"
            params.append(role)
        if not include_retired:
            sql += " and f.status in ('current', 'contradicted')"
        if since:
            sql += " and coalesce(f.valid_from, f.source_datetime, f.extracted_at) >= ?"
            params.append(_since(since))
        sql += " order by coalesce(f.valid_from, f.source_datetime, f.extracted_at) desc"
        facts = [f for f in (self.load_fact(r["id"]) for r in self.store.query(sql, params)) if f is not None]
        if traits:
            keys = {t if isinstance(t, str) else t.key() for t in traits}
            facts = [f for f in facts if keys & set(f.trait_names)]
        return facts

    def related_entities(self, entity: Entity) -> list[dict[str, Any]]:
        rows = self.store.query(
            "select m2.entity_id as other, f.id as fact_id from mentions m1 join mentions m2 "
            "on m1.fact_id = m2.fact_id and m2.entity_id != m1.entity_id join facts f on f.id = m1.fact_id "
            "where m1.entity_id = ? and m2.entity_id is not null and f.status in ('current', 'contradicted')",
            (entity.id,))
        by_other: dict[str, set[str]] = {}
        for row in rows:
            by_other.setdefault(row["other"], set()).add(row["fact_id"])
        out = []
        for other_id, fact_ids in by_other.items():
            other = self.load_entity(other_id)
            if other is None:
                continue
            facts = [f for f in (self.load_fact(i) for i in fact_ids) if f is not None]
            relation = [f for f in facts if _durable(f)]
            weight = sum(f.valid_at() for f in facts)
            out.append({"entity": other, "co_mentions": len(facts), "relation_facts": relation,
                        "weight": round(weight, 4)})
        out.sort(key=lambda r: -r["weight"])
        return out

    def unlinked_facts(self, since: str | None = None) -> list[Fact]:
        sql = ("select distinct f.id from facts f join mentions m on m.fact_id = f.id "
               "where m.entity_id is null and f.status in ('current', 'contradicted')")
        params: list[Any] = []
        if since:
            sql += " and f.extracted_at >= ?"
            params.append(_since(since))
        return [f for f in (self.load_fact(r["id"]) for r in self.store.query(sql, params)) if f is not None]

    def list_facts(self, *, fact_class: type[Fact] | None = None, document_id: str | None = None,
                   status: str | None = None) -> list[Fact]:
        sql, params = "select id from facts where 1=1", []
        if fact_class is not None:
            names = [k.__qualname__ for k in self.fact_classes if issubclass(k, fact_class)] or \
                [fact_class.__qualname__]
            sql += f" and class in ({','.join('?' * len(names))})"
            params += names
        if document_id:
            sql += " and document_id = ?"
            params.append(document_id)
        if status:
            sql += " and status = ?"
            params.append(status)
        return [f for f in (self.load_fact(r["id"]) for r in self.store.query(sql, params)) if f is not None]

    def stats(self) -> dict[str, Any]:
        q = self.store.query
        by_status = {r["status"]: r["n"] for r in q("select status, count(*) n from facts group by status")}
        current_ids = [r["id"] for r in q("select id from facts where status in ('current', 'contradicted')")]
        no_trait = q("select count(*) n from facts where status in ('current','contradicted') and traits = '[]'")[0]
        unlinked = q("select count(*) n from mentions where entity_id is null")[0]["n"]
        single = q("select count(*) n from (select entity_id from mentions where entity_id is not null "
                   "group by entity_id having count(distinct fact_id) = 1)")[0]["n"]
        stale = sum(1 for i in current_ids if (f := self.load_fact(i)) is not None and f.valid_at() < 0.5)
        contradictions = q("select count(*) n from relations where relation = 'contradicts'")[0]["n"]
        entities = q("select count(*) n from entities where merged_into is null")[0]["n"]
        return {
            "documents": q("select count(*) n from documents")[0]["n"],
            "facts": by_status,
            "facts_with_no_trait": no_trait["n"],
            "unlinked_mentions": unlinked,
            "entities": entities,
            "single_fact_entities": single,
            "facts_past_expected_validity": stale,
            "open_contradictions": contradictions,
        }


def _store(path: Path | None) -> Any:
    from .store import Store

    return Store(path)


def _recast(fact: Fact, klass: type[Fact]) -> Fact:
    fact.__class__ = klass
    return fact


def _judge_questions(method: Any) -> dict[str, Any]:
    from .judge import questions_of

    return questions_of(method)


def _fmt(value: datetime | None) -> str | None:
    return format_datetime(value) if value else None


def _parse(value: str | None) -> datetime | None:
    return parse_datetime(value) if value else None


def _since(value: str) -> str:
    units = {"d": "days", "h": "hours", "w": "weeks"}
    if value[:-1].isdigit() and value[-1] in units:
        return format_datetime(now() - timedelta(**{units[value[-1]]: int(value[:-1])}))
    return format_datetime(parse_datetime(value))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


def _durable(fact: Fact) -> bool:
    if fact.expires == "never":
        return True
    if fact.expires == "estimated" and fact.lifetime:
        long = sum(v for k, v in fact.lifetime.items()
                   if LIFETIME_RANGES.get(k, timedelta(0)) >= timedelta(days=30))
        return long >= 0.5
    return False



