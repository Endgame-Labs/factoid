"""Facts: one self-contained sentence, exact source quotes, links to entities, traits, and time.

A `Fact` subclass is like a model without custom fields: a fact's fields are fixed, and the class holds the rules and
behavior around them. Many projects have one fact class, and many have a few for different kinds of evidence.
"""

from __future__ import annotations

import json
import secrets
import time as _time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from .dates import format_datetime, now, parse_datetime
from .fact_evals import EvalResult, FactEval, JevFloors, Nli
from .judge import Choice, Judgments, Question
from .runtime import ModelCalls, Registered, current
from .steps import run_step
from .templates import Template, builtin, render
from .trait import FactTrait
from .validity import EXPIRES, LIFETIME_RANGES, validity

if TYPE_CHECKING:
    from .entity import Entity

__all__ = ["Fact", "Quote", "Mention", "RESOLVE_ANSWERS", "new_id"]


def new_id(prefix: str) -> str:
    """A sortable id: milliseconds then randomness, in Crockford base32."""
    alphabet = "0123456789abcdefghjkmnpqrstvwxyz"
    value = (int(_time.time() * 1000) << 40) | secrets.randbits(40)
    chars = []
    for _ in range(18):
        value, rem = divmod(value, 32)
        chars.append(alphabet[rem])
    return f"{prefix}_{''.join(reversed(chars))}"


@dataclass
class Quote:
    """An exact passage a fact cites. Code attaches it; models never write evidence."""

    document_id: str
    passage_n: int
    start: int
    end: int
    text: str
    speaker: str | None = None
    said_at: str | None = None


@dataclass
class Mention:
    """Something a fact refers to. `entity_id` is set once linking finds or creates the entity."""

    text: str
    kind: str | None = None
    role: str = "about"  # subject, about, or speaker
    entity_id: str | None = None
    method: str | None = None
    confidence: float | None = None
    keys: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)  # other names the source uses for the same thing


RESOLVE_ANSWERS: dict[str, str] = {
    "duplicate": "The new fact states the same claim as the stored fact.",
    "supersedes": "The new fact replaces a value the stored fact gave, which was true until then.",
    "ends": "The new fact says the state in the stored fact stopped, without giving a new value.",
    "corrects": "The new fact shows the stored fact was wrong from the start.",
    "contradicts": "The two facts cannot both be true, and neither replaces the other.",
    "unrelated": "The facts are about different things, or both can be true at once.",
}


class Fact(Registered, ModelCalls):
    """A self-contained fact."""

    _registry: ClassVar[dict[str, type]] = {}

    STEPS: ClassVar[tuple[str, ...]] = (
        "classify", "validate", "evaluate", "repair", "assess", "expiration", "link", "resolve", "save",
        "supersede", "end", "correct", "contradict", "retract", "restore",
    )

    # -- level 2: settings ----------------------------------------------------------------------------------

    #: The traits facts of this class are asked about.
    traits: ClassVar[list[type[FactTrait]]] = []
    #: The fact eval chain.
    fact_evals: ClassVar[list[FactEval]] = [Nli(), JevFloors()]
    #: Extraction guidance: what counts as a fact for this class.
    guidance: ClassVar[str] = ""
    #: Lifetime ranges the decision model chooses from.
    lifetime_ranges = LIFETIME_RANGES
    #: How many stored facts a new fact is compared against in `resolve`.
    resolve_candidates: ClassVar[int] = 5
    #: The probability a resolve answer must reach; below it, the facts are treated as unrelated.
    resolve_threshold: ClassVar[float] = 0.6
    #: Run one repair (a rewording) on a near miss.
    repair_enabled: ClassVar[bool] = True
    #: The longest fact sentence `validate` accepts, in characters.
    max_length: ClassVar[int] = 600

    # -- level 3: wording -----------------------------------------------------------------------------------

    expires_question: ClassVar[str] = (
        "How does this fact age? Pick how it stops being true, judged from what it states."
    )
    lifetime_question: ClassVar[str] = (
        "If nothing new is learned, how long does a fact like this usually stay true from the time it was stated?"
    )
    resolve_question: ClassVar[str] = (
        "Compare the new fact with stored fact {key}. Which answer describes how the new fact relates to it?"
    )
    repair_prompt: ClassVar[str | Template] = builtin("repair.md.j2")

    # -- instance -------------------------------------------------------------------------------------------

    def __init__(
        self,
        text: str,
        *,
        quotes: Iterable[Quote] = (),
        mentions: Iterable[Mention] = (),
        document: Any = None,
        chunk_id: str | None = None,
        id: str | None = None,
        status: str = "current",
        traits: list[str] | None = None,
        trait_scores: dict[str, float] | None = None,
        valid_from: datetime | None = None,
        expires: str | None = None,
        valid_until: datetime | None = None,
        lifetime: dict[str, float] | None = None,
        source_datetime: datetime | None = None,
        extracted_at: datetime | None = None,
        scores: dict[str, Any] | None = None,
        document_id: str | None = None,
    ):
        self.id = id or new_id("fact")
        self.text = " ".join(text.split())
        self.quotes = list(quotes)
        self.mentions = list(mentions)
        self.document = document
        self.document_id = document_id or (document.id if document is not None else None)
        self.chunk_id = chunk_id
        self.status = status
        self.trait_names: list[str] = list(traits or [])
        self.trait_scores: dict[str, float] = dict(trait_scores or {})
        self.valid_from = valid_from
        self.expires = expires
        self.valid_until = valid_until
        self.lifetime = lifetime
        self.source_datetime = source_datetime or (document.source_datetime if document is not None else None)
        self.extracted_at = extracted_at or now()
        self.scores: dict[str, Any] = dict(scores or {})
        self.similar: list[Fact] = []  # stored facts near this one, filled before evaluate and resolve

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id} {self.text!r}>"

    def __str__(self) -> str:
        return self.text

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Fact) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def traits_carried(self) -> list[str]:
        return list(self.trait_names)

    def has(self, trait: type[FactTrait] | str) -> bool:
        key = trait if isinstance(trait, str) else trait.key()
        return key in self.trait_names

    @property
    def entities(self) -> list[Entity]:
        from .entity import Entity

        return [e for e in (Entity.get(m.entity_id) for m in self.mentions if m.entity_id) if e is not None]

    def valid_at(self, at: datetime | str | None = None) -> float:
        """The probability this fact is still true at `at` (now by default)."""
        moment = parse_datetime(at) if at is not None else now()
        seen = max((parse_datetime(q.said_at) for q in self.quotes if q.said_at), default=self.source_datetime)
        if self.status in ("superseded", "ended") and self.valid_until is None:
            return 0.0
        if self.status in ("corrected", "retracted"):
            return 0.0
        return validity(moment, valid_from=self.valid_from, expires=self.expires, valid_until=self.valid_until,
                        lifetime=self.lifetime, seen_at=seen, ranges=type(self).lifetime_ranges)

    def render(self) -> str:
        """How a fact is shown to a reader or a model."""
        return self.text

    def state(self) -> dict[str, Any]:
        return {
            "fact": self.text,
            "document_date": format_datetime(self.source_datetime) if self.source_datetime else None,
            "quotes": [{"speaker": q.speaker, "text": q.text} for q in self.quotes],
        }

    def eval_state(self) -> dict[str, Any]:
        state = self.state()
        state["cited_passages"] = state.pop("quotes")
        if self.document is not None:
            state["document"] = {"type": self.document.type, "title": self.document.title,
                                 **self.document.context()}
        state["similar_stored_facts"] = [f.text for f in self.similar]
        return state

    # -- fact classes ---------------------------------------------------------------------------------------

    @classmethod
    def classify(cls, fact: Fact, judgments: Judgments) -> bool | float | None:
        """How well `fact` fits this class. The default reads this class's share of one shared choice."""
        return judgments["fact_class"].get(cls.__qualname__, 0.0)

    @classmethod
    def class_question(cls, candidates: list[type[Fact]]) -> dict[str, Question]:
        options = {klass.__qualname__: klass.description() for klass in candidates}
        return {"fact_class": Choice("Which kind of evidence is this fact?", options)}

    # -- steps ----------------------------------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Code checks. Returns problems; an empty list passes."""
        problems = []
        if len(self.text) < 12:
            problems.append("too short")
        if len(self.text) > type(self).max_length:
            problems.append("too long for one fact")
        if not self.quotes:
            problems.append("cites no passage")
        return problems

    def evaluate(self) -> EvalResult:
        """Run the fact eval chain. The chain stops at the first failure."""
        combined = EvalResult(passed=True)
        for check in type(self).fact_evals:
            result = check.check(self)
            combined.scores.update({f"{check.name}.{k}": v for k, v in result.scores.items()})
            if result.skipped:
                combined.note = (combined.note + f" {check.name}: {result.note}").strip()
                continue
            if not result.passed:
                combined.passed = False
                combined.failed = [f"{check.name}.{name}" for name in result.failed]
                combined.near_miss = result.near_miss
                break
        return combined

    def repair(self, result: EvalResult) -> str | None:
        """One rewording for a near miss. Returns the new sentence, or None."""
        prompt = render(type(self).repair_prompt, fact=self, failed=result.failed,
                        passages=[q.text for q in self.quotes])
        raw = self.generate(prompt, json_mode=True)
        try:
            text = json.loads(raw).get("text")
        except (json.JSONDecodeError, AttributeError):
            return None
        return text if isinstance(text, str) and text.strip() else None

    @classmethod
    def assess_questions(cls) -> dict[str, Question]:
        """Every question `assess` asks: each trait's questions, then the time questions."""
        asked: dict[str, Question] = {}
        for trait in cls.traits:
            asked.update(trait.questions())
        asked["expires"] = Choice(cls.expires_question, EXPIRES)
        asked["lifetime"] = Choice(cls.lifetime_question, {name: name for name in cls.lifetime_ranges})
        return asked

    def assess(self) -> Judgments:
        """Traits and time properties, in one request."""
        judgments = current().client.ask(self.state(), type(self).assess_questions())
        carried, scores = [], {}
        for trait in type(self).traits:
            decided = trait.decide(self, judgments)
            scores[trait.key()] = float(judgments[trait.key()])
            if decided is True or (not isinstance(decided, bool) and float(decided) >= trait.threshold):
                carried.append(trait.key())
        self.trait_names, self.trait_scores = carried, scores
        run_step(self, "expiration", judgments)
        return judgments

    def expiration(self, judgments: Judgments) -> None:
        """Fill in `valid_from`, `expires`, and `lifetime` from the judgments and the text."""
        if self.valid_from is None:
            self.valid_from = self.source_datetime
        expires = judgments["expires"]
        self.expires = max(expires, key=expires.get)
        if self.valid_until is not None and self.expires == "estimated":
            self.expires = "at_deadline"
        if self.expires == "estimated":
            total = sum(judgments["lifetime"].values()) or 1.0
            self.lifetime = {k: round(v / total, 4) for k, v in judgments["lifetime"].items() if v > 0.001}
        else:
            self.lifetime = None

    def link(self) -> None:
        """Link each mention to an entity, finding or creating it."""
        from .entity import link_mention

        for mention in self.mentions:
            if mention.entity_id is None:
                link_mention(mention, self)

    def resolve(self) -> list[tuple[str, Fact, float]]:
        """Compare against stored facts that share an entity. Returns (answer, other, probability) per match."""
        app = current()
        candidates = app.related_facts(self, limit=type(self).resolve_candidates)
        if not candidates:
            return []
        keys = [f"F{i + 1}" for i in range(len(candidates))]
        state = {
            "new_fact": {"text": self.text, "date": _fmt(self.valid_from or self.source_datetime)},
            "stored_facts": {
                key: {"text": other.text, "date": _fmt(other.valid_from or other.source_datetime)}
                for key, other in zip(keys, candidates)
            },
        }
        questions = {key: Choice(type(self).resolve_question.format(key=key), RESOLVE_ANSWERS) for key in keys}
        judgments = app.client.ask(state, questions)
        out = []
        for key, other in zip(keys, candidates):
            answer = judgments[key]
            best = max(answer, key=answer.get)
            if best != "unrelated" and answer[best] >= type(self).resolve_threshold:
                out.append((best, other, answer[best]))
        return out

    def save(self) -> None:
        current().save_fact(self)

    # -- outcomes -------------------------------------------------------------------------------------------

    def supersede(self, older: Fact) -> None:
        """This fact replaces `older`, which was true until this one took effect."""
        app = current()
        until = self.valid_from or self.source_datetime
        app.store.set_fields(older.id, valid_until=format_datetime(until) if until else None)
        app.store.set_status(older.id, "superseded", "superseded", by=self.id)
        app.store.relate(self.id, older.id, "supersedes")
        self._trait_hooks("after_supersede", older)

    def end(self, older: Fact) -> None:
        app = current()
        until = self.valid_from or self.source_datetime
        app.store.set_fields(older.id, valid_until=format_datetime(until) if until else None)
        app.store.set_status(older.id, "ended", "ended", by=self.id)
        app.store.relate(self.id, older.id, "ends")
        self._trait_hooks("after_end", older)

    def correct(self, older: Fact) -> None:
        app = current()
        app.store.set_status(older.id, "corrected", "corrected", by=self.id)
        app.store.relate(self.id, older.id, "corrects")
        self._trait_hooks("after_correct", older)

    def contradict(self, other: Fact) -> None:
        app = current()
        self.status = "contradicted"
        app.store.set_status(other.id, "contradicted", "contradicted", with_=self.id)
        app.store.relate(self.id, other.id, "contradicts")
        self._trait_hooks("after_contradict", other)

    def retract(self, reason: str = "") -> None:
        current().store.set_status(self.id, "retracted", "retracted", reason=reason)
        self.status = "retracted"

    def restore(self) -> None:
        current().store.set_status(self.id, "current", "restored")
        self.status = "current"

    def _trait_hooks(self, name: str, other: Fact) -> None:
        for trait in type(self).traits:
            if trait.key() in self.trait_names:
                trait.call_hook(name, self, other)

    # -- reads ----------------------------------------------------------------------------------------------

    @classmethod
    def get(cls, fact_id: str) -> Fact | None:
        return current().load_fact(fact_id)

    @classmethod
    def search(cls, query: str, **options: Any) -> list[Any]:
        """Search facts. On a subclass, results are scoped to that class."""
        if cls is not Fact:
            options.setdefault("fact_class", cls)
        return current().search_facts(query, **options)

    @classmethod
    def unlinked(cls, since: str | None = None) -> list[Fact]:
        """Facts with a mention that matched no entity."""
        return current().unlinked_facts(since=since)

    @classmethod
    def all(cls, **filters: Any) -> list[Fact]:
        return current().list_facts(fact_class=None if cls is Fact else cls, **filters)


def _fmt(value: datetime | None) -> str | None:
    return format_datetime(value) if value else None

