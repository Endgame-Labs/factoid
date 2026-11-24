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

    replacement_pattern = r"in\s+(?:its|their)\s+entirety"
    partial_replacement_pattern = r"paragraph|subsection|clause|sentence|definition|proviso|\d\s*\([a-z0-9]+\)"
    deletion_pattern = r"(?s)^(?!.*(?:replaced|as follows|to read)).*deleted\s+in\s+(?:its|their)\s+entirety"

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
        if "specific named thing" in question.instructions and \
                str(state.get("mention", "")).lower() in ("agreement", "the agreement", "amendment"):
            return 0.1
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
    fake.noul = lambda q, s: (0.1 if "specific named thing" in q.instructions and s["mention"] == "Orion"
                              else inner(q, s))
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
    assert result.facts == [] and result.rejected[0].reasons == ["decision_floors.useful"]


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
    calls = []
    fake.rerank = lambda query, docs: calls.append(docs) or [1.0 if "$2M" in d else 0.1 for d in docs]
    hits = Fact.search("liability cap", as_of="2027-06-01T00:00:00Z")
    assert "$2M" in hits[0].fact.text and hits[0].score > hits[-1].score
    assert calls and any("$1M" in d for d in calls[-1]) and any("$2M" in d for d in calls[-1])
    # With freshness off and retired facts in, both facts weigh the same, so the reranker alone decides the order.
    for favorite in ("$1M", "$2M"):
        fake.rerank = lambda query, docs, f=favorite: [1.0 if f in d else 0.1 for d in docs]
        assert favorite in Fact.search("liability cap", freshness="any", include_retired=True)[0].fact.text


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
    # The skipped nli eval counts the 2 stored facts, not the candidate the repair replaced.
    assert dict(app.skipped_evals) == {"nli: no nli model is set; skipped": 2}


def test_same_claim_from_a_later_document_supersedes(make_app, fake):
    app = build(make_app, fake)
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F"):
            probs = {"duplicate": 0.4, "supersedes": 0.32, "unrelated": 0.18, "contradicts": 0.06}
            return {k: probs.get(k, 0.01) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    first = app.ingest_text("The territory is the United States and [*].", document_type=Contract,
                            metadata={"signed_at": "1996-10-01T00:00:00Z"}, uri="i.txt")
    app.ingest_text("The territory is amended to be United States, [*].", document_type=Contract,
                    metadata={"signed_at": "1998-07-15T00:00:00Z"}, uri="j.txt")
    assert Fact.get(first.facts[0].id).status == "superseded"


def test_sections_are_labeled():
    from factoid.document import Passage, label_sections

    passages = label_sections([Passage(1, 0, 1, "ARTICLE 3 FEES"), Passage(2, 0, 1, "Section 3.1 FEES. Pay 50%."),
                               Passage(3, 0, 1, "The fee is due monthly."), Passage(4, 0, 1, "3.2 Payment terms.")])
    assert [p.section for p in passages] == ["3", "3.1", "3.1", "3.2"]


def test_a_generic_defined_term_does_not_link_across_documents(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        name, alias = ("Supply Agreement between Orion and Vega", ["Agreement"]) if "Orion" in prompt else \
            ("Services Agreement between Acme and Globex", ["Agreement"])
        n = int(re.search(r"^\[(\d+)\]", prompt, re.M).group(1))
        return json.dumps({"facts": [{"text": f"The {name} is governed by Delaware law.", "passages": [n],
                                      "mentions": [{"name": name, "kind": "agreement", "aliases": alias}]}]})

    inner = fake.noul

    def noul(question, state):
        if question.instructions.startswith("Is the mention") and " the same " in question.instructions:
            names = re.findall(r'"([^"]+)"', question.instructions)
            return 0.95 if len(names) == 2 and names[0] == names[1] else 0.05
        return inner(question, state)

    fake.generator, fake.noul = generator, noul
    app.ingest_text("The Orion supply agreement is governed by Delaware law.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="k.txt")
    second = app.ingest_text("The Acme services agreement is governed by Delaware law.", document_type=Contract,
                             metadata={"signed_at": "2025-04-01T00:00:00Z"}, uri="l.txt")
    rows = app.store.query("select name, aliases from entities where name like '%Agreement between%'")
    assert len(rows) == 2 and all(json.loads(r["aliases"]) == [] for r in rows)
    linked = {f.mentions[0].entity_id for f in Fact.all()}
    assert len(linked) == 2 and second.facts


def test_a_section_replaced_in_its_entirety_retires_the_old_facts(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        facts = []
        for n, text in re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M):
            facts.append({"text": f"Under the supply agreement between Vega and Orion, {text}", "passages": [int(n)],
                          "mentions": [{"name": "Vega", "kind": "company"}, {"name": "Orion", "kind": "company"}]})
        return json.dumps({"facts": facts})

    fake.generator = generator
    base = app.ingest_text(
        "Section 3.1 FEES. Orion pays Vega a fee of 50% of revenues.\n\n"
        "Section 3.2 PAYMENT. Orion pays each fee 120 days after the invoice.\n\n"
        "Section 4 GOVERNING LAW. Delaware law governs the supply agreement.",
        document_type=Contract, metadata={"signed_at": "1996-01-01T00:00:00Z"}, uri="base.txt")
    app.ingest_text(
        "1. Section 3.2 of the supply agreement is amended to read in its entirety as follows.\n\n"
        "Section 3.2 PAYMENT. Orion pays each royalty 60 days after the invoice.",
        document_type=Contract, metadata={"signed_at": "1999-01-01T00:00:00Z"}, uri="amend.txt")
    statuses = {f.text.split(", ", 1)[1][:12]: Fact.get(f.id).status for f in base.facts}
    assert statuses == {"Section 3.1 ": "current", "Section 3.2 ": "superseded", "Section 4 GO": "current"}


def test_a_partial_amendment_does_not_retire_a_section():
    doc = Contract("1. Section 2.2 of the Development Agreement is hereby amended to allow Cargill to add staff.")
    assert doc.replacements(doc.segment()) == []


def test_a_replaced_section_without_a_kept_instruction_fact(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        facts = []
        for n, text in re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M):
            if "entirety" in text:
                continue  # the extractor kept no fact for the instruction itself
            facts.append({"text": f"Under the supply agreement between Vega and Orion, {text}", "passages": [int(n)],
                          "mentions": [{"name": "Vega", "kind": "company"}, {"name": "Orion", "kind": "company"}]})
        return json.dumps({"facts": facts})

    fake.generator = generator
    base = app.ingest_text("Section 3.2 PAYMENT. Orion pays each fee 120 days after the invoice.",
                           document_type=Contract, metadata={"signed_at": "1996-01-01T00:00:00Z"}, uri="b2.txt")
    app.ingest_text("1. Section 3.2 is amended to read in its entirety as follows.\n\n"
                    "Section 3.2 PAYMENT. Orion pays each royalty 60 days after the invoice.",
                    document_type=Contract, metadata={"signed_at": "1999-01-01T00:00:00Z"}, uri="a2.txt")
    assert Fact.get(base.facts[0].id).status == "superseded"


def test_replaced_sections_are_off_by_default():
    class Memo(ProseDocument):
        """A memo."""

    doc = Memo("1. Section 3.2 of the agreement is amended to read in its entirety as follows.")
    assert doc.replacements(doc.segment()) == []



def test_a_sibling_clause_in_a_replaced_section_stays_current(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        facts = []
        for n, text in re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M):
            facts.append({"text": f"Under the license between Fox and Glu, {text}", "passages": [int(n)],
                          "mentions": [{"name": "Fox", "kind": "company"}, {"name": "Glu", "kind": "company"}]})
        return json.dumps({"facts": facts})

    inner = fake.noul

    def noul(question, state):
        if "was replaced as a whole" in question.instructions:
            key = re.search(r"new fact (N\d+)", question.instructions).group(1)
            both = state["old_fact"] + state["new_facts"][key]
            return 0.9 if both.count("term") >= 2 else 0.05
        return inner(question, state)

    fake.generator, fake.noul = generator, noul
    base = app.ingest_text(
        "Section 4 TERM. The license term ends 18 months after each release.\n\n"
        "Glu has a right of first negotiation on new films during the Term.",
        document_type=Contract, metadata={"signed_at": "2004-12-16T00:00:00Z"}, uri="glu.txt")
    app.ingest_text(
        "1. The first paragraph of Section 4 is deleted in its entirety and replaced with the following.\n\n"
        "Section 4 TERM. The license term ends March 31, 2008.",
        document_type=Contract, metadata={"signed_at": "2007-02-19T00:00:00Z"}, uri="glu-a3.txt")
    statuses = {f.text.split(", ", 1)[1][:20]: Fact.get(f.id).status for f in base.facts}
    assert statuses == {"Section 4 TERM. The ": "superseded", "Glu has a right of f": "current"}


def test_a_whole_section_replaced_retires_restructured_clauses(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        facts = []
        for n, text in re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M):
            facts.append({"text": f"Under the agreement between Neon and Peregrine, {text}", "passages": [int(n)],
                          "mentions": [{"name": "Neon", "kind": "company"}, {"name": "Peregrine", "kind": "company"}]})
        return json.dumps({"facts": facts})

    inner = fake.noul
    fake.generator = generator
    fake.noul = lambda q, s: 0.2 if "was replaced as a whole" in q.instructions else inner(q, s)
    base = app.ingest_text("Section 3.2 PAYMENT. Fees are payable 120 days after the invoice.",
                           document_type=Contract, metadata={"signed_at": "1996-01-01T00:00:00Z"}, uri="n.txt")
    app.ingest_text("1. Section 3.2 is hereby amended to read in its entirety as follows.\n\n"
                    "Section 3.2 PAYMENT. Neon pays quarterly royalty advances.",
                    document_type=Contract, metadata={"signed_at": "1999-01-01T00:00:00Z"}, uri="n1.txt")
    assert Fact.get(base.facts[0].id).status == "superseded"


def test_a_rewrite_split_across_sentences_is_found():
    from factoid.document import Passage

    doc = Contract("x")
    passages = [Passage(1, 0, 1, "2. The text of Section 2."),
                Passage(2, 0, 1, "A. and B. of the Agreement is hereby deleted in its entirety and replaced.")]
    assert [r.sections for r in doc.replacements(passages)] == [["2"]]


def test_a_shared_short_alias_does_not_link_two_named_things(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        name = "Amendment No. 3 to the Orion Supply Agreement" if "Orion" in prompt else \
            "Amendment No. 3 to the Globex Services Agreement"
        n = int(re.search(r"^\[(\d+)\]", prompt, re.M).group(1))
        return json.dumps({"facts": [{"text": f"{name} extends the term to 2030.", "passages": [n],
                                      "mentions": [{"name": name, "kind": "agreement",
                                                    "aliases": ["Amendment No. 3"]}]}]})

    inner = fake.noul

    def noul(question, state):
        if question.instructions.startswith("Is the mention") and " the same " in question.instructions:
            names = re.findall(r'"([^"]+)"', question.instructions)
            return 0.95 if len(names) == 2 and names[0] == names[1] else 0.05
        return inner(question, state)

    fake.generator, fake.noul = generator, noul
    app.ingest_text("Amendment No. 3 to the Orion supply agreement extends the term.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="m.txt")
    app.ingest_text("Amendment No. 3 to the Globex services agreement extends the term.", document_type=Contract,
                    metadata={"signed_at": "2025-04-01T00:00:00Z"}, uri="n.txt")
    linked = {f.mentions[0].entity_id for f in Fact.all()}
    assert len(linked) == 2


def test_a_claimed_fact_is_found_under_its_new_entity(make_app, fake):
    app = build(make_app, fake)

    def generator(prompt):
        n = int(re.search(r"^\[(\d+)\]", prompt, re.M).group(1))
        if "first" in prompt:
            mentions = [{"name": "Orion", "kind": "company"}]
        else:
            mentions = [{"name": "Vega", "kind": "company"}]
        return json.dumps({"facts": [{"text": "Orion buys servo motors from Vega.", "passages": [n],
                                      "mentions": mentions}]})

    fake.generator = generator
    first = app.ingest_text("The first contract: Orion buys servo motors from Vega.", document_type=Contract,
                            metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="p.txt")
    app.ingest_text("Vega makes servo motors.", document_type=Contract,
                    metadata={"signed_at": "2025-04-01T00:00:00Z"}, uri="q.txt")
    vega = Company.find("Vega")
    hits = app.search_facts("servo motors", about=vega, freshness=False, include_retired=True)
    assert first.facts[0].id in {h.fact.id for h in hits}


def test_a_document_class_sets_its_own_fact_evals_and_questions(make_app, fake):
    from factoid import DecisionFloors, Noul

    class Transcript(ProseDocument):
        """A broadcast transcript."""

        fact_evals = [DecisionFloors(useful=0.01, questions={
            "atomic": None, "on_topic": Noul("Is the fact about the segment's topic?")}, on_topic=0.5)]

    app = build(make_app, fake)
    app.document_classes.append(Transcript)
    inner = fake.noul
    fake.noul = lambda q, s: 0.05 if "worth keeping" in q.instructions else inner(q, s)
    text = "VAUSE: The plane landed safely.\n\nVAUSE: It was carrying 200 passengers to Seattle."
    result = app.ingest_text(text, document_type=Transcript)
    assert result.facts and not result.rejected  # the transcript's own useful floor
    _, questions = fake.asked[-1] if "on_topic" in fake.asked[-1][1] else next(
        a for a in fake.asked if "on_topic" in a[1])
    assert "atomic" not in questions and "grounded" in questions
    second = next(s for s, q in fake.asked if "on_topic" in q and "200" in s["fact"])
    assert second["text_before_passages"].endswith("The plane landed safely.")
    result = app.ingest_text("Vega's liability is capped at $1M.", document_type=Contract,
                             metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert result.rejected[0].reasons == ["decision_floors.useful"]  # a contract keeps the fact class's chain


def test_decision_floors_check_their_settings():
    import pytest

    from factoid import DecisionFloors, Noul

    with pytest.raises(ValueError, match="no floor"):
        DecisionFloors(questions={"on_topic": Noul("On topic?")})
    with pytest.raises(ValueError, match="not asked"):
        DecisionFloors(questions={"atomic": None}, atomic=0.3)
    assert repr(DecisionFloors()) == "decision_floors"
    assert "grounded=0.3" in repr(DecisionFloors(grounded=0.3))


def test_a_fact_below_its_target_is_repaired_or_kept_as_it_was(make_app, fake):
    from factoid import DecisionFloors, Noul

    class Explicit(SourceFact):
        """What a contract says."""

        fact_evals = [DecisionFloors(questions={"explicit": Noul("Every reference resolved?")}, explicit=0.0,
                                targets={"explicit": 0.5})]

    app = build(make_app, fake)
    app.fact_classes = [Explicit]
    inner = fake.noul
    fake.noul = lambda q, s: (0.9 if "Vega Components" in s["fact"] else 0.2) if "resolved" in q.instructions \
        else inner(q, s)
    fake.generator = lambda p: (json.dumps({"facts": ["Vega Components Corp.'s liability is capped at $1M."]})
                                if "failed these checks" in p else extractor(p))
    result = app.ingest_text("Its liability is capped at $1M.", document_type=Contract,
                             metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert [f.text for f in result.facts] == ["Vega Components Corp.'s liability is capped at $1M."]
    fake.generator = lambda p: json.dumps({"facts": ["Its cap is $1M."]}) if "failed these checks" in p \
        else extractor(p)
    result = app.ingest_text("Its liability is capped at $2M.", document_type=Contract,
                             metadata={"signed_at": "2025-04-01T00:00:00Z"})
    assert [f.text for f in result.facts] == ["Its liability is capped at $2M."]  # the repair missed: kept as was
    assert result.facts[0].scores["repair_missed"][0]["failed"] == ["short: decision_floors.explicit"]


def test_repair_guidance_and_blocks_reach_the_repair(make_app, fake):
    from factoid import DecisionFloors, Noul

    class Explicit(SourceFact):
        """What a contract says."""

        repair_guidance = "Fact rule: keep an open reference as worded."
        fact_evals = [DecisionFloors(questions={"explicit": Noul("Every reference resolved?")}, explicit=0.0,
                                targets={"explicit": 0.5})]

    class GuidedContract(Contract):
        """A contract, with rules for the repair."""

        repair_guidance = "Document rule: never guess a name."

    app = build(make_app, fake)
    app.document_classes = [*app.document_classes, GuidedContract]
    app.fact_classes = [Explicit]
    inner = fake.noul
    fake.noul = lambda q, s: (0.9 if "Vega Components" in s["fact"] else 0.2) if "resolved" in q.instructions \
        else inner(q, s)
    prompts = []

    def generator(p):
        if "failed these checks" not in p:
            return extractor(p)
        prompts.append(p)
        return json.dumps({"facts": ["Vega Components Corp.'s liability is capped at $1M."]})

    fake.generator = generator
    app.ingest_text("Its liability is capped at $1M.", document_type=GuidedContract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert "Document rule: never guess a name.\nFact rule: keep an open reference as worded." in prompts[-1]

    # A project template extends the built-in one and replaces a block.
    GuidedContract.repair_prompt = (
        '{% extends "factoid/repair.md.j2" %}{% block references %}Keep every reference as worded.\n{% endblock %}')
    app.ingest_text("Its liability is capped at $3M.", document_type=GuidedContract,
                    metadata={"signed_at": "2025-05-01T00:00:00Z"})
    assert "Keep every reference as worded." in prompts[-1] and "First list every reference" not in prompts[-1]
    assert "Document rule" in prompts[-1]


def test_decision_floors_use_a_decision_models_own_floors_unless_the_project_set_one():
    from factoid.fact_evals import DEFAULT_FLOORS, DEFAULT_TARGETS, MODEL_FLOORS, MODEL_TARGETS, DecisionFloors

    floors, targets = DecisionFloors().floors_for("typesafe/jev-1.13.0")
    assert floors == DEFAULT_FLOORS and targets == DEFAULT_TARGETS
    floors, targets = DecisionFloors().floors_for("fireworks/rune")
    assert floors["atomic"] == MODEL_FLOORS["fireworks/rune"]["atomic"]
    assert targets["self_contained"] == MODEL_TARGETS["fireworks/rune"]["self_contained"]
    floors, targets = DecisionFloors(atomic=0.3, targets={"self_contained": 0.6}).floors_for("fireworks/rune")
    assert floors["atomic"] == 0.3 and targets["self_contained"] == 0.6
    assert floors["useful"] == MODEL_FLOORS["fireworks/rune"]["useful"]

    class Strict(DecisionFloors):
        floors = {**DEFAULT_FLOORS, "atomic": 0.4}

    strict = Strict().floors_for("fireworks/rune")[0]
    assert strict["atomic"] == 0.4
    # The subclass changed only atomic, so Rune keeps its own floors for every other question.
    assert all(strict[k] == v for k, v in MODEL_FLOORS["fireworks/rune"].items() if k != "atomic")


def test_reingesting_skips_an_unchanged_document_and_keeps_unchanged_fact_ids(make_app, fake):
    app = build(make_app, fake)
    meta = {"signed_at": "2025-03-01T00:00:00Z"}
    text = ("Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
            "Orion may not assign the supply agreement to anyone without Vega's written consent.")
    first = app.ingest_text(text, document_type=Contract, metadata=meta, uri="supply.txt")
    ids = {f.text: f.id for f in first.facts}

    again = app.ingest_text(text, document_type=Contract, metadata=meta, uri="supply.txt")
    assert again.unchanged and {f.id for f in again.facts} == set(ids.values())

    edited = app.ingest_text(text + "\n\nVega will deliver monthly to Orion.", document_type=Contract,
                             metadata=meta, uri="supply.txt")
    assert not edited.unchanged and len(edited.facts) == 3
    for fact in edited.facts:
        if fact.text in ids:
            assert fact.id == ids[fact.text] and Fact.get(fact.id).status == "current"
    events = [r["type"] for r in app.store.events_for(ids[first.facts[0].text])]
    assert events[-1] == "fact.restated"


def test_a_document_whose_ingest_failed_is_ingested_again(make_app, fake):
    import pytest

    app = build(make_app, fake)
    meta = {"signed_at": "2025-03-01T00:00:00Z"}
    text = "Vega's liability to Orion is capped at $1M under the supply agreement."
    good = fake.generator

    def broken(prompt):
        raise RuntimeError("the model is down")

    fake.generator = broken
    with pytest.raises(RuntimeError):
        app.ingest_text(text, document_type=Contract, metadata=meta, uri="supply.txt")
    fake.generator = good
    again = app.ingest_text(text, document_type=Contract, metadata=meta, uri="supply.txt")
    assert not again.unchanged and len(again.facts) == 1


def test_chunk_search_finds_source_text(make_app, fake):
    from factoid import Chunk

    app = build(make_app, fake)
    app.ingest_text("Vega's liability to Orion is capped at $1M under the supply agreement.",
                    document_type=Contract, metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="supply.txt")
    rows = Chunk.search("liability capped")
    assert rows and "capped" in rows[0]["text"]
    assert Chunk.search("liability capped", about=Company.find("Vega"))


def _ingest_cap_and_amendment(app):
    first = app.ingest_text(
        "Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
        "Orion may not assign the supply agreement to anyone without Vega's written consent.",
        document_type=Contract, metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="supply.txt")
    app.ingest_text("Amendment 2 raises Vega's liability cap to Orion to $2M from January 1, 2027.",
                    document_type=Contract, metadata={"signed_at": "2026-10-03T00:00:00Z"}, uri="amendment2.txt")
    return Fact.get(first.facts[0].id)


def test_resolve_verify_drops_a_supersession_the_check_rejects(make_app, fake, monkeypatch):
    app = build(make_app, fake)
    inner = fake.noul
    fake.noul = lambda q, s: 0.2 if "itself state" in q.instructions else inner(q, s)
    monkeypatch.setattr(SourceFact, "resolve_verify", 0.5)
    assert _ingest_cap_and_amendment(app).status == "current"
    assert any("itself state" in q.instructions for _, qs in fake.asked for q in qs.values())


def test_resolve_verify_keeps_a_supersession_the_check_confirms(make_app, fake, monkeypatch):
    app = build(make_app, fake)
    monkeypatch.setattr(SourceFact, "resolve_verify", 0.5)
    assert _ingest_cap_and_amendment(app).status == "superseded"
    assert any("itself state" in q.instructions for _, qs in fake.asked for q in qs.values())


def test_resolve_batch_asks_about_one_stored_fact_per_request(make_app, fake, monkeypatch):
    app = build(make_app, fake)
    monkeypatch.setattr(SourceFact, "resolve_batch", 1)
    assert _ingest_cap_and_amendment(app).status == "superseded"
    resolves = [s for s, qs in fake.asked if isinstance(s, dict) and "stored_facts" in s]
    assert resolves and all(len(s["stored_facts"]) == 1 for s in resolves)
    assert len(resolves) >= 2  # the amendment's fact is compared with both stored facts, one at a time


def test_rune_gets_its_resolve_check_by_default(make_app, fake):
    app = build(make_app, fake)
    fake.models["choose"] = type("M", (), {"name": "fireworks/rune"})()
    assert SourceFact.resolve_settings(app) == (None, 0.5)
    fake.models["choose"] = "fake"
    assert SourceFact.resolve_settings(app) == (None, None)


def test_rune_gets_its_own_contradiction_and_link_bars(make_app, fake, monkeypatch):
    from factoid import Entity

    app = build(make_app, fake)
    fake.models["choose"] = type("M", (), {"name": "fireworks/rune"})()
    assert (SourceFact.contradiction_bar(app), Entity.link_bar(app)) == (0.95, 0.975)
    monkeypatch.setattr(SourceFact, "contradiction_threshold", 0.8)
    monkeypatch.setattr(Entity, "link_threshold", 0.7)
    assert (SourceFact.contradiction_bar(app), Entity.link_bar(app)) == (0.8, 0.7)  # a project's own value wins
    fake.models["choose"] = "fake"
    monkeypatch.setattr(SourceFact, "contradiction_threshold", None)
    monkeypatch.setattr(Entity, "link_threshold", None)
    assert (SourceFact.contradiction_bar(app), Entity.link_bar(app)) == (0.75, 0.6)


def _answer(fake, answer, new_has, old_has):
    """Make resolve give `answer` when a new fact containing `new_has` meets a stored fact containing `old_has`."""
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F") and new_has in state["new_fact"]["text"] \
                and old_has in json.dumps(state["stored_facts"][name]):
            return {k: (0.9 if k == answer else 0.01) for k, _ in question.options}
        if name.startswith("F"):
            return {k: (0.9 if k == "unrelated" else 0.01) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice


def _cap(app, text, signed, uri):
    return app.ingest_text(text, document_type=Contract, metadata={"signed_at": signed}, uri=uri)


def test_a_duplicate_confirms_the_stored_fact(make_app, fake):
    app = build(make_app, fake)
    _answer(fake, "duplicate", "$1M", "$1M")
    first = _cap(app, "Vega's liability to Orion is capped at $1M.", "2025-03-01T00:00:00Z", "a.txt").facts[0]
    second = _cap(app, "Vega's liability to Orion is capped at $1M.", "2025-06-01T00:00:00Z", "b.txt")
    assert second.facts == [] and second.duplicates == 1
    assert {q["document_id"] for q in app.store.quotes(first.id)} == {first.document_id, second.document.id}
    assert app.stats()["facts"] == {"current": 1}


def test_a_correction_was_never_true(make_app, fake):
    app = build(make_app, fake)
    _answer(fake, "corrects", "$2M", "$1M")
    old = _cap(app, "Vega's liability to Orion is capped at $1M.", "2025-03-01T00:00:00Z", "a.txt").facts[0]
    new = _cap(app, "Vega's liability to Orion was always capped at $2M.", "2025-06-01T00:00:00Z", "b.txt").facts[0]
    old = Fact.get(old.id)
    assert old.status == "corrected" and old.valid_at("2025-04-01T00:00:00Z") == 0.0
    assert (new.id, "corrects", old.id) in [(r["fact_id"], r["relation"], r["other_id"])
                                            for r in app.store.relations(old.id)]
    # An as-of search before the correction still leaves the wrong fact out.
    assert old.id not in {h.fact.id for h in Fact.search("liability cap", as_of="2025-04-01T00:00:00Z")}


def test_an_end_closes_the_old_fact_at_the_new_one(make_app, fake):
    app = build(make_app, fake)
    _answer(fake, "ends", "no longer", "$1M")
    old = _cap(app, "Vega's liability to Orion is capped at $1M.", "2025-03-01T00:00:00Z", "a.txt").facts[0]
    _cap(app, "Vega's liability to Orion is no longer capped from 2027.", "2026-10-03T00:00:00Z", "b.txt")
    old = Fact.get(old.id)
    assert old.status == "ended" and old.valid_until.date().isoformat() == "2027-01-01"
    assert old.id in {h.fact.id for h in Fact.search("liability cap", as_of="2026-06-01T00:00:00Z")}


def test_a_later_restatement_does_not_supersede(make_app, fake):
    # A counsel email restating a contract clause: duplicate 0.78, just under the bar, and no weight on a change.
    app = build(make_app, fake)
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F"):
            probs = {"duplicate": 0.78, "unrelated": 0.22}
            return {k: probs.get(k, 0.0) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    first = app.ingest_text("The territory is the United States and [*].", document_type=Contract,
                            metadata={"signed_at": "1996-10-01T00:00:00Z"}, uri="i.txt")
    app.ingest_text("Counsel says the territory is the United States and [*].", document_type=Contract,
                    metadata={"signed_at": "1998-07-15T00:00:00Z"}, uri="j.txt")
    assert Fact.get(first.facts[0].id).status == "current"


def test_a_grounded_failure_is_trimmed_unless_turned_off(make_app, fake):
    from factoid import DecisionFloors, Nli

    app = build(make_app, fake)
    prompts = []

    def noul(question, state):
        if question.instructions.startswith("Do the cited passages support the claim"):
            return 0.2 if "January 2027" in str(state.get("fact")) else 0.95
        return 0.9

    def generator(prompt):
        prompts.append(prompt)
        if "Rewrite the fact" in prompt or "Split it" in prompt:
            return json.dumps({"references": [], "facts": ["The second clinic's network upgrade slips to January."]})
        return json.dumps({"facts": [{"text": "The second clinic's network upgrade slips to January 2027.",
                                      "passages": [1], "mentions": [{"name": "Orion", "kind": "company",
                                                                     "role": "subject"}]}]})

    fake.noul, fake.generator = noul, generator
    note = "Grace Liu raised that the second clinic's network upgrade slips to January."
    meta = {"signed_at": "2026-11-01T00:00:00Z"}
    kept = app.ingest_text(note, document_type=Contract, metadata=meta, uri="a.txt").facts
    assert [f.text for f in kept] == ["The second clinic's network upgrade slips to January."]
    assert any("Keep only what they state" in p for p in prompts)
    SourceFact.fact_evals = [Nli(), DecisionFloors(repair_grounded=False)]
    try:
        assert app.ingest_text(note, document_type=Contract, metadata=meta, uri="b.txt").facts == []
    finally:
        del SourceFact.fact_evals


def test_assess_can_ride_along_with_the_fact_evals(make_app, fake):
    text = "Vega's liability to Orion is capped at $1M under the supply agreement."
    meta = {"signed_at": "2025-03-01T00:00:00Z"}
    counts = []
    for early in (False, True):
        app = build(make_app, fake)
        asks = []
        inner = fake.ask
        fake.ask = lambda state, questions, inner=inner, asks=asks: (asks.append(sorted(questions)),
                                                                     inner(state, questions))[1]
        SourceFact.assess_with_evaluate = early
        try:
            fact = app.ingest_text(text, document_type=Contract, metadata=meta, uri=f"{early}.txt").facts[0]
        finally:
            del SourceFact.assess_with_evaluate
            fake.ask = inner
        counts.append(len(asks))
        assert fact.trait_names == ["liability_cap"] and fact.expires is not None
    assert counts[1] == counts[0] - 1  # one request fewer for the one fact


def test_rune_gets_its_own_trait_bar(make_app, fake, monkeypatch):
    from factoid import FactTrait
    from factoid.runtime import active

    class Plain(FactTrait):
        """A plain trait."""

    class Own(FactTrait):
        """A trait with its own bar."""

        threshold = 0.6

    app = build(make_app, fake)
    with active(app):
        fake.models["choose"] = type("M", (), {"name": "fireworks/rune"})()
        assert (Plain.bar(), Own.bar()) == (0.85, 0.6)
        assert not Plain.decide(None, {"plain": 0.8}) and Plain.decide(None, {"plain": 0.9})
        fake.models["choose"] = "fake"
        assert (Plain.bar(), Own.bar()) == (0.5, 0.6)


def _resolve_as(fake, table):
    """Resolve answers by (text in the new fact, text in the stored fact): a dict of answer probabilities."""
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F"):
            new, old = state["new_fact"]["text"], json.dumps(state["stored_facts"][name])
            for (new_has, old_has), probs in table.items():
                if new_has in new and old_has in old:
                    return {k: probs.get(k, 0.0) for k, _ in question.options}
            return {k: (1.0 if k == "unrelated" else 0.0) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice


def test_a_duplicate_can_still_apply_its_other_changes(make_app, fake, monkeypatch):
    # Issue #25: the new fact repeats the $2M cap and also replaces the $1M cap.
    table = {("liability is capped at $2M", "$2M"): {"duplicate": 0.9},
             ("liability is capped at $2M", "$1M"): {"supersedes": 0.9}}
    for on in (False, True):
        app = build(make_app, fake)
        _resolve_as(fake, table)
        monkeypatch.setattr(SourceFact, "duplicate_applies_changes", on)
        old = _cap(app, "Vega's liability to Orion is capped at $1M.", "2025-01-01T00:00:00Z", "a.txt").facts[0]
        dup = _cap(app, "Orion's liability to Vega is capped at $2M.", "2025-02-01T00:00:00Z", "b.txt").facts[0]
        later = _cap(app, "Vega's liability is capped at $2M.", "2025-06-01T00:00:00Z", "c.txt")
        assert later.facts == [] and later.duplicates == 1
        old = Fact.get(old.id)
        if not on:
            assert old.status == "current"
            continue
        assert old.status == "superseded" and old.valid_until.date().isoformat() == "2025-06-01"
        assert (dup.id, "supersedes", old.id) in [(r["fact_id"], r["relation"], r["other_id"])
                                                  for r in app.store.relations(old.id)]


def test_a_change_split_between_supersedes_and_corrects_can_be_pooled(make_app, fake, monkeypatch):
    # Issue #25: supersedes 0.45 and corrects 0.25 each miss the 0.6 bar, but together say the old value is gone.
    for on in (False, True):
        app = build(make_app, fake)
        _resolve_as(fake, {("$2M", "$1M"): {"supersedes": 0.45, "corrects": 0.25, "unrelated": 0.3}})
        monkeypatch.setattr(SourceFact, "pool_changes", on)
        old = _cap(app, "Vega's liability to Orion is capped at $1M.", "2025-01-01T00:00:00Z", "a.txt").facts[0]
        _cap(app, "Vega's liability to Orion is capped at $2M.", "2025-06-01T00:00:00Z", "b.txt")
        assert Fact.get(old.id).status == ("superseded" if on else "current")


def test_resolve_shows_redaction_markers_as_redacted(make_app, fake, monkeypatch):
    app = build(make_app, fake)
    seen = []
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F"):
            seen.append(json.dumps(state))
        return inner(question, state, name)

    fake.choice = choice
    monkeypatch.setattr(SourceFact, "redaction_markers", ["[*]"])
    _cap(app, "Vega's liability to Orion is capped at $1M and [*].", "2025-01-01T00:00:00Z", "a.txt")
    _cap(app, "Vega's liability to Orion is capped at $2M and [*].", "2025-06-01T00:00:00Z", "b.txt")
    assert seen and all("[*]" not in s for s in seen) and any("[redacted]" in s for s in seen)
    assert any("[*]" in f.text for f in app.list_facts())  # stored text is unchanged
