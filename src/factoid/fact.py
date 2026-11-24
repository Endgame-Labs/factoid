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
from .fact_evals import DecisionFloors, EvalResult, FactEval, Nli
from .judge import Choice, Judgments, Noul, Question
from .runtime import ModelCalls, Registered, current, stored_name
from .steps import run_step
from .templates import Template, builtin, render
from .trait import FactTrait
from .validity import EXPIRES, LIFETIME_RANGES, validity

if TYPE_CHECKING:
    from .entity import Entity

__all__ = ["MODEL_RESOLVE", "RESOLVE_ANSWERS", "Fact", "Mention", "Quote", "new_id"]


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
    section: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)  # copied from the passage


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
    "contradicts": "The two facts cannot both be true at the same time and in the same case, and neither replaces "
                   "the other.",
    "unrelated": "The facts are about different things, or both can be true at once, such as a rule and an exception "
                 "to it, or terms that apply in different cases. When the facts report what someone said, compare "
                 "what was said, not whether it was said: a later statement that changes an earlier one is not "
                 "unrelated because both statements were made.",
}


#: Resolve settings for decision models other than the default. Rune calls many pairs a supersession that only refer
#: to what changed, at probabilities a floor cannot separate from real ones, so each of its changes is checked with
#: `resolve_verify_question` (SPEC decision 94). Rune is also far surer of a contradiction than Jev, so it needs a
#: higher bar to flag one (decision 140).
MODEL_RESOLVE: dict[str, dict[str, Any]] = {
    "fireworks/rune": {"verify": 0.5, "contradiction": 0.95},
}


class Fact(Registered, ModelCalls):
    """A self-contained fact."""

    _registry: ClassVar[list[type]] = []

    STEPS: ClassVar[tuple[str, ...]] = (
        "classify", "validate", "evaluate", "repair", "assess", "expiration", "link", "resolve", "save",
        "supersede", "end", "correct", "contradict", "retract", "restore",
    )

    # -- level 2: settings ----------------------------------------------------------------------------------

    #: The traits facts of this class are asked about.
    traits: ClassVar[list[type[FactTrait]]] = []
    #: The fact eval chain.
    fact_evals: ClassVar[list[FactEval]] = [Nli(), DecisionFloors()]
    #: Extraction guidance: what counts as a fact for this class.
    guidance: ClassVar[str] = ""
    #: Lifetime ranges the decision model chooses from.
    lifetime_ranges = LIFETIME_RANGES
    #: How many stored facts a new fact is compared against in `resolve`.
    resolve_candidates: ClassVar[int] = 8
    #: The probability a resolve answer must reach; below it, the facts are treated as unrelated.
    resolve_threshold: ClassVar[float] = 0.6
    #: Answers that drop or flag a fact need more: a duplicate is merged away, and a contradiction marks both facts.
    #: Below these, the next best answer is used.
    duplicate_threshold: ClassVar[float] = 0.8
    #: None takes the decision model's value from `MODEL_RESOLVE`, else 0.75.
    contradiction_threshold: ClassVar[float | None] = None
    #: When the model is sure two facts state the same claim but not whether the value changed, a later fact from
    #: another document supersedes, but only if "supersedes" got at least this much. A restatement the model calls a
    #: duplicate at 0.78 and a change at 0 is not a change.
    resolve_split_floor: ClassVar[float] = 0.2
    #: When a new fact is a duplicate of one stored fact and also supersedes, ends, or corrects another, apply those
    #: changes too, made by the stored fact it confirms and dated at the new fact's date (issue #25). Off, a duplicate
    #: drops them.
    duplicate_applies_changes: ClassVar[bool] = True
    #: Markers in fact text that stand for a redacted value, such as "[*]" in filed contracts. Resolve shows each one to
    #: the decision model as "[redacted]", so a model that reads "[*]" as part of the text still sees that a hidden
    #: value can differ (issue #26). Stored text and quotes are unchanged.
    redaction_markers: ClassVar[list[str]] = []
    #: When "supersedes" and "corrects" together reach `resolve_threshold` but neither does alone, and the new fact is
    #: newer and from another document, take the larger of the two (issue #25): both say the old value no longer holds.
    pool_changes: ClassVar[bool] = True
    #: How sure the decision model must be that a new fact replaces an older one in a section replaced as a whole.
    replace_threshold: ClassVar[float] = 0.6
    #: Run one repair (a rewording) on a near miss.
    repair_enabled: ClassVar[bool] = True
    #: Ask the assess questions (traits and time) in the same decision request as the fact evals, instead of in a
    #: second request with the same fact. Off by default while evals decide (issue #7).
    assess_with_evaluate: ClassVar[bool] = False
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
    #: The answers to `resolve_question`, each with what it means. Keep the keys; reword the meanings.
    resolve_answers: ClassVar[dict[str, str]] = RESOLVE_ANSWERS
    #: How many stored facts one resolve request compares; None asks about all candidates at once. None here takes
    #: the decision model's value from `MODEL_RESOLVE`.
    resolve_batch: ClassVar[int | None] = None
    #: When set, a supersession, end, or correction is checked with `resolve_verify_question` and dropped below this
    #: probability. None here takes the decision model's value from `MODEL_RESOLVE`.
    resolve_verify: ClassVar[float | None] = None
    resolve_verify_question: ClassVar[str] = (
        "Does stored fact {key} itself state a term, amount, date, party, place, or rule that the new fact sets "
        "differently, so that what stored fact {key} says stops being true when the new fact takes effect? Answer no "
        "if stored fact {key} only refers to or depends on what changed, if it is about a different agreement or "
        "signing, or if both facts can be true at once."
    )
    repair_prompt: ClassVar[str | Template] = builtin("repair.md.j2")
    #: Guidance shown to the repair, after the document class's `repair_guidance`. The `guidance` block of
    #: `repair.md.j2` shows it.
    repair_guidance: ClassVar[str] = ""

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
        self.skipped_evals: list[str] = []  # fact evals that did not run on this fact, such as nli with no model

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
        if self.status in ("corrected", "retracted", "replaced"):
            return 0.0
        if self.status in ("superseded", "ended"):
            # Replaced at `valid_until`, so it held until then: no decay inside the window. A standing that "lasts
            # about a day" by its lifetime was still the standing the day after, if nothing replaced it sooner.
            return validity(moment, valid_from=self.valid_from, expires="never", valid_until=self.valid_until,
                            lifetime=None, seen_at=seen)
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
            before = self.document.text_before(self)
            if before:
                state["text_before_passages"] = before
        app = current()
        state["similar_stored_facts"] = [
            {"text": f.text, "source": app.document_title(f.document_id),
             "date": _fmt(f.valid_from or f.source_datetime)}
            for f in self.similar
        ]
        return state

    # -- fact classes ---------------------------------------------------------------------------------------

    @classmethod
    def classify(cls, fact: Fact, judgments: Judgments) -> bool | float | None:
        """How well `fact` fits this class. The default reads this class's share of one shared choice."""
        return judgments["fact_class"].get(stored_name(cls), 0.0)

    @classmethod
    def class_question(cls, candidates: list[type[Fact]]) -> dict[str, Question]:
        options = {stored_name(klass): klass.description() for klass in candidates}
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

    def fact_eval_chain(self) -> list[FactEval]:
        """The fact evals this fact must pass: its document class's chain when set, otherwise its class's."""
        chain = getattr(type(self.document), "fact_evals", None) if self.document is not None else None
        return list(type(self).fact_evals if chain is None else chain)

    def evaluate(self) -> EvalResult:
        """Run the fact eval chain. The chain stops at the first failure."""
        combined = EvalResult(passed=True)
        self.skipped_evals = []
        for check in self.fact_eval_chain():
            result = check.check(self)
            combined.scores.update({f"{check.name}.{k}": v for k, v in result.scores.items()})
            if result.skipped:
                combined.note = (combined.note + f" {check.name}: {result.note}").strip()
                self.skipped_evals.append(f"{check.name}: {result.note}")  # counted when the fact is saved
                continue
            if not result.passed:
                combined.passed = False
                combined.failed = [f"{check.name}.{name}" for name in result.failed]
                combined.short = []
                combined.near_miss = result.near_miss
                break
            combined.short += [f"{check.name}.{name}" for name in result.short]
        return combined

    def repair(self, result: EvalResult) -> list[str]:
        """One repair for a near miss: a rewording, or a split into several facts when it states several claims.
        Returns the new sentences, or an empty list."""
        split = any(name.endswith(".atomic") for name in result.failed)  # several claims: a rewording cannot fix it
        # Repair sees the document's title and context, as the extractor did: a cited sentence such as "The
        # expiration date is extended to March 26, 2006" does not name the parties, and the title does.
        document, wording = None, type(self).repair_prompt
        guidance = [type(self).repair_guidance.strip()]
        if self.document is not None:
            document = {"type": self.document.type, "title": self.document.title,
                        "context": self.document.context(), "text_before": self.document.text_before(self)}
            wording = getattr(type(self.document), "repair_prompt", None) or wording
            guidance.insert(0, str(getattr(type(self.document), "repair_guidance", "")).strip())
        trim = any(name.endswith(".grounded") for name in result.failed)  # says more than its passages
        prompt = render(wording, fact=self, failed=result.failed, split=split, trim=trim,
                        passages=[q.text for q in self.quotes], document=document,
                        guidance="\n".join(g for g in guidance if g))
        raw = self.generate(prompt, json_mode=True, step="repair")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []
        texts = data.get("facts") if isinstance(data.get("facts"), list) else [data.get("text")]
        return [t for t in texts if isinstance(t, str) and t.strip()][:6]

    def copy(self, text: str) -> Fact:
        """A new candidate with the same evidence and mentions, and a different sentence."""
        clone = type(self)(text, quotes=self.quotes, mentions=[Mention(**{**vars(m), "entity_id": None})
                                                                 for m in self.mentions],
                           document=self.document, chunk_id=self.chunk_id, valid_from=self.valid_from,
                           valid_until=self.valid_until, source_datetime=self.source_datetime,
                           extracted_at=self.extracted_at, document_id=self.document_id)
        clone.similar = self.similar
        return clone

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
        """Traits and time properties, in one request, or from the fact evals' request when they asked them."""
        early = getattr(self, "assessed_early", None)
        judgments = early[1] if early and early[0] == self.text else \
            current().client.ask(self.state(), type(self).assess_questions())
        carried, scores = [], {}
        for trait in type(self).traits:
            decided = trait.decide(self, judgments)
            scores[trait.key()] = float(judgments[trait.key()])
            if decided is True or (not isinstance(decided, bool) and float(decided) >= trait.bar()):
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
        klass = type(self)
        batch, verify = klass.resolve_settings(app)

        def shown(text: str) -> str:
            for marker in klass.redaction_markers:
                text = text.replace(marker, "[redacted]")
            return text

        new_fact = {"text": shown(self.text), "date": _fmt(self.valid_from or self.source_datetime),
                    "source": app.document_title(self.document_id)}

        def ask(group: list[Fact], make: Any) -> list[Any]:
            keys = [f"F{i + 1}" for i in range(len(group))]
            state = {"new_fact": new_fact, "stored_facts": {
                key: {"text": shown(other.text), "date": _fmt(other.valid_from or other.source_datetime),
                      "source": app.document_title(other.document_id)} for key, other in zip(keys, group)}}
            judgments = app.client.ask(state, {key: make(key) for key in keys})
            return [judgments[key] for key in keys]

        def batched(group: list[Fact], make: Any) -> list[Any]:
            size = batch or len(group)
            return [a for i in range(0, len(group), size) for a in ask(group[i:i + size], make)]

        answers = batched(candidates, lambda key: Choice(klass.resolve_question.format(key=key), klass.resolve_answers))
        out = self._resolve_outcomes(candidates, answers, klass.contradiction_bar(app))
        if verify is not None:
            changes = [o for o in out if o[0] in ("supersedes", "ends", "corrects")]
            if changes:
                sure = batched([o[1] for o in changes], lambda key: Noul(klass.resolve_verify_question.format(key=key)))
                dropped = {id(o[1]) for o, p in zip(changes, sure) if float(p) < verify}
                out = [o for o in out if id(o[1]) not in dropped]
        return out

    @classmethod
    def resolve_settings(cls, app: Any) -> tuple[int | None, float | None]:
        """`resolve_batch` and `resolve_verify` for the decision model: the class's own values, else the model's."""
        model = app.client.models.get("choose")
        defaults = MODEL_RESOLVE.get(getattr(model, "name", model) or "", {})
        return (cls.resolve_batch if cls.resolve_batch is not None else defaults.get("batch"),
                cls.resolve_verify if cls.resolve_verify is not None else defaults.get("verify"))

    @classmethod
    def contradiction_bar(cls, app: Any) -> float:
        """`contradiction_threshold` for the decision model: the class's own value, else the model's, else 0.75."""
        if cls.contradiction_threshold is not None:
            return cls.contradiction_threshold
        model = app.client.models.get("choose")
        return MODEL_RESOLVE.get(getattr(model, "name", model) or "", {}).get("contradiction", 0.75)

    def _resolve_outcomes(self, candidates: list[Fact], answers: list[Any],
                          contradiction: float = 0.75) -> list[tuple[str, Fact, float]]:
        out = []
        klass = type(self)
        bars = {"duplicate": klass.duplicate_threshold, "contradicts": contradiction}
        mine = self.valid_from or self.source_datetime
        for answer, other in zip(answers, candidates):
            theirs = other.valid_from or other.source_datetime
            same_subject = answer.get("duplicate", 0) + answer.get("supersedes", 0)
            if (max(answer, key=answer.get) in ("duplicate", "supersedes")
                    and answer[max(answer, key=answer.get)] < bars.get("duplicate", 1)
                    and same_subject >= klass.resolve_threshold and other.document_id != self.document_id
                    and answer.get("supersedes", 0) >= klass.resolve_split_floor
                    and mine is not None and theirs is not None and mine > theirs):
                # Sure it is the same claim, unsure whether the value changed, and newer from another source:
                # the newer version supersedes. Superseding a true duplicate only ends the old one at the new date.
                out.append(("supersedes", other, same_subject))
                continue
            change = answer.get("supersedes", 0) + answer.get("corrects", 0)
            top = max(answer, key=answer.get)
            if (klass.pool_changes and top in ("supersedes", "corrects") and answer[top] < klass.resolve_threshold
                    and change >= klass.resolve_threshold and other.document_id != self.document_id
                    and mine is not None and theirs is not None and mine > theirs):
                out.append((top, other, change))
                continue
            for choice in sorted(answer, key=answer.get, reverse=True):
                if answer[choice] >= bars.get(choice, klass.resolve_threshold):
                    if choice != "unrelated":
                        out.append((choice, other, answer[choice]))
                    break
                if choice in bars:
                    continue  # not confident enough to drop or flag: consider the next answer
                break
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

