"""A docs assistant: answers about Python's standard library, from its "What's New" pages, with sources.

    uv run python rag.py "Can I use distutils?" --python 3.12
    uv run python rag.py "Which module parses TOML?" --python 3.11 --retriever chunks

This is a whole retrieval-augmented generation (RAG) pipeline in one file: retrieve sources for the question, pack
them into a budget, and ask a model to answer from them alone, citing the ones it used. Only the retriever changes
between the three ways it can run:

- `facts`: Factoid's facts, searched as of the version's release date. A fact that a later release changed (a module
  that was deprecated, then removed) is shown as it stood then, and a fact from a later release is left out.
- `chunks`: plain RAG, the usual baseline. The pages are cut into overlapping windows of about 500 tokens, and the
  best windows by hybrid search (BM25 and embeddings) are shown, from the pages released by that version.
- `both`: facts first, then windows in the space left, for detail a fact leaves out.

`evals/qa.py` scores all three on the same questions.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factoid.project import load
from factoid.steps import labelled

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TOP_K = 40  # sources considered before packing
WINDOW, STEP = 2000, 1800  # characters per window, and how far each window starts after the last
BUDGET = 8000  # characters of sources, about 2,000 tokens

SYSTEM = (
    "You answer questions about Python's standard library from the numbered sources only. The sources come from the "
    "\"What's New\" pages of Python releases, and things change between releases: a module can be added, deprecated, "
    "and later removed. Answer for the Python version in the question. Say plainly whether the thing exists in that "
    "version, whether it is deprecated, and what to use instead when the sources say. Keep it to two or three "
    "sentences. Return ONLY JSON: {\"answer\": \"...\", \"sources\": [numbers of the sources you used]}. If the "
    "sources do not answer the question, answer exactly \"The sources do not say.\""
)


def releases() -> dict[str, dict[str, Any]]:
    """Each fetched release's metadata, by version, oldest first."""
    found = [json.loads(p.read_text()) for p in DATA.glob("whatsnew-*.md.meta.json")]
    return {m["version"]: m for m in sorted(found, key=lambda m: m["released_at"])}


@dataclass
class Answer:
    question: str
    python: str
    retriever: str
    text: str
    sources: list[str]  # what the reader saw, numbered from 1
    cited: list[int] = field(default_factory=list)


# -- retrieve ----------------------------------------------------------------------------------------------------------


def facts(app: Any, question: str, python: str) -> list[str]:
    """Facts valid when `python` came out, best first, each with the release it came from."""
    released = releases()[python]["released_at"]
    hits = app.search_facts(question, as_of=released, valid_at=released, top_k=TOP_K, contradictions=False)
    return [f"{app.document_title(h.fact.document_id)}: {h.fact.text}" for h in hits]


_windows: dict[str, dict[str, Any]] = {}


def _index_windows(app: Any) -> None:
    """Cut every page into windows and index them once per process. Embeddings are cached, so this is free after
    the first run."""
    if _windows:
        return
    for version, meta in releases().items():
        text = (DATA / f"whatsnew-{version}.md").read_text()
        for start in range(0, max(1, len(text) - WINDOW + STEP), STEP):
            body = text[start:start + WINDOW].strip()
            if body:
                _windows[f"{version}:{start}"] = {"id": f"{version}:{start}", "text": body, "version": version,
                                                   "title": meta["title"]}
    rows = list(_windows.values())
    vectors = app.client.embed([w["text"] for w in rows])
    app.index.upsert(app.ns("rag-windows"), [{**w, "vector": v} for w, v in zip(rows, vectors)])


def chunks(app: Any, question: str, python: str) -> list[str]:
    """Windows from the pages released by `python`, best first."""
    _index_windows(app)
    order = list(releases())
    allowed = order[:order.index(python) + 1]
    vector = app.client.embed([question])[0]
    hits = app.index.hybrid(app.ns("rag-windows"), question, vector, TOP_K, {"version": allowed})
    return [f"{_windows[w]['title']}: {_windows[w]['text']}" for w, _ in hits if w in _windows]


def both(app: Any, question: str, python: str) -> list[str]:
    """Facts, then windows. `pack` keeps as many of each as fit, facts first."""
    return facts(app, question, python) + chunks(app, question, python)


RETRIEVERS = {"facts": facts, "chunks": chunks, "both": both}


# -- pack and answer ---------------------------------------------------------------------------------------------------


def pack(sources: list[str], budget: int) -> list[str]:
    """The best sources that fit in `budget` characters. The first one is cut to fit if it is too long alone."""
    out, used = [], 0
    for source in sources:
        if used + len(source) > budget:
            if not out:
                out.append(source[:budget])
            if budget - used < 200:
                break
            continue  # a long window does not fit, but a short fact after it may
        out.append(source)
        used += len(source)
    return out


def answer(app: Any, question: str, python: str, *, retriever: str = "facts", budget: int = BUDGET) -> Answer:
    sources = pack(RETRIEVERS[retriever](app, question, python), budget)
    numbered = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(sources))
    with labelled("answer"):
        raw = app.client.generate(f"Python version: {python}\nQuestion: {question}\n\nSources:\n{numbered}",
                                  json_mode=True, max_tokens=3000, system=SYSTEM)
    try:
        parsed = json.loads(raw)
        text = str(parsed.get("answer") or "").strip() or "The sources do not say."
        cited = [int(n) for n in parsed.get("sources") or [] if str(n).isdigit() and 0 < int(n) <= len(sources)]
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        text, cited = "The sources do not say.", []
    return Answer(question, python, retriever, text, sources, cited)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("question")
    parser.add_argument("--python", default=None, help="the Python version to answer for (default: the latest)")
    parser.add_argument("--retriever", choices=sorted(RETRIEVERS), default="facts")
    parser.add_argument("--budget", type=int, default=BUDGET, help="characters of sources (default: %(default)s)")
    args = parser.parse_args()
    known = releases()
    if not known:
        sys.exit("No pages yet: run `uv run python fetch.py`, then ingest them (see README.md).")
    python = args.python or list(known)[-1]
    if python not in known:
        sys.exit(f"--python {python}: pick one of {', '.join(known)}")
    app = load(HERE).app()
    result = answer(app, args.question, python, retriever=args.retriever, budget=args.budget)
    print(result.text)
    for n in result.cited:
        print(f"  [{n}] {result.sources[n - 1][:300]}")


if __name__ == "__main__":
    main()
