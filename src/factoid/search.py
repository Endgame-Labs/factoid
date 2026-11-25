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
        self._vectors: dict[str, _Vectors] = {}

    def upsert(self, namespace: str, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            saved: dict[str, tuple[bytes | None, str]] = {}
            for row in rows:
                vector = row.get("vector")
                blob = np.asarray(vector, dtype=np.float32).tobytes() if vector is not None else None
                attrs = json.dumps({k: v for k, v in row.items() if k not in ("id", "text", "vector")})
                self.db.execute("insert or replace into rows values (?,?,?,?,?)",
                                (namespace, row["id"], row.get("text", ""), attrs, blob))
                self.db.execute("delete from fts where ns = ? and id = ?", (namespace, row["id"]))
                self.db.execute("insert into fts values (?,?,?)", (namespace, row["id"], row.get("text", "")))
                saved[row["id"]] = (blob, attrs)
            self.db.commit()
            if (cached := self._vectors.get(namespace)) is not None:
                cached.drop(list(saved))
                try:
                    cached.add([(id_, np.frombuffer(blob, dtype=np.float32), json.loads(attrs))
                                for id_, (blob, attrs) in saved.items() if blob is not None])
                except ValueError:  # vectors of another length: the next search loads them all, as it did before
                    del self._vectors[namespace]

    def delete(self, namespace: str, ids: list[str]) -> None:
        with self._lock:
            for id_ in ids:
                self.db.execute("delete from rows where ns = ? and id = ?", (namespace, id_))
                self.db.execute("delete from fts where ns = ? and id = ?", (namespace, id_))
            self.db.commit()
            if (cached := self._vectors.get(namespace)) is not None:
                cached.drop(ids)

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
            # data_version moves only when another connection writes, which this cache would not see
            version = self.db.execute("pragma data_version").fetchone()[0]
            cached = self._vectors.get(namespace)
            if cached is None or cached.version != version:
                rows = self.db.execute("select id, vector, attrs from rows where ns = ? and vector is not null",
                                       (namespace,)).fetchall()
                cached = self._vectors[namespace] = _Vectors(version)
                cached.add([(r[0], np.frombuffer(r[1], dtype=np.float32), json.loads(r[2])) for r in rows])
            if not cached.ids or top_k < 1:
                return []
            query = np.asarray(vector, dtype=np.float32)
            query = query / (np.linalg.norm(query) or 1.0)
            scores = cached.matrix[:len(cached.ids)] @ query
            picked: list[int] = []
            for i in np.argsort(-scores):
                if len(picked) >= top_k and scores[i] < scores[picked[top_k - 1]] - 1e-4:
                    break
                if self._passes(cached.attrs[cached.ids[i]], filters):
                    picked.append(i)
            # BLAS rounds a row's score by where the row sits, so near ties are scored again row by row, then by id
            exact = np.einsum("ij,j->i", cached.matrix[picked], query)
            ranked = sorted(zip(exact.tolist(), (cached.ids[i] for i in picked)), key=lambda p: (-p[0], p[1]))
        return [id_ for _, id_ in ranked[:top_k]]


class _Vectors:
    """One namespace's stored vectors, normalized, in a matrix with room to grow, so a save need not load them all
    again. Row order is not the database's: a dropped row takes the last row's place."""

    def __init__(self, version: int):
        self.version = version
        self.ids: list[str] = []
        self.at: dict[str, int] = {}
        self.attrs: dict[str, dict[str, Any]] = {}
        self.matrix = np.empty((0, 0), dtype=np.float32)

    def add(self, rows: list[tuple[str, np.ndarray, dict[str, Any]]]) -> None:
        if not rows:
            return
        new = np.stack([vector for _, vector, _ in rows])
        norms = np.linalg.norm(new, axis=1, keepdims=True)
        new = new / np.where(norms == 0, 1, norms)
        held = len(self.ids)
        if held + len(new) > len(self.matrix):
            grown = np.empty((max(2 * len(self.matrix), held + len(new)), new.shape[1]), dtype=np.float32)
            if held:
                grown[:held] = self.matrix[:held]
            self.matrix = grown
        self.matrix[held:held + len(new)] = new
        for id_, _, attrs in rows:
            self.at[id_] = len(self.ids)
            self.ids.append(id_)
            self.attrs[id_] = attrs

    def drop(self, ids: list[str]) -> None:
        for id_ in ids:
            i = self.at.pop(id_, None)
            if i is None:
                continue
            last = self.ids.pop()
            if last != id_:
                self.matrix[i] = self.matrix[len(self.ids)]
                self.ids[i], self.at[last] = last, i
            del self.attrs[id_]


#: Attributes the index stores as lists, which filter by membership.
ARRAY_ATTRIBUTES = {"traits"}

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
            if key in ARRAY_ATTRIBUTES or key.endswith("_ids"):
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
