"""Question answering on the amendment chains: Factoid facts against plain RAG over chunks.

Each as-of question in a chain ("What is the Purchase Expiration Date ...?" on a date) is answered twice by the same
reader, with the same prompt and the same source budget. Only the sources differ:

- facts: `search_facts(question, as_of=date)`, each fact shown with its source and the date it took effect.
- chunks: plain hybrid search (BM25 and embeddings) over 2,000-character windows of the documents signed by that
  date, each shown with its source and signing date. This is the baseline: a common RAG setup with date metadata,
  and no facts, resolve, or supersession. It has its own windows, not Factoid's 6,000-character extraction chunks,
  which would leave room for one chunk at the small budget.

Both arms are scored at two source budgets: about 2,000 and 8,000 tokens.

The same judge then decides whether each answer gives the term in force on that date, the outdated one, or neither,
from the two clauses the chain's labels point at.
"""

from __future__ import annotations

import json
from typing import Any

from factoid.models import Model, ModelClient

READER = Model("fireworks/glm-5p3-flash", reasoning_effort="low")  # the ISC-RAG reader; thinking cannot be turned off
JUDGE = Model("fireworks/kimi-k3p1-pro", reasoning_effort="none")
BUDGETS = (8000, 32000)  # characters of sources per question, about 2,000 and 8,000 tokens, for both arms
TOP_K = 40
WINDOW, STEP = 2000, 1800

ANSWER_SYSTEM = (
    "Answer the question from the supplied contract sources only. Contracts are amended over time, so give the terms "
    "in force on the stated date. Return ONLY JSON: {\"answer\": \"...\"}. If the sources do not establish an answer, "
    "answer exactly \"Insufficient source evidence.\""
)
JUDGE_SYSTEM = (
    "You judge an answer to a question about a contract on a given date. You see the clause in force on that date, an "
    "outdated clause it replaced or that was not yet in force, and the answer. Decide whether the answer gives the "
    "terms of the clause in force (\"current\"), the terms of the outdated clause (\"outdated\"), or neither "
    "(\"neither\", including no answer). Return ONLY JSON: {\"verdict\": \"current\"} or {\"verdict\": \"outdated\"} "
    "or {\"verdict\": \"neither\"}."
)


def _pack(items: list[str], budget: int) -> str:
    out, used = [], 0
    for item in items:
        if used + len(item) > budget:
            if not out:
                out.append(item[:budget])
            break
        out.append(item)
        used += len(item)
    return "\n\n".join(out)


def _context(text: str, start: int, end: int, pad: int = 800) -> str:
    # Wide enough for a schedule: NEON's payment terms step from 120 days to 90 days in the next sentence, and a
    # 300-character excerpt hid that from the judge, so a right answer was graded wrong.
    return " ".join(text[max(0, start - pad):end + pad].split())


def qa_scores(suite: Any, app: Any) -> dict[str, Any]:
    """Accuracy of each arm on the suite's as-of questions, with one row per question."""
    reader = ModelClient({"generate": READER}, app.calls, app.meter)
    judge = ModelClient({"generate": JUDGE}, app.calls, app.meter)
    signed = {f"amend_{d['key'].replace('-', '_')}": d["signed_at"] for c in suite.chains for d in c["documents"]}
    titles = {f"amend_{d['key'].replace('-', '_')}": d["name"] for c in suite.chains for d in c["documents"]}
    questions = []
    for chain in suite.chains:
        for query, as_of, (want_key, want_snip), (old_key, old_snip) in chain["as_of"]:
            want, old = suite.locate(want_key, want_snip), suite.locate(old_key, old_snip)
            questions.append({
                "query": query, "as_of": as_of,
                "current": _context(suite.texts[want_key], want.start, want.end),
                "outdated": _context(suite.texts[old_key], old.start, old.end),
                "documents": [f"amend_{d['key'].replace('-', '_')}" for d in chain["documents"]
                              if d["signed_at"] <= as_of],
            })

    def facts_for(q: dict[str, Any]) -> list[str]:
        hits = app.search_facts(q["query"], as_of=q["as_of"], top_k=TOP_K, contradictions=False)
        return [f"[{i + 1}] {titles.get(h.fact.document_id, h.fact.document_id)}, in force from "
                f"{(h.fact.valid_from or h.fact.source_datetime or '')!s:.10}: {h.fact.text}"
                for i, h in enumerate(hits)]

    namespace = app.ns("rag-windows")
    windows = []
    for key, text in suite.texts.items():
        doc_id = f"amend_{key.replace('-', '_')}"
        for start in range(0, max(1, len(text) - WINDOW + STEP), STEP):
            body = " ".join(text[start:start + WINDOW].split())
            if body:
                windows.append({"id": f"{doc_id}:w{start}", "text": body, "document_id": doc_id})
    vectors = app.client.embed([w["text"] for w in windows])
    app.index.upsert(namespace, [{**w, "vector": v} for w, v in zip(windows, vectors)])
    by_id = {w["id"]: w for w in windows}

    def chunks_for(q: dict[str, Any]) -> list[str]:
        if not q["documents"]:
            return []
        vector = app.client.embed([q["query"]])[0]
        hits = app.index.hybrid(namespace, q["query"], vector, TOP_K, {"document_id": q["documents"]})
        return [f"[{i + 1}] {titles.get(by_id[w]['document_id'], '')}, signed "
                f"{signed.get(by_id[w]['document_id'], '')[:10]}: {by_id[w]['text']}"
                for i, (w, _) in enumerate(hits) if w in by_id]

    def answer(q: dict[str, Any], context: str) -> str:
        raw = reader.generate(f"Date: {q['as_of'][:10]}\nQuestion: {q['query']}\n\nSources:\n{context}",
                              json_mode=True, max_tokens=3000, system=ANSWER_SYSTEM)
        try:
            return str(json.loads(raw).get("answer") or "").strip() or "Insufficient source evidence."
        except (json.JSONDecodeError, AttributeError):
            return "Insufficient source evidence."

    def verdict(q: dict[str, Any], generated: str) -> str:
        raw = judge.generate(
            f"Date: {q['as_of'][:10]}\nQuestion: {q['query']}\n\nClause in force: {q['current']}\n\n"
            f"Outdated clause: {q['outdated']}\n\nAnswer: {generated}", json_mode=True, max_tokens=200,
            system=JUDGE_SYSTEM)
        try:
            return str(json.loads(raw).get("verdict"))
        except (json.JSONDecodeError, AttributeError):
            return "neither"

    out: dict[str, Any] = {}
    rows = [{"as_of": q["as_of"][:10], "query": q["query"][:80]} for q in questions]
    for arm, sources in (("facts", facts_for), ("chunks", chunks_for)):
        retrieved = app.map(sources, questions)
        for budget in BUDGETS:
            cell = f"{arm}@{budget // 4}"
            answers = app.map(lambda pair, b=budget: answer(pair[0], _pack(pair[1], b)),
                              list(zip(questions, retrieved)))
            verdicts = app.map(lambda pair: verdict(*pair), list(zip(questions, answers)))
            for row, v, a in zip(rows, verdicts, answers):
                row[cell] = v
                row[f"{cell} answer"] = a[:160]
            n = len(verdicts)
            out[f"qa_{cell}"] = round(sum(v == "current" for v in verdicts) / n, 3) if n else None
            out[f"qa_{cell}_outdated"] = round(sum(v == "outdated" for v in verdicts) / n, 3) if n else None
    out["qa_questions"] = len(questions)
    out["qa_details"] = rows
    return out
