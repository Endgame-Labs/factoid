import io
import json

from test_exports import AMENDMENT, FIRST
from test_pipeline import build

from factoid.mcp_server import Server


def _session(server, *messages):
    """Run messages through the server as stdio lines and return the replies by id."""
    out = io.StringIO()
    server.out = out
    server.run(io.StringIO("".join(json.dumps(m) + "\n" for m in messages)))
    return {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}


def _call(n, tool, **arguments):
    return {"jsonrpc": "2.0", "id": n, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}


def _data(reply):
    assert not reply["result"]["isError"], reply
    return json.loads(reply["result"]["content"][0]["text"])


def test_an_agent_ingests_searches_and_reads_over_mcp(make_app, fake):
    server = Server(build(make_app, fake))
    meta = {"signed_at": "2025-03-01T00:00:00Z"}
    replies = _session(
        server,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        _call(3, "ingest_text", text=FIRST, document_type="Contract", uri="supply.txt", metadata=meta),
        _call(4, "ingest_text", text=AMENDMENT, document_type="Contract", uri="amendment2.txt",
              metadata={"signed_at": "2026-10-03T00:00:00Z"}),
        _call(5, "search_facts", query="liability cap", as_of="2026-06-01"),
        _call(6, "read_entity", name="Vega"),
        _call(7, "find_entities", name="ori"),
        _call(8, "list_facts", status="all"),
        _call(9, "stats"),
        {"jsonrpc": "2.0", "id": 10, "method": "ping"},
    )
    assert len(replies) == 10  # the notification gets no reply
    init = replies[1]["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "factoid"
    assert "tools" in init["capabilities"]
    names = {t["name"] for t in replies[2]["result"]["tools"]}
    assert {"search_facts", "read_fact", "read_entity", "ingest_text"} <= names
    cap = next(f for f in _data(replies[3])["facts"] if "$1M" in f["text"])
    # Before the amendment took effect, the $1M cap was in force, so an as-of search finds it with its quote.
    hit = next(h for h in _data(replies[5]) if h["id"] == cap["id"])
    assert hit["quotes"][0]["text"] and hit["validity"] > 0.5
    vega = _data(replies[6])
    assert vega["name"] == "Vega" and vega["related"][0]["name"] == "Orion"
    assert [e["name"] for e in _data(replies[7])] == ["Orion"]
    assert len(_data(replies[8])) == 3 and _data(replies[9])["facts"] == {"current": 2, "superseded": 1}
    assert replies[10]["result"] == {}

    read = _session(server, _call(11, "read_fact", id=cap["id"]))[11]
    assert _data(read)["status"] == "superseded"


def test_errors_reach_the_agent_and_read_only_drops_ingest(make_app, fake):
    server = Server(build(make_app, fake), read_only=True)
    replies = _session(
        server,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        _call(3, "read_fact", id="nope"),
        _call(4, "search_facts"),
        _call(5, "ingest_text", text="x"),
        {"jsonrpc": "2.0", "id": 6, "method": "resources/list"},
    )
    assert replies[1]["result"]["protocolVersion"] == "2025-06-18"  # an unknown version gets the newest
    assert "ingest_text" not in {t["name"] for t in replies[2]["result"]["tools"]}
    assert replies[3]["result"]["isError"] and "no fact nope" in replies[3]["result"]["content"][0]["text"]
    assert "missing argument 'query'" in replies[4]["result"]["content"][0]["text"]
    assert replies[5]["error"]["code"] == -32602 and replies[6]["error"]["code"] == -32601
