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
