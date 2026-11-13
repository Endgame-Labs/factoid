# Factoid 🧮

> **Design draft:** Factoid is in the design stage, nothing is built yet, and the docs get updated before code is
> written.

Factoid turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factoid updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

```sh
factoid new support_kb && cd support_kb
factoid generate document support_thread
factoid generate fact plan_tier
factoid ingest ./sample_tickets
factoid search "Acme billing tier"
factoid read fact_01j8x9
factoid eval
factoid eval --vary judge=none,nli,jev_floors
```

A Factoid project is a small Rust crate (2024 edition). During development, the `factoid` CLI runs incremental
`cargo build` behind the scenes and forwards subcommands to your compiled project binary. For deployment, `cargo build
--release` builds a single binary that embeds your declarations, the CLI, the HTTP API, and the MCP server. When
`factoid eval --vary` runs, the eval harness writes stage overrides into the runtime `Context` before each trial, so
strategies vary across runs without editing files or recompiling.

## Project layout

```text
support_kb/
  Cargo.toml
  evals/tickets.jsonl
  src/
    main.rs          # calls factoid::run::<App>()
    settings.rs      # models, storage, index, search, and default judges
    documents/       # one struct per document type
    facts/           # one struct per fact type
    judges/          # custom verification checks
    sources/         # external document feeds
```

## Declarations

Each concept is a Rust struct that implements a trait with eval-backed default methods. Settings and pipeline choices
are methods. You override the methods you want to change, and any setting can compute a value dynamically at runtime.

```rust
// src/documents/support_thread.rs
#[derive(Document)]
pub struct SupportThread;

impl DocumentConfig for SupportThread {
    fn segment(&self, _ctx: &Context) -> Segment { Segment::Turns }
    fn extract(&self, _ctx: &Context) -> Extract { Extract::Passages }
    fn facts(&self) -> FactTypes { FactTypes::of::<(PlanTier, RenewalDate)>() }
}
```

```rust
// src/facts/plan_tier.rs
// Produces a self-contained sentence plus slot (account_id, "plan_tier", tier).
#[derive(Fact)]
#[fact(field = "plan_tier", resolve = Resolve::Slot, supersede = Supersede::NewerWins)]
pub struct PlanTier {
    #[slot(entity)]
    pub account_id: String,
    #[slot(value)]
    pub tier: Tier,
}
```

```rust
// src/judges/min_quote.rs
pub struct MinQuoteWords(pub usize);

impl Judge for MinQuoteWords {
    fn check(&self, candidate: &CandidateFact, _ctx: &Context) -> Verdict {
        if candidate.quote.split_whitespace().count() >= self.0 {
            Verdict::Pass
        } else {
            Verdict::Reject("source quote is too short")
        }
    }
}
```

```rust
// src/sources/inbox.rs
pub struct SupportInbox;

impl ImapSource for SupportInbox {
    fn host(&self, _ctx: &Context) -> &str { "imap.acme.example" }
    fn password(&self, ctx: &Context) -> Secret { ctx.env("SUPPORT_IMAP_PASSWORD") }
    fn classify(&self, _ctx: &Context) -> Classify { Classify::Declared::<SupportThread>() }
}
```

```rust
// src/settings.rs
pub struct App;

impl Settings for App {
    fn models(&self) -> Models {
        Models::new().pin("fast", "claude-haiku-4-5-20251001")
    }
    fn store(&self, ctx: &Context) -> Store { Store::s3(ctx.env("FACTOID_BUCKET")) }
    fn index(&self, _ctx: &Context) -> Index { Index::SqliteFts("./var/index.db") }
    fn judges(&self, _ctx: &Context) -> JudgeChain {
        // Runs in order and rejects at the first failure; cheap judges go first.
        JudgeChain::new().then(MinQuoteWords(4)).then(Nli).then(JevFloors).then(Llm("fast"))
    }
    fn search(&self, ctx: &Context) -> Search {
        Search::new(Retrieve::HybridRrf)
            .rerank(true)
            .budget_tokens(if ctx.is_agent() { 1200 } else { 400 })
    }
}
```

## Core ideas

- **Facts are what a reader reads.** Queries return self-contained fact sentences with speaker, time, and quote. On
  dialogue, fact retrieval beat chunk retrieval at about a seventh of the read tokens
  ([docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages from segmentation, and Rust code attaches the
  exact source quote.
- **History is the truth.** Deduplication, supersede rules, and contradiction checks happen at ingest, on write. Every
  change appends to an immutable event log (`added`, `superseded`, `contradicted`, `retracted`, and `restored`), and
  current state and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** `factoid eval` scores your pipeline (`classify`, `segment`, `extract`,
  `judge`, `repair`, `resolve`, and `tag`) and search setup against labeled data, reporting accuracy, cost, and latency.
  Built-in defaults come from eval runs.

## Pluggable seams

Storage, sources, models, and judges are open traits backed by built-in options: local folder and S3-compatible storage;
`folder`, `jsonl`, `imap`, and `mcp` sources; `declared`, `rules`, `systemone`, and `llm` classifiers; `auto`, `turns`,
`email`, `paragraphs`, and `rows` segmenters; `passages` and `staged` extractors; `nli`, `jev-floors`, and `llm` judges;
`hash`, `slot`, and `vector-judge` resolvers; `sqlite-fts`, `pgvectorscale`, and `turbopuffer` indexes; and `bm25`,
`vector`, and `hybrid-rrf` retrieval. Models are named once and pinned to exact versions, never `"latest"`. Secrets come
from environment variables.

## Why this approach

Traits with default methods, derive macros, and conventional modules keep declarations in small, predictable files while
checking slot types, pinned model names, and stage signatures at compile time. Standard Rust tooling provides
autocomplete, refactoring, and inline documentation without custom editor plugins, and `cargo build --release` produces
one self-contained binary. Rust lacks class inheritance, so sharing custom logic across document types takes helper
functions or composition traits, and mixed collections of custom components require trait objects. Changing a
declaration also requires a Cargo compile step, and authors have to work within Rust's type and ownership rules.

## Documentation

Start with [docs/mental-model.md](docs/mental-model.md), and then read [docs/README.md](docs/README.md).
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design.
