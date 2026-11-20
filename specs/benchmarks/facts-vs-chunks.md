# Facts versus chunks

**Status: Decided** (Kyle, 2026-11-14) that this benchmark exists. The details below are Proposed.

## Why

Factoid indexes facts and chunks in separate namespaces (`SPEC.md`, "Chunking"). Besides serving search, the split lets
us run the same questions against facts, against chunks, and against both, on the same corpus with the same models. The
point is to show, on a user's own data, what the ISC papers showed on public data: facts give the same or better answers
for far fewer tokens.

## Prior result

From earlier research on the ISC-RAG data:

- ISC-RAG: 500 held-out documents, 69,746 facts, and 499 questions. Facts won all 32 cells against chunk policies. The
  best fact cell scored 85.2% at about 2.2k read tokens. The best plain chunk cell scored 72.5% at 16.3k.
- Full contextual retrieval (situated chunks) tied facts in quality (88.0%, p = 0.20) at about 21 times the read tokens.
- Accuracy for facts peaks near a 2k-token read budget and declines past it.
- When facts only pointed back to the chunks they came from (the Enron study), most of the gain disappeared. Facts have
  to be what the reader reads.
- Open negative result: with an agent using tools, fixed chunks led facts on evidence coverage. The suite includes an
  agent reader so this is measured, not assumed.

## Arms

All arms use the same corpus, questions, embedding model, reader model, and token budgets.

| Arm | What the reader gets |
| --- | --- |
| Facts | Fact sentences with their quotes, from the facts namespace |
| Chunks | Plain chunk text, from the chunks namespace, with `situate` off |
| Situated chunks | Chunks with their situation in front (contextual retrieval), with `situate` on |
| Both | Hybrid search in each namespace, then the reranker over the combined list |
| Facts pointing to chunks | Facts used only to find chunks; the reader gets the chunks |

Each arm runs with and without the reranker, and at several read budgets (for example 1k, 2k, 4k, 8k, and 16k tokens).
Each arm also runs with a single-call reader and with an agent reader that can search again.

## Measures

- Answer accuracy, judged against gold answers.
- Gold evidence in context, measured separately from reading accuracy.
- Read tokens per question, and total cost per question, including the ingest cost spread over the questions.
- Ingest cost and time per document for each arm: extraction for facts, and situation calls for situated chunks.
- Latency per question.
- Recall@k for each namespace.
- Variance across repeated runs.

## Running it

- `factoid eval --vary retrieval=facts,chunks,situated_chunks,both` on a project with labeled questions.
- A public version runs on the ISC-RAG corpus, so results can be compared with the paper.
- Raw model calls are archived, so a run can be replayed.

## Expected result

Facts match or beat situated chunks on accuracy at a small fraction of the read tokens, and beat plain chunks on both.
"Both" with a reranker may edge out facts alone on some questions; the benchmark measures whether that is worth its
token cost.

## Open

- Which labeled question sets ship with Factoid, beyond ISC-RAG.
- How ingest cost is spread across questions in the cost-per-question figure.
