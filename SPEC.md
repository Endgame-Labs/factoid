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
  `facts.py`, `judges.py`, and `prompts/`. The same classes work when defined anywhere and passed to `Factoid(...)`.

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
  judges.
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
  5. A yes-or-no question to the choice model.
- A mention in a fact never creates an entity.
- Entities come from sources that carry records with identifiers, or from a discovery step per document. A discovered
  entity is stored only when it has a strong identity or is named in two or more documents. Placeholder names are
  refused. (The bar of two documents is a guess that needs an eval.)
- When an entity is stored, it claims stored facts: Factoid searches them for the entity's names, and the choice model
  confirms each hit.
- Entities that share a strong identity merge by rule. Entities that share only a weak identity go to a question with a
  high floor. Merge and split are events, so each can be undone.

Sources for these choices: cerebro's link ladder and its over-creation cleanup jobs, and OpenEndgame's claims,
unlinked facts, and reversible merges (`docs/prior-art.md`, and the research summarized in the session of 2026-11-13).

**Open.** Entity types of unknown kind, relations between entities, sides (ours and theirs), and how high-cardinality
identifiers such as SKUs are handled.

## 8. Pipeline

**Proposed.** Each step is a hook on the class that owns it.

| Class | Hooks |
| --- | --- |
| `FactoidDocument` | `classify`, `segment`, `chunk`, `situate`, `extract`, and `discover` |
| `FactoidFact` | `judge`, `repair`, `label`, `link`, and `resolve` |
| `FactoidEntity` | `identify`, `claim`, and `merge` |

**Decided.** The framework is principally for organizing AI code and prompts. Hooks that customize model work
(classifying, extracting, and judging) are the main case, and plain deterministic hooks are secondary.

Every hook can be customized three ways: class attributes, a prompt file, or a method override that may call `super()`.
A setting can be a computed property.

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

**Open.** Whether chunks are searchable at all, or only facts are.

### Classification

**Decided.** Classifiers are fast choice models (Jev-like) by default: a typed question answered in one pass, with a
probability per option and no generated text.

**Proposed.** A document is typed with one request whose options are the document classes and their docstrings.
`classify_view` controls what the classifier sees, and `classify_threshold` is calibrated.

### Judging

**Proposed.**

- Every candidate fact passes a default chain before it is stored: `nli` (a small entailment model), then `jev_floors`.
  The chain rejects at the first failure.
- `jev_floors` asks six yes-or-no questions in one call: grounded, attribution, self-contained, atomic, useful, and
  distinct. Each has its own floor, and all six must pass. Scores are never averaged.
- Starting floors, from OpenEndgame: grounded 0.75, attribution 0.7, self-contained 0.65, atomic 0.4, useful 0.7, and
  distinct 0.6. Floors are calibrated on labeled data.
- A near miss gets one repair (a rewording), then is judged again.
- A project changes one floor or adds a judge without replacing the chain.

### Resolving

**Proposed.** For each new fact, Factoid gathers the stored facts that share its entities, and asks the choice model
one question with four answers: duplicate, supersedes, contradicts, or unrelated.

Neither cerebro nor OpenEndgame detects that a newer fact replaces or contradicts an older one, so this step is new
work and needs evals before any claim about its quality.

**Open.** How a contradiction gets cleared.

## 9. Model calls and prompts

**Proposed.**

- Hooks call models through `choose`, `decide`, and `score` (choice model) and `generate` (generative model). Calls made
  this way are logged, priced, budgeted, replayed, and fingerprinted.
- Models are named once in settings and pinned to exact versions.
- Prompts are Jinja templates. A file at `prompts/<class_name>/<hook>.md.j2` replaces a built-in prompt for one class,
  and a project template can extend a built-in one and change a block.

**Open.**

- "Prompt" is too narrow a word, and a `prompts/` folder may be the wrong abstraction (Kyle). The working decomposition
  of a model step is five parts: inputs, the view of each input, the question (type, instruction, and criteria), the
  rule that turns answers into a decision, and the model.
- For Jev, each kind of use fixes the inputs, and the author supplies criteria. Classifying, judging, resolving,
  identifying, and ranking may all become one `Question` shape.
- The pieces an author writes (definition, guidance, examples, and rubric) may live on the class, with a type that
  outgrows one file getting its own folder.

### Workloads, providers, and keys

**Decided.**

- The `choose` workload (classifying, judging, labeling, linking, and resolving) is done by a decision model, also
  called a System One model. A generative model does not stand in for it.
- Jev (TypeSafe) is the recommended decision model: it is the best and it is cheap. Other providers have one too, and
  Factoid supports them: OpenAI's decisions API, Fireworks' Rune, and Cloudflare's Clef.
- Keys belong to providers, and a provider can serve several kinds of model. The README must not pair one key with one
  kind of model.

**Proposed.**

- Workloads: `choose`, `generate`, `embed`, and `rerank`. A hook can pin its own model.
- An assignment maps a workload to a model, written `provider/model`. The provider in the name says which key the
  assignment needs, and a missing key is reported by name.
- One provider key is enough to start when that provider has a decision model, a generative model, and an embedding
  model. Adding TypeSafe moves `choose` to Jev.
- Factoid ships a catalog: for each provider, the recommended model per workload, with quality, cost, and latency from
  the shipped evals.
- Setup is two steps: add a provider key, then review the assignments. Commands: `factoid keys set <provider>`,
  `factoid models`, and `factoid models set <workload> <provider/model>`. `factoid setup` is the same as a terminal UI.
  `factoid doctor` checks assignments as well as keys.
- Assignments live in the project's `settings.py`, committed, so a team extracts with the same models.
- A provider can be keyless: a local runtime, or a gateway that injects credentials.

**Open.** Whether the four decision models share a request shape. Jev takes a JSON state plus named questions of type
`noul`, `choice`, or `score`, each with instructions and criteria. The other three have not been checked.

## 10. History and fingerprints

**Proposed** (Kyle has seen the trade-offs and has not confirmed).

- An append-only event log is the truth. Fact events are `added`, `superseded`, `contradicted`, `retracted`, and
  `restored`. Entity events are `linked`, `merged`, and `split`. Current state and search indexes are views rebuilt
  from the log.
- Each fact records a fingerprint of the prompts, questions, floors, and settings that made it. A change makes the old
  facts stale, and `factoid rebuild --estimate` prices re-deriving them. The model is left out of the fingerprint.

## 11. Storage and dependencies

**Open.** Kyle wants to discuss this before anything is decided. See `TODO.md`.

- Local mode: Postgres with pgvector and pgvectorscale, plus a local embedding model (Gemma?).
- Production mode: unknown.
- Can Postgres be the system of record in both modes, or is a files-only store better? If files, how do secondary
  lookups work, such as all facts for an entity?

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
- Default providers: TypeSafe (Jev) for the choice model, Fireworks for the generative model, and OpenAI for
  embeddings.
- Commands in use across the docs: `new`, `ingest`, `search`, `read`, `eval`, `rebuild`, `stats`, `serve`, `mcp`,
  `keys`, `doctor`, and `setup`.

## 13. Out of scope

**Proposed.** Factoid stops at facts and entities. Deciding which entities a workspace should cover, writing articles
or briefs, digests, and publishing are readers built on Factoid (`docs/potential/crm-starter.md`).

## 14. Evals

**Decided.** Benchmarks decide algorithms. Do not ask Kyle to pick between judging chains, extraction strategies,
retrieval methods, or thresholds. Make each a selectable strategy, and measure.

**Proposed.** `factoid eval` scores a project against labeled data and reports quality, cost, and latency.
`--vary` runs the same documents under each strategy. Defaults are eval results. The scorecard includes coverage: the
share of facts with no label, and the share of mentions with no entity.

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
9. The framework is mainly for organizing AI code and prompts. Classifiers are Jev-like choice models by default.
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
