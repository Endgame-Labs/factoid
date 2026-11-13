# Prior art

Factorial takes the best of three working fact systems and the findings of the ISC papers. This is what each taught us.
Surveyed on November 13, 2026.

## At a glance

| | OpenEndgame | endgame-wiki | cerebro | ISC papers |
| --- | --- | --- | --- | --- |
| Fact | sentence | sentence, plus claim facts for fields | triple plus prose | atomic claim plus quote, or a typed slot row |
| Quotes | model cites passage ids, code attaches | same | model writes, fuzzy-matched at 0.7 | exact-quote gate, never repaired |
| Acceptance | six JEV floors, one rewording repair | same (lifted) | none: quote found and speaker resolved | quote gate only |
| Dedup across sources | none | none | offline batch, cosine ≥ 0.96, with merge guards | content hash |
| Supersede and retract | none | tombstone lines in the log | `superseded_by`, resurrection | lifecycle state, `superseded_by` |
| Search | BM25 in SQL, LLM thesaurus, JEV rerank | lexical prefix match | turbopuffer hybrid with RRF | pgvector, turbopuffer |
| Document type | the connector | folder and header heuristics | the connector; gpt-5-mini for knowledge docs | System One `choice` (proposed, untested) |
| Storage | Postgres | append-only JSONL plus a SQLite index | AlloyDB, BigQuery, and turbopuffer | Postgres plus an index outbox |

None of them deduplicates across sources at ingest, handles contradictions in extracted facts, or types documents with
System One. Factorial does all three, and measures them.

## OpenEndgame (`Endgame-Labs/openendgame`)

Keep:
- Sentence-first facts. Triples were removed on purpose.
- The model cites numbered passages, and code attaches the quote; then a judge trims the quote to the sentences that
  carry the fact.
- Fixed windows of about 3.5 KB of new text, with the document's opening and the previous window's tail as uncitable
  context. Window size never depends on model context; 10 KB windows cut accepted facts per source by about 70%.
- Per-criterion floors, never averaged, calibrated on 272 hand-labeled candidates (`fact_acceptance_labels.jsonl`):
  0.8 to 0.85 floors gave precision 0.97 and recall 0.17; the current floors give 0.96 and 0.91.
- A deterministic roster that completes first names to full names only when exactly one roster person matches.
- A version fingerprint over prompts, floors, and constants, excluding the model, that converges the corpus without
  backfills.
- Search with no vectors (BM25, a thesaurus written once by an LLM, and a JEV rerank) matched Qwen3-8B reranking on
  TREC DL (nDCG@10 0.696 against 0.699).

Avoid:
- Fact ids that hash the assessment, so a re-judge mints new ids and leaves citations dangling.
- No supersede, retract, or contradiction handling; novelty checked within one source only.
- Total dependence on one judge with a 28 KB request limit, which forces narrowing ladders everywhere.
- Coupling to Postgres, the job queue, and the wiki's identity graph.

## endgame-wiki (`Endgame-Labs/endgame-wiki`)

Keep:
- An append-only JSONL log as the authority, with tombstones (retire, retract) instead of rewrites.
- A rebuildable SQLite index that returns a superset and re-checks every hit against the log.
- Content-addressed ids: the same claim from the same record is always the same fact.
- A contract version that hashes the effective prompts **and** a probe run of the engine against fake models, so a hidden
  wording change still moves the version.
- A rebuild that re-links without any model call when only linking changed, and shows a cost estimate first.
- A daily budget, an archive of every model call, and one-line stops for provider auth and billing failures.
- Code keeps indexes, formats, logs, budgets, and guards; judgment lives in prompts you can copy out and change.

Avoid:
- No dedup or novelty across records; no semantic retrieval.
- The lifted engine reached through an in-process HTTP bridge.
- Document type from folder names and header lines.
- Product vocabulary (accounts, deals, curators) tangled into fact reads.

## cerebro (`Endgame-Labs/cerebro`)

Keep:
- Grounding as a gate: quote found in the source, with character offsets, and the speaker and their side (ours or
  theirs) from transcript markup, never a model.
- A cheap staged pipeline: a small model extracts `{fact, quote}`, a smaller one tags in batches of 25.
- Supersede, not delete: losers get `superseded_by`, keepers collect `related_facts`, chains resolve transitively, and a
  superseded fact is resurrected if its keeper is deleted.
- Merge guards: never merge across speakers' sides, document types, different days with an older keeper, or mismatched
  entities and numbers.
- Hybrid search: vector and BM25 for one to three query phrasings, fused with RRF (k = 60), with deterministic ties.
- Salience learned from 50,000 real citations (AUC 0.704), as a ranking prior rather than a gate.
- Facts from people (`user_assertion`) in the same store, with dispute and supersede semantics.
- NLI (DeBERTa) to verify claims derived from facts.

Avoid:
- Logic split across Python, Go, and YAML with string contracts between them.
- Hard-coded models, prompts, tags, and thresholds.
- Dedup as an offline batch.
- A re-sync that silently destroyed facts for 275 meetings over nine days (END-8632): deletes must be events.

## The ISC papers (`dorkitude/phd`)

- **Facts are the payload, not the pointer.** ISC-RAG (500 held-out documents, 69,746 facts, 499 questions): facts won
  all 32 cells against chunk policies; best fact cell 85.2% at about 2.2k read tokens against 72.5% for the best chunk
  cell at 16.3k. Full contextual retrieval tied facts (88.0%, p = 0.20) at about 21 times the tokens. When facts only
  pointed back to chunks (the Enron study), most of the gain disappeared.
- **Accuracy peaks near a 2k-token read budget** for facts and declines past it.
- **The exact-quote gate rejects about 1%** of candidates (29 of 2,724).
- **Compiling governed facts at ingest** (iCAST-ES 2026): a cheap model reading compiled rows was exact on 6 of 6 hard
  governance questions in every seed; reconstructing at query time it was exact on 0 or 1 of 6, at 12.9 times the cost.
- **Rephrasing compresses dialogue** to 0.49 times its tokens but leaves prose at 1.03, so the right extraction depends
  on the document type.
- **Maintenance cost scales with change, not corpus size**, and an embedding-model switch can be handled by alignment
  instead of a full re-embed.
- **Measure** tokens and cost per stage, gate rejection rate, facts per document, gold evidence in context separately from
  reading accuracy, recall@k, calibration, and draw-to-draw variance. Archive raw calls so results can be replayed.
- **An open negative result:** with an agent using tools, fixed chunks led facts on evidence coverage. The fact advantage
  does not automatically survive the agent layer. Factorial's suites should include an agent reader.

## System One (`dorkitude/system-one-techniques`)

Fast choice models (TypeSafe's Jev) answer typed questions in one pass, 27 to 225 ms, with no generated text: `noul`
(probability true), `choice` (a distribution over options), and `score` (a rubric level). `choice` is the natural fit for
document typing. Lessons: pin model versions (`jev-1.14.0` was not an upgrade), send one item per request, give a
representative view (head, label, and tail beat the first sentence alone: recall@10 0.975 against 0.738), and pick
thresholds by calibration, not 0.5.
