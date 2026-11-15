from __future__ import annotations

import json
import re

from factoid import Entity, Fact, FactTrait, ProseDocument


class Company(Entity):
    """A company that is a party to a deal or a contract."""

    unique_keys = ["domain"]
    jurisdiction: str


class LiabilityCap(FactTrait):
    """A limit on how much a party can owe."""


class SourceFact(Fact):
    """What a contract says."""

    traits = [LiabilityCap]


class Contract(ProseDocument):
    """A signed contract or an amendment to one."""

    @property
    def source_datetime(self):
        return self.metadata["signed_at"]


def extractor(prompt: str) -> str:
    """Turn every cited passage into a fact that names Vega and Orion."""
    facts = []
    for n, text in re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M):
        facts.append({"text": text, "passages": [int(n)],
                      "mentions": [{"name": "Vega", "kind": "company", "role": "subject"},
                                   {"name": "Orion", "kind": "company", "role": "about"}],
                      "valid_from": "2027-01-01T00:00:00Z" if "2027" in text else None})
    return json.dumps({"facts": facts})


def build(make_app, fake):
    fake.generator = extractor

    def noul(question, state):
        if "same company" in question.instructions:
            return 0.95
        if "trait" in question.instructions:
            return 0.9 if "cap" in json.dumps(state) else 0.1
        return 0.9

    def choice(question, state, name):
        options = [k for k, _ in question.options]
        if name.startswith("F"):  # resolve: the 2027 cap supersedes the old cap
            new = state["new_fact"]["text"]
            if "$2M" in new and "cap" in json.dumps(state["stored_facts"][name]):
                return {k: (0.9 if k == "supersedes" else 0.02) for k in options}
            return {k: (0.9 if k == "unrelated" else 0.02) for k in options}
        if name == "entity_class":
            return {k: (0.9 if k == "Company" else 0.1) for k in options}
        return fake._default_choice(question, state, name)

    fake.noul, fake.choice = noul, choice
    return make_app(documents=[Contract], entities=[Company], facts=[SourceFact])


def test_ingest_link_resolve_and_search(make_app, fake):
    app = build(make_app, fake)
    first = app.ingest_text(
        "Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
        "Orion may not assign the supply agreement to anyone without Vega's written consent.",
        document_type=Contract, metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="supply.txt")
    assert len(first.facts) == 2
    cap = first.facts[0]
    assert cap.has(LiabilityCap) and not first.facts[1].has(LiabilityCap)
    assert cap.expires == "estimated" and cap.lifetime
    assert {m.entity_id is not None for m in cap.mentions} == {True}

    vega = Company.find("Vega")
    assert vega is not None and isinstance(vega, Company)
    assert len(vega.facts()) == 2

    second = app.ingest_text(
        "Amendment 2 raises Vega's liability cap to Orion to $2M from January 1, 2027.",
        document_type=Contract, metadata={"signed_at": "2026-10-03T00:00:00Z"}, uri="amendment2.txt")
    assert len(second.facts) == 1
    old = Fact.get(cap.id)
    assert old.status == "superseded"
    assert old.valid_until is not None and old.valid_until.year == 2027

    hits = Fact.search("liability cap", about=vega, as_of="2027-02-01T00:00:00Z")
    assert hits[0].fact.text.startswith("Amendment 2")
    scoped = SourceFact.search("liability cap", traits=[LiabilityCap])
    assert all(h.fact.has(LiabilityCap) for h in scoped)

    related = vega.related()
    assert related[0]["entity"].name == "Orion"
    stats = app.stats()
    assert stats["facts"]["superseded"] == 1


def test_placeholders_are_refused(make_app, fake):
    app = build(make_app, fake)
    inner = fake.noul
    fake.noul = lambda q, s: 0.1 if "specific named thing" in q.instructions and s["mention"] == "Orion" else inner(q, s)
    result = app.ingest_text("Vega's liability is capped at $1M.", document_type=Contract,
                             metadata={"signed_at": "2025-03-01T00:00:00Z"})
    fact = result.facts[0]
    linked = {m.text: m.entity_id for m in fact.mentions}
    assert linked["Vega"] is not None and linked["Orion"] is None
    assert Fact.unlinked() == [fact]


def test_failed_floors_reject(make_app, fake):
    app = build(make_app, fake)
    inner = fake.noul
    fake.noul = lambda q, s: 0.05 if "worth keeping" in q.instructions else inner(q, s)
    result = app.ingest_text("Vega's liability is capped at $1M.", document_type=Contract,
                             metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert result.facts == [] and result.rejected[0].reasons == ["jev_floors.useful"]
