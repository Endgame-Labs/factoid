"""Documents: prose and structured.

A document's class normally comes from its source. Classification runs only when it is unknown. Every `Document`
subclass registers itself, and the central classifier asks one request per file: a shared choice over the classes'
docstrings, a yes-or-no question asking whether any of them applies, and each class's own `@judge` questions.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from .dates import DateError, format_datetime, parse_datetime
from .fact import Fact, Mention, Quote
from .fact_evals import FactEval
from .judge import Choice, Judgments, Noul, Question, questions_of
from .runtime import ModelCalls, Registered, current
from .steps import SKIPPED, run_step
from .templates import Template, builtin, render

if TYPE_CHECKING:
    from .app import Factoid

__all__ = [
    "Raw",
    "Passage",
    "Replacement",
    "Chunk",
    "Document",
    "ProseDocument",
    "ClassificationError",
    "classify_raw",
]


@dataclass
class Raw:
    """A document before its class is known."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    uri: str | None = None
    title: str | None = None

    def head(self, n: int) -> str:
        return self.text[:n]

    def tail(self, n: int) -> str:
        return self.text[-n:]


@dataclass
class Passage:
    """A unit a fact can cite: a paragraph, a sentence, or a speaker turn."""

    n: int
    start: int
    end: int
    text: str
    speaker: str | None = None
    said_at: str | None = None
    section: str | None = None  # the numbered section the passage falls under, such as "3.2"


@dataclass
class Chunk:
    """Passages that go to the extractor together. A chunk never splits a passage."""

    id: str
    n: int
    passages: list[Passage]
    context_passages: list[Passage] = field(default_factory=list)
    situation: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.passages)


class ClassificationError(RuntimeError):
    """Two classes claimed one document."""


class ExtractionError(ValueError):
    """The extractor's answer could not be read."""


class Document(Registered, ModelCalls):
    """Base class for documents. Subclass `ProseDocument` or `StructuredDocument`."""

    _registry: ClassVar[dict[str, type]] = {}

    STEPS: ClassVar[tuple[str, ...]] = ("classify", "discover", "context", "source_datetime", "ingest")

    #: Probability above which the default `classify` claims a document.
    classify_threshold: ClassVar[float] = 0.8
    #: Probability below which the default `classify` rejects a document.
    reject_threshold: ClassVar[float] = 0.2
    #: Describes this class's boundary with close classes, for the classifier.
    not_for: ClassVar[str | None] = None
    #: Narrows which fact classes facts from this document can be. None means every fact class.
    fact_classes: ClassVar[list[type[Fact]] | None] = None

    # How facts from this document are written and checked. Prose and structured documents share these: a
    # structured document's `Text()` cells go through the same extractor, evals, and repair.

    #: Extraction guidance shown to the extractor, before each fact class's own guidance.
    guidance: ClassVar[str] = ""
    #: The extractor's prompt.
    extract_prompt: ClassVar[str | Template] = builtin("extract.md.j2")
    #: The repair prompt for near misses from this document. None uses the fact class's.
    repair_prompt: ClassVar[str | Template | None] = None
    #: The fact eval chain for facts from this document, such as `[Nli(), DecisionFloors(grounded=0.3)]` for
    #: transcripts.
    #: None uses the fact class's chain.
    fact_evals: ClassVar[list[FactEval] | None] = None
    #: Characters of the document just before a fact's first cited passage, shown to the fact evals and to repair.
    #: The extractor resolves "he" and "the plane" from earlier text, so the checks need that text too. 0 shows none.
    evidence_context: ClassVar[int] = 1200

    def __init__(self, text: str, *, metadata: dict[str, Any] | None = None, uri: str | None = None,
                 id: str | None = None, title: str | None = None):
        self.text = text
        self.metadata = dict(metadata or {})
        self.uri = uri
        self.title = title or self.metadata.get("title")
        self.content_hash = hashlib.sha256(text.encode()).hexdigest()
        self.id = id or (f"doc_{hashlib.sha256((uri or self.content_hash).encode()).hexdigest()[:16]}")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id} {self.title or self.uri or ''}>"

    @property
    def type(self) -> str:
        return type(self).__name__

    @property
    def source_datetime(self) -> Any:
        """The document's own date, from its metadata. Override to read another field."""
        return self.metadata.get("source_datetime")

    def dated(self) -> datetime | None:
        """`source_datetime`, validated. A value Factoid does not accept is an error."""
        value = self.source_datetime
        if value is None or value == "":
            return None
        try:
            return parse_datetime(value)
        except DateError as err:
            raise DateError(f"{self.type} {self.uri or self.id}: source_datetime: {err}") from err

    def context(self) -> dict[str, Any]:
        """Shown to the extractor before the passages: sender, channel, speakers, and the like."""
        return {}

    def state(self) -> dict[str, Any]:
        return {"document_type": self.type, "title": self.title, "text": self.text[:4000]}

    def text_before(self, fact: Fact) -> str:
        """The text just before the fact's first cited passage, `evidence_context` characters, cut at a word."""
        size = type(self).evidence_context
        starts = [q.start for q in fact.quotes if q.document_id == self.id and q.start is not None]
        if size <= 0 or not starts:
            return ""
        end = min(starts)
        start = max(0, end - size)
        if start > 0:
            space = self.text.find(" ", start, end)
            start = space + 1 if space >= 0 else start
        return self.text[start:end].strip()

    # -- classification -------------------------------------------------------------------------------------

    @classmethod
    def classify_view(cls, raw: Raw) -> str:
        """What the classifier sees."""
        return raw.text[:3000]

    @classmethod
    def classify(cls, raw: Raw, judgments: Judgments) -> bool | float | None:
        """True, False, None (not sure), or a score. The default reads one shared choice."""
        if judgments["any_document_class"] < 0.3:
            return False
        p = judgments["document_class"].get(cls.__qualname__, 0.0)
        if p >= cls.classify_threshold:
            return True
        if p <= cls.reject_threshold:
            return False
        return None

    # -- discovery and ingest -------------------------------------------------------------------------------

    def discover(self, facts: list[Fact]) -> list[Mention]:
        """Propose entities: the mentions this document's facts carry."""
        return [m for fact in facts for m in fact.mentions]

    def ingest(self, app: Factoid) -> list[Fact]:
        raise NotImplementedError

    def record(self, passages: list[Passage], chunks: list[Chunk]) -> tuple[dict[str, Any], list[dict[str, Any]],
                                                                            list[dict[str, Any]]]:
        dated = self.dated()
        doc = {"id": self.id, "class": type(self).__qualname__, "uri": self.uri, "title": self.title,
               "source_datetime": format_datetime(dated) if dated else None, "metadata": self.metadata,
               "text": self.text, "content_hash": self.content_hash}
        rows = [{"n": p.n, "start": p.start, "end": p.end, "speaker": p.speaker, "said_at": p.said_at}
                for p in passages]
        chunk_rows = [{"id": c.id, "n": c.n, "first_passage": c.passages[0].n, "last_passage": c.passages[-1].n,
                       "text": c.text, "situation": c.situation} for c in chunks]
        return doc, rows, chunk_rows


_SENTENCE = re.compile(r"(?<=[.;!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_ABBREV = re.compile(r"\b(?:No|Nos|Sec|Secs|Inc|Ltd|Corp|Co|Mr|Mrs|Ms|Dr|St|U\.S|e\.g|i\.e|vs|etc|Art|Para)\.$")


def split_sentences(text: str, offset: int = 0) -> list[tuple[int, int]]:
    """Sentence spans in `text`, as (start, end) offsets plus `offset`."""
    spans, start = [], 0
    for match in _SENTENCE.finditer(text):
        piece = text[start:match.start()]
        if _ABBREV.search(piece) or len(piece.strip()) < 25:
            continue
        spans.append((offset + start, offset + match.start()))
        start = match.end()
    if text[start:].strip():
        spans.append((offset + start, offset + len(text.rstrip())))
    return spans


class ProseDocument(Document):
    """Text: emails, transcripts, contracts, memos, and articles."""

    STEPS: ClassVar[tuple[str, ...]] = (
        "classify", "segment", "chunk", "situate", "extract", "replacements", "discover", "context",
        "source_datetime", "ingest",
    )

    #: The largest chunk, in characters.
    chunk_size: ClassVar[int] = 6000
    #: Characters (400) or a share of chunk_size ("15%") repeated as context at the start of the next chunk.
    chunk_overlap: ClassVar[int | str] = "10%"
    #: Passages longer than this are split into sentences.
    max_passage: ClassVar[int] = 1200
    #: Split every passage into sentences, for precise quotes.
    sentence_passages: ClassVar[bool] = False
    #: Write a situation for each chunk (contextual retrieval). Whether it is on by default is an eval result.
    situate: ClassVar[bool | Callable[..., Any]] = False
    situate_prompt: ClassVar[str | Template] = builtin("situate.md.j2")
    #: Wording that says numbered sections of an earlier document are replaced, matched by code, not a model. The
    #: wording belongs to the domain, so the framework ships none: a class that wants replaced sections sets it
    #: (SPEC "Sections and replaced sections"). None turns the step off.
    replacement_pattern: ClassVar[str | None] = None
    #: Wording that says only part of a section is replaced ("the first paragraph of"), so each older fact is
    #: checked before it is retired.
    partial_replacement_pattern: ClassVar[str | None] = None
    #: Wording that says a section is deleted with no new text, so its older facts end.
    deletion_pattern: ClassVar[str | None] = None
    #: The longest extractor answer, in tokens. A cut-off answer is retried as two half chunks.
    extract_max_tokens: ClassVar[int] = 12000
    #: A regular expression that matches a speaker label at the start of a paragraph. Groups named `speaker`, or
    #: starting with `speaker`, give the name: r"(?:(?P<speaker>Q)\.|(?P<speaker_name>[A-Z][A-Z .'-]+):)\s" reads
    #: "Q." and "STEPHEN CURRY:". The label moves to the passage's `speaker`, and the paragraphs after it keep that
    #: speaker until the next label. None turns it off.
    speaker_pattern: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        overlap = cls.__dict__.get("chunk_overlap")
        if overlap is not None:
            cls.overlap_chars()

    @classmethod
    def overlap_chars(cls) -> int:
        overlap = cls.chunk_overlap
        if isinstance(overlap, bool) or isinstance(overlap, float):
            raise TypeError(f"{cls.__name__}.chunk_overlap must be an int or a percent string, not {overlap!r}")
        if isinstance(overlap, str):
            if not overlap.endswith("%"):
                raise ValueError(f"{cls.__name__}.chunk_overlap {overlap!r} must end with %")
            percent = float(overlap[:-1])
            if not 0 <= percent <= 50:
                raise ValueError(f"{cls.__name__}.chunk_overlap must be 0% to 50%")
            return int(cls.chunk_size * percent / 100)
        if overlap >= cls.chunk_size:
            raise ValueError(f"{cls.__name__}.chunk_overlap must be smaller than chunk_size")
        return int(overlap)

    # -- steps ----------------------------------------------------------------------------------------------

    def segment(self) -> list[Passage]:
        """Split the document into passages: paragraphs, with long ones split into sentences."""
        spans: list[tuple[int, int]] = []
        for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\s*\Z)", self.text, re.S):
            start, end = match.start(), match.end()
            if self.sentence_passages or end - start > self.max_passage:
                spans.extend(split_sentences(self.text[start:end], start))
            else:
                spans.append((start, end))
        passages = []
        speakers = self._speakers(spans)
        spans = [(start + skip, end) for (start, end), (skip, _) in zip(spans, speakers)]
        for start, end in spans:
            if end - start > self.max_passage:  # one long sentence: cut at word boundaries
                cursor = start
                while cursor < end:
                    stop = min(end, cursor + self.max_passage)
                    if stop < end:
                        space = self.text.rfind(" ", cursor, stop)
                        stop = space if space > cursor else stop
                    passages.append((cursor, stop))
                    cursor = stop
            else:
                passages.append((start, end))
        who = _speaker_at(spans, [name for _, name in speakers])
        out = [Passage(n=i + 1, start=s, end=e, text=" ".join(self.text[s:e].split()), speaker=who(s))
               for i, (s, e) in enumerate(passages) if self.text[s:e].strip()]
        return label_sections(out)

    def _speakers(self, spans: list[tuple[int, int]]) -> list[tuple[int, str | None]]:
        """For each span: how many characters of speaker label to skip, and who is speaking."""
        pattern = type(self).speaker_pattern
        if not pattern:
            return [(0, None)] * len(spans)
        out, current_speaker = [], None
        for start, end in spans:
            match = re.match(pattern, self.text[start:end])
            skip = 0
            if match:
                named = next((v for k, v in match.groupdict().items() if k.startswith("speaker") and v), None)
                if named:
                    current_speaker = " ".join(named.split())
                    rest = self.text[start + match.end():end]
                    skip = match.end() + len(rest) - len(rest.lstrip())
            out.append((skip if skip < end - start else 0, current_speaker))
        return out

    def chunk(self, passages: list[Passage]) -> list[Chunk]:
        """Group passages into chunks of at most `chunk_size` characters, with overlap as context."""
        chunks: list[Chunk] = []
        current_group: list[Passage] = []
        size = 0
        overlap = self.overlap_chars()
        for passage in passages:
            if current_group and size + len(passage.text) > self.chunk_size:
                chunks.append(self._make_chunk(len(chunks), current_group, chunks, overlap))
                current_group, size = [], 0
            current_group.append(passage)
            size += len(passage.text) + 2
        if current_group:
            chunks.append(self._make_chunk(len(chunks), current_group, chunks, overlap))
        return chunks

    def _make_chunk(self, n: int, group: list[Passage], previous: list[Chunk], overlap: int) -> Chunk:
        context: list[Passage] = []
        if previous and overlap > 0:
            used = 0
            for passage in reversed(previous[-1].passages):
                if used + len(passage.text) > overlap and context:
                    break
                context.insert(0, passage)
                used += len(passage.text)
        return Chunk(id=f"{self.id}:c{n + 1}", n=n + 1, passages=list(group), context_passages=context)

    def situate_chunk(self, chunk: Chunk) -> str:
        text = self.generate(type(self).situate_prompt, step="situate", document=self, chunk=chunk)
        return " ".join(text.split())

    def extract(self, chunk: Chunk, **context: Any) -> list[Fact]:
        """Candidate facts from one chunk. The extractor cites passages; code attaches the quotes.

        Keyword arguments are passed to the extract template, so an override can add context:
        `return super().extract(chunk, thread=summary)`.
        """
        dated = self.dated()
        prompt = render(
            type(self).extract_prompt,
            document={"type": self.type, "title": self.title, "text": self.text,
                      "source_datetime": format_datetime(dated) if dated else None},
            context=self.context(),
            situation=chunk.situation,
            guidance=self.extraction_guidance(),
            passages=chunk.passages,
            context_passages=chunk.context_passages,
            **context,
        )
        raw = current().client.generate(prompt, json_mode=True, max_tokens=type(self).extract_max_tokens,
                                        step="extract")
        try:
            return self.parse_candidates(raw, chunk)
        except ExtractionError:
            if len(chunk.passages) < 2:
                return []
            # The answer was cut off or malformed: extract each half of the chunk instead of losing it.
            half = len(chunk.passages) // 2
            first = Chunk(f"{chunk.id}a", chunk.n, chunk.passages[:half], chunk.context_passages, chunk.situation)
            second = Chunk(f"{chunk.id}b", chunk.n, chunk.passages[half:], chunk.passages[:half][-2:],
                           chunk.situation)
            return self.extract(first, **context) + self.extract(second, **context)

    def extraction_guidance(self) -> str:
        parts = [type(self).guidance.strip()]
        for klass in self.candidate_fact_classes():
            if klass.guidance.strip():
                parts.append(klass.guidance.strip())
        return "\n".join(p for p in parts if p)

    def candidate_fact_classes(self) -> list[type[Fact]]:
        app = current()
        classes = type(self).fact_classes or app.fact_classes
        return list(classes)

    def parse_candidates(self, raw: str, chunk: Chunk) -> list[Fact]:
        """Facts from the extractor's JSON. Raises `ExtractionError` when the JSON is cut off or malformed."""
        try:
            data = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as err:
            raise ExtractionError(str(err)) from err
        items = data.get("facts") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ExtractionError("the answer has no list of facts")
        owned = {p.n: p for p in chunk.passages}
        dated = self.dated()
        out = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            cited = [n for n in _ints(item.get("passages")) if n in owned]
            quotes = [Quote(document_id=self.id, passage_n=n, start=owned[n].start, end=owned[n].end,
                            text=owned[n].text, speaker=owned[n].speaker,
                            said_at=owned[n].said_at or (format_datetime(dated) if dated else None),
                            section=owned[n].section)
                      for n in dict.fromkeys(cited)]
            mentions = []
            for m in item.get("mentions") or []:
                if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"].strip():
                    role = m.get("role") if m.get("role") in ("subject", "about", "speaker") else "about"
                    kind = m.get("kind") if isinstance(m.get("kind"), str) else None
                    aliases = [a.strip() for a in m.get("aliases") or [] if isinstance(a, str) and a.strip()
                               and a.strip().lower() != m["name"].strip().lower()]
                    mentions.append(Mention(text=m["name"].strip(), kind=(kind or "").strip().lower() or None,
                                            role=role, aliases=aliases))
            out.append(Fact(item["text"], quotes=quotes, mentions=mentions, document=self, chunk_id=chunk.id,
                            source_datetime=dated, valid_from=_date_or_none(item.get("valid_from")),
                            valid_until=_date_or_none(item.get("valid_until"))))
        return out

    def ingest(self, app: Factoid) -> list[Fact]:
        """Run the steps in order: segment, chunk, situate, extract, then the fact steps."""
        passages = run_step(self, "segment")
        chunks = run_step(self, "chunk", passages)
        # `situate = True` runs the default step; a method named `situate` replaces it.
        step = "situate" if callable(type(self).situate) else "situate_chunk"
        if type(self).situate:
            situations = app.map(lambda c: run_step(self, step, c), chunks)
            for chunk_, situation in zip(chunks, situations):
                chunk_.situation = situation if situation is not SKIPPED else None
        app.retire_document_facts(self)
        app.store.save_document(*self.record(passages, chunks))
        app.index_chunks(self, chunks)
        batches = app.map(lambda c: run_step(self, "extract", c), chunks)
        candidates = [fact for batch in batches if batch is not SKIPPED for fact in batch]
        facts = app.process_candidates(self, candidates)
        replaced = run_step(self, "replacements", passages)
        if replaced and replaced is not SKIPPED:
            app.replace_sections(self, replaced, facts)
        return facts

    def replacements(self, passages: list[Passage]) -> list[Replacement]:
        """Passages that say numbered sections of an earlier document are replaced, with those numbers.

        Plain code on the text, using the class's `replacement_pattern`, `partial_replacement_pattern`, and
        `deletion_pattern`. A class can override this step for wording a regular expression can't catch."""
        cls = type(self)
        pattern = cls.replacement_pattern
        if not pattern:
            return []
        found = []
        for i, passage in enumerate(passages):
            match = re.search(pattern, passage.text, re.I)
            if match is None:
                continue
            head = passage.text[:match.start()]
            if not re.search(r"sections?\s+\d", head, re.I) and i > 0:
                # "Section 2. A. and B. ... is deleted": a sentence split can leave the number in the passage before
                head = passages[i - 1].text[-200:] + " " + head
            numbers = re.findall(r"\d+(?:\.\d+)*", " ".join(re.findall(r"sections?\s+[\d.,\sand]+", head, re.I)))
            sections = list(dict.fromkeys(n.rstrip(".") for n in numbers if n.rstrip(".")))
            if not sections:
                continue
            partial = bool(cls.partial_replacement_pattern
                           and re.search(cls.partial_replacement_pattern, passage.text, re.I))
            deleted = bool(cls.deletion_pattern and re.search(cls.deletion_pattern, passage.text, re.I))
            found.append(Replacement(passage, sections, partial=partial, deleted=deleted))
        return found


@dataclass
class Replacement:
    """A passage that says numbered sections of an earlier document are replaced.

    `partial`: only part of each section is replaced, so an older fact is retired only when a new fact replaces it.
    `deleted`: the sections are deleted with no new text, so their older facts end."""

    passage: Passage
    sections: list[str]
    partial: bool = False
    deleted: bool = False


def classify_raw(raw: Raw, classes: list[type[Document]], ask: Callable[[Any, dict[str, Question]], Judgments],
                 ) -> tuple[type[Document] | None, dict[str, Any]]:
    """Pick one class for a document, or None when no class claims it. Two claims is an error."""
    if not classes:
        return None, {}
    if len(classes) == 1:
        options = {classes[0].__qualname__: classes[0].description(), "_other": "Something else."}
    else:
        options = {}
        for klass in classes:
            label = klass.description()
            if klass.not_for:
                label += f" Not: {klass.not_for}"
            options[klass.__qualname__] = label
    questions: dict[str, Question] = {
        "document_class": Choice("Which kind of document is this?", options),
        "any_document_class": Noul("Is this document one of these kinds: "
                                   + "; ".join(k.description() for k in classes) + "?"),
    }
    for klass in classes:
        questions.update(questions_of(klass.classify))
    views = {klass.classify_view(raw) for klass in classes}
    state = {"document": views.pop() if len(views) == 1 else raw.text[:3000], "title": raw.title}
    judgments = ask(state, questions)
    answers = {klass: run_step(klass, "classify", raw, judgments) for klass in classes}
    claimed = [klass for klass, answer in answers.items() if answer is True]
    if len(claimed) > 1:
        raise ClassificationError(f"{raw.uri or 'document'} claimed by {[k.__name__ for k in claimed]}")
    if claimed:
        return claimed[0], {k.__name__: _show(v) for k, v in answers.items()}
    scored = [(float(v), k) for k, v in answers.items() if not isinstance(v, bool) and v is not None
              and v is not SKIPPED]
    if scored:
        best = max(scored, key=lambda pair: pair[0])
        if best[0] >= best[1].classify_threshold:
            return best[1], {k.__name__: _show(v) for k, v in answers.items()}
    return None, {k.__name__: _show(v) for k, v in answers.items()}


_SECTION = re.compile(r"^(?:(?:section|sec\.|article|clause|§)\s*)?(\d+(?:\.\d+)*)(?:\.|\)|\s)", re.I)


def label_sections(passages: list[Passage]) -> list[Passage]:
    """Give each passage the number of the section it falls under. A passage that starts with a section number
    (such as "Section 3.2 TERMS OF PAYMENT" or "3.2 Payment") opens that section; the passages after it inherit
    it until the next one."""
    current: str | None = None
    for passage in passages:
        match = _SECTION.match(passage.text)
        if match and len(match.group(1)) <= 8:
            current = match.group(1).rstrip(".")
        passage.section = current
    return passages


def _speaker_at(spans: list[tuple[int, int]], names: list[str | None]) -> Callable[[int], str | None]:
    """Who speaks at a character offset: the speaker of the span that holds it."""
    def who(offset: int) -> str | None:
        for (start, end), name in zip(spans, names):
            if start <= offset < end:
                return name
        return None
    return who


def _show(value: Any) -> Any:
    return value if isinstance(value, (bool, float, int)) or value is None else str(value)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw


def _ints(value: Any) -> list[int]:
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, int) and not isinstance(v, bool)]
    return []


def _date_or_none(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return parse_datetime(value)
    except DateError:
        return None

