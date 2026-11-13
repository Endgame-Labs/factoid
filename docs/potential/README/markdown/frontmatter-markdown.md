# Factoid 🧮

> **Status: Design draft.** Nothing is built yet. We update the docs and design first, before any code is written.

Factoid turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factoid updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

Create a project, generate your declarations, ingest sample mail, query facts, and run an eval:

```sh
factoid new support_desk
cd support_desk

factoid generate source inbox --kind imap
factoid generate document support_thread --segment email
factoid generate fact plan_tier --slot
factoid generate judge specificity --kind llm

factoid ingest ./sample_mail --source inbox
factoid search "Acme renewal tier" --budget-tokens 800
factoid read fact_01j8x9

factoid eval smoke
factoid eval smoke --vary judge=none,nli,jev-floors
```

## Project files

A project is a directory of Markdown files in conventional folders. Each file declares one item. YAML frontmatter holds
structured settings, and the Markdown body holds the instructions, rubrics, examples, and notes read by models and
people. You do not write application code to configure a project. When custom logic is needed, frontmatter references a
script in `scripts/`.

```text
support_desk/
  project.md
  sources/inbox.md
  documents/support_thread.md
  facts/plan_tier.md
  judges/specificity.md
  evals/smoke.md
  scripts/
```

Shared models, storage, indexes, search defaults, and the judge chain live in `project.md`. Models are named once and
pinned to exact versions. Secrets come from environment variables. The judge chain runs in order and rejects at the
first failure, so cheap checks run first.

```markdown
---
store: { kind: folder, path: ./data }
index: { kind: sqlite-fts, path: ./data/index.db }
models:
  fast: { provider: openai, id: gpt-4.1-mini-2025-04-14, api_key_env: OPENAI_API_KEY }
  judge_lm: { provider: anthropic, id: claude-haiku-4-5-20251001, api_key_env: ANTHROPIC_API_KEY }
judges: [nli, jev-floors, specificity]
search: { retrieve: hybrid-rrf, rerank: true, budget_tokens: 1200 }
---
Shared defaults for Support Desk. All timestamps normalize to UTC on ingest.
```

A document file in `documents/support_thread.md` configures pipeline stages (`classify`, `segment`, `extract`, `judge`,
`repair`, `resolve`, and `tag`) and holds the extraction instructions:

```markdown
---
classify: rules
match: { source: inbox, header_contains: "Support" }
segment: email
extract: { strategy: passages, model: fast }
facts: [plan_tier]
---
Extract customer commitments, subscription changes, and reported blockers.
Name the company and the speaker in every sentence. Skip greetings and signatures.
```

A fact file in `facts/plan_tier.md` defines an optional typed slot (`entity`, `field`, and `value`) and write-time
resolution rules:

```markdown
---
slot:
  entity: account
  field: plan_tier
  values: [free, pro, enterprise]
resolve: [hash, slot, vector-judge]
supersede: { by: slot, winner: newer }
---
State the current subscription tier for one customer account.
Example: "Acme Corp is on the enterprise plan as of 2026-03-01."
```

A judge file in `judges/specificity.md` pairs a built-in judge kind with its rubric:

```markdown
---
kind: llm
model: judge_lm
---
Reject any fact that uses unresolved pronouns, omits the account name, or states
a future guess as a settled commitment.
```

Any run or eval can override any frontmatter setting from the CLI by stage name or dotted path, such as `factoid eval
smoke --vary judge=none,nli,jev-floors` or `--vary search.retrieve=bm25,vector,hybrid-rrf`.

## Core ideas

- **Facts are what a reader reads.** Queries return short sentences with provenance under a token budget. On dialogue
  benchmarks, fact retrieval beat chunk retrieval at about a seventh of the read tokens; see
  [docs/prior-art.md](docs/prior-art.md).
- **Models never write evidence.** The extractor cites numbered source passages, and Factoid code attaches the exact
  quote, speaker, and timestamp.
- **History is the truth.** Deduplication, superseding, and contradiction checks run on write at ingest. Every change
  writes to an append-only event log (`added`, `superseded`, `contradicted`, `retracted`, and `restored`). Current fact
  tables and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** `factoid eval` scores a project against labeled sets and reports accuracy,
  cost, and latency. Built-in defaults come from eval results.

## Pluggable seams

- **Storage and indexes:** Store logs in a local folder or an S3-compatible bucket. Index views with `sqlite-fts`,
  `pgvectorscale`, or `turbopuffer`.
- **Sources:** Ingest from `folder`, `jsonl`, `imap`, `mcp`, or a custom script.
- **Pipeline strategies:** Mix built-in `classify` (`declared`, `rules`, `systemone`, and `llm`), `segment` (`auto`,
  `turns`, `email`, `paragraphs`, and `rows`), `extract` (`passages` and `staged`), and `resolve` (`hash`, `slot`, and
  `vector-judge`) strategies.
- **Models and judges:** Pin any supported model provider, and chain `nli`, `jev-floors`, `llm`, or script judges.

## Why this approach

Prompts and rubrics sit next to the settings that govern them, so a person can read one short file to understand one
document type, fact type, or judge. Git diffs stay small and readable, generators create clean starter files, and
non-programmers can edit prose without touching code. The tradeoff is cross-file indirection: renaming a fact type,
judge, or model touches multiple files and relies on `factoid check` to catch broken references. Expressing complex
conditional logic in YAML also hits a ceiling quickly, which pushes edge cases out into `scripts/`.

## Read next

Start with [docs/mental-model.md](docs/mental-model.md), and then read [docs/README.md](docs/README.md) for the full
design map. Note that [docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older
single-YAML design.
