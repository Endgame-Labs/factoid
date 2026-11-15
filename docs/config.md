# Config: `factoid.yml`

## The project layout

`factoid new acme-facts` makes this, and every command assumes it:

```text
acme-facts/
  factoid.yml      # the one config file
  corpus/            # sample documents (delete when you have real ones)
  prompts/           # empty until you copy a default prompt out to change it
  plugins/           # your own strategies, sources, stores, or indexes
  evals/             # suites; a sample one ships
  data/              # the log and its views (or point `store` at a bucket)
  runs/              # eval results
```

## A whole config

Most projects need only the first three keys. Everything else has a default.

```yaml
store: ./data                       # or s3://bucket/prefix, r2://..., gs://...

models:                             # names for models, used by stages below
  flash: fireworks/glm-5p3-flash    # provider/model, always pinned, never "latest"
  judge: typesafe/jev-1.13.0
  embed: openai/text-embedding-3-small

sources:
  - {name: calls, use: folder, path: ~/calls, type: call}

pipeline:
  classify: {use: declared, fallback: {use: systemone, model: judge}}
  segment:  {use: auto}
  extract:  {use: passages, model: flash, window_bytes: 3500, max_per_window: 16}
  judge:
    - {use: nli, min_entail: 0.6}
    - {use: jev-floors, model: judge, floors: {grounded: 0.75, attribution: 0.7, self_contained: 0.65, atomic: 0.4, useful: 0.7}}
  repair:   {use: reword-once}
  resolve:  {use: [hash, slot, vector-judge], model: judge, neighbors: 20}
  tag:      {use: none}

indexes:
  - sqlite-fts                      # always on; zero setup
  - {use: turbopuffer, namespace: acme-facts, embed: embed}
  # - {use: pgvectorscale, url: $DATABASE_URL, embed: embed}

search:
  retrieve: hybrid-rrf              # bm25, vector, or hybrid-rrf
  rerank: none                      # none, jev, or a reranker model
  budget_tokens: 2000               # how much a reader gets by default

budget:
  daily_usd: 20                     # stop extracting for the day past this
```

## Rules

- **Every stage has `use:`**, naming a strategy. Built-in names are plain words; a path (`./plugins/x.py`) is a plugin.
- **A stage that takes a list runs it as a chain**, in order. A judge chain rejects at the first failure, so put cheap
  judges first.
- **Models are named once** under `models:` and referred to by name, so swapping a model is a one-line change.
- **`$NAME` reads an environment variable.** Secrets never go in the file.
- **Prompts:** every model-calling strategy has a default prompt. `factoid prompts copy extract` puts it in `prompts/`,
  and from then on the copy is used and fingerprinted.
- **Fingerprints:** a stage's fingerprint covers its strategy, settings, and prompt, but not its model.
  See [the mental model](mental-model.md#staying-current).

## Defaults are eval results

A default is a claim: "on the shipped suites, this was the best trade-off of quality and cost." Each default in the
built-in config cites the run that chose it (`factoid defaults --why`). When a new strategy wins, the default changes,
and the run that showed it is checked in.
