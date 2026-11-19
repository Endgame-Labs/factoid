from test_pipeline import Company, Contract, build

from factoid import Fact, Mention


class CallNote(Contract):
    """A rep's note from a call with an account."""

    def context_entities(self):
        return [Mention(self.metadata["account"], kind="Company", keys={"crm_id": self.metadata["crm_id"]})]


def test_each_fact_carries_what_its_document_is_about(make_app, fake):
    app = build(make_app, fake)
    app.document_classes.append(CallNote)
    prompts = []
    inner = fake.generator

    def generator(prompt):
        prompts.append(prompt)
        return inner(prompt)

    fake.generator = generator
    meta = {"signed_at": "2026-11-01T00:00:00Z", "account": "Brightwater Logistics", "crm_id": "001A"}
    first = app.ingest_text("The rep agreed to send a pilot plan by 10 November 2026.", document_type=CallNote,
                            metadata=meta, uri="note-1.txt")
    second = app.ingest_text("Security must sign off before the pilot starts.", document_type=CallNote,
                             metadata={**meta, "account": "Brightwater"}, uri="note-2.txt")
    assert "This CallNote is about Brightwater Logistics." in prompts[0].replace("\n", " ")
    account = Company.get(app.store.entity_by_key("crm_id", "001A"))
    assert account is not None and account.name == "Brightwater Logistics"
    for fact in (*first.facts, *second.facts):  # the second note named it differently; the key links it
        context = [m for m in Fact.get(fact.id).mentions if m.role == "context"]
        assert [(m.entity_id, m.method) for m in context] == [(account.id, "context")]
    assert {f.id for f in account.facts()} == {f.id for f in (*first.facts, *second.facts)}


def test_a_document_without_context_changes_nothing(make_app, fake):
    app = build(make_app, fake)
    prompts = []
    inner = fake.generator
    fake.generator = lambda prompt: (prompts.append(prompt), inner(prompt))[1]
    result = app.ingest_text("Vega's liability to Orion is capped at $1M.", document_type=Contract,
                             metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="a.txt")
    assert "is about" not in prompts[0]
    assert all(m.role != "context" for f in result.facts for m in Fact.get(f.id).mentions)


class SidedCall(Contract):
    """A call transcript where the project knows which side each speaker is on."""

    def segment(self):
        passages = super().segment()
        for passage in passages:
            passage.attrs["side"] = "customer" if "Orion" in passage.text.split()[0] else "ours"
        return passages


def test_passage_attrs_reach_each_quote(make_app, fake):
    from factoid import api

    app = build(make_app, fake)
    result = app.ingest_text("Orion's team said the cap is $1M.\n\nVega's rep said consent is needed.",
                             document_type=SidedCall, metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="call.txt")
    sides = {f.text: Fact.get(f.id).quotes[0].attrs["side"] for f in result.facts}
    assert sides == {"Orion's team said the cap is $1M.": "customer", "Vega's rep said consent is needed.": "ours"}
    assert api.fact(app, result.facts[0].id)["quotes"][0]["attrs"]["side"] in ("customer", "ours")
