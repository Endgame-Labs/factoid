# Factoid 🧮

> **Status:** Design draft. Nothing is built yet. Documentation is updated before code is written.

Factoid turns documents into short, self-contained facts, each tied to an exact source quote, the speaker, and the
timestamp.

As new documents arrive, Factoid updates its set of facts. It retires outdated facts, merges duplicate facts, and
flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Core ideas

- **Facts are what a reader reads.** On dialogue benchmarks, reading extracted facts beat chunk retrieval at about a
  seventh of the read tokens (see [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and Factoid code attaches the exact quote
  from the source document.
- **History is the truth.** An append-only event log records every state change: `added`, `superseded`, `contradicted`,
  `retracted`, and `restored`. Deduplication, superseding, and contradiction checks run on write at ingest. Current
  state and search indexes are views rebuilt from the log.
- **Algorithm choices are made by evals.** `factoid eval` scores a setup against labeled data and reports accuracy,
  cost, and latency. Framework defaults are eval results.

## Fifteen minutes

Create a project, generate definitions, ingest documents, query facts, and evaluate variations:

```bash
factoid new acme-kb
cd acme-kb
factoid generate source inbox --kind imap
factoid generate document meeting --segment turns --extract passages
factoid generate fact ownership --slot service,owner
factoid ingest ./sample-meetings
factoid search "who owns billing?"
factoid read fact_01j9x4k
factoid eval
factoid eval --vary judge=none,nli,jev-floors
```

## Project layout

Each file in `sources/`, `documents/`, `facts/`, and `judges/` declares one component named after its filename. Shared
settings and pipeline defaults live in `factoid.config.ts`.

```text
acme-kb/
  factoid.config.ts
  sources/
    inbox.ts
  documents/
    meeting.ts
  facts/
    ownership.ts
  judges/
    speaker_present.ts
  evals/
    golden.jsonl
```

## Declarations

Shared configuration pins model versions once, reads secrets from environment variables, and sets defaults across the
seven pipeline stages (`classify`, `segment`, `extract`, `judge`, `repair`, `resolve`, and `tag`). Cheap judges go first
because the judge chain rejects at the first failure.

```ts
// factoid.config.ts
import { defineConfig } from "factoid";

export default defineConfig({
  store: { kind: "s3", bucket: "acme-facts", secretKey: process.env.S3_SECRET_KEY! },
  index: { kind: "pgvectorscale", url: process.env.DATABASE_URL! },
  models: { fast: "claude-haiku-4-5-20251001", strong: "claude-sonnet-4-5-20250929" },
  pipeline: {
    classify: "rules", // declared | rules | systemone | llm
    segment: "auto",   // auto | turns | email | paragraphs | rows
    extract: { kind: "passages", model: "fast" },
    judge: ["speaker_present", "nli", "jev-floors", { kind: "llm", model: "strong" }],
    repair: { attempts: 1, model: "fast" },
    resolve: ["hash", "slot", "vector-judge"],
    tag: [],
  },
  search: { retrieve: "hybrid-rrf", rerank: true, budget_tokens: 1500 }, // bm25 | vector | hybrid-rrf
});
```

Sources, document types, fact types, and custom judges each live in small, focused files:

```ts
// sources/inbox.ts
import { defineSource } from "factoid";

export default defineSource({ kind: "imap", host: "imap.acme.internal", password: process.env.IMAP_PASSWORD! });
```

```ts
// documents/meeting.ts
import { defineDocument } from "factoid";

export default defineDocument({
  match: { path: "meetings/**" },
  segment: "turns",
  extract: { kind: "staged", model: "strong" },
});
```

```ts
// facts/ownership.ts
import { defineFact, slot } from "factoid";

export default defineFact({
  description: "Which person or team owns a service.",
  slot: { entity: slot.string("service"), field: "owner", value: slot.string("owner") },
  supersede: { by: "slot", prefer: "newer" }, // same entity and field: newer value wins
});
```

```ts
// judges/speaker_present.ts
import { defineJudge } from "factoid";

export default defineJudge((candidate) => ({
  pass: Boolean(candidate.speaker && candidate.saidAt),
  reason: "Fact requires a known speaker and timestamp.",
}));
```

**Overriding choices in evals.** At startup, Factoid loads `factoid.config.ts` and the conventional directories into
one addressable configuration tree. Passing `--vary judge=none,nli,jev-floors` or `--vary
documents.meeting.extract=passages,staged` clones that tree per trial and swaps the targeted path in memory before
running the suite.

## Pluggable seams

- **Storage:** Store the event log in a local folder or an S3-compatible bucket, and index views in `sqlite-fts`,
  `pgvectorscale`, or `turbopuffer`.
- **Sources:** Ingest from built-in `folder`, `jsonl`, `imap`, and `mcp` sources, or write an async iterator in
  `sources/`.
- **Models:** Name models once with pinned version IDs (never `"latest"`) and reference those names across stages.
- **Judges:** Chain built-in `nli`, `jev-floors`, and `llm` judges with custom functions in `judges/`.

## Why this approach

Conventional TypeScript modules give every source, document type, fact type, and judge a guessable file path for people
and coding agents. Standard editors autocomplete built-in strategies, check model names, and validate slot definitions
with zero extra build tooling. Custom classifiers, sources, and judges use plain functions in the same directory
structure as declarative configs. This approach requires a JavaScript runtime such as Node or Bun, even when callers use
Factoid through the CLI, HTTP API, or MCP. Because configuration files are executable code, external tooling must load
the modules to inspect the resolved graph.

## Docs

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md).
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design.
