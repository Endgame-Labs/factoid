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
| Base classes | `Document` (with `ProseDocument` and `StructuredDocument`), `Fact`, `FactTrait`, `Entity`, and `Settings`, with no `Factoid` prefix (Kyle, 2026-11-15). Import them from `factoid`. |
| Example company in docs | Acme Corp, project name `acme`. Acme's shared fact class is `AcmeBaseFact`. |

Do not use the names "Rails" or "Django" in docs or file names.

## 3. Language and packaging

**Decided** (Kyle, 2026-11-14; it had been assumed all along and was only marked Proposed).

- Python 3.13 or newer, installed and run with uv.
- `uv tool install factoid` puts one `factoid` command on the path. Inside a project, the command finds the project's
  environment and runs there. Users never type `uv run`.
- A second install path is an `install.sh` piped into bash. It installs uv when missing, then installs Factoid.
- Other languages (Ruby, Go, Rust, TypeScript, and frontmatter markdown) were sketched early and then removed; they are
  in git history before 2026-11-15. Kyle liked the object-oriented feel of the Python and Ruby versions: inherited
  defaults, method overrides, and computed properties.

**Decided** (Kyle, 2026-11-14): **MIT license**, for Factoid and for prosaic. Copyright holder: Endgame Labs. Kyle
considered Apache 2.0 for its patent grant and chose MIT. If Endgame ever wants a patent on anything here, it has to
file before the repo is made public.

**Decided** (Kyle, 2026-11-14): **prosaic is a separate repo and a dependency** (`Endgame-Labs/prosaic`). Endgame will
use it too. prosaic turns rows into sentences with cell citations and knows nothing about Factoid. Factoid builds
`StructuredDocument` on it and adds entities, linking, and supersede by row key. See "Prose and structured
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

- `factoid init` sets up a project in the current folder, once (Kyle, 2026-11-14; it replaces `factoid new`). After
  that the CLI reads code and writes only data. The exception is `factoid struct parser`, which writes a parser class
  the user asked for.
- A project with no classes still works on the base classes' defaults.

## 5. Facts

**Decided.**

- A fact is: one sentence, its exact source quotes (each with who said it and when), and links to one or more entities.
- **A fact has no typed slot and no typed fields.** The sentence carries the meaning. This reverses the earlier
  "sentence plus an optional (entity, field, value) slot" decision. Kyle's reason: facts can hold arbitrary meaning, and
  a triple is old-school and limiting.
- Models never write evidence. The extractor cites numbered passages, and code attaches the exact quote.

**Proposed.**

- Traits (section 6) classify a fact, and its time properties (see "Time on a fact") say how it ages. A fact's class,
  when a project has several, says what kind of evidence it is (see "Fact classes").
- A fact whose mentions match no entity is kept, with the mentions recorded as unlinked. (Kyle asked for facts to link
  to one or more entities, and separately asked that unclassified facts and entities be accounted for. Keeping unlinked
  facts is how the README squares the two.)
- Reads are by entity and trait, plus search: `entity.facts(traits=..., since=...)`, `Fact.search(query, about=...)`,
  and `Fact.unlinked(...)`. There are no typed reads.

### Fact classes

**Decided** (Kyle, 2026-11-15). A `Fact` subclass is like a model without custom fields: a fact's fields are
fixed, and the class holds the rules and behavior around them. Many projects have one fact class, and many have a few.

- **One class per project** is the common case: the project's rules for facts.
- **A few classes for different kinds of evidence** is also common: in a CRM, what a customer told us (`CustomerFact`)
  versus what our own team said internally (`InternalFact`). These are not tied to document types: an email or a call
  can produce both.

**Proposed.** What a fact class can own:

1. What counts as a fact: extraction guidance.
2. Which traits are asked.
3. Quality rules: `validate()`, fact evals, and thresholds.
4. Trust: how much its facts weigh in search, and whether they can contradict facts of another class (a rep's hunch
   should not contradict what a customer said).
5. Visibility: who may read them (an agent writing to a customer never sees `InternalFact`).
6. How a fact is shown to a reader or a model: `render()`.
7. Reactions: the `after_` hooks, such as notifying a deal owner when a pricing fact is superseded.
8. Queries scoped to the class: `InternalFact.search(...)`.

With several fact classes, each extracted fact is classified on its own, with the same registry pattern as documents:
every `Fact` subclass registers itself and has a `classify(fact, judgments)` classmethod, and the central
classifier picks one class per fact. Its class is picked before its traits, since the class says which traits are
asked. Known structure helps: a quote's speaker from a transcript or an email header. A document can optionally narrow
the candidates (`fact_classes = [InternalFact]` on a sales Slack channel); otherwise every fact class is a candidate.

## 6. Traits

**Decided** (Kyle, 2026-11-15). A trait is a `FactTrait` subclass (earlier drafts called these labels). A simple
trait is just its docstring; a trait that needs more holds settings and code on the class. A fact class lists the
traits it asks, so one trait can be shared by several fact classes.

```python
from factoid import Fact, FactTrait, Noul, judge

class PainPoint(FactTrait):
    """A problem the customer says they have today."""

class Pricing(FactTrait):
    """Budget, price, discount, or contract terms."""
    threshold = 0.8
    examples = ["Globex's budget for the tool is $40k a year."]

    @classmethod
    @judge(states_amount=Noul("Does it state an amount of money?"))
    def decide(cls, fact, judgments):
        return judgments.pricing > cls.threshold and judgments.states_amount > 0.5

    @classmethod
    def after_supersede(cls, fact, older):
        notify(fact.account.owner, f"Pricing changed: {older.text} → {fact.text}")

class CustomerFact(Fact):
    traits = [PainPoint, Pricing]
```

**Proposed.**

- The docstring is the definition a model reads. With no `decide`, the default is Jev's yes-or-no question built from
  the docstring, compared with `threshold`. A `decide` method gets that answer as `judgments.<trait name>`, plus any
  factor questions it declares with `@judge`.
- A trait can carry `after_` hooks that run for facts with that trait.
- Reads take the class: `globex.facts(traits=[Pricing])`.
- A fact carries zero or more traits. By default each trait is one yes-or-no question. Traits are not mutually
  exclusive.
- A fact that matches no trait is kept.
- "Use case" and "pain point" are traits, not fact subclasses.
- Later: suggest new traits by clustering facts with none, and apply a new trait to stored facts without re-extracting.

### Time on a fact

**Decided** (Kyle, 2026-11-15). There are no fact kinds. How a fact behaves over time is a set of properties on each
fact instance, filled in automatically. The base `Fact` class holds the configuration and the default judgment
questions that fill them, and a project can change those on its fact classes. This replaces `FactKind` and the seven
kinds (fixed, state, event, decision, plan, forecast, and rule), and leaves traits as the only way a project
classifies facts. Harvey's public material has no equivalent of kinds either: its review tables treat a date as a typed
value, not a category of fact.

**Proposed.** The properties:

| Property | What it holds | Where it comes from |
| --- | --- | --- |
| `valid_from` | When the fact became true or happened | The text, resolved against `source_datetime`; otherwise `source_datetime` |
| `expires` | `"never"`, `"estimated"`, or `"at_deadline"` | A judgment in `assess` |
| `valid_until` | The exact end or due time, when the text gives one | The extractor |
| `lifetime` | A distribution over ranges, when `expires` is `"estimated"` | A judgment in `assess` |

- `expires = "never"`: true for good, as history or as an invariant. "Orion signed Amendment 2 on October 3, 2026."
- `expires = "estimated"`: true until something changes it, which nobody can date. "Orion may not assign the Vega
  supply agreement without Vega's written consent." The lifetime ranges are an hour, a day, a week, a month, a quarter,
  a year, a few years, or longer. Factoid keeps the distribution, not one cutoff, and computes the chance the fact is
  still true at a given time.
- `expires = "at_deadline"`: the fact carries a date by which it is settled. "Vega said it will answer the consent
  request by November 20, 2026."
- A future `valid_from` is allowed: "Amendment 2 raises the liability cap to $2M from January 1, 2027" is valid from
  that date.
- The clock for an estimated lifetime starts at the most recent time the fact was seen to be true, and each confirmation
  restarts it.
- Factoid already records when a fact was observed (each quote's `source_datetime`) and when it was extracted
  (`extracted_at`). Neither is a fact's date.
- The judgments go in the same `assess` request as the trait questions, so they add no call. The step is the
  `expiration` method, with `before_expiration` and `after_expiration`.
- Configuration on `Fact`, overridable on a fact class: the wording of the `expires` and `lifetime` questions
  (level 3), the list of lifetime ranges and thresholds (level 2), and the `expiration` method itself (level 4).
- Whether two disagreeing facts contradict or one supersedes the other is the resolve step's answer per pair, not a
  property of either fact. The resolve question sees both facts' time properties.
- **Open:** what a passed deadline means. A plan whose date passes without confirmation is overdue, not false, and an
  expected outcome whose date passes is unsettled. Whether that needs a property, or is left to resolve and search, is
  not settled.
- **Open** (Kyle, 2026-11-15): stance, meaning how confidently a fact is stated. The draft had two optional questions,
  hedged and opinion-or-observed; the research suggests one question (direct, uncertain, or evaluative). Left out of v1
  until it can be judged on about 20 real facts from a test corpus, with Jev's answers and what each would change in
  search and contradictions.
- Uses:
  - Search ranks facts past `valid_until` lower and flags them stale. `valid_at=` filters to facts likely still true.
  - An open contradiction goes stale when its facts' `valid_until` passes. See "Resolving".
  - `factoid stats` lists facts past `valid_until`, so a person or agent can re-check them.
  - Calibration eval: when a fact is superseded, its real lifetime is compared with the predicted validity.
- The old kind rubrics (fixed, state, event, decision, plan, forecast, and rule) are useful wording for the default
  `expires` question, and can be its examples.

## 7. Entities

**Decided.** Entities are a base class (`Entity`), and a fact links to one or more of them.

**Proposed.**

- **The v1 entity class** (Kyle, 2026-11-14; replaces the earlier `identities = {"email": "strong", ...}`):
  - The docstring says what the class is. Discovery uses it to route entities into the class.
  - `unique_keys` lists the identifiers that prove two records are the same thing. Optional: by default, email, domain,
    and URL found in text count. Names are always the weak match, checked by the decision model.
  - Typed, first-class properties, validated on write, with `Class.where(...)` queries (stored in the JSON `props`
    column; see "Entity storage").
  - Per-class tuning of the AI steps: guidance and examples for discovery, link and merge thresholds, the model, and the
    wording of the link and merge questions. Factoid's point is wrapping AI work, so this is in v1.
  - Every entity, typed or not, has `name`, `aliases`, `kind`, `props`, `find()`, `search()`, `facts()`, and
    `related()`, plus the management commands.
  - Not in v1 (see `specs/roadmap/entities.md`): domain methods built on reads, lifecycle callbacks, and `normalize`.
    Level 4 overrides of `identify`, `claim`, and `merge` still work, but are not documented in v1.
- Each link from a fact to an entity carries a role (`subject`, `about`, or `speaker`), the method that made it, and a
  confidence.
- Linking goes from sure to unsure, and stops at the first step that settles it:
  1. An exact identifier from the source.
  2. A strong identity.
  3. A name that matches exactly one entity in the same document.
  4. A name that matches exactly one entity in the store.
  5. A yes-or-no question to the decision model.
- Entities come from sources that carry records with identifiers, or from a discovery step per document. Every
  discovered entity is kept, typed or not, once the link ladder finds no existing match (see "Untyped entities").
  Placeholder names ("the customer", "someone") are refused.
- When an entity is stored, it claims stored facts: Factoid searches them for the entity's names, and the decision model
  confirms each hit.
- Entities that share a strong identity merge by rule. Entities that share only a weak identity go to a question with a
  high floor. Merge and split are logged as events, so each can be traced (and, if section 10's proposal holds, undone).

Sources for these choices: cerebro's link ladder and its over-creation cleanup jobs, and OpenEndgame's claims,
unlinked facts, and reversible merges (`docs/prior-art.md`, and the research summarized in the session of 2026-11-13).

### Relations between entities

**Decided** (Kyle, 2026-11-14). Relations are not declared. There is no `Relation` class and no relation schema.

**Proposed.**

- **Co-mention.** For each pair of entities, Factoid keeps the number of facts linked to both, the most recent one, and
  the roles each entity plays in them. It is counting, with no model call.
- **Relation facts.** A durable relation is a fact that links two or more entities, that never expires or has a
  lifetime of months or longer (see "Time on a fact"), and that is still valid. It is a view over stored facts,
  with no extra extraction. `entity.related()` returns connected entities, each with its co-mention count and its
  current relation facts. Freshness weighting applies, so a relation that has ended ranks lower.
- Direction is carried by the fact sentence.

Pair summaries and relation types that emerge from the data are in `specs/roadmap/relations.md`.

### Sides and groups

**Decided** (Kyle, 2026-11-14). Factoid has no concept of sides (ours and theirs) or entity groups in v1. It is too
fitted to CRM: many corpora (papers, news, lore) have no home team.

**Known issue in CRM corpora.** The home company appears in nearly every fact, so it dominates co-mention counts and
`related()`. Facts can also blur whose commitment or pain point something is ("Dana promised a discount" when there is a
Dana on each side). A CRM project can work around this with traits, speaker identities, and filtering out its own
company entity. Revisit if CRM evals show real harm.

### Untyped entities

**Decided** (Kyle, 2026-11-14). An entity does not need a declared class to be useful. Any entity Factoid can extract
is kept and linked, whether or not it matches a class: linking is better than nothing. Untyped entities are searchable,
mergeable, editable, and deletable through the CLI, the API, and MCP, like typed ones. The model is an emergent schema:
data first, classes later if the developer wants them. This reverses two earlier proposals: "a mention never creates an
entity", and "a discovered entity is stored only with a strong identity or when named in two or more documents".

**Proposed.**

- Discovery asks the decision model which declared class an entity is, with "none of these" as an option. With no
  match, the entity is a plain `Entity`.
- An untyped entity carries a free-text `kind` written by discovery ("S.F. Giants" is a "baseball team"), normalized
  to lowercase and singular.
- `factoid entities kinds` lists kinds by entity and fact count. `factoid entities retype --kind "baseball team"
  SportsTeam` moves them to a declared class. The decision model confirms each one, and nothing is re-extracted.
- Identity for untyped entities: name and aliases (weak), plus any strong identifier found (URL, email, or domain).
  They are linked with the same ladder as typed entities.
- Commands: `factoid entities search`, `show`, `edit`, `rename`, `merge`, `split`, `retype`, and `delete`. Each is an
  event.
- Guards against over-creation (the problem cerebro's cleanup jobs fixed): link before create; refuse placeholders;
  dedupe continuously, with candidate duplicates (similar names, shared facts) sent to the decision model as merge
  questions; and report entities with only one fact in `factoid stats`.

### Entity altitude and properties

**Decided** (Kyle, 2026-11-14).

- **High-cardinality things are entities like any other.** An account, an opportunity, a support ticket, an invoice,
  or a baseball game each gets its own entity. There is no separate tag mechanism for identifiers.
- **The discovery prompt teaches altitude.** It says which things make sense as entities: things with an identity that
  facts can be about over time (people, organizations, accounts, deals, tickets, products, projects, events such as a
  game or a meeting). It also says which do not: amounts, dates, generic nouns, and placeholders.
- **Every entity has a property bag.** `Entity` has `props`, a JSON dict, so untyped entities can hold
  properties too.
- **Typed entities declare properties, without an ORM** (Kyle, 2026-11-14, revising the earlier "like an ORM model").
  A subclass lists property names and types. They are validated on write and queryable, and live in the same JSON
  column as untyped properties.

**Proposed.**

- `related()` ranks by co-mention count, so entities with one fact sink without special handling.
- A property change is an event, with its source (a structured row, a source record, a person, or an agent).
- Properties come from structured documents (a column map can map a column to a property), from source records, and
  from edits through the CLI, the API, and MCP.

**Decided** (Kyle, 2026-11-14): entity storage.

- Entities live in SQLite in one table for all classes: id, class, kind, name, aliases, `props` (JSON), and times. No
  table per class, and no migrations when a class changes.
- A class's declared properties are validated with Pydantic when written.
- `Class.where(prop=value)` queries properties through SQLite's JSON functions. A busy property can get an index later
  without a schema change.
- Entities are mirrored into a third turbopuffer namespace, `<project-id>-entities` (names, aliases, kind, and a name
  embedding), for entity search and fuzzy linking. SQLite stays the record.
- turbopuffer was checked as a document store (2026-11-14): vectors are optional, attribute filters and ordering work,
  and it has patches, conditional writes, and strong reads. It has no nested objects, no multi-document transactions,
  no get-by-id, writes of about 165 ms p50, and 16 concurrent queries per namespace. So it is not the record.

**Decided** (Kyle, 2026-11-14). Extraction from prose writes facts only, never properties. Properties come from
structured rows, source records, and edits, so they always have clear provenance.

## 8. Pipeline

**Proposed.** Each step is a hook on the class that owns it.

| Class | Hooks |
| --- | --- |
| `Document` | `classify`, `segment`, `chunk`, `situate`, `extract`, and `discover` (prose); `read`, `row_facts`, and `discover` (structured) |
| `Fact` | `validate`, `evaluate`, `repair`, `assess`, `link`, and `resolve` |
| `Entity` | `identify`, `claim`, `merge`, and `split` |

The full list, with classmethods and instance methods, is in "Steps are methods".

**Decided.** The framework is principally for organizing AI code and prompts. Hooks that customize model work
(classifying, extracting, and evaluating facts) are the main case, and plain deterministic hooks are secondary.

Every hook can be customized three ways: class attributes, a prompt file, or a method override that may call `super()`.
A setting can be a computed property.

### Steps are methods

**Decided** (Kyle, 2026-11-15). Every core pipeline step is a classmethod or an instance method, so it can be inspected
and overridden. Class attributes are inputs to the default method, not behavior of their own.

**Decided** (Kyle, 2026-11-15): **before and after hooks.** Every step has `before_<step>` and
`after_<step>`. They do nothing in the base class, but they are always called. There are no separate lifecycle
callbacks (`on_added` and the rest are gone).

**Proposed.**

- `before_<step>(...)` gets the step's inputs, and can raise `factoid.Skip` to skip the step for this item.
- `after_<step>(..., result)` gets the inputs and the result, and can return a replacement, or `None` to keep it.
- The rule for which is which: a step about one thing that exists is an instance method; a step that decides which class
  or which record applies, before there is an instance, is a classmethod.

| Class | Classmethods | Instance methods |
| --- | --- | --- |
| `Document` | `classify(raw, judgments)` | Prose: `segment`, `chunk`, `situate`, and `extract`. Structured: `read` and `row_facts`. Both: `discover`, `context`, the `source_datetime` property, and `ingest`, which runs the steps in order |
| `Fact` | Reads, such as `search` | `validate`, `evaluate`, `repair`, `assess` (traits and time properties, in one request), `expiration`, `link`, `resolve`, and `save`; outcomes `supersede`, `end`, `correct`, `contradict`, `retract`, and `restore` |
| `Entity` | `identify(mention)`, `create`, and reads `find` and `where` | `claim`, `merge`, `split`, `retype`, `related`, and `facts` |

- Overriding an outcome (such as `supersede`) and calling `super()`, or defining `after_supersede`, is how a project
  reacts to a change. An agent outside the project reads the event log instead.
- `factoid steps show TenantEmail` lists each step, the class that defines it, and its hooks, so overrides are visible.

### Jev judges, code decides

**Decided** (Kyle, 2026-11-15). Following the Jev best practices in `tiffygk/jev-mode` (`shared/jev-rules.md`): where a
step needs a judgment, it asks the decision model several atomic questions (Nouls, Scores, and Choices) about factors,
and code decides from the probabilities with thresholds and ranges it controls. One broad question per step is the
default, not the ideal.

**Proposed.**

- A step declares its questions with the `@judge(...)` decorator. The judgments arrive as an argument. All questions for
  one item go in one request (jev-rules E1), and identical questions from different classes are asked once.
- Thresholds live in code, with a middle band that goes to review instead of one cutoff (E2, E6), set from the
  probabilities observed on real data (E7).
- The example the docs use:

```python
from factoid import Choice, ProseDocument, Noul, judge

class TenantEmail(ProseDocument):
    """An email from a tenant to the leasing office."""

    @classmethod
    @judge(
        is_email=Noul("Is this an email?"),
        sender=Choice("Who sent it?", ["tenant", "vendor", "staff", "someone else"]),
    )
    def classify(cls, raw, judgments):
        if judgments.is_email > 0.9 and judgments.sender["tenant"] > 0.7:
            return True
        if judgments.is_email < 0.3:
            return False
        return None   # the middle band goes to review
```

### Levels of customization

**Decided** (Kyle, 2026-11-14). Every level is optional.

| Level | What the user writes |
| --- | --- |
| 0. Nothing | No code. The defaults run. |
| 1. Declare types | Classes with a description (`Document`, `Entity`, `FactTrait`, and so on). |
| 2. Tune a type | Settings on the class: guidance, examples, thresholds, and which model it uses. |
| 3. Replace a step's wording | A question for a decision step, or a prompt for a generation step. |
| 4. Replace a step's logic | Override the hook method, and call `super()` to keep the default. |

Project-wide settings (`settings.py`) sit beside these: models, store, search, and budgets.

Every step offers levels 2 to 4. What level 3 holds depends on the kind of step:

| Kind of step | Steps | Level 3 |
| --- | --- | --- |
| Decision | classify, evaluate, assess, link, resolve, and rerank | A question, with yes and no criteria or with options |
| Generation | situate, extract, repair, and discover | A prompt |
| Plain code | segment and chunk | None: settings or a method override |

**Decided** (Kyle, 2026-11-14): level 3 wording is assigned explicitly on the class, as a string or as a file reference.
There is no lookup by naming convention.

```python
from factoid import Entity, template

class Customer(Entity):
    """A company that buys from us or might."""
    link_question = "Is this mention the same company as {{ entity.name }}?"   # a string

class CallTranscript(ProseDocument):
    """A recorded sales call."""
    extract_prompt = template("prompts/call_extract.md")                       # a file
```

**Proposed.**

- Both forms are Jinja templates. `template(path)` resolves the path relative to the file that defines the class.
- A missing file or an undefined field fails when the class is defined, not at the first model call.
- `factoid prompts show CallTranscript.extract` prints the wording in effect and where it came from (a string on the
  class, a file, or the default).

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
- `Fact.search(...)` returns facts, and `chunks.search(...)` returns chunks with their situation, document, and
  position. A search for both runs hybrid search in each namespace in parallel,
  then reranks the combined list (Kyle, 2026-11-14). Without a reranker, it falls back to reciprocal rank fusion.
- Separate namespaces also let Factoid benchmark facts against chunks on the same corpus. See
  `specs/benchmarks/facts-vs-chunks.md`.
- Whether the default search returns facts only or both is an eval result.


### Prose and structured documents

**Decided** (Kyle, 2026-11-14).

- `Document` is an abstract base with two kinds under it. `ProseDocument` is text, and runs segment,
  chunk, situate, and extract. `StructuredDocument` is rows: CSV, JSONL, a JSON array, or records from a source.
- A structured document has a **column map**, worked out once per file layout and not once per row. Each column is one
  of: an identity of an entity (an exact link, with no model call), a value with a sentence template (one fact per
  value), free text (run through the prose pipeline with the row's entities already known), or ignored.
- `key` names the column that identifies a row across re-imports. `row_entity` says what entity each row is. `when`
  names the column that dates the row.
- **Documents declare their dates and context** (Decided, Kyle, 2026-11-15). Emails, Slack messages, transcripts, and
  news articles carry dates and authors outside their text. A document class says where to find them, and Factoid
  gives them to the extractor ahead of the passages, so fact dates come from the text plus this structure. Proposed
  shape for prose documents:
  - Every document has one universal date field, `source_datetime` (Kyle, 2026-11-15), for its own date (an email's
    sent time, an article's publish date, a wiki page's last edit). It comes from the document's metadata, through the
    same interface for every document class.
  - Factoid also stamps every fact with `extracted_at`, for internal use: the time extraction concluded, before the
    first judging step. It is never used as a fact's date. (The split follows Keen IO's `keen.timestamp` and
    `keen.created_at`.)
  - The date is validated by Pydantic and stored as an ISO-8601 UTC string with microseconds. Accepted inputs: ISO-8601
    strings, which must carry a timezone offset or `Z` (Kyle, 2026-11-15); epoch seconds, milliseconds, or microseconds,
    with the unit inferred from the size of the number; and timezone-aware `datetime` values. A re-ingested, edited
    document gets the newer date.
  - `context()` returns a dict shown to the extractor before the passages (sender, channel, speakers, and the like).
  - Passages can carry their own time from `segment` (a transcript turn's timestamp, each message in a thread).
  - Built-in document classes for email, Slack, transcripts, and news fill these in. With no declared date, the
    extractor reads dates from the text only, and nothing is anchored to the ingest time.
- Joins across files come from entities: two files whose columns point at the same entity are connected through it.
  There is no file-to-file join logic.
- Provenance for a structured fact is the cell, with the file, row, and column.
- On re-import, a changed value for the same row key and column supersedes the old fact by rule, with no model call.
- A file is matched to a structured class by its header first. The decision model is the fallback.
- **A parser is a Python class.** A `StructuredDocument` subclass is the parser: the column map at level 2,
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

**Decided** (Kyle, 2026-11-15): structured-document commands sit under `factoid struct`. prosaic has the same commands
on its own (`prosaic inspect`, `prosaic parser new`, and `prosaic run --dry-run`), and Factoid's wrap them:

- `factoid struct inspect <file>` shows the columns, types, sample values, guessed identities, the column map a parser
  would start from, and which structured class matches the file and why.
- `factoid struct parser <file> [--name OpenDeals]` has a model write the parser class. `--prompt` prints the prompt
  and inspection instead of calling a model.
- `factoid struct try <file> [--rows 20]` is the parser's dry run: it prints the sentences and their citations and
  writes nothing.
- The real import is `factoid ingest <file>`, the same as for prose. `factoid ingest --dry-run` runs the whole pipeline
  on any document kind and writes nothing.

**Open.** Whether value columns read better in search as template sentences or as one model-written sentence per row.
An eval decides, so both are built.

### Classification

**Decided.** Classifiers are fast decision models (Jev-like) by default: a typed question answered in one pass, with a
probability per option and no generated text.

**Decided** (Kyle, 2026-11-15). A document's class normally comes from its source, and classification runs only when
it is unknown (for example, a folder of unmarked files).

**Proposed.**

- Every `Document` subclass registers itself when it is defined (`__init_subclass__`), so the registry builds
  itself. The central classifier loops over the registry.
- Each class's `classify(raw, judgments)` classmethod returns `True`, `False`, or `None` (not sure), or a score. A class
  can declare factor questions with `@judge` (see "Jev judges, code decides").
- The default, for classes that declare nothing: one Choice whose options are the document classes and their
  docstrings (jev-rules Q3), plus a Noul asking whether any of them applies (Q6). An optional `not_for` on a class
  describes its boundary with close classes. Each default `classify` reads its own class's probability from that one
  shared answer. For high stakes, the Choice is averaged over option orders (E4).
- Two `True` answers for one file is an error. Files no class claims go to an unclassified list for review.
- `classify_view` controls what the classifier sees. `factoid classifiers show` lists the registry.

### Sections and replaced sections

**Proposed** (2026-11-15, for Kyle to confirm).

- `segment` labels each passage with the numbered section it falls under ("3.2", "14.1"), and quotes carry the label.
- A prose document's `replacements` step finds passages that say numbered sections are replaced as a whole ("Sections
  3.1 and 3.2 ... are amended to read in their entirety", "deleted in its entirety"). It is plain code on the text,
  using the class setting `replacement_pattern`, not a model. A change to part of a section does not match.
- **Off by default**, and the evidence is against turning it on as built. A class can turn it on with
  `replacement_pattern = ProseDocument.ENTIRETY`. It was designed while looking at the NEON chain. On three chains
  labeled before any run and scored once (Glu and Fox, ScanSource and Cisco, PC Quote), it found no supersession that
  `resolve` missed, and raised false changes from 2.5% to 3.6%: an amendment replacing "the first paragraph of
  Section 4" retired all of Section 4. Labeling sections by number is too coarse for that; a design would need
  paragraph- or clause-level scope.
- After the document's facts are saved, facts from earlier documents that share an entity with the facts quoting
  that passage, and that quote a replaced section, are retired: superseded by the most similar new fact from the
  same section of the new document, or ended when the new document gives no text for it.
- Why: an amendment that rewrites a section often restructures it, so no single new fact reads as replacing a single
  old one, and `resolve` judged them unrelated.

### Fact evals

**Decided** (Kyle, 2026-11-14). The checks that decide whether a candidate fact is good enough to store are called
**fact evals** (base class `FactEval`), not judges. A fact eval answers one question: keep this fact, or not.
Assessing, linking, and resolving are separate decisions about facts already kept.

Names that follow: the `Fact` hook is `evaluate`, the class attribute is `fact_evals`, the module is
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
one question with six answers: duplicate, supersedes, ends, corrects, contradicts, or unrelated.

**Decided** (Kyle, 2026-11-15): ends and corrects are answers here, not a trait asked of every fact.

- **Supersedes:** the new fact gives a new value for the same thing ("Dana now leads sales" replaces "Maya leads
  sales"). The old fact was true until then.
- **Ends:** the new fact says a state stopped, with no new value ("the hotfix resolved the 502s" ends "Acme gets 502s").
  The old fact gets an end date and was true until then.
- **Corrects:** the new fact says the old one was wrong from the start ("restated Q1 revenue was $380M" corrects
  "$402M"). The old fact is marked `corrected` and is not shown as true at any time.

Neither cerebro nor OpenEndgame detects that a newer fact replaces or contradicts an older one, so this step is new
work and needs evals before any claim about its quality.

**Decided** (Kyle, 2026-11-14): how contradictions are handled.

- Two facts that contradict are both marked `contradicted`, and each points at the other. Reads show both.
- A contradiction is settled by new evidence (resolve checks each new fact against open contradictions) or by a person
  or agent picking a side (`factoid contradictions`). Either way the settlement is an event.
- If neither happens, the contradiction goes stale when its facts pass `valid_until`. It is never settled
  automatically: the facts rank lower, and `factoid stats` counts them.
- **Search results carry contradictions by default.** A fact with known contradictions comes back with the first N
  contradicting facts in full and the ids of the rest. Set per search: `contradictions=3` (the default count is a
  proposal), `contradictions=0` for ids only, or `contradictions=False` to leave them out.

**Proposed: freshness weighting in search.**

- From a fact's validity distribution (see "Time on a fact"), Factoid computes the probability the fact is still
  valid at a date.
- Search multiplies relevance by `floor + (1 - floor) * P(still valid at as_of)`. The floor keeps stale facts findable
  and ranks them lower. Events and stable facts score near 1.
- Per search: `as_of=` (default now), and `freshness="any"` to turn weighting off for history and research.
- It runs in Factoid after retrieval: over-fetch from each namespace, weight, then rerank or fuse. Search queries stay
  plain turbopuffer queries with no custom server-side scoring.
- The floor and the over-fetch factor are eval results.


## 9. Model calls and prompts

**Proposed.**

- Hooks call models through `choose`, `decide`, and `score` (decision model) and `generate` (generative model). Calls
  made this way are logged, priced, budgeted, replayed, and fingerprinted.
- Models are named once in settings and pinned to exact versions.
- Prompts are Jinja templates. A file at `prompts/<class_name>/<hook>.md.j2` replaces a built-in prompt for one class,
  and a project template can extend a built-in one and change a block.

**Open.**

- "Prompt" is too narrow a word, and a `prompts/` folder may be the wrong abstraction (Kyle). The working decomposition
  of a model step is five parts: inputs, the view of each input, the question (type, instruction, and criteria), the
  rule that turns answers into a decision, and the model.
- For Jev, each kind of use fixes the inputs, and the author supplies criteria. Classifying, evaluating facts,
  resolving, identifying, and ranking may all become one `Question` shape.
- The pieces an author writes (definition, guidance, examples, and rubric) may live on the class, with a type that
  outgrows one file getting its own folder.

### Workloads, providers, and keys

**Decided.**

- The `choose` workload (classifying, evaluating facts, assessing, linking, and resolving) is done by a decision model,
  also called a System One model. A generative model does not stand in for it.
- Jev (TypeSafe) is the recommended decision model: it is the best and it is cheap. Other providers have one too, and
  Factoid supports them: OpenAI's decisions API, Fireworks' Rune, and Cloudflare's Clef.
- Keys belong to providers, and a provider can serve several kinds of model. The README must not pair one key with one
  kind of model.
- **Generation is set per step** (Kyle, 2026-11-15). One `generate` model is too broad: steps need to be tuned
  separately, and `situate` and `extract` are the first two. Each generation step (`situate`, `extract`, `repair`, and
  `discover`) can have its own entry in `models`, falling back to `generate` when unset, so a project can pick and
  evaluate a model per step. Usage and cost are reported per step; the replay cache keys on the request, so moving a
  step to its own entry with the same model still replays.

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
  resolves to, and whether each has a working key. `factoid init` and `factoid setup` write `settings.py` once, when the
  project is created. After that, a person changes a model by editing the file.
- A provider can be keyless: a local runtime, or a gateway that injects credentials.

**Open.** Whether the four decision models share a request shape. Jev takes a JSON state plus named questions of type
`noul`, `choice`, or `score`, each with instructions and criteria. The other three have not been checked.

## 10. History and fingerprints

**Decided** (Kyle, 2026-11-14).

- **Current state is the truth.** The facts, entities, links, and traits tables say what is true now, and reads go to
  them. Nothing is rebuilt from history.
- **The event log is for audit and provenance.** Every change also writes an event. Fact events are `added`,
  `superseded`, `ended`, `corrected`, `contradicted`, `retracted`,
  and `restored`. Entity events are `linked`, `merged`, and `split`. Each
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
  links, traits, entities, and the event log, and it answers every lookup that is not a search: facts for an entity,
  entities by identity, facts by trait and time, and unlinked facts.
- **v1 search: turbopuffer, or any endpoint compatible with its API.** It is required. It serves vector, BM25, and
  hybrid search, and the nearest-neighbor queries that resolve and entity linking need. The endpoint's base URL is a
  setting, so a compatible server can stand in for turbopuffer.
- **No flat-file store for now.** Set aside: files with a SQLite index (as endgame-wiki does), and a bucket-only store
  (an event log in S3 or R2, with LanceDB tables as views).

**Proposed.**

- SQLite is the truth, and the turbopuffer namespace is a view. If the index is lost or its settings change,
  `factoid rebuild` repopulates it from SQLite.
- Two turbopuffer namespaces per project, named from the project id: one for facts and one for chunks. Each row is a
  fact or a chunk, with its vector, its text for BM25, and its entity ids, traits, and times as filterable attributes.
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

**Decided** (Kyle, 2026-11-14): **Factoid requires keys.** There is no keyless local mode in v1, and maybe never. The
setup wizard makes getting keys easy. A provider can still be pointed at a custom base URL with no key (a gateway, or a
local runtime such as Ollama), but local runtimes are not promised or tested.

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
    stable project id, at `~/.factoid/projects/<id>/.env`. `factoid init` writes the id into the project, and
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
    `factoid init` writes it. The id is the project's name plus a short random suffix, such as `acme-7k2m`, and it is
    committed, so every checkout and every teammate shares it.
  - With a project found, the command loads that project's keys, then re-runs itself inside the project's own
    environment, so it can import the project's classes and their dependencies.
  - The global command is a thin launcher. When a project pins its own version of Factoid, the project's version does
    the work.
  - Outside a project, `init`, `keys`, `setup`, and `doctor` work with the user's defaults.
- Terms: the README says "decision model" (not "choice model"), and the settings key for that workload is `choose`.
- The README's Setup section follows the workloads and providers model in section 9: one provider key to start, Jev
  recommended for `choose`, `factoid models` to review, and `factoid setup` as the terminal UI.
- Commands in use across the docs: `init`, `ingest`, `search`, `read`, `eval`, `rebuild`, `stats`, `serve`, `mcp`,
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

**Decided** (Kyle, 2026-11-14). The wizard is built with Textual.

## 13. Out of scope

**Decided** (Kyle, 2026-11-14). Factoid is a self-contained fact service. It creates, changes, ranks, and serves facts
and entities, and that is where it stops. It can be used in many ways, and those uses are built on it rather than in
it: briefs and articles about an entity, digests of what changed, choosing which entities to track, publishing, and so
on (`docs/potential/crm-starter.md` sketches one).

One use the docs call out: personal agents can use Factoid over MCP as a more rigorous memory, with facts that carry
sources, dates, validity, and contradictions instead of loose notes.

Generated text that Factoid keeps and cites (situations, and pair summaries on the roadmap) is inside the line. Prose
written for people to read is outside it.

## 14. Evals

**Decided.** Benchmarks decide algorithms. Do not ask Kyle to pick between fact eval chains, extraction strategies,
retrieval methods, or thresholds. Make each a selectable strategy, and measure.

**Proposed.** `factoid eval` scores a project against labeled data and reports quality, cost, and latency.
`--vary` runs the same documents under each strategy. Defaults are eval results. The scorecard includes coverage: the
share of facts with no trait, and the share of mentions with no entity.

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

- `docs/facts.md`, `docs/mental-model.md`, `docs/config.md`, `docs/plugins.md`, `docs/cli.md`, and
  `docs/potential/crm-starter.md` predate the entity redesign. `docs/config.md` and `docs/plugins.md` also describe
  the single-YAML design.
- README.md is up to date with the decisions through 62, and uses the legal example (Acme buying Orion, and
  Orion's supply agreement with Vega).
- The `TenantEmail` example in "Jev judges, code decides" is from the old rental example. The README uses
  `Contract.classify` instead.

## 17. Implementation status

The first code is in `src/factoid`. It follows this spec, with these differences and gaps. Each is either a choice
the code had to make that the spec leaves open, or work not done yet. The first app built on it is the legal
diligence app in `examples/legal`, scored on CUAD; `examples/iscrag` reruns the ISC-RAG held-out benchmark.

- **Built:** prose documents (segment, chunk, situate, extract), steps as methods with `before_` and `after_` hooks,
  `@judge` with Noul, Choice, and Score, the document classifier registry, fact classes with per-fact
  classification, traits with `decide`, time properties, the fact eval chain with repair, entity linking with the
  five-step ladder, discovery, untyped entities and claiming, resolve with the six answers, the SQLite store with an
  event log, search over facts and chunks with freshness weighting, the model client with a replay cache, `factoid`
  CLI commands (`init`, `ingest`, `search`, `read`, `stats`, `entities`, `steps show`, `classifiers show`,
  `prompts show`, `keys set`, `models`, `doctor`, and `eval`), and the eval harness with `--vary`.
- **Search backend:** with no `search` setting, a project uses `LocalIndex`, a SQLite file with FTS5 for BM25 and
  exact vector search. `Turbopuffer` is built and used when set. The spec says a project needs turbopuffer; the
  local index makes tests and small projects work without it.
- **`Nli`** is in the default chain but runs only when a project sets an `nli` model. With none set, it is skipped
  and the scorecard says so, so the working default chain is `JevFloors`.
- **Starting floors** for `JevFloors` are fixed values until calibration is built: grounded 0.45, attribution 0.3,
  self-contained 0.4, atomic 0.25, useful 0.45, and distinct 0.2. They were set from CUAD runs (2026-11-15). The
  first values (0.45 to 0.6) rejected most good facts; with these, and the grounded and attribution questions narrowed
  to the claim, the share of gold clauses quoted by a kept fact went from 0.61 to 0.96 on 20 contracts.
- **Not built yet:** `StructuredDocument` (waits for prosaic), `factoid struct`, sources (`imap`, `mcp`), MCP and
  HTTP serving, `factoid setup`, fact-class trust and visibility, entity `merge`, `split`, and `retype` commands,
  fingerprint-driven `rebuild`, and decision models other than Jev.
- **`situate`:** the setting `situate = True` runs the built-in step (`situate_chunk`); a method named `situate` on a
  class replaces it.
- **A duplicate** adds its quotes to the stored fact, which restarts its clock, and writes no event.
- **A passed deadline** (Open in "Time on a fact") is scored as one half in validity until it is decided.
- **Extraction never drops a chunk silently.** An answer that is cut off or malformed is retried as two half chunks.
  Before this, about 1% of chunks were lost, and with them clauses such as a governing-law section.
- **Mentions carry aliases**: the extractor lists other names the document uses for a thing (a defined short name
  such as "Vega" for Vega Components Corp.), and linking matches on them. Without this, the same company became two
  entities across documents.
- **As-of search** includes superseded and ended facts that were still valid on the `as_of` date.
- **Repair can split.** A near miss that states several claims is split into one fact per claim, each evaluated
  again, instead of only being reworded.
- **Resolve thresholds.** Answers that drop or flag a fact need more confidence than others: a duplicate 0.8 and a
  contradiction 0.75 (the distinct floor mirrors the duplicate bar). When the model is sure two facts state the same
  claim but not whether the value changed, and the new one is later and from another document, it supersedes. A
  fact's own document gets at most half of resolve's candidate slots.
- **Search** reranks the best 50 candidates after freshness weighting.
- **Sections:** passages and quotes carry section labels, and a section replaced in its entirety retires the older
  facts quoting it (see "Sections and replaced sections").
- **First try at replaced sections, removed** (2026-11-15): the extractor flagged which facts replace sections. It
  flagged the new section's facts instead of the instruction, so it missed, and a linking error (below) spread its
  changes across unrelated contracts. The current version finds the instruction with code instead.
- **Generic defined terms stay local.** An alias becomes an entity's alias only when the placeholder question says
  it is a specific name. Before, "Agreement" and "Amendment" from one contract became global aliases, and mentions
  in an unrelated contract linked to them, which led resolve to supersede facts across contracts.
- **Repair** also runs when a narrow "useful" failure comes with a repairable one, since a split often fixes both.
- **Tried and reverted** (2026-11-15): a yes-or-no question in resolve asking whether two facts set the same term,
  with a later document's version superseding at 0.7, and giving the "useful" check the fact class's guidance. It
  aimed at a restructured payment clause in the held-out NEON chain. It did not catch that clause, raised false
  supersessions (signature and date facts), and broke 4 of 12 checks on the sample deal.
- **Repair splits on an atomic failure**: a fact that failed the atomic check states several claims, so repair must
  split it rather than reword it.
- **Fresh amendment chains** (2026-11-15), labeled before any run and scored once: supersessions 2 of 4, untouched
  clauses 2 of 2, as-of search 3 of 4, dated windows 2 of 2, false changes 2.5% with replaced sections off. The
  misses: a base clause never kept as a fact (ScanSource's inventory claim window), a section deleted and replaced
  with fully redacted text (PC Quote), and one as-of question. These are the honest numbers for amendments; the
  chains used while tuning score higher.
- **Results while tuning** (2026-11-15), with replaced sections on: every amendment check passed on the four chains
  used while tuning (supersessions 4 of 4, untouched clauses 5 of 5, as-of search 5 of 5, dated windows 2 of 2),
  the sample deal passed 12 of 12, and CUAD clause F1 was 0.82, 0.84, and 0.81 on contracts 1 to 20, 21 to 40,
  and 41 to 60.
- **SEC amendment chains** (2026-11-16): three credit agreements from public EDGAR exhibits, labeled before any run
  and scored once. Supersessions 4 of 4, untouched clauses 2 of 2, as-of search 6 of 6, false changes 1.4%; the one
  miss is a temporary window's end date. Replaced sections made no difference there (4 of 4 with it off, 1.1% false
  changes), since those amendments changed values that `resolve` catches. They help with restructured rewrites,
  measured only on chains used while building them (NEON 1 to 2 of 2, PC Quote).
- **Tried and reverted** (2026-11-16): asking the extractor for one fact per period when a clause sets different
  values for different periods. It fixed dated windows on a 2010 dev set (14 to 17 of 20) but cost contract dates on
  the CUAD tuning set and broke supersession on the SEC chains, where a stepped schedule split into periods no longer
  reads as replacing the flat clause it amends. Dated windows inside a schedule remain a known miss.
- **Held-out check** (2026-11-15). The values above were tuned on CUAD contracts 1 to 20 and three amendment
  chains. On CUAD contracts 21 to 40, never looked at while tuning, clause F1 was 0.85 (0.82 on the tuning set),
  coverage 0.93 (0.95), and expiration dates 5 of 5. On a held-out amendment chain, as-of search was 2 of 2 and
  supersession 1 of 2. Details are in `examples/legal/README.md`.
- **Not on PyPI yet:** `uv tool install factoid` does not work until a release is published. Install from the repo.
- **Keys:** with no key set for a provider, the client calls that provider's exe.dev integration host, which injects
  credentials. With a key set, it calls the vendor.

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
28. `FactoidDocument` splits into `FactoidProseDocument` and `FactoidStructuredDocument`. A structured parser is a
    Python class with a column map. Factoid can write it with a model, or print the prompt for any coding agent, and it
    has a dry run.
29. MIT license for Factoid and prosaic.
30. prosaic is a separate repo (`Endgame-Labs/prosaic`) and a dependency of Factoid. Endgame uses it too.
31. Chunks are searchable as well as facts. A chunk is indexed with its situation when `situate` is on. Facts and
    chunks are in separate namespaces.
32. Searching facts and chunks together is hybrid search in each, then a rerank. Benchmark specs live in
    `specs/benchmarks/`, starting with facts versus chunks.
33. Fact traits: during labeling, the decision model also judges the kind of fact and how long it stays valid.
34. Contradictions are settled only by evidence or by a person or agent, and go stale when their facts expire.
    Search results include a fact's contradictions by default.
35. Relations between entities are not declared. Co-mention counts and relation facts (durable, valid facts that
    link entities) are the relations. Pair summaries and emergent types are on the roadmap.
36. No sides or entity groups in v1. Logged as a known issue for CRM corpora.
37. Untyped entities: every extracted entity is kept and linked, with a free-text kind. Declared classes are optional
    and can be applied later with `retype`.
38. High-cardinality things (accounts, tickets, games) are ordinary entities. The discovery prompt teaches entity
    altitude. Every entity has a JSON property bag; typed entities declare first-class properties.
39. No ORM for entities: one SQLite table with a JSON `props` column, validated per class, plus an entities
    namespace in turbopuffer for search and linking.
40. The v1 entity class: a docstring, optional `unique_keys`, typed properties with `where()`, and per-class tuning of
    the AI steps. Domain methods, callbacks, and `normalize` are on the roadmap. No trait defaults per entity class.
41. Prose extraction never fills entity properties; it writes facts only.
42. Factoid requires API keys. No keyless local mode in v1, and maybe never.
43. Factoid is a self-contained fact service. Briefs, digests, publishing, and agents' memory are uses built on it.
44. Python 3.13+ with uv, confirmed. `factoid init` sets up the current folder and replaces `factoid new`. The setup
    wizard uses Textual.
45. Level 3 wording is set explicitly on the class: a string, or `template("path.md")`. No naming-convention lookup.
46. `decision` stays its own kind of fact, separate from `event`, after the trait research. (2026-11-15)
47. Resolve gains two answers, ends and corrects, so endings and corrections need no per-fact trait. (2026-11-15)
48. `plan` and `forecast` are separate kinds: an intended action versus an expected outcome. (2026-11-15)
49. Kinds of fact are fixed, state, event, decision, plan, forecast, and rule. Stable, slow-changing, and current state
    are dropped; lifetime ranges say how fast a state changes. World knowledge has no kind of its own. (2026-11-15)
50. Kinds of fact are declared on `FactoidFact` as `FactoidKind` classes, so projects can override and extend them.
    Documents declare their own dates and context for the extractor. Fact dates come from the text and that
    context, not from ingest time. (2026-11-15)
51. Every document has `source_datetime`, its own date from its metadata, the same for every document class. ISO
    strings need a timezone; epoch seconds, milliseconds, and microseconds are accepted. Facts get `extracted_at` for
    internal use. (2026-11-15)
52. A fact's expiration is decided per fact: an exact time from the text when there is one, otherwise a range from
    an hour to longer than a few years, chosen by a model. The clock restarts when the fact is confirmed. (2026-11-15)
53. Stance (hedged, opinion) is Open and out of v1, to be judged on real examples. (2026-11-15)
54. Structured-document commands: `factoid struct inspect`, `factoid struct parser`, and `factoid struct try`.
    (2026-11-15)
55. README brought up to date by a Carbon pass: documents, `source_datetime`, structured documents, kinds and
    expiration, untyped entities, resolve and contradictions, freshness, and relations. (2026-11-15)
56. Every pipeline step is a classmethod or instance method, with `before_` and `after_` hooks that are always called
    and do nothing by default. They replace lifecycle callbacks. (2026-11-15)
57. Jev judges, code decides: steps ask several atomic questions with `@judge` and decide in code with thresholds.
    (2026-11-15)
58. A document's class normally comes from its source. Classification is a registry of every document class, each
    with a `classify` classmethod; the default is one Choice over the docstrings plus an "any of these?" Noul.
    (2026-11-15)
59. Fact classes: one per project is common, and a few for different kinds of evidence (such as customer-stated
    versus internal) is also common. They are not tied to document types; each fact is classified on its own.
    (2026-11-15)
60. Labels are `FactoidFactLabel` subclasses (renamed from `FactoidLabel`): a docstring for simple ones, settings and
    a `decide` method with `@judge` for the rest. Fact classes list the labels they ask. (2026-11-15)
61. Labels are renamed traits: `FactoidTrait`, with the design from decision 60, and `traits = [...]` on fact
    classes. Kind and lifetime are no longer called traits. The step that judges traits, kind, and lifetime in one
    request is `assess`; `characterize` is gone. (2026-11-15)
62. The other-language README sketches in `docs/potential/README/` are removed. Python is the only language.
    (2026-11-15)
63. The README's running example is legal due diligence (a firm advising Acme on buying Orion), replacing the
    apartment-rental and CRM examples. (2026-11-15)
64. Base classes drop the `Factoid` prefix: `Document`, `ProseDocument`, `StructuredDocument`, `Fact`, `FactTrait`,
    `FactKind`, `Entity`, and `Settings`. This matches the README intro. (2026-11-15)

65. There are no fact kinds. `valid_from`, `expires`, `valid_until`, and `lifetime` are properties of each fact,
    filled in by `assess` from defaults on `Fact`. `FactKind` is gone. (2026-11-15)
66. Generation models are set per step (`situate`, `extract`, `repair`, and `discover`), each falling back to
    `generate`. (2026-11-15)
67. Example apps live in this repo under `examples/` (`legal` and `iscrag`), each its own Factoid project using the
    framework from the repo root. (2026-11-15)
