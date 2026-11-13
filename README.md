# Factorial 🧮

> **Status: design draft.** Nothing here is built yet. These docs are the spec we build against, so change them first.

Factorial turns documents into **facts you can trust**: short, self-contained sentences, each tied to the exact words it
came from, who said them, and when. It keeps them current as new documents arrive. When a later email updates a price,
the old fact is superseded rather than duplicated, and when two calls disagree, the disagreement is recorded rather than
hidden. Then it serves them to people and agents through a CLI, an HTTP API, and MCP.

It is also a **workbench for deciding how to do all that**. Every step (how documents are typed, how facts are extracted,
judged, deduplicated, and searched) is a strategy you choose in one config file, and `factorial eval` measures any choice
against labeled data, with the cost and the latency of each. Algorithms are picked by evidence, not taste.

## Fifteen minutes

```sh
factorial new acme-facts          # a project with a sample corpus and a sample eval
cd acme-facts
factorial ingest corpus/          # documents in, facts out
factorial search "renewal price"
factorial read f_8k2m1            # the fact, its quotes, and its history
factorial eval                    # how good was that? a scorecard
factorial eval --vary judge=none,nli,jev    # which judge is worth paying for?
```

## The ideas

- **Facts are the payload, not a pointer.** A reader (a person or a model) reads facts, not the chunks they came from.
  On dialogue this beat chunk retrieval at about a seventh of the read tokens ([prior art](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages; code attaches the exact quote. A quote cannot be
  invented, so every fact can be checked against its source.
- **History is the truth.** Everything that happens to a fact (added, superseded, contradicted, retracted, restored) is an
  event in an append-only log. Current state and every search index are views rebuilt from it, so any automatic change
  can be undone, and any two configs can be compared on the same history.
- **Conventions over configuration.** One project layout, one config file, and defaults that work. Change a stage only
  when an eval says it is worth it.
- **Pluggable at the seams that matter:** storage, sources, models, and judges. Built-in strategies cover the common
  cases, and anything else is a small program in any language ([plugins](docs/plugins.md)).

## Docs

Start with [the mental model](docs/mental-model.md), then [docs/README.md](docs/README.md) for the rest.
