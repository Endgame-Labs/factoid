# Command line

Factoid is one program, `factoid`. Inside a project folder, it finds the project (the folder with `pyproject.toml` and
the package) and runs in the project's environment, so you never type `uv run`. `factoid --version` prints the version
and the git commit it was installed from. `README.md` has the walkthrough; `SPEC.md` section 17 says what is built.

## Set up

```sh
factoid init [--models jev|fireworks|openai] [--package NAME]  # create a project in the current folder
factoid keys set [PROVIDER] [--project]                        # store API keys
factoid keys list                                              # show provider keys and sources
factoid models                                                 # show workloads, models, and key status
factoid doctor                                                 # test each workload and show the search index
```

- `init` writes `settings.py`, sample classes, a sample contract, and an eval. Presets: `jev` (default) uses TypeSafe
  and Fireworks, `fireworks` uses Fireworks only (experimental), and `openai` uses OpenAI only. In an existing project,
  `init --models <preset>` switches `settings.py` to that preset unless you edited its models by hand. It never overwrites a file, and it
  writes back any sample file you deleted, such as `evals/sample.py`.
- `keys set` stores a key in `~/.factoid/.env`, or with `--project` in `~/.factoid/projects/<id>/.env`, named by the
  `id` that `init` writes into `pyproject.toml` (a project without one gets one). With no provider,
  it asks for each key the project needs and says where to get it; Enter skips. Providers: `fireworks`, `openai`,
  `openrouter`, `turbopuffer`, and `typesafe`. Without a terminal for prompting, it prints how to pipe a key in instead.
- `keys list` prints each provider, whether its key is set, where it comes from, what uses it, and where to get one.
- `models` prints each workload (`choose`, `generate`, `embed`, and `rerank`), its model, and whether its key is set.
- `doctor` runs one small call per workload and prints the search index in use.

## Ingest and read

```sh
factoid ingest PATHS... [--as CLASS] [--dry-run] [--again] [--fresh]  # ingest files or folders
factoid facts list [--document NAME] [--trait NAME] [--status STATUS] [--limit 50] [--json]  # facts, in order added
factoid search QUERY [--about ENTITY] [--as-of DATE] [--top-k 10] [--chunks] [--json]  # search facts or source chunks
factoid read FACT_ID                                                  # show full details for one fact
factoid stats [--examples N] [--json]                                 # show counts and store health
factoid entities list [--class NAME]                                  # list entities and aliases
factoid entities kinds                                                # count untyped entity kinds
```

- `ingest` classifies each document unless `--as` names the class. `--dry-run` runs everything, writes nothing, and
  prints the facts and the rejected candidates with reasons. A stored document with unchanged text, class, and metadata
  is skipped; `--again` ingests it anyway. Re-ingesting a changed document retracts its old facts, and a new fact saying
  the same thing as an old one takes the old fact's id. `--fresh` calls the models even when an identical request is
  cached. Output ends with model calls, tokens, calls replayed from `.factoid/calls.db`, and whether any saved answers
  came from a different version of Factoid.
- `facts list` prints facts in the order added, with ids and traits (`--limit 0` lists all). `--status` is `current`
  (the default), `superseded`, `ended`, `corrected`, `contradicted`, `retracted`, or `all`.
- `search` returns facts, or source chunks with `--chunks`. The score orders results: keyword and vector ranks fused
  with reciprocal rank fusion, times how likely the fact is still valid now or at `--as-of`. It is not a similarity;
  values near 0.03 are normal. No reranker runs unless `settings.py` sets a `rerank` model.
- `read` prints the sentence, traits, `valid_from`, `expires`, `valid_until`, lifetime estimate, "still valid now" and
  how it was worked out, quotes with passages, entity mentions and how each was linked, related facts, and events, in
  local time.
- `stats` counts documents, facts, and entities by class; facts by status; and facts with no trait, unlinked mentions,
  stale facts, and open contradictions. `--examples N` adds up to `N` sample facts per fact class (at most one per
  document) and the `N` entities with the most facts per entity class.
- `entities list` shows id, class, untyped kind, name, and other names (aliases). `entities kinds` ranks untyped kinds
  by entity and fact count.
- `facts list`, `search`, `read`, `stats`, and `entities list` take `--data-dir` to read another store, such as
  `runs/<time>/<suite>/<variant>`.

## Evals

```sh
factoid eval [SUITE...] [--vary SETTING=A,B] [--limit N] [--fresh] [--quiet]  # run eval suites and write scorecards
```

- Runs each suite in `evals/` on a fresh store per variant and prints a scorecard. Scorecards, stores, and
  `rejected.jsonl` (every rejected fact, its scores, and repair attempts) go in `runs/<local time>/`.
- `--vary` runs each value of a setting on the same documents, such as `fact_evals=none,nli,decision_floors` or
  `models=@evals.variants:NAME` for a value defined in Python.
- Cached calls replay by default, so a rerun costs nothing, is repeatable, and measures a code change alone. `--fresh`
  calls the models again and shows how much results vary between draws.

## Inspect

```sh
factoid steps show CLASS                                     # show steps for a document or fact class
factoid classifiers show                                     # show the document classifier registry
factoid prompts show TARGET                                  # print a prompt or question as sent
factoid struct inspect FILE [--json]                         # inspect columns and suggest a parser
factoid struct parser FILE [--name] [--prompt] [--out FILE]  # generate a parser class or agent prompt
factoid struct try FILE [--rows 20] [--as CLASS]             # dry-run a parser on initial rows
```

- `steps show` lists the steps a document or fact class runs and where each comes from.
- `struct inspect` prints columns, types, sample values, guessed roles, a starting parser class, and which class
  matches.
- `struct parser` has a model write the parser class, or prints the prompt for your own coding agent with `--prompt`.
- `struct try` dry-runs a parser on the first rows, writes nothing, and calls no model.

## Planned

Planned and not built: `setup` (a guided terminal UI), `serve` (HTTP API and daemon), `mcp`, `rebuild`, and
`contradictions`.
