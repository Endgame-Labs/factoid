"""Entities: the things facts are about.

Each `Entity` subclass declares one kind of thing. The docstring describes it in plain language, and discovery uses
it to route extracted entities to the class. `unique_keys` lists identifiers that prove two records are the same
entity. Typed properties are class annotations, validated on write and stored in `props`.

An entity does not need a declared class: an extracted entity that matches no class is stored as a plain `Entity`
with a free-text `kind`.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar, get_type_hints

from pydantic import TypeAdapter, ValidationError

from .fact import Mention, new_id
from .judge import Choice, Noul
from .runtime import ModelCalls, Registered, current, stored_name
from .templates import render

if TYPE_CHECKING:
    from .fact import Fact

__all__ = ["MODEL_LINK", "PLACEHOLDER_QUESTION", "Entity", "link_mention"]

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"https?://[^\s/]+[^\s]*")
DOMAIN = re.compile(r"^(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})$", re.I)

PLACEHOLDER_QUESTION = Noul(
    "Is the mention a specific named thing, such as a named company, person, court, product, place, or titled "
    "document? Generic placeholders such as 'the tenant', 'the Company', 'the parties', 'someone', 'this "
    "Agreement', or a plain common noun are not.",
    true="A specific named thing.",
    false="A placeholder or a generic noun.",
)

#: Link thresholds for decision models whose probabilities run on a different scale from Jev's, which the default was
#: set on. Rune answers the link question at 0.99 for a true match and up to 0.96 for a near miss such as "Robert
#: Smith Jr." (decision 140).
MODEL_LINK: dict[str, float] = {"fireworks/rune": 0.975}


class Entity(Registered, ModelCalls):
    """A thing facts are about. Subclass it and write a docstring."""

    _registry: ClassVar[list[type]] = []

    STEPS: ClassVar[tuple[str, ...]] = (
        "identify", "create", "find", "where", "claim", "merge", "split", "retype", "related", "facts",
    )

    #: Identifiers that prove two records are the same entity. Email, domain, and URL count by default.
    unique_keys: ClassVar[list[str]] = []
    #: The probability the link question must reach to link a mention to an existing entity. None takes the decision
    #: model's value from `MODEL_LINK`, else 0.6.
    link_threshold: ClassVar[float | None] = None
    #: Asked when a mention may match an existing entity.
    link_question: ClassVar[str] = (
        "Is the mention \"{{ mention }}\" the same {{ kind }} as \"{{ entity.name }}\"?"
    )
    #: Guidance for discovery: what belongs in this class.
    discovery_guidance: ClassVar[str] = ""

    def __init__(self, name: str, *, id: str | None = None, kind: str | None = None,
                 aliases: list[str] | None = None, props: dict[str, Any] | None = None):
        self.id = id or new_id("ent")
        self.name = name
        self.kind = kind or _kind_of(type(self))
        self.aliases = list(aliases or [])
        self.props: dict[str, Any] = {}
        for key, value in (props or {}).items():
            self.set(key, value)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id} {self.name!r}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Entity) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in type(self).typed_props():
            return self.__dict__.get("props", {}).get(name)
        raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")

    @classmethod
    def link_bar(cls, app: Any) -> float:
        """`link_threshold` for the decision model: the class's own value, else the model's, else 0.6."""
        if cls.link_threshold is not None:
            return cls.link_threshold
        model = app.client.models.get("choose")
        return MODEL_LINK.get(getattr(model, "name", model) or "", 0.6)

    @classmethod
    def typed_props(cls) -> dict[str, Any]:
        hints = {}
        for klass in reversed(cls.__mro__):
            if klass in (Entity, Registered, ModelCalls, object) or not issubclass(klass, Entity):
                continue
            for name, hint in get_type_hints(klass).items():
                if not name.startswith("_") and "ClassVar" not in str(hint):
                    hints[name] = hint
        return hints

    def set(self, key: str, value: Any) -> None:
        """Set a property. Typed properties are validated."""
        hint = type(self).typed_props().get(key)
        if hint is not None and value is not None:
            try:
                value = TypeAdapter(hint).validate_python(value)
            except ValidationError as err:
                raise ValueError(f"{type(self).__name__}.{key}: {err.errors()[0]['msg']}") from err
        self.props[key] = value

    def state(self) -> dict[str, Any]:
        return {"entity": self.name, "kind": self.kind, "aliases": self.aliases, "props": self.props}

    # -- steps ----------------------------------------------------------------------------------------------

    @classmethod
    def create(cls, name: str, *, kind: str | None = None, props: dict[str, Any] | None = None,
               keys: dict[str, str] | None = None, aliases: list[str] | None = None) -> Entity:
        entity = cls(name, kind=kind, props=props, aliases=aliases)
        all_keys = dict(keys or {})
        for key in cls.unique_keys:
            if entity.props.get(key):
                all_keys[key] = str(entity.props[key])
        current().save_entity(entity, all_keys)
        return entity

    @classmethod
    def upsert(cls, name: str, *, keys: dict[str, Any], aliases: list[str] | None = None,
               props: dict[str, Any] | None = None) -> Entity:
        """For an app that keeps its own records: the entity with any of these keys, renamed and updated to match,
        or a new one. A renamed entity keeps its old name as an alias. No model call."""
        return current().upsert_entity(cls, name, keys=keys, aliases=aliases, props=props)

    def merge(self, other: Entity, reason: str = "") -> Entity:
        """Fold `other` into this entity: its facts' links, keys, names, and properties this one lacks."""
        return current().merge_entities(self, other, reason)

    def split(self, facts: list[Any], name: str, *, keys: dict[str, Any] | None = None,
              props: dict[str, Any] | None = None, reason: str = "") -> Entity:
        """A new entity named `name` takes this entity's links on the given facts (or fact ids)."""
        return current().split_entity(self, facts, name, keys=keys, props=props, reason=reason)

    # -- reads ----------------------------------------------------------------------------------------------

    @classmethod
    def get(cls, entity_id: str) -> Entity | None:
        return current().load_entity(entity_id)

    @classmethod
    def find(cls, name_or_key: str) -> Entity | None:
        """By a unique key value, then by name or alias."""
        app = current()
        for key in [*cls.unique_keys, "email", "domain", "url"]:
            entity_id = app.store.entity_by_key(key, name_or_key)
            if entity_id:
                found = app.load_entity(entity_id)
                if found is not None and isinstance(found, cls):
                    return found
        for row in app.store.entities_named(name_or_key):
            found = app.load_entity(row["id"])
            if found is not None and isinstance(found, cls):
                return found
        return None

    @classmethod
    def where(cls, **props: Any) -> list[Entity]:
        """Entities of this class whose properties equal the given values."""
        app = current()
        marks = ",".join("?" * len(_class_names(cls)))
        rows = app.store.query(f"select id, props from entities where merged_into is null and class in ({marks})",
                               _class_names(cls))
        out = []
        for row in rows:
            data = json.loads(row["props"])
            if all(data.get(k) == v for k, v in props.items()):
                found = app.load_entity(row["id"])
                if found is not None:
                    out.append(found)
        return out

    def facts(self, *, traits: list[Any] | None = None, since: str | None = None, role: str | None = None,
              include_retired: bool = False) -> list[Fact]:
        """Facts linked to this entity, newest first."""
        return current().entity_facts(self, traits=traits, since=since, role=role, include_retired=include_retired)

    def related(self) -> list[dict[str, Any]]:
        """Connected entities with co-mention counts and current relation facts, weighted by freshness."""
        return current().related_entities(self)


def _class_names(cls: type[Entity]) -> list[str]:
    if cls is Entity:
        return [stored_name(k) for k in Entity.registered()] + ["Entity"]
    return [stored_name(k) for k in Entity.registered() if issubclass(k, cls)]


def _kind_of(cls: type[Entity]) -> str | None:
    if cls is Entity:
        return None
    return re.sub(r"(?<!^)(?=[A-Z])", " ", cls.__name__).lower()


def _key_from_text(text: str) -> tuple[str, str] | None:
    if (m := EMAIL.fullmatch(text.strip())) is not None:
        return "email", m.group(0).lower()
    if (m := URL.fullmatch(text.strip())) is not None:
        return "url", m.group(0).lower()
    if (m := DOMAIN.fullmatch(text.strip())) is not None:
        return "domain", m.group(1).lower()
    return None


def link_mention(mention: Mention, fact: Fact) -> None:
    """Link a mention, from sure to unsure, stopping at the first step that settles it.

    1. An exact identifier from the source. 2. A unique key: email, domain, URL, or a class's unique key.
    3. A name belonging to one entity in the same document. 4. A name belonging to one entity in the store.
    5. A yes-or-no question for what is left. Then: refuse placeholders, or create the entity.
    """
    app = current()
    store = app.store
    # 1 and 2: keys
    keys = dict(mention.keys)
    found = _key_from_text(mention.text)
    if found:
        keys.setdefault(found[0], found[1])
    for key, value in keys.items():
        entity_id = store.entity_by_key(key, value)
        if entity_id:
            return _linked(mention, entity_id, "key", 1.0)
    # 3: same document, by name or by an alias the document gave
    norm = " ".join(mention.text.lower().split())
    names = [norm, *(" ".join(a.lower().split()) for a in mention.aliases)]
    doc_names = app.document_entities.setdefault(fact.document_id or "", {})
    for name in names:
        if name in doc_names:
            _remember(doc_names, names, doc_names[name])
            return _linked(mention, doc_names[name], "document_name", 1.0)
    # remembered placeholder decisions
    if norm in app.placeholders:
        mention.method = "placeholder"
        return None
    # 4: one entity in the store with that name or alias
    rows = store.entities_named(mention.text)
    by_alias = False
    if not rows:
        for alias in mention.aliases:
            rows = store.entities_named(alias)
            if rows:
                by_alias = True
                break
    # A match on the mention's own name settles it. A match on only a short alias does not: "Amendment No. 3" of
    # one contract is not "Amendment No. 3" of another, so an alias match goes to the question in step 5.
    if len(rows) == 1 and not by_alias:
        _remember(doc_names, names, rows[0]["id"])
        for alias in mention.aliases:
            app.add_alias(rows[0]["id"], alias)
        return _linked(mention, rows[0]["id"], "store_name", 1.0)
    # 5: ask about close candidates
    candidates = rows or app.similar_entities(mention.text, limit=5)
    if candidates:
        questions = {}
        for i, row in enumerate(candidates):
            cls = app.entity_class(row["class"])
            wording = render(cls.link_question, mention=mention.text, kind=row["kind"] or "thing",
                             entity={"name": row["name"]})
            questions[f"E{i}"] = Noul(wording.strip())
        state = {"fact": fact.text, "mention": mention.text, "mention_kind": mention.kind,
                 "mention_aliases": mention.aliases,
                 "candidates": {f"E{i}": {"name": r["name"], "kind": r["kind"],
                                          "aliases": json.loads(r["aliases"])} for i, r in enumerate(candidates)}}
        judgments = app.client.ask(state, questions)
        best = max(range(len(candidates)), key=lambda i: judgments[f"E{i}"])
        p = judgments[f"E{best}"]
        cls = app.entity_class(candidates[best]["class"])
        if p >= cls.link_bar(app):
            entity_id = candidates[best]["id"]
            for alias in [mention.text, *mention.aliases]:
                app.add_alias(entity_id, alias)
            _remember(doc_names, names, entity_id)
            return _linked(mention, entity_id, "decision", p)
    # discovery: route to a class, refuse placeholders, or create
    entity = discover_entity(mention, fact)
    if entity is None:
        app.placeholders.add(norm)
        mention.method = "placeholder"
        return None
    for key, value in keys.items():
        store.save_entity_key(key, value, entity.id)
    for alias in mention.aliases:
        app.add_alias(entity.id, alias)
    _remember(doc_names, names, entity.id)
    _linked(mention, entity.id, "created", 1.0)
    app.claim(entity)
    return None


def discover_entity(mention: Mention, fact: Fact) -> Entity | None:
    app = current()
    classes = [k for k in app.entity_classes if k is not Entity]
    questions: dict[str, Any] = {"named": PLACEHOLDER_QUESTION}
    if classes:
        options = {stored_name(k): k.description() + (f" {k.discovery_guidance}" if k.discovery_guidance else "")
                   for k in classes}
        options["_none"] = "None of these."
        questions["entity_class"] = Choice("Which kind of thing is the mention?", options)
    state = {"fact": fact.text, "mention": mention.text, "mention_kind": mention.kind}
    judgments = app.client.ask(state, questions)
    if judgments["named"] < app.placeholder_floor:
        return None
    cls: type[Entity] = Entity
    if classes:
        choice = judgments["entity_class"]
        best = max(choice, key=choice.get)
        if best != "_none" and choice[best] >= 0.5:
            cls = app.entity_class(best)
    kind = mention.kind if cls is Entity else None
    return cls.create(mention.text, kind=kind)


def _remember(doc_names: dict[str, str], names: list[str], entity_id: str) -> None:
    for name in names:
        doc_names.setdefault(name, entity_id)


def _linked(mention: Mention, entity_id: str, method: str, confidence: float) -> None:
    mention.entity_id = entity_id
    mention.method = method
    mention.confidence = round(float(confidence), 4)
