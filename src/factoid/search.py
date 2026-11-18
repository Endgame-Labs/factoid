"""Search indexes. Facts, chunks, and entities each have their own namespace.

`Turbopuffer` is the v1 index, and any turbopuffer-compatible endpoint works through `base_url`. `LocalIndex` keeps
the same interface in a SQLite file, with FTS5 for BM25 and exact vector search, for tests and small projects.

Hybrid search runs BM25 and vector search and fuses them with reciprocal rank fusion.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

import httpx
import numpy as np

__all__ = ["Index", "LocalIndex", "Turbopuffer", "rrf"]


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: -pair[1])


class Index:
    """The interface every search backend implements."""

    def upsert(self, namespace: str, rows: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    def delete(self, namespace: str, ids: list[str]) -> None:
        raise NotImplementedError

    def vectors(self, namespace: str, ids: list[str]) -> dict[str, list[float]]:
        """The stored vectors of these rows, by id. A row with none is left out."""
        return {}

    def bm25(self, namespace: str, text: str, top_k: int, filters: dict[str, Any] | None = None) -> list[str]:
        raise NotImplementedError

    def nearest(self, namespace: str, vector: list[float], top_k: int,
                filters: dict[str, Any] | None = None) -> list[str]:
        raise NotImplementedError

    def hybrid(self, namespace: str, text: str, vector: list[float] | None, top_k: int,
               filters: dict[str, Any] | None = None) -> list[tuple[str, float]]:
        rankings = [self.bm25(namespace, text, top_k, filters)]
        if vector is not None:
            rankings.append(self.nearest(namespace, vector, top_k, filters))
        return rrf(rankings)[:top_k]


_FTS_WORD = __import__("re").compile(r"[A-Za-z0-9]+")


class LocalIndex(Index):
    """An index in a SQLite file: FTS5 for BM25, and exact cosine search over stored vectors."""

    def __init__(self, path: Path | None):
        self._lock = threading.RLock()
        if path is None:
            self.db = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute("pragma journal_mode=wal")
        self.db.executescript(
            """create table if not exists rows (ns text, id text, text text, attrs text, vector blob,
               primary key (ns, id));
               create virtual table if not exists fts using fts5(ns unindexed, id unindexed, text);"""
        )
        self.db.commit()
        self._vectors: dict[str, tuple[list[str], np.ndarray | None]] = {}

    def upsert(self, namespace: str, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            for row in rows:
                vector = row.get("vector")
                blob = np.asarray(vector, dtype=np.float32).tobytes() if vector is not None else None
                attrs = {k: v for k, v in row.items() if k not in ("id", "text", "vector")}
                self.db.execute("insert or replace into rows values (?,?,?,?,?)",
                                (namespace, row["id"], row.get("text", ""), json.dumps(attrs), blob))
                self.db.execute("delete from fts where ns = ? and id = ?", (namespace, row["id"]))
                self.db.execute("insert into fts values (?,?,?)", (namespace, row["id"], row.get("text", "")))
            self.db.commit()
            self._vectors.pop(namespace, None)

    def delete(self, namespace: str, ids: list[str]) -> None:
        with self._lock:
            for id_ in ids:
                self.db.execute("delete from rows where ns = ? and id = ?", (namespace, id_))
                self.db.execute("delete from fts where ns = ? and id = ?", (namespace, id_))
            self.db.commit()
            self._vectors.pop(namespace, None)

    def vectors(self, namespace: str, ids: list[str]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        with self._lock:
            for start in range(0, len(ids), 500):
                part = ids[start:start + 500]
                rows = self.db.execute(
                    f"select id, vector from rows where ns = ? and vector is not null and id in "
                    f"({','.join('?' * len(part))})", (namespace, *part)).fetchall()
                out.update({id_: np.frombuffer(blob, dtype=np.float32).tolist() for id_, blob in rows})
        return out

    def _passes(self, attrs: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for key, want in filters.items():
            have = attrs.get(key)
            if isinstance(want, (list, tuple, set)):
                if isinstance(have, list):
                    if not set(have) & set(want):
                        return False
                elif have not in want:
                    return False
            elif isinstance(have, list):
                if want not in have:
                    return False
            elif have != want:
                return False
        return True

    def bm25(self, namespace: str, text: str, top_k: int, filters: dict[str, Any] | None = None) -> list[str]:
        words = _FTS_WORD.findall(text)
        if not words:
            return []
        query = " OR ".join(f'"{w}"' for w in words)
        with self._lock:
            rows = self.db.execute(
                "select fts.id, rows.attrs from fts join rows on rows.ns = fts.ns and rows.id = fts.id "
                "where fts.ns = ? and fts match ? order by bm25(fts) limit ?",
                (namespace, query, top_k * 5 if filters else top_k),
            ).fetchall()
        out = [id_ for id_, attrs in rows if self._passes(json.loads(attrs), filters)]
        return out[:top_k]

    def nearest(self, namespace: str, vector: list[float], top_k: int,
                filters: dict[str, Any] | None = None) -> list[str]:
        with self._lock:
            cached = self._vectors.get(namespace)
            if cached is None:
                rows = self.db.execute("select id, vector, attrs from rows where ns = ? and vector is not null",
                                       (namespace,)).fetchall()
                ids = [r[0] for r in rows]
                matrix = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows]) if rows else None
                if matrix is not None:
                    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                    matrix = matrix / np.where(norms == 0, 1, norms)
                attrs = {r[0]: json.loads(r[2]) for r in rows}
                cached = (ids, matrix)
                self._vectors[namespace] = cached
                self._attrs = getattr(self, "_attrs", {})
                self._attrs[namespace] = attrs
        ids, matrix = cached
        if matrix is None:
            return []
        query = np.asarray(vector, dtype=np.float32)
        query = query / (np.linalg.norm(query) or 1.0)
        scores = matrix @ query
        order = np.argsort(-scores)
        attrs = self._attrs[namespace]
        out = []
        for i in order:
            if self._passes(attrs[ids[i]], filters):
                out.append(ids[i])
                if len(out) >= top_k:
                    break
        return out


class Turbopuffer(Index):
    """turbopuffer, or any service with a turbopuffer-compatible API."""

    def __init__(self, base_url: str | None = None, retrieve: str = "hybrid-rrf", budget_tokens: int = 1500,
                 prefix: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or os.environ.get("TURBOPUFFER_BASE_URL") or self._default_url()).rstrip("/")
        self.retrieve = retrieve
        self.budget_tokens = budget_tokens
        self.prefix = prefix
        self._http = httpx.Client(timeout=timeout)

    @staticmethod
    def _default_url() -> str:
        return "https://gcp-us-central1.turbopuffer.com"

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        key = os.environ.get("TURBOPUFFER_API_KEY")
        if key:
            headers["authorization"] = f"Bearer {key}"
        return headers

    def _ns(self, namespace: str) -> str:
        return f"{self.prefix}-{namespace}" if self.prefix else namespace

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post(f"{self.base_url}{path}", headers=self._headers(), json=body)
        if response.status_code == 404 and "/query" in path:
            return {"rows": []}
        if response.status_code >= 400:
            raise RuntimeError(f"turbopuffer {path}: HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def upsert(self, namespace: str, rows: list[dict[str, Any]]) -> None:
        for start in range(0, len(rows), 200):
            batch = []
            for row in rows[start:start + 200]:
                item = {k: v for k, v in row.items() if v is not None}
                batch.append(item)
            self._post(f"/v2/namespaces/{self._ns(namespace)}", {
                "upsert_rows": batch,
                "distance_metric": "cosine_distance",
                "schema": {"text": {"type": "string", "full_text_search": True}},
            })

    def delete(self, namespace: str, ids: list[str]) -> None:
        if ids:
            self._post(f"/v2/namespaces/{self._ns(namespace)}", {"deletes": ids})

    def vectors(self, namespace: str, ids: list[str]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for start in range(0, len(ids), 500):
            part = ids[start:start + 500]
            body = {"filters": ["id", "In", part], "rank_by": ["id", "asc"], "top_k": len(part),
                    "include_attributes": ["vector"]}
            for row in self._post(f"/v2/namespaces/{self._ns(namespace)}/query", body)["rows"]:
                if row.get("vector") is not None:
                    out[row["id"]] = row["vector"]
        return out

    @staticmethod
    def _filters(filters: dict[str, Any] | None) -> list[Any] | None:
        if not filters:
            return None
        clauses = []
        for key, want in filters.items():
            if key.endswith("_ids"):  # array attributes
                if isinstance(want, (list, tuple, set)):
                    clauses.append([key, "ContainsAny", list(want)])
                else:
                    clauses.append([key, "Contains", want])
            elif isinstance(want, (list, tuple, set)):
                clauses.append([key, "In", list(want)])
            else:
                clauses.append([key, "Eq", want])
        return clauses[0] if len(clauses) == 1 else ["And", clauses]

    def bm25(self, namespace: str, text: str, top_k: int, filters: dict[str, Any] | None = None) -> list[str]:
        body: dict[str, Any] = {"rank_by": ["text", "BM25", text], "top_k": top_k}
        if (f := self._filters(filters)) is not None:
            body["filters"] = f
        return [row["id"] for row in self._post(f"/v2/namespaces/{self._ns(namespace)}/query", body)["rows"]]

    def nearest(self, namespace: str, vector: list[float], top_k: int,
                filters: dict[str, Any] | None = None) -> list[str]:
        body: dict[str, Any] = {"rank_by": ["vector", "ANN", vector], "top_k": top_k}
        if (f := self._filters(filters)) is not None:
            body["filters"] = f
        return [row["id"] for row in self._post(f"/v2/namespaces/{self._ns(namespace)}/query", body)["rows"]]
