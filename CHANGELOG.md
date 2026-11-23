# Changelog

Features and fixes that change what Factoid does, by version. `SPEC.md` has the reasons behind each one.

## Unreleased

- **A demo app.** `examples/demo` is a sales call and two emails, with a five-check eval. It runs in a minute for
  under a cent.
- **Eval cost.** Each suite's summary line gives what its calls cost at list prices, replayed or not.

## 0.1.24 (2026-11-23)

- **`factoid init` puts the code in `app/`.** A new project gets `app/settings.py`, `app/documents.py`, and the rest,
  the same layout as the example apps, and `pyproject.toml` and the project's id are named after the folder.
  `--package` still picks another name. Existing projects are unchanged.
- **Small costs show.** A run under a cent shows its cost to four places instead of $0.00.

## 0.1.23 (2026-11-23)

- **Costs at list prices.** `prices.json` holds list prices for Jev, Rune, GLM 5.3 Flash, and the Fireworks embedders
  and reranker, so runs show dollars without setting `price_in` and `price_out`. A replayed call still counts at list
  price in `full_cost`, so an eval on the cache shows what it would cost fresh, and the scorecards break cost down by
  step. A mediasum dev run costs about $2.70, of which Jev's decisions are $1.60.

## 0.1.22 (2026-11-23)

- **Grounded repair is on by default.** A fact that fails `grounded` is trimmed to what its passages say instead of
  being dropped. The evals showed fewer rejected facts and better as-of answers on the legal suites, with QA on iscrag
  holding (issue #6). `DecisionFloors(repair_grounded=False)` turns it off.
- **Looser entity linking.** `Entity.link_threshold` is 0.6 by default, down from 0.8. The linking suite's accuracy
  went from 0.79 to 0.92 with no new false links (issue #23).

## 0.1.21 (2026-11-23)

- **Rules for the repair.** `repair_guidance` on a document or fact class adds rules to the repair prompt, such as
  keeping a reference the passage leaves open as worded. `repair.md.j2` has `guidance` and `references` blocks that a
  project template can replace. Nothing changes for an app that sets neither.

## 0.1.20 (2026-11-23)

- **An overloaded model is retried.** HTTP 529 ("overloaded") now waits and tries again, like 429 and 503. Before,
  one 529 ended the whole run.

## 0.1.19 (2026-11-19)

- **Fewer decision requests, as an experiment.** `assess_with_evaluate = True` on a fact class asks the trait and time
  questions in the fact evals' request, one request per fact instead of two. Off by default until the evals decide
  (issue #7).

## 0.1.18 (2026-11-19)

- **Steadier decisions.** A decision request asks its questions in the order the code lists them, not by a hash of
  their wording, so rewording one question no longer moves the others. The call cache keys on that order (issue #8).
- **Speakers.** Extraction marks who says or reports a claim as its `speaker`, and what the claim is about as its
  `subject` (issue #12).

## 0.1.17 (2026-11-19)

- **Grounded repair, as an experiment.** `DecisionFloors(repair_grounded=True)` trims a fact that fails `grounded` to
  what its passages say, instead of dropping it. Off by default until the evals decide (issue #6).

## 0.1.16 (2026-11-19)

- **Keys in code.** `Model(..., api_key=..., base_url=...)` takes a key, or a function that returns one, for apps that
  keep keys in a secrets store. It never enters a request body, the call cache, or a repr (issue #14).
- **Passage attrs.** A `segment` override can set `passage.attrs`, such as which side of a call spoke, and each quote
  keeps a copy (issue #18).

## 0.1.15 (2026-11-19)

- **Reads for apps.** A fact's document comes with its uri, date, and metadata, and `GET /documents/<id>` reads one
  (issue #15). `min_score` leaves out facts the reranker scores low, in Python, HTTP, and MCP (issue #16).
  `Factoid.events`, `GET /events?after=`, and the MCP tool `read_events` read what changed from a cursor (issue #17).

## 0.1.14 (2026-11-19)

- **Following another system's records.** `Entity.upsert(name, keys=...)` finds an entity by key and renames or
  updates it, or creates it, with no model call. `entity.merge(other)` and `entity.split(facts, name)`, and
  `factoid entities merge` and `split`, move facts' links and keep search right. Factoid's entities stay optional: an
  app with its own linking can ignore them (issue #11).

## 0.1.13 (2026-11-19)

- **What a document is about.** A document class can return `context_entities()`: the account, deal, or case it is
  about, with keys. Each is linked by key or exact name, or created, with no model call, and every fact from the
  document gets it as a `context` mention, so a fact that never names the account still reaches it. The extractor is
  asked to name it in facts about it (issue #9).

## 0.1.12 (2026-11-19)

- **A call log with no text.** `Settings.call_log = "metadata"` keeps each model call's model, step, and tokens but no
  request or answer text, and `"none"` keeps nothing. Both turn off replay (issue #10).

## 0.1.11 (2026-11-19)

- **Class names.** An app refuses two document, entity, or fact classes with the same name, where one used to replace
  the other without a word. `class_name = "..."` stores a class under another name, and a stored class an app does not
  list loads as the base class, never as another project's class of the same name (issue #13).

## 0.1.10 (2026-11-19)

- **Model calls by step.** Each model call is labelled with the step that made it (`evaluate`, `assess`, `link`,
  `resolve`, and so on). `ingest` prints calls and tokens by step, eval scorecards add `usage.by_step`, and
  `factoid calls` lists recent calls with their step, tokens, and the questions a decision call asked (issue #7).

## 0.1.9 (2026-11-19)

- **Bounds on model calls.** `Settings.model_attempts` (12 by default), `model_timeout` (180 seconds per response),
  and `model_deadline` (seconds for one call in all, tries and waits included) let an app that answers people fail a
  stuck call in seconds instead of minutes (issue #5).

## 0.1.8 (2026-11-19)

- **Saving a changed document again.** Old facts stay current until the new version's facts are saved, so a failed
  run loses nothing. The old text is kept as a revision, and each fact records its revision, so old quotes still
  point at the text they quote. A new fact that says what an old one said keeps its id, judged by an exact match, a
  close match, or the decision model's "duplicate" (event `fact.restated`). An old fact the new version changes or
  drops becomes `replaced`, apart from a person's `retracted` (issue #3).

## 0.1.7 (2026-11-19)

- **Many apps in one process.** Worker threads now use the app that started the work, not the last one made, so two
  apps in one process no longer write into each other's stores (issue #2). `app.active()` makes an app active for class
  reads such as `Fact.get` in a block. `factoid serve` no longer makes reads wait for an ingest.

## 0.1.6 (2026-11-19)

- **Resolve fix.** A later restatement of a fact no longer supersedes it when the decision model gives a change no
  weight. Resolve's split rule now needs `resolve_split_floor` (0.2) on "supersedes" (issue #4).
- **Eval rerun.** Every example suite was run again. The legal as-of questions add a reranked-chunks arm. Amendment
  recall counts only facts quoting the labeled new clause, and false changes cover every document. iscrag scores its
  tuning and unseen transcripts apart. Scorecards are committed under each example's `scorecards/`.

## 0.1.5 (2026-11-19)

- **Eval fixes.** AUPR and precision at recall treat tied scores as one threshold, so they no longer depend on input
  order or overstate the area. A `DecisionFloors` subclass that changes one floor keeps each decision model's other
  floors. The sample eval checks each of the three facts on its own and counts extra facts against precision.
- **Fixes.** `stats` no longer counts a contradiction whose side was retracted, and turbopuffer filters traits with its
  array operator.
- **Example evals.** `cuad_heldout` and `cuad_fresh` score 20 contracts each without `--limit`, and two diligence
  checks no longer pass when the email extracted nothing.
- **Tests.** Duplicates, corrections, ends, contradictions settled by evidence, and checks that the reranker and the
  resolve check run.

## 0.1.4 (2026-11-19)

- **Settling contradictions.** `factoid contradictions` lists pairs of facts that disagree, and `factoid contradictions
  settle` keeps one side (retracting the other) or both, with a reason. New evidence settles a pair too: when a newer
  fact supersedes, ends, or corrects one side, the other stands. Every settlement is a `fact.settled` event. The HTTP
  API (`GET /contradictions`, `POST /contradictions/settle`) and the MCP server (`list_contradictions`,
  `settle_contradiction`) do the same.

## 0.1.3 (2026-11-19)

- **MCP server.** `factoid mcp` gives an agent the project's facts as MCP tools over stdio: search, read a fact, list
  facts, find and read entities, stats, and ingest. `--read-only` leaves out ingest. Add it to Claude Code with
  `claude mcp add factoid -- factoid mcp`.

## 0.1.2 (2026-11-19)

- **HTTP API.** `factoid serve` serves search, facts, entities, stats, and ingest as JSON. It listens on 127.0.0.1
  by default, and `FACTOID_API_TOKEN` guards it when it serves other machines.
- **Exports.** `factoid export` sends facts, entities, documents, and events to Parquet files (a local folder, S3, or
  R2) and to a turbopuffer namespace. Each export sends only what changed since its last run, and
  `export_after_ingest` runs them after each ingest.
- **First-run fixes.** `factoid keys set` works without a terminal, `factoid init` switches an existing project's
  preset and writes back deleted sample files, and the sample eval scores all three sample facts.
- **Releases.** Package metadata, CI, and a trusted-publishing workflow for PyPI.
- **Resolve with Rune.** Decision models that need it get a yes-or-no check on each change, which cuts false
  supersessions.

## 0.1.1 (2026-11-17)

- **Onboarding.** One-provider presets, guided `factoid keys set`, per-project keys in `~/.factoid/projects/`, and
  clear errors for missing keys.
- **Structured documents.** `StructuredDocument` reads rows from CSV, JSONL, JSON, or records, and `factoid struct`
  inspects a file, writes a parser, and dry-runs it.
- **Fact evals.** `DecisionFloors` with floors per decision model, fact evals per document class, and repair that
  splits a fact with several claims and names unclear references.
- **Reading facts.** `factoid stats` and `factoid facts list`. A re-ingest skips unchanged documents and keeps fact
  ids.
- **Models.** Generation models per step, and calls that ride out rate limits.

## 0.1.0 (2026-11-15)

- The first package: ingest documents into facts and entities, link and resolve them, search with as-of dates, and
  measure everything with `factoid eval`.
- Example apps: `legal` (contracts and amendments) and `iscrag` (the ISC-RAG benchmark).
