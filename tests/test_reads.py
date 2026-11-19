import io
import json
import threading
import urllib.request

import pytest
from test_mcp import _call, _data, _session
from test_pipeline import Contract, build

from factoid import api
from factoid.mcp_server import Server
from factoid.serve import make_server

TEXT = ("Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
        "Orion may not assign the agreement without Vega's consent.")


def _app(make_app, fake):
    app = build(make_app, fake)
    result = app.ingest_text(TEXT, document_type=Contract, uri="deals/supply.txt",
                             metadata={"signed_at": "2025-03-01T00:00:00Z", "record": "OPP-7"})
    return app, result


def test_a_fact_says_where_its_document_came_from(make_app, fake):
    app, result = _app(make_app, fake)
    found = api.fact(app, result.facts[0].id)["document"]
    assert found["uri"] == "deals/supply.txt" and found["metadata"]["record"] == "OPP-7"
    assert app.document(result.document.id)["revisions"] == 0
    with pytest.raises(api.NotFound):
        api.document(app, "doc_none")


def test_search_drops_what_the_reranker_scores_low(make_app, fake):
    app, _ = _app(make_app, fake)
    with pytest.raises(ValueError, match="min_score needs a rerank model"):
        app.search_facts("cap", min_score=0.5)
    app.client.models["rerank"] = "fake"
    fake.rerank = lambda query, docs: [0.9 if "capped" in d else 0.2 for d in docs]
    hits = app.search_facts("cap", min_score=0.5, freshness="any")
    assert [h.fact.text for h in hits] == [TEXT.split("\n\n")[0]]


def test_events_read_on_from_a_cursor_over_http_and_mcp(make_app, fake):
    app, _ = _app(make_app, fake)
    first = app.events(limit=3)
    assert [e["seq"] for e in first] == sorted(e["seq"] for e in first) and len(first) == 3
    rest = app.events(after=first[-1]["seq"])
    assert rest and rest[0]["seq"] == first[-1]["seq"] + 1
    server = make_server(app, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/events?after={first[-1]['seq']}&limit=2"
        with urllib.request.urlopen(url) as response:
            assert [e["seq"] for e in json.load(response)] == [e["seq"] for e in rest[:2]]
    finally:
        server.shutdown()
    replies = _session(Server(app, out=io.StringIO()), _call(1, "read_events", after=0, limit=2))
    assert [e["seq"] for e in _data(replies[1])] == [e["seq"] for e in first[:2]]
