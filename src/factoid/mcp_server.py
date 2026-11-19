"""`factoid mcp`: the project's facts as MCP tools, over stdio.

An agent connects with, for example, `claude mcp add factoid -- factoid mcp` run in the project folder. The server
speaks JSON-RPC 2.0, one message per line, and uses only the standard library. The tools share `api.py` with
`factoid serve`.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from . import api

__all__ = ["TOOLS", "Server"]

PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]  # newest first

_STR = {"type": "string"}
_INT = {"type": "integer"}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_facts",
        "description": (
            "Search the facts Factoid extracted from the project's documents. Each fact is a short, self-contained "
            "sentence with its quotes from the source, its status, its dates, and the chance it still holds now "
            "(still_valid). Superseded facts are left out unless as_of falls before they were replaced."),
        "inputSchema": {"type": "object", "required": ["query"], "properties": {
            "query": {**_STR, "description": "What to look for, in plain words."},
            "about": {**_STR, "description": "Only facts about this entity (a name, key, or id)."},
            "as_of": {**_STR, "description": "A date (2026-06-01) or ISO time: rank by what was true then."},
            "top_k": {**_INT, "description": "How many facts to return, 1 to 100. Default 10."},
        }},
    },
    {
        "name": "read_fact",
        "description": "One fact by id, with its quotes, mentions, relations to other facts, and history.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": _STR}},
    },
    {
        "name": "list_facts",
        "description": "Facts in the order they were added, optionally from one document or with one trait.",
        "inputSchema": {"type": "object", "properties": {
            "document": {**_STR, "description": "A document's id, title, or file name."},
            "trait": {**_STR, "description": "A trait name, such as liability_cap."},
            "status": {**_STR, "description": "current (default), superseded, ended, corrected, contradicted, "
                                              "retracted, or all."},
            "limit": {**_INT, "description": "Default 50."},
        }},
    },
    {
        "name": "find_entities",
        "description": "Entities (companies, people, agreements, and so on) with their fact counts, most facts first.",
        "inputSchema": {"type": "object", "properties": {
            "name": {**_STR, "description": "Part of a name or another name."},
            "class": {**_STR, "description": "An entity class, such as Company."},
            "limit": {**_INT, "description": "Default 20."},
        }},
    },
    {
        "name": "read_entity",
        "description": "One entity by name, key, or id: its current facts, newest first, and the entities it appears "
                       "with most.",
        "inputSchema": {"type": "object", "required": ["name"], "properties": {
            "name": {**_STR, "description": "A name, other name, key, or id."},
            "limit": {**_INT, "description": "How many facts. Default 50."},
        }},
    },
    {
        "name": "stats",
        "description": "Counts of documents, facts, and entities by class and status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_contradictions",
        "description": "Open contradictions: pairs of facts that cannot both be true and that nobody has settled yet, "
                       "newest first, with both facts in full. stale is true when either fact has passed its end "
                       "date.",
        "inputSchema": {"type": "object", "properties": {
            "include_stale": {"type": "boolean", "description": "Default true."},
            "limit": {**_INT, "description": "Default 20."},
        }},
    },
    {
        "name": "settle_contradiction",
        "description": "Settle an open contradiction by picking a side: keep one fact's id (the other is retracted) "
                       "or keep both when they do not really conflict. Give the reason, such as the source that "
                       "decides it. The settlement is recorded on both facts.",
        "inputSchema": {"type": "object", "required": ["fact_id", "other_id", "keep", "reason"], "properties": {
            "fact_id": _STR,
            "other_id": _STR,
            "keep": {**_STR, "description": "fact_id, other_id, or both."},
            "reason": {**_STR, "description": "Why this side, in a sentence."},
        }},
    },
    {
        "name": "ingest_text",
        "description": "Add a document's text to the project. Factoid extracts, checks, and links its facts, and "
                       "returns the facts it kept and rejected. This calls models and can take a minute.",
        "inputSchema": {"type": "object", "required": ["text"], "properties": {
            "text": {**_STR, "description": "The document's full text."},
            "document_type": {**_STR, "description": "A document class in the project; omit to let it classify."},
            "uri": {**_STR, "description": "Where the text came from, such as a file name or URL."},
            "title": _STR,
            "metadata": {"type": "object", "description": "Fields the document class reads, such as signed_at."},
        }},
    },
]

WRITES = {"ingest_text", "settle_contradiction"}
READ_ONLY = [t for t in TOOLS if t["name"] not in WRITES]


class Server:
    """Reads requests from `inp` and writes responses to `out`, one JSON message per line."""

    def __init__(self, app: Any, *, read_only: bool = False, out: TextIO | None = None):
        self.app = app
        self.tools = READ_ONLY if read_only else TOOLS
        self.out = out or sys.stdout
        self.client = "mcp"  # who settles a contradiction, from the client's name at initialize

    def run(self, inp: TextIO) -> None:
        for line in inp:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
                continue
            for reply in self.handle_all(message):
                self._send(reply)

    def handle_all(self, message: Any) -> list[dict[str, Any]]:
        batch = message if isinstance(message, list) else [message]
        return [r for r in (self.handle(m) for m in batch) if r is not None]

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(message, dict) or "method" not in message:
            return None  # a response or junk: nothing to answer
        method, msg_id = message["method"], message.get("id")
        if msg_id is None:
            return None  # a notification, such as notifications/initialized
        params = message.get("params") or {}
        try:
            result = self._dispatch(method, params)
        except _RpcError as err:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": err.code, "message": str(err)}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            from .version import version

            asked = params.get("protocolVersion")
            client = (params.get("clientInfo") or {}).get("name")
            if client:
                self.client = f"mcp:{client}"
            return {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "factoid", "version": version()},
                    "instructions": "Facts extracted from this project's documents. Start with search_facts; each "
                                    "fact cites quotes from its source. Use read_entity for everything about one "
                                    "company or person. list_contradictions shows facts that "
                                    "disagree."}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "tools/call":
            return self._call(params.get("name", ""), params.get("arguments") or {})
        raise _RpcError(-32601, f"method not found: {method}")

    def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in {t["name"] for t in self.tools}:
            raise _RpcError(-32602, f"unknown tool: {name}")
        stdout, sys.stdout = sys.stdout, sys.stderr  # anything printed while working must not reach the protocol
        try:
            data = self._run_tool(name, args)
        except KeyError as err:
            return _text(f"error: missing argument {err}", error=True)
        except (api.NotFound, ValueError, TypeError) as err:
            return _text(f"error: {err}", error=True)
        except Exception as err:  # the server keeps running; the agent sees why
            return _text(f"error: {type(err).__name__}: {err}", error=True)
        finally:
            sys.stdout = stdout
        return _text(json.dumps(data, ensure_ascii=False, indent=1))

    def _run_tool(self, name: str, a: dict[str, Any]) -> Any:
        app = self.app
        if name == "search_facts":
            return api.search(app, a["query"], about=a.get("about"), as_of=a.get("as_of"),
                              top_k=int(a.get("top_k", 10)))
        if name == "read_fact":
            return api.fact(app, a["id"])
        if name == "list_facts":
            return api.facts(app, document=a.get("document"), trait=a.get("trait"),
                             status=a.get("status", "current"), limit=int(a.get("limit", 50)))
        if name == "find_entities":
            return api.entities(app, class_name=a.get("class"), name=a.get("name"), limit=int(a.get("limit", 20)))
        if name == "read_entity":
            return api.entity(app, a["name"], limit=int(a.get("limit", 50)))
        if name == "stats":
            return api.stats(app)
        if name == "list_contradictions":
            return api.contradictions(app, include_stale=bool(a.get("include_stale", True)),
                                      limit=int(a.get("limit", 20)))
        if name == "settle_contradiction":
            return api.settle(app, a["fact_id"], a["other_id"], keep=a["keep"], reason=a["reason"], by=self.client)
        return api.ingest(app, a["text"], document_type=a.get("document_type"), uri=a.get("uri"),
                          title=a.get("title"), metadata=a.get("metadata"))

    def _send(self, message: dict[str, Any]) -> None:
        self.out.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.out.flush()


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _text(text: str, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": error}
