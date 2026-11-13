# Factorial 🧮

> **Status: design draft.** Nothing is built yet. These docs are updated before code is written.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

A Factorial project is a directory of small Ruby classes, laid out by Rails-style conventions. A file's name and
location say what it is, and base classes supply the defaults, so a new project needs very little code. (Ruby 3.4+ is
the working assumption for these sketches. The language is still an [open question](docs/open-questions.md).)

## Fifteen minutes

```sh
factorial new acme-facts                        # create a project, sample corpus, and sample eval
cd acme-facts
factorial generate document support_ticket
factorial generate judge price
factorial ingest corpus/                        # documents in, resolved facts out
factorial search "renewal price"
factorial read f_8k2m1                          # inspect the fact, its quotes, and its event history
factorial eval                                  # score quality, cost, and latency
factorial eval --vary judge=none,nli,jev_floors
```

## Project layout

```text
acme-facts/
  app/
    documents/
      application_document.rb
      support_ticket.rb
    facts/
      application_fact.rb
      renewal_price.rb
    judges/
      price_judge.rb
    sources/
      support_inbox.rb
  config/
    application.rb
    environments/
      development.rb
      production.rb
  evals/
```

Storage, models, indexes, the default judge chain, and search settings live in `config/application.rb`, with
per-environment overrides in `config/environments/`. Models are named once and pinned to exact snapshots. Secrets come
from environment variables.

```ruby
# config/application.rb
class Application < Factorial::Application
  store :s3, bucket: "acme-facts", access_key_id: ENV.fetch("AWS_ACCESS_KEY_ID")
  index :pgvectorscale, embed: :embed

  model :flash, "fireworks/glm-5p3-flash"
  model :judge, "typesafe/jev-1.13.0"
  model :embed, "openai/text-embedding-3-small"

  judges :nli, :jev_floors, PriceJudge
  search retrieve: :hybrid_rrf, rerank: :none, budget_tokens: 1500
end
```

At ingest, each document moves through seven stages: `classify`, `segment`, `extract`, `judge`, `repair`, `resolve`, and
`tag`. Deduplication, superseding, and contradiction checks run on write during `resolve`.

Each class configures its own behavior:

```ruby
# app/sources/support_inbox.rb
class SupportInbox < Factorial::Source
  adapter :imap, host: "imap.acme.example", password: ENV.fetch("IMAP_PASSWORD")
  default_document SupportTicket
end
```

```ruby
# app/documents/support_ticket.rb
class SupportTicket < ApplicationDocument
  classify :rules, header: { "X-Zendesk-Ticket" => /.+/ }
  segment :turns
  extract :passages, model: :flash
  extracts RenewalPrice
  tag :department, from: :metadata
end
```

A fact is a sentence with an optional typed slot (`entity`, `field`, and `value`). Slots let rules retire older values
when a newer value arrives for the same entity and field.

```ruby
# app/facts/renewal_price.rb
class RenewalPrice < ApplicationFact
  slot entity: :account_id, field: :annual_price, value: :integer
  resolve :hash, :slot, :vector_judge
  supersede by: [:entity, :field], prefer: :newest
end
```

A judge chain runs in order and rejects a candidate fact at the first failure, so cheap checks go before model calls:

```ruby
# app/judges/price_judge.rb
class PriceJudge < Factorial::Judge
  def check(fact, quote:)
    return accept unless fact.is_a?(RenewalPrice)
    quote.match?(/\$\d+|USD/) ? accept : reject("price fact requires currency in quote")
  end
end
```

## Core ideas

- **Facts are what a reader reads.** People and agents read extracted facts directly. On dialogue benchmarks, fact
  retrieval beat chunk retrieval at about a seventh of the read tokens ([prior art](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and Factorial code attaches the exact quote
  from the source document.
- **History is the truth.** Every fact lifecycle change (`added`, `superseded`, `contradicted`, `retracted`, and
  `restored`) is written to an append-only event log. Current state and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** `factorial eval` scores a project against labeled data and reports quality,
  cost, and latency. Built-in defaults are the winners of those evals.
- **Pluggable seams.** Storage, sources, models, and judges each have built-ins, and each takes a custom class. Every
  pipeline stage has built-in strategies to choose from ([plugins](docs/plugins.md)).

## Docs

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md) for the full
specification. [docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older
single-YAML design and will be updated.
