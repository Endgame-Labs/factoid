"""First-run fixes: the last paragraph, dead hosts, model presets, keys, and the three decision models."""

from __future__ import annotations

import tomllib

import httpx
import pytest
from click.testing import CliRunner

from factoid import Choice, Model, Noul, ProseDocument, Score
from factoid.cli import cli
from factoid.models import PROVIDERS, CallLog, ModelClient, ModelError, check_models


class Memo(ProseDocument):
    """A memo."""


def test_segment_keeps_the_last_paragraph_before_a_trailing_newline():
    text = "TITLE\n\nFirst paragraph here.\n\nLast paragraph is capped at $1,000,000.\n"
    passages = Memo(text).segment()
    assert [p.text for p in passages][-1] == "Last paragraph is capped at $1,000,000."
    assert len(passages) == 3
    assert len(Memo(text.rstrip()).segment()) == 3
    assert len(Memo(text + "\n  \n").segment()) == 3


def test_a_host_that_never_answers_fails_fast_and_says_where(monkeypatch, tmp_path):
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
    monkeypatch.setenv("FIREWORKS_BASE_URL", "http://wrong.test/v1")
    calls = []

    def handler(request):
        calls.append(request.url)
        raise httpx.ConnectTimeout("timed out", request=request)

    client = ModelClient({"generate": Model("fireworks/glm-5p3-flash")}, CallLog(None))
    client.replay = False
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError, match="could not connect to http://wrong.test/v1"):
        client.generate("hi")
    assert len(calls) == 1  # no retries


def test_check_models_names_providers_that_cannot_serve_a_workload():
    assert check_models({"choose": Model("fireworks/rune"), "embed": Model("openai/text-embedding-3-small"),
                         "extract": Model("openrouter/some/model")}) == []
    problems = check_models({"embed": Model("openrouter/x"), "choose": Model("acme/x")})
    assert "openrouter cannot serve the embed workload" in problems[0]
    assert "unknown provider 'acme'" in problems[1]
    client = ModelClient({"choose": Model("openrouter/x")}, CallLog(None))
    with pytest.raises(ModelError, match="cannot serve the choose workload"):
        client.ask({"text": "x"}, {"ok": Noul("Is this a test?")})


def test_every_provider_says_where_to_get_a_key():
    assert all(p.key_url.startswith("https://") for p in PROVIDERS.values())
    assert "waitlist" in PROVIDERS["typesafe"].access


def _client_answering(model, response):
    client = ModelClient({"choose": Model(model)}, CallLog(None))
    seen = {}

    def post(workload, model, path, body, cache_kind=None):
        seen.update(path=path, body=body)
        return response(body), False

    client._post = post  # type: ignore[method-assign]
    return client, seen


def test_fireworks_rune_serves_choose_over_system_one():
    def response(body):
        return {"answers": {key: {"type": "noul", "noul": 0.9} for key in body["questions"]}}

    client, seen = _client_answering("fireworks/rune", response)
    judgments = client.ask({"text": "x"}, {"ok": Noul("Is this a test?")})
    assert judgments.ok == 0.9
    assert seen["path"] == "/systemone"
    assert seen["body"]["model"] == "accounts/fireworks/models/rune"


def test_jev_still_uses_its_own_path():
    def response(body):
        return {"answers": {key: {"type": "noul", "noul": 0.2} for key in body["questions"]}}

    client, seen = _client_answering("typesafe/jev-1.13.0", response)
    assert client.ask({"text": "x"}, {"ok": Noul("Is this a test?")}).ok == 0.2
    assert seen["path"] == "/v1/systemone" and seen["body"]["model"] == "jev-1.13.0"


def test_openai_decisions_api_serves_choose():
    questions = {
        "yes": Noul("Is this a contract?", true="It is a signed contract.", false="Anything else."),
        "court": Choice("Which court?", {"federal": "A federal court.", "state": "A state court."}),
        "useful": Score("How useful is the fact?", ["Useless.", "Somewhat.", "Very."]),
    }

    def response(body):
        answers = []
        for q in body["questions"]:
            if q["type"] == "predicate":
                answers.append({"type": "predicate", "name": q["name"], "probability": 0.8})
            elif q["type"] == "choice":
                answers.append({"type": "choice", "name": q["name"], "choice": "state", "confidence": 0.7,
                                "probabilities": [{"value": "federal", "probability": 0.3},
                                                  {"value": "state", "probability": 0.7}]})
            else:
                answers.append({"type": "score", "name": q["name"], "score": 1.1, "confidence": 0.7,
                                "probabilities": [{"value": 0, "label": "0", "probability": 0.1},
                                                  {"value": 1, "label": "1", "probability": 0.7},
                                                  {"value": 2, "label": "2", "probability": 0.2}]})
        return {"answers": answers, "model": "gpt-6-luna", "usage": {"input_tokens": 10, "output_tokens": 0}}

    client, seen = _client_answering("openai/gpt-6-luna", response)
    judgments = client.ask({"text": "Orion and Vega"}, questions)
    assert seen["path"] == "/decisions"
    body = seen["body"]
    assert body["model"] == "gpt-6-luna"
    assert body["input"] == [{"role": "user", "content": [{"type": "input_json", "data": {"text": "Orion and Vega"}}]}]
    by_type = {q["type"]: q for q in body["questions"]}
    assert "It is a signed contract." in by_type["predicate"]["instructions"]
    assert by_type["choice"]["choices"][0] == {"value": "federal", "description": "A federal court."}
    assert [lvl["description"] for lvl in by_type["score"]["levels"]] == ["Useless.", "Somewhat.", "Very."]
    assert judgments.yes == 0.8
    assert judgments.court == {"federal": 0.3, "state": 0.7}
    assert float(judgments.useful) == 1.1 and judgments.useful.probabilities[1] == 0.7


def test_openai_refusal_is_an_error():
    def response(body):
        return {"answers": [{"type": "refusal", "name": q["name"]} for q in body["questions"]]}

    client, _ = _client_answering("openai/gpt-6-luna", response)
    with pytest.raises(ModelError, match="refused"):
        client.ask("plain text state", {"ok": Noul("Is this a test?")})


def test_openai_generation_uses_max_completion_tokens():
    client = ModelClient({"generate": Model("openai/gpt-6-luna")}, CallLog(None))
    seen = {}

    def post(workload, model, path, body, cache_kind=None):
        seen.update(body)
        return {"choices": [{"message": {"content": "ok"}}]}, False

    client._post = post  # type: ignore[method-assign]
    client.generate("hi", max_tokens=100)
    assert seen["max_completion_tokens"] == 100 and "max_tokens" not in seen and "temperature" not in seen


@pytest.mark.parametrize("preset,choose", [("jev", "typesafe/"), ("fireworks", "fireworks/rune"),
                                           ("openai", "openai/gpt-6-luna")])
def test_init_presets_write_settings_that_check_clean(tmp_path, monkeypatch, preset, choose):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(cli, ["init", "--package", "acme", "--models", preset])
    assert result.exit_code == 0, result.output
    assert "factoid keys set" in result.output
    settings = (tmp_path / "acme" / "settings.py").read_text()
    assert choose in settings
    namespace: dict = {}
    exec(settings, namespace)  # noqa: S102 - the settings file init just wrote
    assert check_models(namespace["Project"].models) == []
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert pyproject["tool"]["uv"]["sources"]["factoid"]["git"].startswith("https://github.com/")


def test_keys_set_with_no_provider_walks_the_needed_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path / "home"))
    for env in ("TYPESAFE_API_KEY", "FIREWORKS_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    result = CliRunner().invoke(cli, ["keys", "set"], input="\nfw_test123\n")
    assert result.exit_code == 0, result.output
    assert "typesafe" in result.output and "waitlist" in result.output and "skipped typesafe" in result.output
    assert "https://app.fireworks.ai/settings/users/api-keys" in result.output
    assert "FIREWORKS_API_KEY=fw_test123" in (tmp_path / "home" / ".env").read_text()


def test_keys_list_shows_status_use_and_where_to_get_each_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_x")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    result = CliRunner().invoke(cli, ["keys", "list"])
    assert result.exit_code == 0, result.output
    rows = {line.split()[0]: line for line in result.output.splitlines()}
    assert "set (environment variable)" in rows["fireworks"] and "generate, embed" in rows["fireworks"]
    assert "not set" in rows["typesafe"] and "console.typesafe.ai" in rows["typesafe"]
