# Changelog

Features and fixes that change what Factoid does, by version. `SPEC.md` has the reasons behind each one.

## 0.1.10 (2026-11-19)

- **Model calls by step.** Each model call is labelled with the step that made it (`evaluate`, `assess`, `link`,
  `resolve`, and so on). `ingest` prints calls and tokens by step, eval scorecards add `usage.by_step`, and
  `factoid calls` lists recent calls with their step, tokens, and the questions a decision call asked (issue #7).

## 0.1.9 (2026-11-19)

- **Bounds on model calls.** `Settings.model_attempts` (12 by default), `model_timeout` (180 seconds per response),
  and `model_deadline` (seconds for one call in all, tries and waits included) let an app that answers people fail a
  stuck call in seconds instead of minutes (issue #5).

## 0.1.8 (2026-11-19)

- **Saving a changed document again.** Old facts stay current until the new version's facts are saved, so a failed
  run loses nothing. The old text is kept as a revision, and each fact records its revision, so old quotes still
  point at the text they quote. A new fact that says what an old one said keeps its id, judged by an exact match, a
  close match, or the decision model's "duplicate" (event `fact.restated`). An old fact the new version changes or
  drops becomes `replaced`, apart from a person's `retracted` (issue #3).

## 0.1.7 (2026-11-19)

- **Many apps in one process.** Worker threads now use the app that started the work, not the last one made, so two
  apps in one process no longer write into each other's stores (issue #2). `app.active()` makes an app active for class
  reads such as `Fact.get` in a block. `factoid serve` no longer makes reads wait for an ingest.

## 0.1.6 (2026-11-19)

- **Resolve fix.** A later restatement of a fact no longer supersedes it when the decision model gives a change no
  weight. Resolve's split rule now needs `resolve_split_floor` (0.2) on "supersedes" (issue #4).
- **Eval rerun.** Every example suite was run again. The legal as-of questions add a reranked-chunks arm. Amendment
  recall counts only facts quoting the labeled new clause, and false changes cover every document. iscrag scores its
  tuning and unseen transcripts apart. Scorecards are committed under each example's `scorecards/`.

## 0.1.5 (2026-11-19)

- **Eval fixes.** AUPR and precision at recall treat tied scores as one threshold, so they no longer depend on input
  order or overstate the area. A `DecisionFloors` subclass that changes one floor keeps each decision model's other
  floors. The sample eval checks each of the three facts on its own and counts extra facts against precision.
- **Fixes.** `stats` no longer counts a contradiction whose side was retracted, and turbopuffer filters traits with its
  array operator.
- **Example evals.** `cuad_heldout` and `cuad_fresh` score 20 contracts each without `--limit`, and two diligence
  checks no longer pass when the email extracted nothing.
- **Tests.** Duplicates, corrections, ends, contradictions settled by evidence, and checks that the reranker and the
  resolve check run.

## 0.1.4 (2026-11-19)

- **Settling contradictions.** `factoid contradictions` lists pairs of facts that disagree, and `factoid contradictions
  settle` keeps one side (retracting the other) or both, with a reason. New evidence settles a pair too: when a newer
  fact supersedes, ends, or corrects one side, the other stands. Every settlement is a `fact.settled` event. The HTTP
  API (`GET /contradictions`, `POST /contradictions/settle`) and the MCP server (`list_contradictions`,
  `settle_contradiction`) do the same.

## 0.1.3 (2026-11-19)

- **MCP server.** `factoid mcp` gives an agent the project's facts as MCP tools over stdio: search, read a fact, list
  facts, find and read entities, stats, and ingest. `--read-only` leaves out ingest. Add it to Claude Code with
  `claude mcp add factoid -- factoid mcp`.

## 0.1.2 (2026-11-19)

- **HTTP API.** `factoid serve` serves search, facts, entities, stats, and ingest as JSON. It listens on 127.0.0.1
  by default, and `FACTOID_API_TOKEN` guards it when it serves other machines.
- **Exports.** `factoid export` sends facts, entities, documents, and events to Parquet files (a local folder, S3, or
  R2) and to a turbopuffer namespace. Each export sends only what changed since its last run, and
  `export_after_ingest` runs them after each ingest.
- **First-run fixes.** `factoid keys set` works without a terminal, `factoid init` switches an existing project's
  preset and writes back deleted sample files, and the sample eval scores all three sample facts.
- **Releases.** Package metadata, CI, and a trusted-publishing workflow for PyPI.
- **Resolve with Rune.** Decision models that need it get a yes-or-no check on each change, which cuts false
  supersessions.

## 0.1.1 (2026-11-17)

- **Onboarding.** One-provider presets, guided `factoid keys set`, per-project keys in `~/.factoid/projects/`, and
  clear errors for missing keys.
- **Structured documents.** `StructuredDocument` reads rows from CSV, JSONL, JSON, or records, and `factoid struct`
  inspects a file, writes a parser, and dry-runs it.
- **Fact evals.** `DecisionFloors` with floors per decision model, fact evals per document class, and repair that
  splits a fact with several claims and names unclear references.
- **Reading facts.** `factoid stats` and `factoid facts list`. A re-ingest skips unchanged documents and keeps fact
  ids.
- **Models.** Generation models per step, and calls that ride out rate limits.

## 0.1.0 (2026-11-15)

- The first package: ingest documents into facts and entities, link and resolve them, search with as-of dates, and
  measure everything with `factoid eval`.
- Example apps: `legal` (contracts and amendments) and `iscrag` (the ISC-RAG benchmark).
