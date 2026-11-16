from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from click.testing import CliRunner

from factoid import Choice, Fact, Noul, ProseDocument, Raw, judge
from factoid.cli import cli
from factoid.document import ClassificationError, classify_raw
from factoid.evals import aupr, fact_eval_chain, parse_vary, precision_at_recall, prf
from factoid.validity import validity


class Memo(ProseDocument):
    """A memo a lawyer wrote about a deal."""


class Filing(ProseDocument):
    """A court filing."""

    @classmethod
    @judge(is_filing=Noul("Is this a court filing?"), court=Choice("Which court?", ["federal", "state", "none"]))
    def classify(cls, raw, judgments):
        if judgments.is_filing > 0.9 and judgments.court["none"] < 0.5:
            return True
        if judgments.is_filing < 0.3:
            return False
        return None


def asker(answers):
    def ask(state, questions):
        from factoid.judge import Judgments

        out = {}
        for name, q in questions.items():
            if name in answers:
                out[name] = answers[name]
            elif isinstance(q, Choice):
                out[name] = {k: 0.0 for k, _ in q.options}
            else:
                out[name] = 0.0
        return Judgments(out)

    return ask


def test_classify_default_and_judge():
    raw = Raw("MEMORANDUM to the deal team about Vega's consent.")
    klass, _ = classify_raw(raw, [Memo, Filing], asker({
        "document_class": {"Memo": 0.95, "Filing": 0.05}, "any_document_class": 0.9, "is_filing": 0.1}))
    assert klass is Memo
    klass, _ = classify_raw(raw, [Memo, Filing], asker({
        "document_class": {"Memo": 0.5, "Filing": 0.5}, "any_document_class": 0.9, "is_filing": 0.5,
        "court": {"federal": 0.5, "state": 0.4, "none": 0.1}}))
    assert klass is None  # the middle band goes to review


def test_two_claims_is_an_error():
    raw = Raw("text")
    with pytest.raises(ClassificationError):
        classify_raw(raw, [Memo, Filing], asker({
            "document_class": {"Memo": 0.95, "Filing": 0.05}, "any_document_class": 0.9, "is_filing": 0.95,
            "court": {"federal": 0.9, "state": 0.1, "none": 0.0}}))


def test_validity():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    later = start + timedelta(days=365)
    assert validity(later, valid_from=start, expires="never", valid_until=None, lifetime=None, seen_at=None) == 1.0
    assert validity(start - timedelta(days=1), valid_from=start, expires="estimated", valid_until=None,
                    lifetime={"year": 1.0}, seen_at=None) == 0.0
    p = validity(later, valid_from=start, expires="estimated", valid_until=None, lifetime={"year": 1.0},
                 seen_at=start)
    assert 0.3 < p < 0.4  # exp(-1)
    assert validity(later, valid_from=start, expires="at_deadline", valid_until=start + timedelta(days=30),
                    lifetime=None, seen_at=None) == 0.5


def test_fact_classes_are_chosen_per_fact(make_app, fake):
    class ClientFact(Fact):
        """What a client told us."""

    class CounselView(Fact):
        """What our lawyers concluded."""

    def generator(prompt):
        return json.dumps({"facts": [
            {"text": "Acme's general counsel said Vega must consent to the assignment.", "passages": [1]},
            {"text": "Our deal team concluded that Vega's consent is a closing risk for Acme.", "passages": [2]},
        ]})

    def choice(question, state, name):
        if name == "fact_class":
            mine = "CounselView" if "concluded" in state["fact"] else "ClientFact"
            return {k: (0.9 if k.endswith(mine) else 0.1) for k, _ in question.options}
        return fake._default_choice(question, state, name)

    fake.generator, fake.choice = generator, choice
    app = make_app(documents=[Memo], entities=[], facts=[ClientFact, CounselView])
    result = app.ingest_text("Vega must consent.\n\nWe think consent is a closing risk.", document_type=Memo)
    assert [type(f).__name__ for f in result.facts] == ["ClientFact", "CounselView"]
    assert [f.text for f in CounselView.all()] == [result.facts[1].text]


def test_vary_and_metrics():
    variants = parse_vary(["fact_evals=none,jev_floors(atomic=0.2;grounded=0.4)", "situate=on,off"])
    assert len(variants) == 4
    chain = fact_eval_chain("jev_floors(atomic=0.2;grounded=0.4)")
    assert chain[1].floors["atomic"] == 0.2
    assert prf(8, 2, 2)["f1"] == 0.8
    assert aupr([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert precision_at_recall([0.9, 0.5, 0.4], [True, False, True], 1.0) == pytest.approx(0.6667, abs=1e-3)


def test_init_scaffolds_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["init", "--package", "deal"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "deal" / "facts.py").is_file()
    assert "[tool.factoid]" in (tmp_path / "pyproject.toml").read_text()


def test_fireworks_model_ids():
    from factoid import Model

    assert Model("fireworks/glm-5p3-flash").wire_id() == "accounts/fireworks/models/glm-5p3-flash"
    assert Model("fireworks/nomic-ai/nomic-embed-text-v1.5").wire_id() == "nomic-ai/nomic-embed-text-v1.5"
    assert Model("fireworks/accounts/fireworks/routers/rune").wire_id() == "accounts/fireworks/routers/rune"


def test_generation_steps_pick_their_own_model():
    from factoid import Model
    from factoid.models import CallLog, ModelClient

    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash"), "situate": Model("fireworks/kimi-k3")},
                         CallLog(None))
    seen = []

    def post(workload, model, path, body, cache_kind=None):
        seen.append((workload, model.name, cache_kind))
        return {"choices": [{"message": {"content": "ok"}}]}, False

    client._post = post  # type: ignore[method-assign]
    client.generate("x", step="situate")
    client.generate("x", step="extract")
    client.generate("x")
    assert seen == [("situate", "fireworks/kimi-k3", "generate"), ("extract", "fireworks/glm-5p3-flash", "generate"),
                    ("generate", "fireworks/glm-5p3-flash", "generate")]


def test_speaker_labels_become_passage_speakers():
    from factoid import ProseDocument

    class Presser(ProseDocument):
        """A press conference transcript."""

        speaker_pattern = r"(?:(?P<speaker>Q)\.|(?P<speaker_name>[A-Z][A-Z .'-]+):)\s"

    text = ("Stephen Curry\n\nQ. What does it mean?\n\nSTEPHEN CURRY: It means a lot.\n\nWe got four.\n\n"
            "Q. And Klay?")
    passages = Presser(text).segment()
    assert [(p.speaker, p.text) for p in passages] == [
        (None, "Stephen Curry"), ("Q", "What does it mean?"), ("STEPHEN CURRY", "It means a lot."),
        ("STEPHEN CURRY", "We got four."), ("Q", "And Klay?")]
    assert all(text[p.start:p.end] == p.text for p in passages)


def test_a_superseded_fact_is_fully_valid_until_it_was_replaced():
    from factoid import Fact
    from factoid.dates import parse_datetime

    fact = Fact("The Celtics lead the series 2-1.", status="superseded",
                valid_from=parse_datetime("2022-06-09T01:00:00Z"), valid_until=parse_datetime("2022-06-11T01:00:00Z"),
                expires="estimated", lifetime={"hour": 0.5, "day": 0.5})
    assert fact.valid_at("2022-06-10T12:00:00Z") == 1.0
    assert fact.valid_at("2022-06-12T00:00:00Z") == 0.0
    assert fact.valid_at("2022-06-08T00:00:00Z") == 0.0


def test_stats_counts_by_class_with_examples(make_app, fake):
    from test_pipeline import Contract, build

    app = build(make_app, fake)
    app.ingest_text("Vega's liability to Orion is capped at $1M under the supply agreement.", document_type=Contract,
                    metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="a.txt")
    data = app.stats(examples=2)
    assert data["facts_by_class"] == {"SourceFact": 1} and data["entities_by_class"]["Company"] == 2
    assert data["examples"]["facts"]["SourceFact"][0].startswith("Vega's liability")
    assert [e["name"] for e in data["examples"]["entities"]["Company"]] == ["Orion", "Vega"]
