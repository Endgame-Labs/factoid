# Relations: pair summaries and emergent types

**Status: Roadmap** (Kyle, 2026-11-14). Not in v1.

In v1, relations between entities are co-mention counts and relation facts: durable, valid facts that link two or more
entities (`SPEC.md`, "Relations between entities"). Nothing is declared. These two ideas build on that.

## Pair summaries

For a pair of entities with many shared facts, generate a one-line summary of how they relate: "Dana runs sales at
Northwind and is the economic buyer on the renewal."

- Written by a generation prompt from the pair's relation facts, like `situate` but for a pair of entities.
- Cached, and rebuilt when the pair's facts change (a new fact, a supersede, or a fact going stale).
- Cites the facts it was written from.
- Open: the minimum number of shared facts before a summary is worth writing, and whether it is written at ingest or on
  first read.

## Relation types that emerge from the data

Relation types are found, never declared upfront.

- Cluster relation-fact sentences across the corpus, and suggest the types found: "works at", "subsidiary of",
  "champion of". This is the same mechanism as suggesting labels from unlabeled facts.
- A project can promote a suggested type to a declared one. A promoted type has a direction and the two entity
  kinds it connects, and the decision model assigns it to existing relation facts without re-extracting.
- Typed relations make structured queries exact and fast: "everyone who works at Northwind", or multi-hop questions
  such as "who at our customers used to work at Contoso".

## Benchmark

Multi-hop questions answered two ways: an agent walking `entity.related()` over relation facts, and typed relations.
The result says when types are worth their cost.
