import json

import pytest
from test_pipeline import Contract, build

from factoid import Fact

META = {"signed_at": "2025-03-01T00:00:00Z"}
CAP = "Vega's liability to Orion is capped at $1M under the supply agreement."
ASSIGN = "Orion may not assign the supply agreement to anyone without Vega's written consent."


def _ingest(app, text):
    return app.ingest_text(text, document_type=Contract, metadata=META, uri="supply.txt")


def test_a_failed_resave_keeps_the_old_facts(make_app, fake):
    app = build(make_app, fake)
    first = _ingest(app, CAP + "\n\n" + ASSIGN)
    good = fake.generator

    def broken(prompt):
        raise RuntimeError("the model is down")

    fake.generator = broken
    with pytest.raises(RuntimeError):
        _ingest(app, CAP + "\n\n" + ASSIGN + "\n\nVega will deliver monthly to Orion.")
    assert {Fact.get(f.id).status for f in first.facts} == {"current"}
    fake.generator = good
    again = _ingest(app, CAP + "\n\n" + ASSIGN + "\n\nVega will deliver monthly to Orion.")
    assert {f.id for f in first.facts} <= {f.id for f in again.facts}


def test_a_dropped_fact_is_replaced_and_keeps_its_old_text(make_app, fake):
    app = build(make_app, fake)
    first = _ingest(app, CAP + "\n\n" + ASSIGN)
    old = next(f for f in first.facts if f.text == ASSIGN)
    _ingest(app, CAP)
    stored = Fact.get(old.id)
    assert stored.status == "replaced" and stored.valid_at() == 0.0
    event = app.store.events_for(old.id)[-1]
    assert event["type"] == "fact.replaced" and "by" not in json.loads(event["data"])
    revision = app.store.one("select revision from facts where id = ?", (old.id,))["revision"]
    quote = stored.quotes[0]
    assert app.store.document_text(old.document_id, revision)[quote.start:quote.end] == quote.text
    assert CAP in app.store.document_text(old.document_id) and ASSIGN not in app.store.document_text(old.document_id)
    assert old.id not in {h.fact.id for h in app.search_facts("assign")}


def test_the_judge_says_what_changed_and_what_is_restated(make_app, fake):
    app = build(make_app, fake)
    first = _ingest(app, CAP + "\n\n" + ASSIGN)
    old_cap = next(f for f in first.facts if f.text == CAP)
    old_assign = next(f for f in first.facts if f.text == ASSIGN)
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F"):
            new, stored = state["new_fact"]["text"], state["stored_facts"][name]["text"]
            if "$3M" in new and stored == CAP:
                return {k: (0.9 if k == "supersedes" else 0.02) for k, _ in question.options}
            if "written approval" in new and stored == ASSIGN:  # reworded, same claim
                return {k: (0.95 if k == "duplicate" else 0.01) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    raised = CAP.replace("$1M", "$3M")
    reworded = "Orion may not assign the supply agreement to anyone without Vega's written approval."
    second = _ingest(app, raised + "\n\n" + reworded)
    by_text = {f.text: f for f in second.facts}
    assert Fact.get(old_cap.id).status == "replaced"
    assert by_text[raised].id != old_cap.id
    assert {"fact_id": by_text[raised].id, "relation": "replaces"}.items() <= dict(
        next(r for r in app.store.relations(old_cap.id) if r["relation"] == "replaces")).items()
    assert by_text[reworded].id == old_assign.id and Fact.get(old_assign.id).text == reworded
    assert app.store.events_for(old_assign.id)[-1]["type"] == "fact.restated"
