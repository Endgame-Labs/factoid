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


def test_aliases_link_short_names_across_documents(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        name = "Vega Components Corp." if "Components" in prompt else "Vega"
        aliases = ["Vega"] if name != "Vega" else []
        n = int(re.search(r"^\[(\d+)\]", prompt, re.M).group(1))
        return json.dumps({"facts": [{"text": f"{name} supplies servo motors to Orion under a contract.",
                                      "passages": [n],
                                      "mentions": [{"name": name, "kind": "company", "aliases": aliases}]}]})

    fake.generator = generator
    app.ingest_text("Vega Components Corp. (\"Vega\") supplies servo motors.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="a.txt")
    app.ingest_text("Vega supplies the motors.", document_type=Contract,
                    metadata={"signed_at": "2025-04-01T00:00:00Z"}, uri="b.txt")
    vega = Company.find("Vega")
    assert vega is not None and vega.name == "Vega Components Corp."
    assert {f.document_id for f in vega.facts()} == {"doc_" + __import__("hashlib").sha256(b"a.txt").hexdigest()[:16],
                                                     "doc_" + __import__("hashlib").sha256(b"b.txt").hexdigest()[:16]}


def test_as_of_search_sees_facts_valid_then(make_app, fake):
    app = build(make_app, fake)
    app.ingest_text("Vega's liability to Orion is capped at $1M.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="c.txt")
    app.ingest_text("Amendment 2 raises Vega's liability cap to Orion to $2M from January 1, 2027.",
                    document_type=Contract, metadata={"signed_at": "2026-10-03T00:00:00Z"}, uri="d.txt")
    before = Fact.search("liability cap", as_of="2026-06-01T00:00:00Z")
    after = Fact.search("liability cap", as_of="2027-06-01T00:00:00Z")
    assert "$1M" in before[0].fact.text and before[0].fact.status == "superseded"
    assert "$2M" in after[0].fact.text


def test_cut_off_extraction_is_retried_in_halves(make_app, fake):
    app = build(make_app, fake)
    calls = []

    def generator(prompt):
        calls.append(prompt)
        passages = re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M)
        if len(passages) > 1:
            return '{"facts": [{"text": "cut off'  # truncated JSON
        return extractor(prompt)

    fake.generator = generator
    result = app.ingest_text("Vega's liability is capped at $1M.\n\nOrion may not assign the agreement.",
                             document_type=Contract, metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert len(calls) == 3 and len(result.facts) == 2


def test_rerank_sees_the_best_weighted_candidates(make_app, fake):
    app = build(make_app, fake)
    app.client.models["rerank"] = "fake"
    fake.rerank = lambda query, docs: [1.0 if "$2M" in d else 0.1 for d in docs]
    app.ingest_text("Vega's liability to Orion is capped at $1M.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="e.txt")
    app.ingest_text("Amendment 2 raises Vega's liability cap to Orion to $2M from January 1, 2027.",
                    document_type=Contract, metadata={"signed_at": "2026-10-03T00:00:00Z"}, uri="f.txt")
    hits = Fact.search("liability cap", as_of="2027-06-01T00:00:00Z")
    assert "$2M" in hits[0].fact.text and hits[0].score > hits[-1].score


def test_an_unsure_duplicate_keeps_the_new_fact(make_app, fake):
    app = build(make_app, fake)
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F"):
            return {k: (0.7 if k == "duplicate" else 0.06) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    app.ingest_text("Vega's liability to Orion is capped at $1M.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="g.txt")
    second = app.ingest_text("Vega's liability to Orion is capped at $1M in total.", document_type=Contract,
                             metadata={"signed_at": "2025-04-01T00:00:00Z"}, uri="h.txt")
    assert len(second.facts) == 1 and second.duplicates == 0


def test_a_compound_near_miss_is_split(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        if "failed these checks" in prompt:
            return json.dumps({"facts": ["Vega's liability to Orion is capped at $1M.",
                                         "Orion may not assign the agreement without Vega's consent."]})
        return extractor(prompt)

    inner = fake.noul

    def noul(question, state):
        if "one claim" in question.instructions:
            return 0.15 if " and " in state["fact"] else 0.9
        return inner(question, state)

    fake.generator, fake.noul = generator, noul
    result = app.ingest_text("Vega's liability is capped at $1M and Orion may not assign the agreement.",
                             document_type=Contract, metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert sorted(f.text for f in result.facts) == ["Orion may not assign the agreement without Vega's consent.",
                                                    "Vega's liability to Orion is capped at $1M."]
    assert all(f.scores["repaired_from"] for f in result.facts) and all(f.quotes for f in result.facts)
