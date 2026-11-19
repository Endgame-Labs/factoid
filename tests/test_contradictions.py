import io
import json
import threading
import urllib.error
import urllib.request

import pytest
from test_mcp import _call, _data, _session
from test_pipeline import build

from factoid import Fact
from factoid.mcp_server import Server
from factoid.serve import make_server

CAP = "Vega's liability to Orion is capped at $1M under the supply agreement."
OTHER = "Vega's liability to Orion is capped at $3M under the supply agreement."


def _contradicting(make_app, fake):
    """An app where a $3M cap contradicts a stored $1M cap, ingested from two documents."""
    app = build(make_app, fake)
    inner = fake.choice

    def choice(question, state, name):
        if name.startswith("F") and "$3M" in state["new_fact"]["text"] \
                and "$1M" in json.dumps(state["stored_facts"][name]):
            return {k: (0.9 if k == "contradicts" else 0.01) for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    one = app.ingest_text(CAP, document_type=app.document_classes[0], uri="a.txt",
                          metadata={"signed_at": "2025-03-01T00:00:00Z"}).facts[0]
    three = app.ingest_text(OTHER, document_type=app.document_classes[0], uri="b.txt",
                            metadata={"signed_at": "2025-03-01T00:00:00Z"}).facts[0]
    return app, one, three


def test_a_person_keeps_one_side(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    [pair] = app.contradictions()
    assert {pair.fact.id, pair.other.id} == {one.id, three.id} and not pair.stale
    assert app.stats()["open_contradictions"] == 1

    app.settle_contradiction(one.id, three.id, keep=three.id, reason="b.txt is the signed copy", by="kyle")
    assert Fact.get(three.id).status == "current" and Fact.get(one.id).status == "retracted"
    assert app.contradictions() == [] and app.stats()["open_contradictions"] == 0
    event = json.loads(app.store.events_for(one.id)[-1]["data"])
    assert app.store.events_for(one.id)[-1]["type"] == "fact.settled"
    assert event == {"status": "retracted", "other": three.id, "how": "picked", "kept": three.id,
                     "reason": "b.txt is the signed copy", "by": "kyle"}
    # A search no longer carries the settled pair as a contradiction.
    hits = app.search_facts("liability cap", include_retired=True)
    assert all(h.contradiction_ids == [] for h in hits)


def test_keeping_both_and_mistakes(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    with pytest.raises(ValueError, match="keep must be"):
        app.settle_contradiction(one.id, three.id, keep="nope")
    app.settle_contradiction(three.id, one.id, keep="both")
    assert {Fact.get(one.id).status, Fact.get(three.id).status} == {"current"}
    with pytest.raises(LookupError, match="no open contradiction"):
        app.settle_contradiction(one.id, three.id, keep="both")


def test_new_evidence_settles_a_contradiction(make_app, fake):
    app, _one, three = _contradicting(make_app, fake)
    # The pipeline's resolve says a $2M cap supersedes every stored cap, so both sides are replaced.
    app.ingest_text("Vega's liability to Orion is capped at $2M from 2027.", document_type=app.document_classes[0],
                    uri="c.txt", metadata={"signed_at": "2026-10-03T00:00:00Z"})
    assert app.contradictions() == []
    settled = [json.loads(e["data"]) for e in app.store.events_for(three.id) if e["type"] == "fact.settled"]
    assert settled and settled[0]["how"] == "evidence" and settled[0]["answer"] == "supersedes"


def test_contradictions_over_http_and_mcp(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    server = make_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(f"{base}/contradictions") as response:
            [pair] = json.load(response)
        assert {pair["fact"]["id"], pair["other"]["id"]} == {one.id, three.id}
        request = urllib.request.Request(f"{base}/contradictions/settle", method="POST",
                                         data=json.dumps({"fact_id": one.id, "other_id": three.id}).encode())
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(request)
        assert err.value.code == 400 and "keep" in json.load(err.value)["error"]
    finally:
        server.shutdown()

    mcp = Server(app, out=io.StringIO())
    replies = _session(
        mcp,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "claude-code"}}},
        _call(2, "list_contradictions"),
        _call(3, "settle_contradiction", fact_id=one.id, other_id=three.id, keep=one.id, reason="earlier is right"),
        _call(4, "list_contradictions"),
    )
    assert len(_data(replies[2])) == 1 and _data(replies[4]) == []
    assert [f["status"] for f in _data(replies[3])["facts"]] == ["current", "retracted"]
    assert json.loads(app.store.events_for(three.id)[-1]["data"])["by"] == "mcp:claude-code"
    names = {t["name"] for t in Server(app, read_only=True).tools}
    assert "settle_contradiction" not in names and "list_contradictions" in names
