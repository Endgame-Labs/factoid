import threading

import httpx
import pytest
from test_exports import AMENDMENT, FIRST
from test_pipeline import build

from factoid.serve import make_server


@pytest.fixture
def served(make_app, fake):
    def start(token=None):
        app = build(make_app, fake)
        server = make_server(app, "127.0.0.1", 0, token)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return app, f"http://127.0.0.1:{server.server_port}"

    servers = []
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_ingest_search_and_read_over_http(served):
    _, base = served()
    first = httpx.post(f"{base}/ingest", json={"text": FIRST, "document_type": "Contract", "uri": "supply.txt",
                                               "metadata": {"signed_at": "2025-03-01T00:00:00Z"}}).json()
    assert len(first["facts"]) == 2 and first["document"]["class"] == "Contract"
    cap = next(f for f in first["facts"] if "$1M" in f["text"])
    assert cap["quotes"][0]["text"] and {m["text"] for m in cap["mentions"]} == {"Vega", "Orion"}
    httpx.post(f"{base}/ingest", json={"text": AMENDMENT, "document_type": "Contract", "uri": "amendment2.txt",
                                       "metadata": {"signed_at": "2026-10-03T00:00:00Z"}})

    hits = httpx.get(f"{base}/search", params={"q": "liability cap"}).json()
    assert all(h["score"] > 0 for h in hits) and any("$2M" in h["text"] for h in hits)
    assert cap["id"] not in {h["id"] for h in hits}  # superseded, so left out of a search for now
    # Before the amendment took effect, the old cap was still in force, so an as-of search finds it.
    then = httpx.get(f"{base}/search", params={"q": "liability cap", "as_of": "2026-06-01"}).json()
    assert cap["id"] in {h["id"] for h in then}

    fact = httpx.get(f"{base}/facts/{cap['id']}").json()
    assert fact["status"] == "superseded" and fact["valid_until"].startswith("2027")
    assert any(r["relation"] == "supersedes" for r in fact["relations"]) and fact["events"]

    assert len(httpx.get(f"{base}/facts", params={"status": "all"}).json()) == 3
    vega = httpx.get(f"{base}/entities/Vega").json()
    assert vega["name"] == "Vega" and vega["facts"] and vega["related"][0]["name"] == "Orion"
    assert {e["name"] for e in httpx.get(f"{base}/entities").json()} == {"Vega", "Orion"}
    assert httpx.get(f"{base}/stats").json()
    assert httpx.get(f"{base}/health").json()["ok"] is True


def test_errors_are_json_with_a_status(served):
    _, base = served()
    assert httpx.get(f"{base}/facts/nope").status_code == 404
    assert httpx.get(f"{base}/entities/Nobody").json() == {"error": "no entity named 'Nobody'"}
    assert httpx.get(f"{base}/search").status_code == 400
    assert httpx.post(f"{base}/ingest", content=b"not json").status_code == 400
    assert httpx.post(f"{base}/ingest", json={"text": "x", "document_type": "Memo"}).status_code == 404
    assert httpx.get(f"{base}/nowhere").status_code == 404


def test_a_token_guards_every_route(served):
    _, base = served(token="s3cret")
    assert httpx.get(f"{base}/health").status_code == 401
    assert httpx.get(f"{base}/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert httpx.get(f"{base}/health", headers={"Authorization": "Bearer s3cret"}).status_code == 200
