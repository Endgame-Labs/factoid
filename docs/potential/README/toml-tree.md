# Factorial 🧮

> **Status:** Design draft. Nothing is built yet. The docs are updated before any code is written.

Factorial turns documents into short, self-contained sentences, each tied to an exact source quote, who said it, and
when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate facts,
and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Core ideas

- **Facts are what a reader reads.** Search returns concise claims with provenance. On dialogue benchmarks, reading
  facts beat chunk retrieval at about a seventh of the read tokens (see [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages from the segmented document, and deterministic
  code attaches the exact quote, speaker, and timestamp.
- **History is the truth.** Storage is an append-only event log of `added`, `superseded`, `contradicted`, `retracted`,
  and `restored` events. Deduplication, superseding, and contradiction checks happen on write at ingest. Current state
  and search indexes are views rebuilt from the log.
- **Algorithm choices are made by evals.** `factorial eval` scores a setup against labeled data and reports quality,
  cost, and latency. Built-in defaults are recorded eval results.

## Fifteen minutes

Factorial ships as a single Rust binary. Generators scaffold small TOML files into conventional folders, and `factorial
check` validates cross-file references before any model call runs.

```sh
factorial new acme-memory && cd acme-memory
factorial generate source inbox --kind folder --path ./sample_docs
factorial generate document meeting --segment turns
factorial generate fact plan_tier --slot account,plan,string

factorial ingest inbox
factorial search "What billing plan is Northwind on?"
factorial read fact_01j8k2m9
factorial eval
factorial eval --vary judge=none,nli,jev-floors
```

## Project layout

A project is a directory of plain TOML files. Folder names give the kind of declaration, and filenames give each item
its identifier.

```text
acme-memory/
├── factorial.toml              # pinned models, store, index, pipeline, search
├── sources/
│   └── inbox.toml              # source "inbox"
├── documents/
│   └── meeting.toml            # document type "meeting"
├── facts/
│   └── plan_tier.toml          # fact type "plan_tier"
├── judges/
│   └── no_speculation.toml     # custom judge "no_speculation"
└── evals/
    └── golden.toml             # eval suite "golden"
```

`factorial.toml` declares shared infrastructure, pinned models (never `"latest"`), default pipeline stages (`classify`,
`segment`, `extract`, `judge`, `repair`, `resolve`, and `tag`), and search settings. Secrets are read from environment
variables.

```toml
# factorial.toml
[models]
extractor = "anthropic/claude-sonnet-4-20250514"
fast_judge = "openai/gpt-4.1-mini-2025-04-14"
embedder = "openai/text-embedding-3-small"

[store]
kind = "s3"
bucket = "acme-factorial"
secret_access_key = "$AWS_SECRET_ACCESS_KEY"

[index]
kind = "sqlite-fts"
path = ".factorial/index.db"

[pipeline]
judges = ["nli", "jev-floors", "no_speculation"]
repair = false
resolve = ["hash", "slot", "vector-judge"]
tag = []

[search]
retrieve = "hybrid-rrf"
rerank = true
budget_tokens = 1200
```

Sources declare where documents come from and how to classify them:

```toml
# sources/inbox.toml
kind = "imap"
host = "imap.acme.test"
password = "$IMAP_PASSWORD"
classify = "rules"
```

Document types declare how matching inputs are segmented and extracted:

```toml
# documents/meeting.toml
match_glob = "meetings/**"
segment = "turns"
extract = { method = "passages", model = "extractor" }
fact_types = ["plan_tier", "commitment"]
```

Fact types define a claim kind and an optional typed slot (`entity`, `field`, and `value`) so newer facts can supersede
older ones by rule:

```toml
# facts/plan_tier.toml
description = "Current subscription tier for a customer account."
slot = { entity = "account", field = "plan", value = "string" }
supersede = "slot" # same entity and field: newer timestamp wins
```

The judge chain in `pipeline.judges` runs in order and rejects a candidate at the first failure, so cheap deterministic
or small-model checks run first:

```toml
# judges/no_speculation.toml
kind = "llm"
model = "fast_judge"
prompt = "Reject if the sentence states an unconfirmed plan as a final decision."
```

### Overriding choices in evals

Factorial loads the directory tree into one resolved map (`documents.meeting.segment`, `pipeline.judges`,
`search.retrieve`). Short aliases cover common axes such as `judge`, `retrieve`, `segment`, and `extract`. Running
`factorial eval --vary judge=none,nli,jev-floors` clones the resolved config in memory per variant, swaps
`pipeline.judges`, and scores each run against an isolated temporary view without modifying files on disk.

## Pluggable seams

Every external boundary has built-in drivers and accepts plugins over HTTP or MCP:

- **Storage:** local `folder` or S3-compatible bucket (`s3`).
- **Indexes:** `sqlite-fts`, `pgvectorscale`, and `turbopuffer`, covering `bm25`, `vector`, and `hybrid-rrf` retrieval.
- **Sources:** `folder`, `jsonl`, `imap`, and `mcp`, paired with `declared`, `rules`, `systemone`, or `llm` classifiers
  and `auto`, `turns`, `email`, `paragraphs`, or `rows` segmenters.
- **Models and extractors:** pinned provider models driving `passages` or `staged` extractors.
- **Judges:** `nli`, `jev-floors`, `llm` prompt files, and external judge endpoints.

## Why this approach

Every declaration lives in a predictable folder where its filename is its name, keeping each file short and easy to find
with `ls` or `grep`. People and coding agents can generate, read, and edit plain TOML without learning a custom grammar
or installing a language runtime. Before running ingest or evals, `factorial check` validates the whole project graph
for missing models, unknown fact types, and invalid settings.

Static TOML files cannot express loops, conditionals, or inline code. Custom behavior that goes beyond built-in
strategies and prompt templates must run in an external HTTP or MCP plugin.

## Reading the docs

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md) for the full design
index. Note that [docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older
single-YAML design.
