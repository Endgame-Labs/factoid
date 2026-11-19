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
    variants = parse_vary(["fact_evals=none,decision_floors(atomic=0.2;grounded=0.4)", "situate=on,off"])
    assert len(variants) == 4
    chain = fact_eval_chain("decision_floors(atomic=0.2;grounded=0.4)")
    assert chain[1].floors["atomic"] == 0.2
    assert prf(8, 2, 2)["f1"] == 0.8
    assert aupr([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert precision_at_recall([0.9, 0.5, 0.4], [True, False, True], 1.0) == pytest.approx(0.6667, abs=1e-3)


def test_tied_scores_make_one_point_on_the_curve():
    # A constant score cannot rank positives above negatives, in either input order.
    assert aupr([0.0, 0.0], [True, False]) == aupr([0.0, 0.0], [False, True]) == 0.5
    assert aupr([0.5, 0.5, 0.5, 0.5], [True, True, False, False]) == 0.5
    assert precision_at_recall([0.0, 0.0], [True, False], 0.5) == 0.5
    assert aupr([0.9, 0.5, 0.5, 0.1], [True, True, False, False]) == aupr([0.9, 0.5, 0.5, 0.1],
                                                                           [True, False, True, False])
    assert aupr([0.1, 0.9], [False, True]) == 1.0  # unsorted input
    assert aupr([0.3, 0.2], [False, False]) == 0.0  # no positives


def test_turbopuffer_filters_traits_by_membership():
    from factoid.search import Turbopuffer

    assert Turbopuffer._filters({"traits": ["liability_cap"]}) == ["traits", "ContainsAny", ["liability_cap"]]
    assert Turbopuffer._filters({"entity_ids": "e1"}) == ["entity_ids", "Contains", "e1"]
    assert Turbopuffer._filters({"status": ["current", "contradicted"]}) == ["status", "In", ["current",
                                                                                           "contradicted"]]
    assert Turbopuffer._filters({"class": "SourceFact", "traits": ["a"]}) == [
        "And", [["class", "Eq", "SourceFact"], ["traits", "ContainsAny", ["a"]]]]


def test_init_scaffolds_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["init", "--package", "deal"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "deal" / "facts.py").is_file()
    assert "[tool.factoid]" in (tmp_path / "pyproject.toml").read_text()


def test_init_in_a_project_switches_its_models(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli, ["init", "--package", "deal"])
    settings = tmp_path / "deal" / "settings.py"
    assert "already a Factoid project" in CliRunner().invoke(cli, ["init"]).output
    result = CliRunner().invoke(cli, ["init", "--models", "openai"])
    assert result.exit_code == 0, result.output
    assert "openai/gpt-6-luna" in settings.read_text() and "typesafe/" not in settings.read_text()
    (tmp_path / "evals" / "sample.py").unlink()
    result = CliRunner().invoke(cli, ["init"])
    assert result.exit_code == 0 and "wrote evals/sample.py" in result.output
    assert "openai/gpt-6-luna" in settings.read_text()  # restoring a sample file leaves settings.py alone
    settings.write_text(settings.read_text().replace("gpt-6-luna", "my-model"))
    result = CliRunner().invoke(cli, ["init", "--models", "jev"])
    assert result.exit_code != 0 and "left it alone" in result.output and "my-model" in settings.read_text()


def test_the_sample_eval_counts_the_signing_as_a_fact():
    from types import SimpleNamespace as NS

    from factoid import scaffold

    namespace: dict = {"__file__": "evals/sample.py"}
    exec(scaffold.SAMPLE_SUITE.format(package="x"), namespace)
    suite = namespace["Sample"]()

    def score(*facts):
        result = NS(facts=[NS(text=text, trait_names=traits) for text, traits in facts])
        return suite.score(None, [result])["facts"]

    consent = ("Orion may not assign it, made on March 1, 2025, without Vega's consent.", ["consent_required"])
    cap = ("Vega's liability under it, made on March 1, 2025, is capped at $1,000,000.", ["liability_cap"])
    signing = ("Orion and Vega made it on March 1, 2025.", [])
    assert score(signing, consent, cap) == {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 3, "fp": 0, "fn": 0}
    assert score(consent, cap)["recall"] < 1.0
    # One fact with both claims, swapped traits, and extra facts all score below 1.
    both = ("Orion needs Vega's consent to assign, and the cap is $1,000,000.", ["consent_required", "liability_cap"])
    assert score(signing, both)["recall"] < 1.0
    assert score(signing, (consent[0], ["liability_cap"]), (cap[0], ["consent_required"]))["recall"] < 1.0
    assert score(signing, consent, cap, ("Vega makes widgets.", []))["precision"] == 0.75


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
    app.ingest_text("Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
                    "Orion may not assign the supply agreement without the prior written consent of Vega.",
                    document_type=Contract, metadata={"signed_at": "2025-03-01T00:00:00Z"}, uri="a.txt")
    # One document, two facts: both are shown, not just the first.
    assert len(app.stats(examples=2)["examples"]["facts"]["SourceFact"]) == 2


def test_vary_can_name_a_project_object():
    from factoid.evals import _value, fact_eval_chain

    assert _value("@factoid.fact_evals:DEFAULT_FLOORS")["grounded"] == 0.45
    assert [type(f).__name__ for f in fact_eval_chain("@factoid.fact:Fact.fact_evals")] == ["Nli", "DecisionFloors"]


def test_keys_set_with_no_terminal_says_how_to_set_a_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(cli, ["keys", "set", "openai"], input="")
    assert result.exit_code != 0 and "no terminal" in result.output and "< key.txt" in result.output
    result = CliRunner().invoke(cli, ["keys", "set"], input="")
    assert result.exit_code != 0 and "no terminal" in result.output and "echoed" not in result.output
    result = CliRunner().invoke(cli, ["keys", "set", "openai"], input="sk-test123\n")
    assert result.exit_code == 0, result.output


def test_keys_set_catches_a_bad_paste():
    from factoid.cli import check_key

    assert check_key("fireworks", "fw_abc123") is None
    assert "escape" in check_key("fireworks", "fw_abc\x1b[200~123")
    assert "start with 'fw_'" in check_key("fireworks", "sk-abc")
    assert check_key("typesafe", "anything-printable") is None


def test_a_provider_with_no_key_and_no_base_url_says_to_set_a_key(monkeypatch, tmp_path):
    import httpx
    import pytest

    from factoid.models import CallLog, Model, ModelClient, ModelError

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.delenv("FIREWORKS_BASE_URL", raising=False)
    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None), replay=False)
    client._http = httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("no call should be made")))
    with pytest.raises(ModelError, match=r"factoid keys set fireworks.*FIREWORKS_BASE_URL"):
        client.generate("hi")


def test_a_base_url_alone_is_enough_and_sends_no_key(monkeypatch, tmp_path):
    import httpx

    from factoid.models import CallLog, Model, ModelClient

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.setenv("FIREWORKS_BASE_URL", "http://gateway.test/v1")
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None), replay=False)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.generate("hi") == "ok"
    assert seen[0][0].startswith("http://gateway.test/v1/") and seen[0][1] is None


def test_a_connect_error_from_a_host_that_has_answered_is_retried(monkeypatch, tmp_path):
    import httpx

    from factoid import models
    from factoid.models import CallLog, Model, ModelClient

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test")
    monkeypatch.setattr(models.time, "sleep", lambda s: None)
    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None), replay=False)
    client._reachable.add("fireworks")
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("blip")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(client._http, "post", post)
    assert client.generate("hi") == "ok"
    assert len(calls) == 2


def test_models_works_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    result = CliRunner().invoke(cli, ["models"])
    assert result.exit_code == 0, result.output
    assert "not in a Factoid project" in result.output and "choose" in result.output


def test_a_project_key_beats_the_home_key_and_the_environment_beats_both(monkeypatch, tmp_path):
    import os

    from factoid import models

    home, project = tmp_path / "home", tmp_path / "proj"
    (home).mkdir()
    (project / ".factoid").mkdir(parents=True)
    (home / ".env").write_text("OPENAI_API_KEY=sk-home\nOPENROUTER_API_KEY=sk-or-home\nFIREWORKS_API_KEY=fw_home\n")
    (project / ".factoid" / ".env").write_text("OPENAI_API_KEY=sk-project\nFIREWORKS_API_KEY=fw_project\n")
    monkeypatch.setenv("FACTOID_HOME", str(home))
    for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_real")
    monkeypatch.setattr(models, "_keys_loaded", False)
    monkeypatch.setattr(models, "KEY_SOURCES", {})
    models.load_keys()  # the home file first, as a command outside a project would
    models.load_keys(project)
    try:
        assert os.environ["OPENAI_API_KEY"] == "sk-project"
        assert os.environ["OPENROUTER_API_KEY"] == "sk-or-home"
        assert os.environ["FIREWORKS_API_KEY"] == "fw_real"
    finally:
        for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
            os.environ.pop(name, None)


def test_vary_refuses_to_replace_a_method_with_a_string():
    import pytest

    from factoid import ProseDocument
    from factoid.evals import applied

    class Memo(ProseDocument):
        """A memo."""

    project = type("P", (), {"documents": [Memo], "facts": [], "entities": [], "settings": type("S", (), {})})()
    with pytest.raises(ValueError, match="is a method"), applied(project, {"classify": "decision"}):
        pass
    assert callable(Memo.classify)


def test_tries_and_the_deadline_bound_one_call(monkeypatch, tmp_path):
    import httpx

    from factoid import models
    from factoid.models import CallLog, Model, ModelClient, ModelError

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test")
    slept, clock = [], [0.0]

    def sleep(seconds):  # a fake clock: waiting moves time on, and nothing really sleeps
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(models.time, "sleep", sleep)
    monkeypatch.setattr(models.time, "monotonic", lambda: clock[0])

    def busy(request):
        return httpx.Response(503, json={"error": "busy"})

    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None), replay=False, attempts=3)
    client._http = httpx.Client(transport=httpx.MockTransport(busy))
    with pytest.raises(ModelError, match="HTTP 503"):
        client.generate("hi")
    assert len(slept) == 2  # three tries, two waits

    slept.clear()
    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None), replay=False, deadline=1.5)
    client._http = httpx.Client(transport=httpx.MockTransport(busy))
    with pytest.raises(ModelError, match="model_deadline"):
        client.generate("hi")
    assert sum(slept) < 1.5


def test_model_calls_are_labelled_by_step(monkeypatch, tmp_path):
    import httpx

    from factoid.models import CallLog, Model, ModelClient
    from factoid.steps import labelled, run_step

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test")
    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None), replay=False)
    client._http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}],
                                            "usage": {"prompt_tokens": 7, "completion_tokens": 1}})))

    class Thing:
        def extract(self, text):
            return client.generate(text)

    run_step(Thing(), "extract", "a")
    with labelled("fact_class"):
        client.generate("b")
    assert client.meter.steps["extract"]["input_tokens"] == 7 and client.meter.steps["fact_class"]["calls"] == 1
    assert [row["step"] for row in client.log.recent()] == ["fact_class", "extract"]


def test_the_call_log_can_keep_no_text(monkeypatch, tmp_path):
    import httpx

    from factoid.models import CallLog, Model, ModelClient

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test")
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "a secret answer"}}],
                                         "usage": {"prompt_tokens": 9, "completion_tokens": 3}})

    for mode, rows in (("metadata", 1), ("none", 0)):
        log = CallLog(tmp_path / f"{mode}.db", mode=mode)
        client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, log)
        client._http = httpx.Client(transport=httpx.MockTransport(handler))
        assert client.generate("a secret note") == "a secret answer"
        assert client.generate("a secret note") == "a secret answer"  # nothing to replay, so it calls again
        stored = log._db.execute("select request, response, input_tokens from calls").fetchall()
        assert len(stored) == rows and all(r[0] is None and r[1] is None and r[2] == 9 for r in stored)
        assert b"secret" not in (tmp_path / f"{mode}.db").read_bytes()
    assert len(sent) == 4
    with pytest.raises(ValueError, match="call_log must be one of"):
        CallLog(None, mode="bodies")


def test_a_key_given_in_code_is_sent_and_never_stored(monkeypatch, tmp_path):
    import httpx

    from factoid.models import CallLog, Model, ModelClient

    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.delenv("FIREWORKS_BASE_URL", raising=False)
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("authorization"), request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    rotating = iter(["k-one", "k-two"])
    model = Model("fireworks/glm-5p3-flash", api_key=lambda: next(rotating), base_url="http://vault.test/v1/")
    log = CallLog(tmp_path / "calls.db")
    client = ModelClient({"generate": model}, log, replay=False)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.generate("hi") == "ok" and client.generate("hi again") == "ok"
    assert [s[1] for s in seen] == ["Bearer k-one", "Bearer k-two"]
    assert seen[0][0].startswith("http://vault.test/v1/") and all(b"k-one" not in s[2] for s in seen)
    assert "k-one" not in repr(model) and b"k-one" not in (tmp_path / "calls.db").read_bytes()
    assert Model("fireworks/glm-5p3-flash", api_key="x") == Model("fireworks/glm-5p3-flash")
