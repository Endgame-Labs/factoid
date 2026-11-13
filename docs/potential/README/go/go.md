# Factoid 🧮

> **Status: Design draft.** Nothing is built yet. We update the documentation to settle the design before writing code.

Factoid turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factoid updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

Scaffold a Go module, generate your first types, ingest sample documents, query the index, and run an evaluation:

```sh
factoid new acme-kb && cd acme-kb
factoid generate source inbox --kind=imap
factoid generate fact account_owner --slot
factoid ingest ./testdata/threads
factoid search "who owns the Globex renewal?"
factoid read fact_01j9z8k2
factoid eval
factoid eval --vary judge=none,nli,jev-floors
```

## A project is a Go module

`factoid new` creates a small Go 1.25+ module with conventional packages:

```text
acme-kb/
  go.mod
  main.go                 # calls factoid.Main(&App{})
  app.go                  # models, store, index, search, judge chain
  documents/
    support_thread.go     # classify, segment, and extract rules
  facts/
    account_owner.go      # typed slots and supersede rules
  judges/
    quote_window.go       # custom verification checks
  sources/
    inbox.go              # folder, jsonl, imap, or mcp inputs
  evals/
    renewal.jsonl         # labeled facts for factoid eval
```

The `factoid` CLI compiles your module into `.factoid/bin/app` whenever `.go` files change and forwards commands to
that binary. Running `go build` produces the same standalone binary for production. Every built-in and custom component
has a registry name, so `factoid eval --vary judge=none,nli,jev-floors` swaps the active step on `App` for each trial
without editing source files.

### Shared settings (`app.go`)

Embed `factoid.BaseApp` to inherit defaults, and override methods for project-wide choices. Models are named once and
pinned to exact versions, and secrets come from environment variables.

```go
package main

import "github.com/factoid-hq/factoid"

type App struct{ factoid.BaseApp }

func (App) Models() factoid.Models {
	return factoid.Models{
		"fast":  "gemini-2.5-flash-2026-01",
		"smart": "claude-sonnet-4-20250514",
	}
}

func (App) Store() factoid.Store { return factoid.S3Store(factoid.Env("FACTOID_BUCKET")) }
func (App) Index() factoid.Index { return factoid.SQLiteFTS(".factoid/index.db") }

func (App) Judges() []factoid.Judge {
	return []factoid.Judge{factoid.NLI(), factoid.JEVFloors(), QuoteWindow{}}
}

func (App) Search() factoid.Search {
	return factoid.Search{Retrieve: factoid.HybridRRF, Rerank: true, BudgetTokens: 1200}
}
```

### Document types (`documents/support_thread.go`)

Pipeline stages run in order: `classify`, `segment`, `extract`, `judge`, `repair`, `resolve`, and `tag`. Embed
`factoid.BaseDocument` and define methods only where a document type differs from the defaults.

```go
package documents

import "github.com/factoid-hq/factoid"

type SupportThread struct{ factoid.BaseDocument }

func (SupportThread) Classify() factoid.Classifier { return factoid.Rules("subject:Case #") }
func (SupportThread) Segment() factoid.Segmenter   { return factoid.Turns() }

func (SupportThread) Extract(doc factoid.Doc) factoid.Extractor {
	if doc.TokenCount() > 8000 {
		return factoid.Staged("smart")
	}
	return factoid.Passages("fast")
}
```

### Fact types and slots (`facts/account_owner.go`)

A fact is a sentence plus an optional typed slot (`entity`, `field`, and `value`). Struct tags declare the slot schema,
and generics type the `Supersedes` method. Dedup, supersede, and contradiction run at ingest, on write, using `hash`,
`slot`, or `vector-judge` resolvers.

```go
package facts

import "github.com/factoid-hq/factoid"

type AccountOwner struct {
	factoid.SlotFact[AccountOwner]
	Account string `slot:"entity"`
	Owner   string `slot:"value" field:"account_owner"`
}

func (curr AccountOwner) Supersedes(prev AccountOwner) bool {
	return curr.Account == prev.Account && curr.ObservedAt.After(prev.ObservedAt)
}
```

### Judges and sources (`judges/quote_window.go`)

A judge chain runs in order and rejects a candidate at the first failure, so cheap deterministic checks run before model
judges.

```go
package judges

import "github.com/factoid-hq/factoid"

type QuoteWindow struct{ factoid.BaseJudge }

func (QuoteWindow) Name() string { return "quote-window" }
func (QuoteWindow) Check(c factoid.Candidate) error {
	if len(c.Quote) > 400 {
		return factoid.Reject("quote exceeds 400 chars")
	}
	return nil
}
```

## Core ideas

- **Facts are what a reader reads.** Queries return short, self-contained sentences with provenance. On dialogue
  benchmarks, reading facts beat chunk retrieval at about a seventh of the read tokens (see
  [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages from the segmented document, and Go code
  attaches the exact quote, speaker, and timestamp.
- **History is the truth.** Writes go to an append-only event log (`added`, `superseded`, `contradicted`, `retracted`,
  and `restored`). Current fact state and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** `factoid eval` scores your pipeline against labeled JSONL sets and reports
  quality, cost, and latency. Built-in defaults come from eval results.

## Pluggable seams

Storage (`local`, `s3`), sources (`folder`, `jsonl`, `imap`, `mcp`), indexes (`sqlite-fts`, `pgvectorscale`,
`turbopuffer`), pinned models, and judges are small Go interfaces. You can swap built-ins or write your own struct in a
few lines of Go.

## Why this approach

Defining a project in Go gives you compile-time checks on slot types, autocomplete across pipeline options, and a single
self-contained binary for local work and production deploys. Dynamic settings are ordinary Go methods that inspect the
document or environment at runtime. Go struct embedding lacks true class inheritance, so embedded base methods cannot
dispatch back into overridden methods on your outer struct; Factoid dispatches through interfaces at the pipeline
boundary instead, and Go adds explicit type boilerplate compared to Ruby or Python.

## Documentation

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md). Note that
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design.
