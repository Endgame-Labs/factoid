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


def test_evidence_against_one_side_lets_the_other_stand(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    inner = fake.choice

    def choice(question, state, name):  # a $5M cap replaces the $3M one only
        if name.startswith("F") and "$5M" in state["new_fact"]["text"]:
            stored = json.dumps(state["stored_facts"][name])
            return {k: (0.9 if k == ("supersedes" if "$3M" in stored else "unrelated") else 0.01)
                    for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    five = app.ingest_text("Vega's liability to Orion is capped at $5M under the supply agreement.",
                           document_type=app.document_classes[0], uri="d.txt",
                           metadata={"signed_at": "2025-06-01T00:00:00Z"}).facts[0]
    assert Fact.get(three.id).status == "superseded" and Fact.get(one.id).status == "current"
    assert app.contradictions() == [] and app.stats()["open_contradictions"] == 0
    event = json.loads(app.store.events_for(one.id)[-1]["data"])
    assert event["how"] == "evidence" and event["by"] == five.id and event["status"] == "current"


def test_search_carries_open_contradictions(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    hits = {h.fact.id: h for h in app.search_facts("liability cap")}
    assert hits[one.id].contradiction_ids == [three.id] and hits[one.id].contradictions[0].id == three.id
    ids_only = {h.fact.id: h for h in app.search_facts("liability cap", contradictions=0)}
    assert ids_only[one.id].contradiction_ids == [three.id] and ids_only[one.id].contradictions == []
    left_out = {h.fact.id: h for h in app.search_facts("liability cap", contradictions=False)}
    assert left_out[one.id].contradiction_ids == []


def test_a_retracted_side_closes_the_pair_everywhere(make_app, fake):
    app, one, _three = _contradicting(make_app, fake)
    Fact.get(one.id).retract("re-ingested")
    assert app.contradictions() == [] and app.stats()["open_contradictions"] == 0


def test_a_fact_in_two_pairs_stays_contradicted_until_both_settle(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    inner = fake.choice

    def choice(question, state, name):  # a $4M cap contradicts the $1M one too
        if name.startswith("F") and "$4M" in state["new_fact"]["text"]:
            stored = json.dumps(state["stored_facts"][name])
            return {k: (0.9 if k == ("contradicts" if "$1M" in stored else "unrelated") else 0.01)
                    for k, _ in question.options}
        return inner(question, state, name)

    fake.choice = choice
    four = app.ingest_text("Vega's liability to Orion is capped at $4M under the supply agreement.",
                           document_type=app.document_classes[0], uri="e.txt",
                           metadata={"signed_at": "2025-03-01T00:00:00Z"}).facts[0]
    assert len(app.contradictions()) == 2
    app.settle_contradiction(one.id, three.id, keep="both")
    assert Fact.get(one.id).status == "contradicted" and Fact.get(three.id).status == "current"
    app.settle_contradiction(one.id, four.id, keep=one.id)
    assert Fact.get(one.id).status == "current" and Fact.get(four.id).status == "retracted"


def test_a_stale_pair_is_marked_and_can_be_left_out(make_app, fake):
    app, one, _three = _contradicting(make_app, fake)
    app.store.set_fields(one.id, valid_until="2025-12-31T00:00:00Z")
    [pair] = app.contradictions()
    assert pair.stale and app.contradictions(include_stale=False) == []


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
        with urllib.request.urlopen(f"{base}/contradictions?stale=false") as response:
            assert len(json.load(response)) == 1
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
    # A read-only server refuses the settle tool even when an agent calls it by name.
    refused = _session(Server(app, read_only=True), _call(5, "settle_contradiction", fact_id=one.id,
                                                          other_id=three.id, keep="both", reason="x"))[5]
    assert refused["error"]["code"] == -32602


def test_settling_over_http(make_app, fake):
    app, one, three = _contradicting(make_app, fake)
    server = make_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def settle(**body):
        request = urllib.request.Request(f"{base}/contradictions/settle", method="POST",
                                         data=json.dumps(body).encode())
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    try:
        done = settle(fact_id=one.id, other_id=three.id, keep=three.id, reason="signed copy", by="http")
        assert done["kept"] == three.id and [f["status"] for f in done["facts"]] == ["retracted", "current"]
        with pytest.raises(urllib.error.HTTPError) as err:
            settle(fact_id=one.id, other_id=three.id, keep="both")
        assert err.value.code == 404 and "no open contradiction" in json.load(err.value)["error"]
    finally:
        server.shutdown()
