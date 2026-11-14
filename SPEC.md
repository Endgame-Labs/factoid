# Factoid spec

This file records the decisions behind Factoid, so the README does not have to spell each one out. The README is for
users. This file is for whoever builds Factoid.

Nothing is built yet. Every section says how settled it is:

- **Decided**: Kyle chose it. Change it only when he says so.
- **Proposed**: written into the README or an example, and not yet confirmed by Kyle.
- **Open**: needs a discussion or an eval before anyone builds it.

The decision log at the end lists changes in date order.

## 1. What Factoid is

**Decided.**

- Factoid turns documents into facts, extracts entities, and links each fact to the entities it is about.
- A fact is a short, self-contained sentence tied to an exact source quote, who said it, and when.
- As documents arrive, Factoid retires outdated facts, merges duplicate facts, and flags facts that disagree. It does
  this on write, at ingest.
- Factoid is a development framework. A project maps it onto a domain by extending base classes.
- People, agents, and data pipelines read facts through a CLI, an HTTP API, and MCP. Search is semantic, BM25, and
  hybrid with reranking.
- It is built to be measured: algorithm choices are made by evals, not picked up front (section 14).

Audiences, which the design has to serve at once:

1. People building RAG systems: a corpus in its own project directory, driven by the CLI.
2. People running personal agents: fact memory over MCP.
3. Backend systems: `import factoid` as a library, or `factoid serve` as an HTTP service.

## 2. Names

**Decided.**

| Thing | Name |
| --- | --- |
| Project and repo | Factoid, `Endgame-Labs/factoid` (renamed from Factorial on 2026-11-13) |
| Command | `factoid` |
| Python package | `factoid` |
| Base classes | `FactoidDocument`, `FactoidFact`, and `FactoidEntity` |
| Example company in docs | Acme Corp, project name `acme`. Acme's shared fact class is `AcmeBaseFact`. |

**Proposed.** `FactoidLabel` and `FactoidSettings` follow the same prefix. `FactoidSettings` avoids a clash with
`BaseSettings` in `pydantic-settings`.

Do not use the names "Rails" or "Django" in docs or file names.

## 3. Language and packaging

**Proposed** (the README assumes it; `docs/open-questions.md` still lists language as open).

- Python 3.13 or newer, installed and run with uv.
- `uv tool install factoid` puts one `factoid` command on the path. Inside a project, the command finds the project's
  environment and runs there. Users never type `uv run`.
- A second install path is an `install.sh` piped into bash. It installs uv when missing, then installs Factoid.
- Other languages were sketched and are kept for reference in `docs/potential/README/` (Ruby, Go, Rust, TypeScript, and
  frontmatter markdown). Kyle likes the object-oriented feel of the Python and Ruby versions: inherited defaults, method
  overrides, and computed properties.

**Decided** (Kyle, 2026-11-14): **MIT license**, for Factoid and for prosaic. Copyright holder: Endgame Labs. Kyle
considered Apache 2.0 for its patent grant and chose MIT. If Endgame ever wants a patent on anything here, it has to
file before the repo is made public.

**Decided** (Kyle, 2026-11-14): **prosaic is a separate repo and a dependency** (`Endgame-Labs/prosaic`). Endgame will
use it too. prosaic turns rows into sentences with cell citations and knows nothing about Factoid. Factoid builds
`FactoidStructuredDocument` on it and adds entities, linking, and supersede by row key. See "Prose and structured
documents" in section 8.

**Proposed: Pydantic.** Use it underneath: model output schemas, stored records, and validating class settings when a
subclass is defined. Do not make the classes users write into Pydantic models. A `BaseModel` subclass rejects a plain
attribute such as `chunk_size = 4000` (tested on Pydantic 2.14), and plain attributes are the surface we want.

## 4. Project shape

**Decided.**

- A project is a Python package of plain classes. There is no single big config file.
- There is no "app" layer. A project that grows uses plain sub-packages, and unrelated domains run as separate
  projects.
- Subclassing a base class is the declaration. There is no registration step.
- The conventional files are defaults, not requirements: `settings.py`, `sources.py`, `documents.py`, `entities.py`,
  `facts.py`, `fact_evals.py`, and `prompts/`. The same classes work when defined anywhere and passed to `Factoid(...)`.

**Proposed.**

- No code generators. `factoid new` creates a sample project once, and after that the CLI reads code and writes only
  data. (Kyle called the generator commands confusing. Renaming `new` to `init` was floated and not taken up.)
- A project with no classes still works on the base classes' defaults.

## 5. Facts

**Decided.**

- A fact is: one sentence, its exact source quotes (each with who said it and when), and links to one or more entities.
- **A fact has no typed slot and no typed fields.** The sentence carries the meaning. This reverses the earlier
  "sentence plus an optional (entity, field, value) slot" decision. Kyle's reason: facts can hold arbitrary meaning, and
  a triple is old-school and limiting.
- Models never write evidence. The extractor cites numbered passages, and code attaches the exact quote.

**Proposed.**

- Labels (section 6) are the fact's only classification.
- A `FactoidFact` subclass is optional and exists for behavior only: its own definition, extraction guidance, or
  fact evals.
- A fact whose mentions match no entity is kept, with the mentions recorded as unlinked. (Kyle asked for facts to link
  to one or more entities, and separately asked that unclassified facts and entities be accounted for. Keeping unlinked
  facts is how the README squares the two.)
- Reads are by entity and label, plus search: `entity.facts(labels=..., since=...)`, `facts.search(query, about=...)`,
  and `facts.unlinked(...)`. There are no typed reads.

## 6. Labels

**Proposed.**

- A label is a small class with a docstring. The docstring is the definition a model reads.
- A fact carries zero or more labels. The tagger asks one yes-or-no question per label. Labels are not mutually
  exclusive.
- A fact that matches no label is kept.
- "Use case" and "pain point" are labels, not fact subclasses.
- Later: suggest new labels by clustering unlabeled facts, and apply a new label to stored facts without re-extracting.

### Fact traits

**Decided** (Kyle, 2026-11-14). When facts are labeled, the decision model (Jev by default) also judges the fact's
inherent content against rubrics Factoid provides: whether it depends on time, and how long it is likely to stay valid.

**Proposed.**

- Traits are extra questions in the same request as the label questions, so they add no call.
- **Kind of fact** (`choice`): stable (true for years), slow-changing (a role, plan, or relationship), current state (a
  status or number that moves within days or weeks), event (happened at a time, and stays true as history), plan
  (intended or expected, and expires when its date passes), or decision (a choice someone made, such as "Northwind
  chose annual billing"; Kyle, 2026-11-14).
- **Validity** (`choice` over ordered ranges): a day, a week, a month, a quarter, a year, several years, or permanent.
  Factoid keeps the distribution and stores `valid_until`: when the fact was stated, plus the median range.
- Optional traits: hedged (`noul`), and opinion or observed (`choice`).
- Uses:
  - Search ranks facts past `valid_until` lower and flags them stale. `valid_at=` filters to facts likely still true.
  - Resolve treats two disagreeing "current state" facts far apart in time as a supersede, and two disagreeing
    "stable" facts as a contradiction.
  - An open contradiction goes stale when its facts' `valid_until` passes. See "Resolving".
  - `factoid stats` lists facts past `valid_until`, so a person or agent can re-check them.
  - Calibration eval: when a fact is superseded, its real lifetime is compared with the predicted validity.
- Name: `FactoidTrait`. A label is a yes-or-no tag. A trait is a property with options. Traits follow the levels of
  customization: options and ranges at level 2 (per label or entity type), rubric wording at level 3. Projects can
  declare their own traits.

## 7. Entities

**Decided.** Entities are a base class (`FactoidEntity`), and a fact links to one or more of them.

**Proposed.**

- An entity class declares its identities and how strong each is: `identities = {"email": "strong", "name": "weak"}`.
  A class can define `normalize` to reduce variant mentions to one form.
- Each link from a fact to an entity carries a role (`subject`, `about`, or `speaker`), the method that made it, and a
  confidence.
- Linking goes from sure to unsure, and stops at the first step that settles it:
  1. An exact identifier from the source.
  2. A strong identity.
  3. A name that matches exactly one entity in the same document.
  4. A name that matches exactly one entity in the store.
  5. A yes-or-no question to the decision model.
- A mention in a fact never creates an entity.
- Entities come from sources that carry records with identifiers, or from a discovery step per document. A discovered
  entity is stored only when it has a strong identity or is named in two or more documents. Placeholder names are
  refused. (The bar of two documents is a guess that needs an eval.)
- When an entity is stored, it claims stored facts: Factoid searches them for the entity's names, and the decision model
  confirms each hit.
- Entities that share a strong identity merge by rule. Entities that share only a weak identity go to a question with a
  high floor. Merge and split are logged as events, so each can be traced (and, if section 10's proposal holds, undone).

Sources for these choices: cerebro's link ladder and its over-creation cleanup jobs, and OpenEndgame's claims,
unlinked facts, and reversible merges (`docs/prior-art.md`, and the research summarized in the session of 2026-11-13).

**Open.** Entity types of unknown kind, relations between entities, sides (ours and theirs), and how high-cardinality
identifiers such as SKUs are handled.

## 8. Pipeline

**Proposed.** Each step is a hook on the class that owns it.

| Class | Hooks |
| --- | --- |
| `FactoidDocument` | `classify`, `segment`, `chunk`, `situate`, `extract`, and `discover` (prose); `read`, `row_facts`, and `discover` (structured) |
| `FactoidFact` | `evaluate`, `repair`, `label`, `link`, and `resolve` |
| `FactoidEntity` | `identify`, `claim`, and `merge` |

**Decided.** The framework is principally for organizing AI code and prompts. Hooks that customize model work
(classifying, extracting, and evaluating facts) are the main case, and plain deterministic hooks are secondary.

Every hook can be customized three ways: class attributes, a prompt file, or a method override that may call `super()`.
A setting can be a computed property.

### Levels of customization

**Decided** (Kyle, 2026-11-14). Every level is optional.

| Level | What the user writes |
| --- | --- |
| 0. Nothing | No code. The defaults run. |
| 1. Declare types | Classes with a description (`FactoidDocument`, `FactoidEntity`, `FactoidLabel`, and so on). |
| 2. Tune a type | Settings on the class: guidance, examples, thresholds, and which model it uses. |
| 3. Replace a step's wording | A question for a decision step, or a prompt for a generation step. |
| 4. Replace a step's logic | Override the hook method, and call `super()` to keep the default. |

Project-wide settings (`settings.py`) sit beside these: models, store, search, and budgets.

Every step offers levels 2 to 4. What level 3 holds depends on the kind of step:

| Kind of step | Steps | Level 3 |
| --- | --- | --- |
| Decision | classify, evaluate, label, link, resolve, and rerank | A question, with yes and no criteria or with options |
| Generation | situate, extract, repair, and discover | A prompt |
| Plain code | segment and chunk | None: settings or a method override |

**Open.** Whether level 3 wording lives on the class in Python, or in markdown files next to it (as flavor text does).

### Chunking

**Decided.**

- Long documents are chunked. `chunk_size` is in characters.
- `chunk_overlap` supports characters and percent.
- Each chunk gets a "situation" in the manner of Anthropic's contextual retrieval, written by a configurable prompt.
  It is configurable, and can be turned off.

**Proposed.**

- `chunk_overlap` is one setting with two forms: an integer for characters, or a string such as `"15%"` for a share of
  `chunk_size`. A float is rejected. Percent is bounded at 0 to 50, and overlap must be smaller than `chunk_size`.
- `segment` splits a document into passages, and `chunk` groups passages. A chunk never splits a passage, and overlap
  rounds to whole passages.
- Overlap is context only. A fact cites a passage only from the chunk that owns it.
- The situation is given to the extractor before the chunk's passages, and is indexed with the chunk's text.
- Whether `situate` is on by default is an eval result. It costs one generative call per chunk.

**Decided** (Kyle, 2026-11-14): **chunks are searchable too.** When `situate` is on, a chunk is indexed with its
situation in front of its text. When it is off, the chunk's text alone is indexed.

**Proposed.**

- Facts and chunks are in two namespaces, `<project-id>-facts` and `<project-id>-chunks`. Reasons: BM25 length and
  term statistics are per namespace, and short facts mixed with long chunks would skew them; a namespace has one vector
  size, and facts and chunks may want different embedding models; each can be dropped and rebuilt alone; chunk
  searches would otherwise be filtered searches over a namespace that is mostly facts; and each schema holds only its
  own fields.
- A chunk's entity ids are the entities linked by the facts extracted from it, so `about=` filters work on chunks too.
- `facts.search(...)` returns facts, and `chunks.search(...)` returns chunks with their situation, document, and
  position. A search for both runs hybrid search in each namespace in parallel,
  then reranks the combined list (Kyle, 2026-11-14). Without a reranker, it falls back to reciprocal rank fusion.
- Separate namespaces also let Factoid benchmark facts against chunks on the same corpus. See
  `specs/benchmarks/facts-vs-chunks.md`.
- Whether the default search returns facts only or both is an eval result.


### Prose and structured documents

**Decided** (Kyle, 2026-11-14).

- `FactoidDocument` is an abstract base with two kinds under it. `FactoidProseDocument` is text, and runs segment,
  chunk, situate, and extract. `FactoidStructuredDocument` is rows: CSV, JSONL, a JSON array, or records from a source.
- A structured document has a **column map**, worked out once per file layout and not once per row. Each column is one
  of: an identity of an entity (an exact link, with no model call), a value with a sentence template (one fact per
  value), free text (run through the prose pipeline with the row's entities already known), or ignored.
- `key` names the column that identifies a row across re-imports. `row_entity` says what entity each row is. `when`
  names the column that dates the row.
- Joins across files come from entities: two files whose columns point at the same entity are connected through it.
  There is no file-to-file join logic.
- Provenance for a structured fact is the cell, with the file, row, and column.
- On re-import, a changed value for the same row key and column supersedes the old fact by rule, with no model call.
- A file is matched to a structured class by its header first. The decision model is the fallback.
- **A parser is a Python class.** A `FactoidStructuredDocument` subclass is the parser: the column map at level 2,
  templates at level 3, and `row_facts(row)` at level 4.
- **Factoid can write the parser.** A command sends a model the parser prompt, the file's inspection, and a truncated
  sample of the file, and writes the class to a Python file. The prompt is a markdown file in the package, like other
  model text.
- **A user's own coding agent can write it too.** The docs give instructions for a coding agent, and a command prints
  the same prompt and inspection without calling a model, to paste into any agent.
- **A parser has a dry run.** It runs the parser on a few rows and prints the facts, links, and warnings (such as
  columns the map does not cover), and writes nothing. It is the loop a person or agent uses to test a parser.
- Taken from prosaic (cerebro branch `kyle/frontend-bridge-integrations`, `src/briefs/briefs/prosaic/`): rows become
  sentences, a file's layout is worked out once, and ID and email columns connect files. Left out: generating parser
  code with an unattended agent run, one long narrative per row, and fuzzy file-to-file joins.

**Decided** (Kyle, 2026-11-14): the generic parts live in prosaic, a separate repo that Factoid depends on. prosaic
reads files, inspects them, holds the column map and sentence templates, writes parser prompts, and has the dry run.
Factoid adds column roles that are entity identities, linking, supersede by row key, and free-text columns through the
prose pipeline.

**Proposed.** Command names (Kyle asked for feedback on the hierarchy). prosaic has the same commands on its own
(`prosaic inspect`, `prosaic parser new`, and `prosaic run --dry-run`), and Factoid's wrap them:

- `factoid inspect <file>` works on any file. It shows which document class matches and why. For a structured file,
  it also shows the columns, types, sample values, guessed identities, and the column map a parser would start from.
- `factoid parser new <file> [--name OpenDeals]` has a model write the parser class. `--prompt` prints the prompt and
  inspection instead of calling a model.
- `factoid ingest <file> --dry-run [--rows 20]` is the dry run. It works for every document kind, so prose classes get
  it too.

**Open.** Whether value columns read better in search as template sentences or as one model-written sentence per row.
An eval decides, so both are built.

### Classification

**Decided.** Classifiers are fast decision models (Jev-like) by default: a typed question answered in one pass, with a
probability per option and no generated text.

**Proposed.** A document is typed with one request whose options are the document classes and their docstrings.
`classify_view` controls what the classifier sees, and `classify_threshold` is calibrated.

### Fact evals

**Decided** (Kyle, 2026-11-14). The checks that decide whether a candidate fact is good enough to store are called
**fact evals** (base class `FactEval`), not judges. A fact eval answers one question: keep this fact, or not.
Labeling, linking, and resolving are separate decisions about facts already kept.

Names that follow: the `FactoidFact` hook is `evaluate`, the class attribute is `fact_evals`, the module is
`factoid.fact_evals`, a project's file is `fact_evals.py`, and the eval switch is `--vary fact_evals=...`.

Note the overlap with `factoid eval`, which scores a whole configuration against labeled data. The two are different
things: a fact eval gates one fact at ingest, and `factoid eval` measures the pipeline.

**Proposed.**

- Every candidate fact passes a default chain before it is stored: `nli` (a small entailment model), then `jev_floors`.
  The chain rejects at the first failure.
- `jev_floors` asks six yes-or-no questions in one call: grounded, attribution, self-contained, atomic, useful, and
  distinct. Each has its own floor, and all six must pass. Scores are never averaged.
- Starting floors, from OpenEndgame: grounded 0.75, attribution 0.7, self-contained 0.65, atomic 0.4, useful 0.7, and
  distinct 0.6. Floors are calibrated on labeled data.
- A near miss gets one repair (a rewording), then is evaluated again.
- A project changes one floor or adds a fact eval without replacing the chain.

### Resolving

**Proposed.** For each new fact, Factoid gathers the stored facts that share its entities, and asks the decision model
one question with four answers: duplicate, supersedes, contradicts, or unrelated.

Neither cerebro nor OpenEndgame detects that a newer fact replaces or contradicts an older one, so this step is new
work and needs evals before any claim about its quality.

**Open.** How a contradiction gets cleared.

## 9. Model calls and prompts

**Proposed.**

- Hooks call models through `choose`, `decide`, and `score` (decision model) and `generate` (generative model). Calls made
  this way are logged, priced, budgeted, replayed, and fingerprinted.
- Models are named once in settings and pinned to exact versions.
- Prompts are Jinja templates. A file at `prompts/<class_name>/<hook>.md.j2` replaces a built-in prompt for one class,
  and a project template can extend a built-in one and change a block.

**Open.**

- "Prompt" is too narrow a word, and a `prompts/` folder may be the wrong abstraction (Kyle). The working decomposition
  of a model step is five parts: inputs, the view of each input, the question (type, instruction, and criteria), the
  rule that turns answers into a decision, and the model.
- For Jev, each kind of use fixes the inputs, and the author supplies criteria. Classifying, evaluating facts, resolving,
  identifying, and ranking may all become one `Question` shape.
- The pieces an author writes (definition, guidance, examples, and rubric) may live on the class, with a type that
  outgrows one file getting its own folder.

### Workloads, providers, and keys

**Decided.**

- The `choose` workload (classifying, evaluating facts, labeling, linking, and resolving) is done by a decision model, also
  called a System One model. A generative model does not stand in for it.
- Jev (TypeSafe) is the recommended decision model: it is the best and it is cheap. Other providers have one too, and
  Factoid supports them: OpenAI's decisions API, Fireworks' Rune, and Cloudflare's Clef.
- Keys belong to providers, and a provider can serve several kinds of model. The README must not pair one key with one
  kind of model.

**Proposed.**

- Workloads: `choose`, `generate`, and `embed` are required. `rerank` is a model workload too, and it is optional
  (Kyle). Without a `rerank` model, search returns results in retrieval order. A hook can pin its own model.
- Real Fireworks ids, checked against the provider's model list on 2026-11-13: `rune` (decision model, Rune 26B-A4B,
  through the System One decisions API), `glm-5p3-flash`, `qwen3-embedding-8b`, and `qwen3-reranker-8b`. Do not put a
  model id in the docs without checking it exists.
- An assignment maps a workload to a model, written `provider/model`. The provider in the name says which key the
  assignment needs, and a missing key is reported by name.
- One provider key is enough to start when that provider has a decision model, a generative model, and an embedding
  model. Adding TypeSafe moves `choose` to Jev.
- Factoid ships a catalog: for each provider, the recommended model per workload, with quality, cost, and latency from
  the shipped evals.
- Setup is two steps: add a provider key, then review the assignments. Commands: `factoid keys set <provider>` and
  `factoid models`. `factoid setup` is the same as a terminal UI.
  `factoid doctor` checks assignments as well as keys.
- Assignments live in the project's `settings.py`, committed, so a team extracts with the same models. Kyle prefers
  this to `pyproject.toml` because settings stay dynamic and programmable: a property can pick a model from the
  environment, the document, or anything else. Only the project id lives in `pyproject.toml`, since the launcher has to
  find the project before it can import any code.
- Because settings are code, the CLI does not edit them. `factoid models` shows the assignments that `settings.py`
  resolves to, and whether each has a working key. `factoid new` and `factoid setup` write `settings.py` once, when the
  project is created. After that, a person changes a model by editing the file.
- A provider can be keyless: a local runtime, or a gateway that injects credentials.

**Open.** Whether the four decision models share a request shape. Jev takes a JSON state plus named questions of type
`noul`, `choice`, or `score`, each with instructions and criteria. The other three have not been checked.

## 10. History and fingerprints

**Decided** (Kyle, 2026-11-14).

- **Current state is the truth.** The facts, entities, links, and labels tables say what is true now, and reads go to
  them. Nothing is rebuilt from history.
- **The event log is for audit and provenance.** Every change also writes an event. Fact events are `added`,
  `superseded`, `contradicted`, `retracted`, and `restored`. Entity events are `linked`, `merged`, and `split`. Each
  event names the facts or entities it touched, the step that made it, and the reason. The log lives in the same
  SQLite database, and the state change and its event are written in one transaction.
- **Responses can show history.** When a fact has superseded another, a read can query the log and return the older
  fact, with when and why it changed.

**Proposed.**

- An event stores the state it replaced, so a merge, split, or supersede can be undone by applying the reverse change.
- Each fact records a fingerprint of the prompts, questions, floors, and settings that made it. A change makes the old
  facts stale, and `factoid rebuild --estimate` prices re-deriving them. The model is left out of the fingerprint.

## 11. Storage and dependencies

**Decided** (Kyle, 2026-11-14).

- **Storage is pluggable.** The system of record and the search index are each behind an interface, and a project
  swaps either one in `settings.py` without changing its classes.
- **v1 system of record: SQLite.** One database file per project. It holds documents, chunks, facts, quotes, entity
  links, labels, entities, and the event log, and it answers every lookup that is not a search: facts for an entity,
  entities by identity, facts by label and time, and unlinked facts.
- **v1 search: turbopuffer, or any endpoint compatible with its API.** It is required. It serves vector, BM25, and
  hybrid search, and the nearest-neighbor queries that resolve and entity linking need. The endpoint's base URL is a
  setting, so a compatible server can stand in for turbopuffer.
- **No flat-file store for now.** Set aside: files with a SQLite index (as endgame-wiki does), and a bucket-only store
  (an event log in S3 or R2, with LanceDB tables as views).

**Proposed.**

- SQLite is the truth, and the turbopuffer namespace is a view. If the index is lost or its settings change,
  `factoid rebuild` repopulates it from SQLite.
- Two turbopuffer namespaces per project, named from the project id: one for facts and one for chunks. Each row is a
  fact or a chunk, with its vector, its text for BM25, and its entity ids, labels, and times as filterable attributes.
- Writes go to SQLite first, then to the index. A write the index has not confirmed is retried, so the index catches
  up with the truth.
- The SQLite file lives in a git-ignored folder in the project, unless `settings.py` points elsewhere.

**Decided** (Kyle, 2026-11-14): writing to SQLite.

- SQLite allows one writer at a time. In v1, model calls run in parallel, and every save goes through a single writer in
  the process. Each document's results are saved in one short transaction.
- WAL mode is on, so reads and searches are not blocked by ingest.
- A second process writing to the same project waits its turn through SQLite's busy timeout.
- Many processes writing at once, or a hosted deployment, is the case for a Postgres backend. It is not built in v1.
- Later back ends behind the same interfaces: Postgres (pgvector and pgvectorscale) for the system of record and for
  search, and LanceDB on a bucket.

**Open.**

- Production mode with SQLite: one writer at a time. Fine for a CLI project and an agent's memory, and a limit for a
  backend with several ingest workers.
- Local models: Ollama is a lead for a keyless local mode (embeddings such as EmbeddingGemma, generation, and a System
  One API for decisions). Not verified.

## 12. Install, setup, and CLI

**Decided.** The README Quickstart has three parts: Install, Setup, and Use. Install offers uv or a piped
`install.sh`. Setup covers the minimum set of API keys, shows the commands, and points to a terminal UI.

**Proposed.**

- `factoid keys set <provider>` stores a key in the user's config directory, outside any project. An environment
  variable of the usual name takes precedence. `factoid doctor` checks each key with one small call. `factoid setup`
  is a terminal UI over the same steps.
- Where keys and config live (modeled on Hermes Agent, which keeps `config.yaml`, a plain-text `.env` for secrets, and
  `auth.json` under `~/.hermes/`, with `HERMES_HOME` behind its profiles):
  - User level, `~/.factoid/` (relocated by `FACTOID_HOME`): `.env` holds API keys, written by `factoid keys set` with
    owner-only permissions. No keychain.
  - Project level, in the repo: `settings.py` holds every non-secret setting and is committed. Data (the store and
    indexes) goes in a git-ignored directory in the project unless `settings.py` points elsewhere.
  - Per-project keys: different projects may need different keys (Kyle). Store them in the user's home, keyed by a
    stable project id, at `~/.factoid/projects/<id>/.env`. `factoid new` writes the id into the project, and
    `factoid keys set <provider> --project` writes there. Do not key by absolute path: a moved or renamed checkout
    would lose its keys, and two checkouts of one project would each need setup. Keeping keys in the home directory
    also keeps secrets out of the working tree, where coding agents and build tools read files. (A git-ignored
    `.env.local` in the project is the alternative, and is simpler but puts the secret in the tree.)
  - Precedence, highest first: a real environment variable, the project's keys, `~/.factoid/.env`, and then the
    defaults in `settings.py`.
  - A provider can set a base URL and run with no key, for gateways that inject credentials (such as exe.dev
    integrations).
- The `factoid` command:
  - It is a real executable on the user's `PATH`, installed once per user. `uv tool install` builds a private
    environment under `~/.local/share/uv/tools/factoid/` and puts a launcher in `~/.local/bin/`. It is not a shell
    alias, and it needs no root.
  - On each run it walks up from the current directory to find the project marker, the way `git` finds `.git`.
  - The marker is a `[tool.factoid]` table in the project's `pyproject.toml`, which holds the project id.
    `factoid new` writes it. The id is the project's name plus a short random suffix, such as `acme-7k2m`, and it is
    committed, so every checkout and every teammate shares it.
  - With a project found, the command loads that project's keys, then re-runs itself inside the project's own
    environment, so it can import the project's classes and their dependencies.
  - The global command is a thin launcher. When a project pins its own version of Factoid, the project's version does
    the work.
  - Outside a project, `new`, `keys`, `setup`, and `doctor` work with the user's defaults.
- Terms: the README says "decision model" (not "choice model"), and the settings key for that workload is `choose`.
- The README's Setup section follows the workloads and providers model in section 9: one provider key to start, Jev
  recommended for `choose`, `factoid models` to review, and `factoid setup` as the terminal UI.
- Commands in use across the docs: `new`, `ingest`, `search`, `read`, `eval`, `rebuild`, `stats`, `serve`, `mcp`,
  `keys`, `doctor`, and `setup`.

### The setup wizard

**Decided** (Kyle).

- `factoid setup` should be super smooth, useful inside the team, and even charming. It is colorful.
- Navigation works two ways: arrow keys and Enter, or WASD and the space bar.
- It shows clickable URLs that open the right section of each provider's dashboard, such as the page where a key is
  created.
- Flavor text, here and everywhere else in the app, lives in markdown files, so it can be changed without touching
  code.

**Proposed.**

- Flavor text is any user-facing copy that is not data: greetings, step titles, hints, tips, empty states, success
  and error messages, and the wording around prompts. It lives in `factoid/text/` as markdown files, one per screen or
  command, such as `text/setup/welcome.md` and `text/setup/keys.md`.
- Each file holds named sections, and the code looks text up by file and section. Text can use simple placeholders for
  live values, such as `{provider}` and `{model}`.
- Dashboard links live in the same files, next to the text that uses them, so a moved provider page is a text change.
  Each link points at a specific section, not a home page.
- Clickable links use the terminal's hyperlink support (OSC 8), with the full URL printed as a fallback in terminals
  that do not support it.
- Color follows the terminal's theme, and the wizard honors `NO_COLOR`. It stays usable with color off.
- Copy in these files follows the same rules as the docs: Carbon writes it, in a plain and pragmatic voice, with room
  for charm in the wizard.

**Open.** The TUI library. Textual is the obvious candidate in Python.

## 13. Out of scope

**Proposed.** Factoid stops at facts and entities. Deciding which entities a workspace should cover, writing articles
or briefs, digests, and publishing are readers built on Factoid (`docs/potential/crm-starter.md`).

## 14. Evals

**Decided.** Benchmarks decide algorithms. Do not ask Kyle to pick between fact eval chains, extraction strategies,
retrieval methods, or thresholds. Make each a selectable strategy, and measure.

**Proposed.** `factoid eval` scores a project against labeled data and reports quality, cost, and latency.
`--vary` runs the same documents under each strategy. Defaults are eval results. The scorecard includes coverage: the
share of facts with no label, and the share of mentions with no entity.

Benchmark specs live in `specs/benchmarks/`. The first is facts versus chunks.

## 15. How the docs are written

**Decided.**

- Everything in `README.md` above "Quickstart" is written by Kyle. Do not edit it.
- Carbon (Gemini 4 Carbon, medium, through `agy`) writes the copy for end-user docs: the README and the examples. The
  tone is matter-of-fact and pragmatic, with plain label headings.
- This file is maintained by the session's agent, without Carbon. Update it whenever a decision is made or changed.
- Always use the Oxford comma. Avoid slogans, "X rather than Y" contrasts, and invented anecdotes.
- `AGENTS.md` holds the shared rules for coding agents. Each developer's own preferences live in `AGENTS.md.local`,
  which agents read and keep current. Every file ending in `.local` is ignored by git.

## 16. Docs that lag the design

- The README intro names the base classes `Document`, `Fact`, and `Entity`. The body uses the `Factoid` prefix.
- `docs/potential/README/python/README.md`, the Ruby README, and the twelve examples still show typed fields, the old
  class names, and the Harbor example.
- `docs/facts.md`, `docs/mental-model.md`, `docs/config.md`, `docs/plugins.md`, `docs/cli.md`, and
  `docs/potential/crm-starter.md` predate the entity redesign. `docs/config.md` and `docs/plugins.md` also describe
  the single-YAML design.

## Decision log

All dates are 2026-11-13 unless noted.

1. Repo created as `Endgame-Labs/factorial`. Docs first, then the eval mental model, then code.
2. Fact unit: a sentence plus an optional typed slot. (Reversed by 11.)
3. Dedup, supersede, and contradiction happen at ingest, on write.
4. Benchmarks decide algorithms.
5. One big YAML config rejected. Declarations live in classes, in sensible places.
6. Python chosen as the language to design against. Framework names stay out of the docs.
7. No app layer.
8. Prompts are Jinja templates.
9. The framework is mainly for organizing AI code and prompts. Classifiers are Jev-like decision models by default.
10. Carbon writes end-user copy.
11. No slot. A fact links to one or more entities, and the sentence carries the meaning.
12. Renamed to Factoid: project, repo, and checkout.
13. Example company is Acme. Base classes are `FactoidFact`, `FactoidDocument`, and `FactoidEntity`.
14. Chunking: `chunk_size`, `chunk_overlap` in characters or percent, and a configurable situation per chunk.
15. Quickstart is Install, Setup, and Use. `SPEC.md` exists and is kept current.
16. `AGENTS.md` added, with per-developer preferences in a git-ignored `AGENTS.md.local`.
17. Keys and config: user keys in `~/.factoid/.env`, per-project keys by project id, and the `factoid` launcher
    that finds the project from the current directory. (Proposed, with Kyle's go-ahead to record it.)
18. `choose` is done by a decision (System One) model. Jev is recommended, and OpenAI's decisions API, Fireworks' Rune,
    and Cloudflare's Clef are supported. Keys are per provider, not per kind of model.
19. Model assignments live in `settings.py`, so they stay programmable. Only the project id is in `pyproject.toml`.
    The README's Setup section was rewritten around provider keys and workloads.
20. `rerank` is an optional model workload. The README's Setup example shows the one-key Fireworks case, with Rune
    doing `choose`.
21. `factoid setup` is smooth, charming, and colorful, with arrow keys and Enter or WASD and space, and clickable
    dashboard links. All flavor text lives in markdown files.
22. No flat-file store for now. Postgres is the leading proposal for the system of record in both modes.
23. Storage is pluggable. v1 uses SQLite as the system of record, and requires turbopuffer or a
    turbopuffer-compatible endpoint for search.
24. Judges are renamed fact evals (`FactEval`).
25. Five levels of customization. Decision steps are worded as questions, and generation steps as prompts.
26. Current state is the source of truth. The event log is kept for audit and provenance, and is not replayed.

27. SQLite in v1 has one writer per process, with WAL mode on. Many writers or hosting means a Postgres backend later.
28. `FactoidDocument` splits into `FactoidProseDocument` and `FactoidStructuredDocument`. A structured parser is a Python
    class with a column map. Factoid can write it with a model, or print the prompt for any coding agent, and it has a dry run.
29. MIT license for Factoid and prosaic.
30. prosaic is a separate repo (`Endgame-Labs/prosaic`) and a dependency of Factoid. Endgame uses it too.
31. Chunks are searchable as well as facts. A chunk is indexed with its situation when `situate` is on. Facts and
    chunks are in separate namespaces.
32. Searching facts and chunks together is hybrid search in each, then a rerank. Benchmark specs live in
    `specs/benchmarks/`, starting with facts versus chunks.
33. Fact traits: during labeling, the decision model also judges the kind of fact and how long it stays valid.
