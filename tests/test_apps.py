import threading

from test_pipeline import build

from factoid import Fact
from factoid.runtime import current

TEXT = ("Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
        "Orion may not assign the agreement without Vega's consent.")


def test_two_apps_in_one_process_keep_their_own_facts(make_app, fake):
    first = build(make_app, fake)
    second = build(make_app, fake)  # made last, so it is the fallback for threads with no active app
    seen = set()
    inner = fake.choice

    def choice(question, state, name):  # runs in pool threads: record which app they see
        seen.add(id(current()))
        return inner(question, state, name)

    fake.choice = choice
    result = first.ingest_text(TEXT, document_type=first.document_classes[0], uri="a.txt",
                               metadata={"signed_at": "2025-03-01T00:00:00Z"})
    assert result.facts and seen == {id(first)}
    assert first.stats()["facts"] == {"current": len(result.facts)} and not second.stats()["facts"]
    with first.active():
        assert Fact.get(result.facts[0].id) is not None
    with second.active():
        assert Fact.get(result.facts[0].id) is None


def test_a_thread_can_activate_its_own_app(make_app, fake):
    first, second = build(make_app, fake), build(make_app, fake)
    found = []

    def work():
        with first.active():
            found.append(current())

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert found == [first] and current() is second


def test_the_step_label_reaches_worker_threads(make_app, fake):
    from factoid.steps import current_step, labelled

    app = build(make_app, fake)
    with labelled("resolve"):
        seen = app.map(lambda _: current_step(), range(6))
    assert seen == ["resolve"] * 6


def test_two_classes_with_one_name_are_refused_in_one_app(make_app):
    import pytest

    def risk(module, **attrs):
        return type("Risk", (Fact,), {"__module__": module, "__doc__": "A risk.", **attrs})

    def make(facts):  # explicit lists: other tests register classes with names of their own
        return make_app(facts=facts, documents=[], entities=[])

    first, second = risk("project_a.facts"), risk("project_b.facts")
    with pytest.raises(ValueError, match="two fact classes are named 'Risk'"):
        make([first, second])
    renamed = risk("project_b.facts", class_name="DealRisk")
    app = make([first, renamed])
    assert app.fact_class("DealRisk") is renamed and app.fact_class("Risk") is first
    other = make([second])  # another app in the process keeps its own Risk
    assert other.fact_class("Risk") is second and other.fact_class("DealRisk") is Fact
