"""`factoid serve`: the project's facts over HTTP, as JSON.

    GET  /health                      {"ok": true, "version": ...}
    GET  /search?q=...                facts that match, best first (about, as_of, top_k, chunks)
    GET  /facts                       facts in the order they were added (document, trait, status, limit)
    GET  /facts/<id>                  one fact with its quotes, mentions, relations, and history
    GET  /entities                    entities with their fact counts (class, name, limit)
    GET  /entities/<name or id>       one entity, its current facts, and the entities it appears with
    GET  /stats                       counts by class and status
    GET  /contradictions              open contradictions, newest first (stale, limit)
    POST /contradictions/settle       {"fact_id", "other_id", "keep": one id or "both", "reason", "by"}
    POST /ingest                      {"text": ..., "document_type", "uri", "title", "metadata"}: the facts kept

It uses only the standard library. Requests run one at a time against the store, so a long ingest delays reads.
With `FACTOID_API_TOKEN` set, every request needs `Authorization: Bearer <token>`.
"""

from __future__ import annotations

import hmac
import json
import threading
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import api

__all__ = ["make_server"]

MAX_BODY = 20 * 1024 * 1024  # 20 MB of document text per ingest


class _Error(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def make_server(app: Any, host: str = "127.0.0.1", port: int = 8765, token: str | None = None) -> ThreadingHTTPServer:
    """A server for `app`; call `serve_forever()` on it. Port 0 picks a free port (`server.server_port`)."""
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "factoid"

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args: Any) -> None:  # one short line per request, on stderr
            import sys

            print(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}", file=sys.stderr)

        def _handle(self, method: str) -> None:
            try:
                if token and not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
                    raise _Error(401, "missing or wrong bearer token")
                url = urlsplit(self.path)
                query = {k: v[-1] for k, v in parse_qs(url.query).items()}
                parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
                # Writes take turns; reads do not wait for them. The store and index lock each query on their own.
                with lock if method == "POST" else nullcontext(), app.active():
                    body = self._route(method, parts, query)
                self._send(200, body)
            except _Error as err:
                self._send(err.status, {"error": str(err)})
            except api.NotFound as err:
                self._send(404, {"error": str(err)})
            except (ValueError, TypeError) as err:
                self._send(400, {"error": str(err)})
            except Exception as err:  # the server keeps running; the client gets the reason
                self._send(500, {"error": f"{type(err).__name__}: {err}"})

        def _route(self, method: str, parts: list[str], q: dict[str, str]) -> Any:
            match method, parts:
                case "GET", ["health"]:
                    from .version import version

                    return {"ok": True, "version": version()}
                case "GET", ["search"]:
                    if not q.get("q"):
                        raise _Error(400, "search needs q, the query")
                    return api.search(app, q["q"], about=q.get("about"), as_of=q.get("as_of"),
                                      top_k=int(q.get("top_k", 10)), chunks=_flag(q.get("chunks")),
                                      min_score=q.get("min_score"))
                case "GET", ["facts"]:
                    return api.facts(app, document=q.get("document"), trait=q.get("trait"),
                                     status=q.get("status", "current"), limit=int(q.get("limit", 50)))
                case "GET", ["facts", fact_id]:
                    return api.fact(app, fact_id)
                case "GET", ["entities"]:
                    return api.entities(app, class_name=q.get("class"), name=q.get("name"),
                                        limit=int(q.get("limit", 100)))
                case "GET", ["entities", name]:
                    return api.entity(app, name, limit=int(q.get("limit", 50)))
                case "GET", ["stats"]:
                    return api.stats(app)
                case "GET", ["events"]:
                    return api.events(app, after=int(q.get("after", 0)), limit=int(q.get("limit", 100)))
                case "GET", ["documents", document_id]:
                    return api.document(app, document_id)
                case "GET", ["contradictions"]:
                    return api.contradictions(app, include_stale=q.get("stale", "true") != "false",
                                              limit=int(q.get("limit", 50)))
                case "POST", ["contradictions", "settle"]:
                    data = self._json()
                    missing = [k for k in ("fact_id", "other_id", "keep") if not isinstance(data.get(k), str)]
                    if missing:
                        raise _Error(400, f"settle needs {', '.join(missing)}")
                    return api.settle(app, data["fact_id"], data["other_id"], keep=data["keep"],
                                      reason=data.get("reason") or "", by=data.get("by"))
                case "POST", ["ingest"]:
                    data = self._json()
                    if not isinstance(data.get("text"), str) or not data["text"].strip():
                        raise _Error(400, "ingest needs text")
                    return api.ingest(app, data["text"], document_type=data.get("document_type"),
                                      uri=data.get("uri"), title=data.get("title"), metadata=data.get("metadata"))
            raise _Error(404, f"no route {method} /{'/'.join(parts)}")

        def _json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise _Error(413, "the request body is over 20 MB")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as err:
                raise _Error(400, f"the body is not JSON: {err}") from err
            if not isinstance(data, dict):
                raise _Error(400, "the body must be a JSON object")
            return data

        def _send(self, status: int, body: Any) -> None:
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), Handler)


def _flag(value: str | None) -> bool:
    return (value or "").lower() in ("1", "true", "yes")
