"""The ISC-RAG held-out benchmark ("RAG Deserves an Index", arXiv 2608.20845), rerun with Factoid.

Corpus: the 500 held-out MediaSum transcripts (`heldout-500-20260726.txt`). Questions: the 499 held-out questions
from the study database (`data/heldout-500-questions.jsonl`, not in git). Everything a reader sees is built the way
the paper built it: the same answer prompt, the same judge prompt, the same source rendering, and greedy packing to a
token budget with cl100k_base.

What changes from the paper:
- Factoid builds the facts (extraction, fact evals, assess, linking, and resolve) instead of the original pipeline.
- The paper's reader (DeepSeek V4 Flash) and judge (Kimi K2.6) are retired. The reader here is GLM 5.3 Flash and the
  judge is Kimi K3.1 Pro, so the paper's numbers are a reference, not a head-to-head. The fair comparison is between
  the arms below, which share reader, judge, questions, and budgets.

Arms: `facts` (Factoid facts, corpus-wide hybrid search, top 300) and `chunks` (Factoid's chunks of the same
transcripts, 4,000 characters with 400 of overlap, like the paper's fixed chunks, top 300).

MediaSum is research-use only (see the ISC-RAG MEDIASUM-NOTICE): the data stays in `data/` and out of git.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tiktoken

from factoid import Model
from factoid.evals import Suite, generate_field
from factoid.models import ModelClient

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
BUDGETS = [256, 512, 1024, 2048, 4096, 8192, 16384]
TOP_K = 300
READER = Model("fireworks/glm-5p3-flash", reasoning_effort="low")  # thinking-only: it cannot be turned off
JUDGE = Model("fireworks/kimi-k3p1-pro", reasoning_effort="none")

ANSWER_SYSTEM = (
    'Answer only from the supplied transcript sources. Return ONLY JSON with this exact schema: '
    '{"answer":"...","cited_source_ids":[1,2]}. cited_source_ids must contain only source IDs that directly support '
    'the answer; use [] when the sources do not establish an answer. When the sources do not establish an answer, set '
    'answer exactly to "Insufficient source evidence." Do not mention source IDs in answer.'
)
JUDGE_SYSTEM = (
    "You judge whether a generated answer is semantically correct. You see only the question, the reference answer, "
    "and the generated answer. Judge whether the generated answer states the same essential fact(s) as the reference "
    "answer; wording may differ. If the generated answer is exactly \"Insufficient source evidence.\" it is correct "
    "only when the reference answer also indicates the question cannot be answered. Return ONLY JSON with this exact "
    "schema: {\"verdict\":\"correct\"} or {\"verdict\":\"incorrect\"}."
)


def load_transcripts(ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted, out = set(ids), {}
    with open(DATA / "mediasum" / "test.json") as f:
        for line in f:
            row = json.loads(line)
            if row["id"] in wanted:
                out[row["id"]] = row
    return out


def transcript_text(row: dict[str, Any]) -> str:
    utterances = json.loads(row["utt"]) if isinstance(row["utt"], str) else row["utt"]
    speakers = row["speaker"]
    if isinstance(speakers, str):
        import ast

        speakers = ast.literal_eval(speakers)
    return "\n".join(f"{' '.join(str(s).split())}: {' '.join(str(u).split())}" for s, u in zip(speakers, utterances))


def render(n: int, document: str, text: str, quote: str | None = None, speaker: str | None = None) -> str:
    """The paper's source rendering (internal/evaluation/evaluate.go, renderSource)."""
    out = f"[S{n} document={document}]\nSOURCE TEXT: {text}\n"
    if quote:
        out += "VERIFIED QUOTE" + (f" (speaker: {speaker})" if speaker else "") + f": {quote}\n"
    return out + "\n"


def pack(sources: list[str], budget: int, encoder: Any) -> tuple[str, int, int]:
    """Greedy packing to a token budget (packSources). Returns the context, sources packed, and tokens used."""
    parts, used = [], 0
    for text in sources:
        tokens = encoder.encode(text)
        if used + len(tokens) > budget:
            if not parts:
                parts.append(encoder.decode(tokens[:budget]))
                used = min(len(tokens), budget)
            break
        parts.append(text)
        used += len(tokens)
    return "".join(parts), len(parts), used


class HeldOut(Suite):
    name = "heldout"
    description = "ISC-RAG held-out 500 (MediaSum), 499 questions, facts against chunks across 7 read budgets."
    parallel = 8
    sample = "heldout-500-20260726.txt"
    budgets = BUDGETS

    def documents(self, limit: int | None = None):
        from app.documents import Transcript

        ids = (HERE / self.sample).read_text().split()
        rows = load_transcripts(ids)
        self.ids = ids[:limit] if limit else ids
        for doc_id in self.ids:
            row = rows[doc_id]
            yield Transcript(transcript_text(row), id=doc_id, uri=f"mediasum:{doc_id}", title=row.get("title"),
                             metadata={"date": row.get("date"), "program": row.get("program"),
                                       "title": row.get("title")})

    def splits(self) -> dict[str, set[str]]:
        """Groups of transcripts scored on their own as well as together. The held-out 500 has none."""
        return {}

    def questions(self) -> list[dict[str, Any]]:
        rows = [json.loads(line) for line in open(DATA / "heldout-500-questions.jsonl")]
        ids = set(self.ids)
        return [q for q in rows if q["transcript_id"] in ids]

    def score(self, app, results) -> dict[str, Any]:
        encoder = tiktoken.get_encoding("cl100k_base")
        reader = ModelClient({"generate": READER}, app.calls, app.meter)
        judge = ModelClient({"generate": JUDGE}, app.calls, app.meter)
        questions = self.questions()

        def sources_for(question: dict[str, Any]) -> dict[str, list[str]]:
            hits = app.search_facts(question["text"], top_k=TOP_K, freshness="any", contradictions=False)
            facts = []
            for i, hit in enumerate(hits):
                quote = hit.fact.quotes[0] if hit.fact.quotes else None
                facts.append(render(i + 1, hit.fact.document_id or "", hit.fact.text,
                                    quote.text if quote else None, quote.speaker if quote else None))
            chunks = [render(i + 1, c["document_id"], c["text"])
                      for i, c in enumerate(app.search_chunks(question["text"], top_k=TOP_K))]
            return {"facts": facts, "chunks": chunks}

        def answer(question: dict[str, Any], context: str) -> str:
            return generate_field(reader, f"Question: {question['text']}\n\nSources:\n{context}", "answer",
                                  "Insufficient source evidence.", system=ANSWER_SYSTEM)

        def correct(question: dict[str, Any], generated: str) -> bool:
            return generate_field(
                judge, f"Question: {question['text']}\n\nReference answer: {question['reference_answer']}\n\n"
                f"Generated answer: {generated}", "verdict", "", system=JUDGE_SYSTEM, max_tokens=200) == "correct"

        retrieved = app.map(sources_for, questions)
        cells: dict[str, Any] = {}
        per_question: dict[str, dict[str, bool]] = {q["external_id"]: {} for q in questions}
        for arm in ("facts", "chunks"):
            for budget in self.budgets:
                packed = [pack(r[arm], budget, encoder) for r in retrieved]

                def run(i: int, packed: list[tuple[str, int, int]] = packed) -> tuple[bool, int]:
                    context, _, used = packed[i]
                    return correct(questions[i], answer(questions[i], context)), used

                outcomes = app.map(run, range(len(questions)))
                right = sum(ok for ok, _ in outcomes)
                key = f"{arm}@{budget}"
                cells[key] = {"accuracy": round(right / len(questions), 4), "correct": right,
                              "questions": len(questions),
                              "mean_read_tokens": round(sum(t for _, t in outcomes) / len(outcomes))}
                for q, (ok, _) in zip(questions, outcomes):
                    per_question[q["external_id"]][key] = ok
        by_type: dict[str, dict[str, float]] = {}
        for key in (f"facts@{self.budgets[len(self.budgets) // 2]}", f"chunks@{self.budgets[len(self.budgets) // 2]}"):
            for q in questions:
                row = by_type.setdefault(q["question_type"], {})
                row[key] = row.get(key, 0) + per_question[q["external_id"]][key]
        for qtype, row in by_type.items():
            n = sum(1 for q in questions if q["question_type"] == qtype)
            for key in list(row):
                row[key] = round(row[key] / n, 3)
        mcnemar = {}
        for budget in self.budgets:
            b = sum(1 for r in per_question.values() if r[f"facts@{budget}"] and not r[f"chunks@{budget}"])
            c = sum(1 for r in per_question.values() if r[f"chunks@{budget}"] and not r[f"facts@{budget}"])
            mcnemar[str(budget)] = {"facts_only": b, "chunks_only": c, "p": _mcnemar(b, c)}
        surname_only, total = 0, 0
        for result in results:
            roster = result.document.roster()
            for fact in result.facts:
                total += 1
                for short, full in roster.items():
                    first = full.split(",")[0].split()[0]
                    tag = short.split("(")[0].strip().title()
                    if tag in fact.text and first.title() not in fact.text:
                        surname_only += 1
                        break
        stats = app.stats()
        (Path(app.data_dir or ".") / "per_question.json").write_text(json.dumps(per_question))
        splits = {}
        for split, ids in self.splits().items():
            chosen = [q for q in questions if q["transcript_id"] in ids]
            row: dict[str, Any] = {"questions": len(chosen)}
            for key in cells if chosen else ():
                row[key] = round(sum(per_question[q["external_id"]][key] for q in chosen) / len(chosen), 4)
            splits[split] = row
        return {"splits": splits,
                "surname_only_facts": round(surname_only / total, 4) if total else None,
                "facts_per_document": round(total / len(results), 1) if results else None, "cells": cells,
                "mcnemar_facts_vs_chunks": mcnemar, "by_question_type_at_2048": by_type,
                "facts_stored": stats["facts"], "entities": stats["entities"]}


def _mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value (binomial test on the discordant pairs)."""
    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 6)


class DevSample(HeldOut):
    """The paper's 100-document development sample and its 200 questions (original and expansion). Tune here, never on
    the held-out 500."""

    name = "dev"
    description = "ISC-RAG fact-development sample: 100 transcripts, 200 questions, for tuning."
    sample = "fact-development-sample-100-20260725.txt"
    budgets = [512, 2048, 8192]
    tuned_on = 30  # the fact evals and prompts were tuned on the first 30 transcripts (2026-11-17)

    def splits(self) -> dict[str, set[str]]:
        return {"tuning": set(self.ids[:self.tuned_on]), "unseen": set(self.ids[self.tuned_on:])}

    def questions(self) -> list[dict[str, Any]]:
        rows = []
        for name in ("questions-100.jsonl", "questions-100-expansion.jsonl"):
            for line in open(DATA / "dev" / name):
                q = json.loads(line)
                q["transcript_id"] = q["evidence"][0]["document_external_id"]
                rows.append(q)
        ids = set(self.ids)
        return [q for q in rows if q["transcript_id"] in ids]

