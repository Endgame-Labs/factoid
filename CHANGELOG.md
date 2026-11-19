# Changelog

Features and fixes that change what Factoid does, by version. `SPEC.md` has the reasons behind each one.

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
