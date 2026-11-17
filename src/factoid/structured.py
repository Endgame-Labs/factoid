"""Structured documents: rows from CSV, JSONL, a JSON array, or records from a source.

A `StructuredDocument` subclass is the parser for one file layout. Its `columns` map says what each column is:

- `Identity(Agreement, "contract_id")`: the value identifies an entity. It links exactly, by key, with no model call.
- `Property(Agreement, "governing_law")`: the value is a property of the row's entity of that class.
- A string such as `"Agreement {contract_id} is worth ${annual_value} a year."`: a value with a sentence template.
  Each non-empty cell becomes one fact, cited to the file, row, and column.
- `Text()`: free text, run through the prose pipeline with the row's entities already known.
- `Ignore()`: skipped.

`row_entity` names the entity class each row is, `key` the column that identifies a row across re-imports, and
`when` the column that dates the row. On re-import, a changed value for the same key and column supersedes the old
fact by rule, with no model call.
"""

from __future__ import annotations

import csv
import io
import json
import re
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from .dates import DateError, format_datetime, parse_datetime
from .document import Chunk, Document, Passage, ProseDocument, Raw
from .fact import Fact, Mention, Quote
from .runtime import current
from .steps import SKIPPED, run_step

if TYPE_CHECKING:
    from .app import Factoid
    from .entity import Entity

__all__ = ["Identity", "Ignore", "Property", "Row", "StructuredDocument", "Text", "inspect_rows", "read_rows"]


@dataclass(frozen=True)
class Identity:
    """The column's value identifies an entity of `entity`, stored under the unique key `key`. `name` is a template
    for the entity's name when Factoid creates it, such as "{company_name}"; by default the value itself."""

    entity: type[Entity]
    key: str
    name: str | None = None


@dataclass(frozen=True)
class Property:
    """The column's value is the property `name` of the row's entity of class `entity`."""

    entity: type[Entity]
    name: str


@dataclass(frozen=True)
class Text:
    """Free text, run through the prose pipeline with the row's entities already known."""


@dataclass(frozen=True)
class Ignore:
    """A column Factoid skips."""


@dataclass
class Row:
    """One row: its number (from 1), its values, and where it sits in the file."""

    n: int
    values: dict[str, Any]
    start: int = 0
    end: int = 0
    entities: dict[str, str] = field(default_factory=dict)  # column -> entity id, filled by `identify`


def read_rows(text: str, format: str | None = None) -> list[Row]:
    """Rows from CSV (or TSV), JSONL, or a JSON array of objects. The format is detected unless given."""
    stripped = text.lstrip()
    if format is None:
        format = "json" if stripped.startswith("[") else "jsonl" if stripped.startswith("{") else "csv"
    if format == "json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("a JSON structured document must be an array of objects")
        return [Row(i + 1, dict(item)) for i, item in enumerate(data) if isinstance(item, dict)]
    if format == "jsonl":
        rows, offset = [], 0
        for line in text.splitlines(keepends=True):
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(Row(len(rows) + 1, item, offset, offset + len(line.rstrip("\r\n"))))
            offset += len(line)
        return rows
    if format != "csv":
        raise ValueError(f"unknown structured format {format!r}")
    head = text[:4096]
    delimiter = max(",\t;|", key=lambda d: head.split("\n", 1)[0].count(d))
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    header: list[str] | None = None
    rows: list[Row] = []
    before = 0
    for record in reader:
        line_from, before = before, reader.line_num
        if header is None:
            header = [h.strip() for h in record]
            continue
        if not any(cell.strip() for cell in record):
            continue
        values = {name: (record[i] if i < len(record) else "") for i, name in enumerate(header) if name}
        start = starts[min(line_from, len(starts) - 1)]
        end = starts[min(before, len(starts) - 1)]
        rows.append(Row(len(rows) + 1, values, start, len(text[:end].rstrip("\r\n"))))
    return rows


def header_of(text: str) -> list[str] | None:
    """The column names of a tabular text, or None when it does not read as rows."""
    try:
        rows = read_rows(text[:65536] if not text.lstrip().startswith("[") else text)
    except (ValueError, csv.Error):
        return None
    if not rows:
        return None
    names: dict[str, None] = {}
    for row in rows[:50]:
        names.update(dict.fromkeys(row.values))
    return list(names) if len(names) > 1 else None


class StructuredDocument(Document):
    """Rows: CSV, JSONL, a JSON array, or records from a source. Subclass it and set `columns`."""

    STEPS: ClassVar[tuple[str, ...]] = (
        "classify", "read", "identify", "row_facts", "text_facts", "discover", "context", "source_datetime",
        "ingest",
    )

    #: What each column is: `Identity`, `Property`, a sentence template string, `Text()`, or `Ignore()`.
    columns: ClassVar[dict[str, Any]] = {}
    #: The entity class each row is. Its `Identity` column names the row's entity.
    row_entity: ClassVar[type[Entity] | None] = None
    #: The column that identifies a row across re-imports.
    key: ClassVar[str | None] = None
    #: The column that dates the row.
    when: ClassVar[str | None] = None
    #: "csv", "jsonl", or "json". None detects it from the text.
    format: ClassVar[str | None] = None
    #: Earlier rows are not context for a text cell; the row's identified entities are.
    evidence_context: ClassVar[int] = 0
    #: Rows per stored chunk, for chunk search.
    rows_per_chunk: ClassVar[int] = 20
    #: Run resolve on templated facts, against stored facts that share an entity. Off by default: a cell is data, and
    #: most columns hold one value per row. Turn it on when rows report a state that changes over time, such as a
    #: series score after each game, so a later row supersedes an earlier one.
    resolve_cells: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, role in cls.columns.items():
            if not isinstance(role, (Identity, Property, Text, Ignore, str)):
                raise TypeError(f"{cls.__name__}.columns[{name!r}]: use Identity, Property, Text, Ignore, or a "
                                f"sentence template string, not {role!r}")
            if isinstance(role, str):
                missing = [f for f in _fields(role) if f not in cls.required_columns()]
                if missing:
                    raise ValueError(f"{cls.__name__}.columns[{name!r}]: the template names unknown columns "
                                     f"{missing}")
        if cls.row_entity is not None and cls.columns and not any(
                isinstance(r, Identity) and issubclass(r.entity, cls.row_entity) for r in cls.columns.values()):
            raise ValueError(f"{cls.__name__}: row_entity {cls.row_entity.__name__} needs an Identity column of "
                             "that class")

    @classmethod
    def from_records(cls, records: list[dict[str, Any]], **kwargs: Any) -> StructuredDocument:
        """A document from records, such as rows from an API or a database."""
        text = "".join(json.dumps(r, default=str) + "\n" for r in records)
        return cls(text, **kwargs)

    # -- classification -------------------------------------------------------------------------------------

    @classmethod
    def required_columns(cls) -> set[str]:
        """The mapped columns plus `key` and `when`, which need not be mapped."""
        return set(cls.columns) | {c for c in (cls.key, cls.when) if c}

    @classmethod
    def matches_header(cls, header: list[str]) -> bool:
        """True when the file has every column this class needs. The match comes before the decision model."""
        return bool(cls.columns) and cls.required_columns() <= set(header)

    @classmethod
    def classify_view(cls, raw: Raw) -> str:
        return raw.text[:3000]

    # -- steps ----------------------------------------------------------------------------------------------

    def read(self) -> list[Row]:
        """Parse the text into rows."""
        return read_rows(self.text, type(self).format)

    def row_datetime(self, row: Row) -> datetime | None:
        """The row's date, from the `when` column, or the document's own date."""
        column = type(self).when
        value = row.values.get(column) if column else None
        if value in (None, ""):
            return self.dated()
        try:
            return parse_datetime(value)
        except DateError as err:
            raise DateError(f"{self.type} {self.uri or self.id}, row {row.n}, column {column}: {err}") from err

    def identify(self, row: Row) -> dict[str, str]:
        """Link each `Identity` cell to its entity by key, creating the entity when none has that key. Then set the
        row's `Property` cells on those entities. Returns column -> entity id."""
        app = current()
        found: dict[str, str] = {}
        for column, role in type(self).columns.items():
            if not isinstance(role, Identity):
                continue
            value = _cell(row.values.get(column))
            if not value:
                continue
            entity_id = app.store.entity_by_key(role.key, value)
            if entity_id is None:
                name = _format(role.name, row.values) if role.name else value
                # A new key for an entity the store already has by exactly this name (say, a company found in a
                # contract's text) joins that entity instead of making a second one. Still no model call.
                same = [r for r in app.store.entities_named(name) if " ".join(r["name"].lower().split())
                        == " ".join(name.lower().split()) and issubclass(app.entity_class(r["class"]), role.entity)]
                if len(same) == 1:
                    entity_id = same[0]["id"]
                    app.store.save_entity_key(role.key, value, entity_id)
                else:
                    entity = role.entity.create(name, keys={role.key: value})
                    entity_id = entity.id
                    app.claim(entity)
            found[column] = entity_id
        for column, role in type(self).columns.items():
            if not isinstance(role, Property):
                continue
            value = row.values.get(column)
            target = next((found[c] for c, r in type(self).columns.items()
                           if isinstance(r, Identity) and issubclass(r.entity, role.entity) and c in found), None)
            if target is None or value in (None, ""):
                continue
            entity = app.load_entity(target)
            if entity is not None:
                entity.set(role.name, value)
                app.save_entity(entity, {})
        return found

    def row_entity_id(self, row: Row) -> str | None:
        cls = type(self)
        if cls.row_entity is None:
            return None
        return next((row.entities[c] for c, r in cls.columns.items() if isinstance(r, Identity)
                     and issubclass(r.entity, cls.row_entity) and c in row.entities), None)

    def row_facts(self, row: Row) -> list[Fact]:
        """One fact per non-empty templated cell, cited to the file, row, and column."""
        cls = type(self)
        dated = self.row_datetime(row)
        subject = self.row_entity_id(row)
        out = []
        for column, role in cls.columns.items():
            if not isinstance(role, str):
                continue
            value = row.values.get(column)
            if value in (None, "") or any(row.values.get(f) in (None, "") for f in _fields(role)):
                continue
            mentions = []
            if subject is not None:
                mentions.append(self._mention(subject, "subject"))
            # An identity the sentence names: its own column, or a column its `name` template uses ("{counterparty}"
            # names the company an email column identifies).
            used = set(_fields(role))
            for other, other_role in cls.columns.items():
                entity_id = row.entities.get(other)
                if entity_id is None or entity_id == subject or not isinstance(other_role, Identity):
                    continue
                if other in used or (other_role.name and used & set(_fields(other_role.name))):
                    mentions.append(self._mention(entity_id, "about"))
            fact = Fact(_format(role, row.values), quotes=[self.cell_quote(row, column, dated)], mentions=mentions,
                        document=self, chunk_id=self._chunk_id(row), source_datetime=dated, valid_from=dated)
            fact.scores["cell"] = {"key": self.row_key(row), "column": column}
            out.append(fact)
        return out

    def text_facts(self, row: Row) -> list[Fact]:
        """Facts from the row's `Text()` cells, extracted by the prose pipeline with the row's entities known."""
        cls = type(self)
        columns = [c for c, r in cls.columns.items() if isinstance(r, Text) and _cell(row.values.get(c))]
        if not columns:
            return []
        dated = self.row_datetime(row)
        app = current()
        known = {}
        for column, entity_id in row.entities.items():
            entity = app.load_entity(entity_id)
            if entity is not None:
                known[column] = f"{entity.name} ({entity.kind or 'entity'})"
        reader = self._text_reader(row, known, dated)
        passages = [Passage(n=row.n, start=row.start, end=row.end, text=" ".join(str(row.values[c]).split()),
                            said_at=format_datetime(dated) if dated else None, section=c) for c in columns]
        facts = []
        for passage in passages:
            # Each cell is its own chunk so its quote names the column; the row's number is the passage number.
            facts.extend(reader.extract(Chunk(id=self._chunk_id(row), n=row.n, passages=[passage])))
        subject = self.row_entity_id(row)
        for fact in facts:
            fact.document = self
            if subject is not None and all(m.entity_id != subject for m in fact.mentions):
                fact.mentions.insert(0, self._mention(subject, "subject"))
        return facts

    def ingest(self, app: Factoid) -> list[Fact]:
        """Read rows, link identities, then save templated facts by rule and run text cells through extraction."""
        rows = run_step(self, "read")
        for row in rows:
            entities = run_step(self, "identify", row)
            row.entities = {} if entities is SKIPPED else entities
        passages = [Passage(n=r.n, start=r.start, end=r.end, text=_row_text(r)) for r in rows]
        size = max(1, type(self).rows_per_chunk)
        chunks = [Chunk(id=f"{self.id}:c{i // size + 1}", n=i // size + 1, passages=passages[i:i + size])
                  for i in range(0, len(passages), size)]
        keyed = type(self).key is not None
        if not keyed:
            app.retire_document_facts(self)
        app.store.save_document(*self.record(passages, chunks))
        app.index_chunks(self, chunks)
        cells = []
        for row in rows:
            made = run_step(self, "row_facts", row)
            cells.extend([] if made is SKIPPED else made)
        saved = app.save_cell_facts(self, cells)
        texts = app.map(lambda r: run_step(self, "text_facts", r), rows)
        candidates = [f for batch in texts if batch is not SKIPPED for f in batch]
        return saved + app.process_candidates(self, candidates)

    # -- helpers --------------------------------------------------------------------------------------------

    def row_key(self, row: Row) -> str:
        column = type(self).key
        return _cell(row.values.get(column)) if column else str(row.n)

    def cell_quote(self, row: Row, column: str, dated: datetime | None) -> Quote:
        return Quote(document_id=self.id, passage_n=row.n, start=row.start, end=row.end,
                     text=_cell(row.values.get(column)), said_at=format_datetime(dated) if dated else None,
                     section=column)

    def _chunk_id(self, row: Row) -> str:
        return f"{self.id}:c{(row.n - 1) // max(1, type(self).rows_per_chunk) + 1}"

    def _mention(self, entity_id: str, role: str) -> Mention:
        entity = current().load_entity(entity_id)
        return Mention(entity.name if entity else entity_id, kind=entity.kind if entity else None, role=role,
                       entity_id=entity_id, method="key", confidence=1.0)

    def _text_reader(self, row: Row, known: dict[str, str], dated: datetime | None) -> ProseDocument:
        cls = type(self)
        reader_class = _READERS.get(cls)
        if reader_class is None:
            # Defined in the factoid package, so it is not registered as a document class of the project.
            reader_class = type(f"{cls.__name__}Text", (ProseDocument,), {
                "__module__": __name__, "__doc__": cls.__doc__, "guidance": cls.guidance,
                "extract_prompt": cls.extract_prompt, "fact_classes": cls.fact_classes})
            _READERS[cls] = reader_class
        context = {**self.context(), **{f"{column} (already identified)": name for column, name in known.items()}}
        reader = reader_class(self.text, metadata=dict(self.metadata), uri=self.uri, id=self.id,
                              title=f"{self.title or self.uri or self.type}, row {row.n}")
        reader.context = lambda: context  # type: ignore[method-assign]
        reader.dated = lambda: dated  # type: ignore[method-assign]
        return reader


_READERS: dict[type, type[ProseDocument]] = {}


def _fields(template: str) -> list[str]:
    return [f for _, f, _, _ in string.Formatter().parse(template) if f]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def _format(template: str, values: dict[str, Any]) -> str:
    return template.format_map({k: _cell(v) for k, v in values.items()})


def _row_text(row: Row) -> str:
    return "; ".join(f"{k}: {_cell(v)}" for k, v in row.values.items() if _cell(v))


# -- inspection ---------------------------------------------------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://\S+")
_DOMAIN = re.compile(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}", re.I)
_NUMBER = re.compile(r"[-+$]?\d[\d,]*(?:\.\d+)?%?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?")


def inspect_rows(rows: list[Row], sample: int = 3) -> list[dict[str, Any]]:
    """What each column looks like: its type, sample values, how many distinct values, and a guessed role. Plain
    code, with no model call."""
    names: dict[str, None] = {}
    for row in rows:
        names.update(dict.fromkeys(row.values))
    out = []
    for name in names:
        values = [_cell(row.values.get(name)) for row in rows]
        filled = [v for v in values if v]
        kind = _kind(name, filled)
        out.append({"column": name, "type": kind, "filled": len(filled), "rows": len(values),
                    "distinct": len(set(filled)), "samples": list(dict.fromkeys(filled))[:sample],
                    "role": _guess(kind, name, filled)})
    return out


def _kind(name: str, values: list[str]) -> str:
    if not values:
        return "empty"
    for kind, pattern in (("email", _EMAIL), ("url", _URL), ("date", _DATE), ("number", _NUMBER),
                          ("domain", _DOMAIN)):
        if all(pattern.fullmatch(v) for v in values):
            return kind
    if sum(len(v) for v in values) / len(values) > 80:
        return "text"
    unique = len(set(values)) == len(values) and all(" " not in v and len(v) <= 40 for v in values)
    if unique and (re.search(r"(?:^|_|\b)(?:id|key|code|number|no)$", name, re.I) or
                   all(re.search(r"\d", v) for v in values)):
        return "id"
    return "string"


def _guess(kind: str, name: str, values: list[str]) -> str:
    if kind == "empty":
        return "Ignore()"
    if kind in ("email", "url", "domain"):
        return f'Identity(Entity, "{kind}")'
    if kind == "id":
        return f'Identity(Entity, "{name}")'
    if kind == "text":
        return "Text()"
    if kind == "date":
        return "when"
    return f'"... {{{name}}} ..."'


def starter_class(name: str, columns: list[dict[str, Any]]) -> str:
    """Python for a parser class that starts from the guessed roles. Entity classes and templates need a person."""
    when = next((c["column"] for c in columns if c["role"] == "when"), None)
    key = next((c["column"] for c in columns if c["role"].startswith("Identity")), None)
    lines = [f"class {name}(StructuredDocument):", '    """Describe what one row of this file is."""', ""]
    if key:
        lines.append(f'    key = "{key}"')
    if when:
        lines.append(f'    when = "{when}"')
    lines.append("    columns = {")
    for column in columns:
        if column["role"] == "when":
            continue
        lines.append(f'        "{column["column"]}": {column["role"]},  # {column["type"]}, e.g. '
                     f'{(column["samples"] or [""])[0][:40]!r}')
    lines.append("    }")
    return "\n".join(lines)
