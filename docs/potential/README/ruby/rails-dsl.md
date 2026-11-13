# Factorial 🧮

> **Status:** This document is a design draft. Nothing is built yet, and the docs get updated before code is written.

Factorial turns documents into short, self-contained sentences called facts. Each fact ties to an exact source quote,
who said the quote, and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts,
merges duplicate facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP
API, and MCP.

## Core ideas

- **Facts are what a reader reads.** Queries return short sentences with provenance. On dialogue benchmarks, fact
  retrieval beat chunk retrieval at about a seventh of the read tokens ([docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and deterministic code attaches the exact
  quote, speaker, and timestamp.
- **History is the truth.** Ingest writes to an append-only event log: `added`, `superseded`, `contradicted`,
  `retracted`, and `restored`. Deduplication, superseding, and contradiction checks run at ingest, on write. Current
  state and search indexes are views rebuilt from the log.
- **Algorithm choices are made by evals.** `factorial eval` scores a setup against labeled data and reports accuracy,
  cost, and latency. Framework defaults are eval results.

## Fifteen minutes

Factorial runs on Ruby 3.4+. Create a project, run the generators, ingest sample files, query the resulting facts, and
compare judges:

```sh
factorial new acme_kb
cd acme_kb
factorial generate source inbox --adapter imap
factorial generate document support_email --segment email
factorial generate fact subscription_tier account:string tier:string
factorial ingest ./samples
factorial search "What tier is Northwind on?"
factorial read fact_01j9x8k2
factorial eval
factorial eval --vary judge=none,nli,jev_floors
```

## Project layout

A project is a directory of small Ruby classes in conventional paths. A file's name and location state its role, and
base classes provide defaults.

```text
acme_kb/
  app/
    documents/
      application_document.rb
      support_email.rb
    facts/
      application_fact.rb
      subscription_tier_fact.rb
    judges/
      citation_span_judge.rb
    sources/
      inbox_source.rb
  config/
    application.rb
    environments/
      development.rb
      production.rb
  evals/
    billing_suite.rb
    billing_gold.jsonl
```

## Declaring a project

Shared settings live in `config/application.rb`, with per-environment overrides in `config/environments/`. Models are
named once with pinned snapshot IDs, and secrets come from environment variables.

```ruby
# config/application.rb
class Application < Factorial::Application
  model :fast_extractor, provider: :anthropic, id: "claude-haiku-4-5-20251001", api_key: ENV.fetch("ANTHROPIC_API_KEY")
  model :strict_judge,   provider: :openai,    id: "gpt-4.1-2025-04-14",        api_key: ENV.fetch("OPENAI_API_KEY")

  store :s3, bucket: ENV.fetch("FACTORIAL_BUCKET")
  index :pgvectorscale, url: ENV.fetch("DATABASE_URL")

  classify :rules
  judges   :jev_floors, :nli, :citation_span, llm: { model: :strict_judge }
  search   retrieve: :hybrid_rrf, rerank: true, budget_tokens: 1200
end
```

The judge chain runs in order and rejects a candidate at the first failure, so fast, cheap checks go first.

Document classes customize the ingest stages (`classify`, `segment`, `extract`, `judge`, `repair`, `resolve`, and
`tag`):

```ruby
# app/documents/support_email.rb
class SupportEmail < ApplicationDocument
  match_header "X-Mailer", /Zendesk/
  segment :email
  extract :passages, model: :fast_extractor
  resolve :hash, :slot, :vector_judge
  tag     :support
  emits   :subscription_tier
end
```

Fact classes declare optional typed slots (`entity`, `field`, and `value`) and supersede rules. When two facts share an
entity and field, the newer value supersedes the older fact:

```ruby
# app/facts/subscription_tier_fact.rb
class SubscriptionTierFact < ApplicationFact
  slot entity: :account, field: :tier, value: :string
  supersede_by :slot, keep: :newest
end
```

Sources and custom judges follow the same pattern in `app/sources/` and `app/judges/`:

```ruby
# app/sources/inbox_source.rb
class InboxSource < Factorial::Source
  adapter :imap, host: "imap.acme.test", password: ENV.fetch("IMAP_PASSWORD")
  classify :declared, document: SupportEmail
end

# app/judges/citation_span_judge.rb
class CitationSpanJudge < Factorial::Judge
  def call(candidate, passage)
    passage.text.length >= 20 ? accept : reject("passage too short")
  end
end
```

At boot, class macros compile into a configuration table. Passing `--vary judge=none,nli,jev_floors` or `--vary
SupportEmail.extract=passages,staged` clones that table per trial, swaps the targeted strategy, and scores each run
against an isolated event log.

## Pluggable seams

- **Storage:** local folders or S3-compatible buckets for the event log and raw documents, plus `sqlite_fts`,
  `pgvectorscale`, or `turbopuffer` for indexes.
- **Sources:** built-in `folder`, `jsonl`, `imap`, and `mcp` adapters, or subclasses of `Factorial::Source`.
- **Models:** pinned model definitions referenced by symbol across classification, extraction, repair, and judging.
- **Judges:** built-in `jev_floors`, `nli`, and `llm` judges mixed in any order with `Factorial::Judge` subclasses.

## Why this approach

Each definition lives in a small, predictable file, and base classes like `ApplicationDocument` and `ApplicationFact`
keep shared defaults in one place. Generators write the initial boilerplate, and standard Ruby tools handle syntax
checks, tests, and shared helpers. Custom judges and sources sit beside declarative macros without a separate plugin
protocol. This approach requires a Ruby 3.4+ runtime, and teams unfamiliar with Ruby must learn Ruby class macros.
Because configuration loads by executing Ruby files at boot, external tools must run `factorial config dump` to inspect
the resolved setup as static data.

## Further reading

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md).
Note: [docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML
design.
