# Factoid spec

This file records the decisions behind Factoid, so the README does not have to spell each one out. The README is for
users. This file is for whoever builds Factoid.

An early implementation is in `src/factoid`; section 17 says what is built and where it differs. Every section says
how settled it is:

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

**Decided** (Kyle, 2026-11-14): **MIT license** for Factoid. Copyright holder: Endgame Labs. Kyle
considered Apache 2.0 for its patent grant and chose MIT. If Endgame ever wants a patent on anything here, it has to
file before the repo is made public.

**Decided** (Kyle, 2026-11-16): **structured documents are part of Factoid**, not a separate library. Turning rows
into sentences with cell citations, inspecting a file, the parser prompt, and the dry run all live in Factoid, next to
entities, linking, and supersede by row key. This reverses the 2026-11-14 decision to build them in a separate repo,
prosaic. See "Prose and structured documents" in section 8.

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

These choices draw on earlier internal fact systems: a link ladder with cleanup of over-created entities, claims,
unlinked facts, and reversible merges.

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
- Guards against over-creation (a problem earlier systems needed cleanup jobs for): link before create; refuse placeholders;
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
- Entities are mirrored into a third namespace, `<project-id>-entities`, in the project's search index (the built-in
  `LocalIndex` by default, or turbopuffer when set), with their names and aliases for BM25 and their class, for entity
  search and fuzzy linking. SQLite stays the record. A name embedding is not built yet.
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
| `Document` | `classify(raw, judgments)` | Prose: `segment`, `chunk`, `situate`, and `extract`. Structured: `read`, `identify`, `row_facts`, and `text_facts`. Both: `discover`, `context`, the `source_datetime` property, and `ingest`, which runs the steps in order |
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
- A missing file or a template syntax error fails when the class is defined, not at the first model call. An
  undefined field still fails only when the template is first rendered (not built: checking fields at definition).
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
- Ideas taken from an earlier prototype: rows become sentences, a file's layout is worked out once, and ID and email columns
  connect files. Left out: generating parser code with an unattended agent run, one long narrative per row, and fuzzy
  file-to-file joins.

**Decided** (Kyle, 2026-11-16): it is all in Factoid. Factoid reads files, inspects them, holds the column map and
sentence templates, writes parser prompts, and has the dry run, along with column roles that are entity identities,
linking, supersede by row key, and free-text columns through the prose pipeline. (On 2026-11-14 the generic parts
were to live in a separate library, prosaic; that is reversed.)

**Decided** (Kyle, 2026-11-15): structured-document commands sit under `factoid struct`:

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
- Two `True` answers for one file is an error. A file no class claims raises `UnclaimedDocument`; `factoid ingest`
  skips it, lists it at the end, and suggests `--as <Class>`. (An unclassified list kept for review is not built.)
- `classify_view` controls what the classifier sees. `factoid classifiers show` lists the registry.

### Sections and replaced sections

**Decided** (2026-11-16; Kyle: "keep what you built").

- `segment` labels each passage with the numbered section it falls under ("3.2", "14.1"), and quotes carry the label.
- A prose document's `replacements` step finds passages that say numbered sections are replaced. It is plain code on
  the text, using three class settings, not a model: `replacement_pattern` (a section is replaced),
  `partial_replacement_pattern` (only part of it is), and `deletion_pattern` (it is deleted with no new text). It
  returns a `Replacement` for each such passage.
- **The framework holds the mechanism; the app holds the wording.** The framework ships no patterns, so the step is off until a class sets `replacement_pattern`.
  "Amended to read in its entirety" is contract wording: the legal app's `Contract` sets all three, and another domain would use its own wording or
  override the step.
- **Evidence.** It was designed while looking at the NEON chain. On three chains labeled before any run and scored
  once (Glu and Fox, ScanSource and Cisco, PC Quote), it found no supersession that `resolve` missed, and raised
  false changes from 2.5% to 3.6%: an amendment replacing "the first paragraph of Section 4" retired all of Section
  4. Partial replacements are now checked fact by fact, which fixed that case on the chains used while building it.
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

- Every candidate fact passes a default chain before it is stored: `nli` (a small entailment model), then
  `decision_floors`. The chain rejects at the first failure.
- `decision_floors` asks six yes-or-no questions in one call: grounded, attribution, self-contained, atomic, useful, and
  distinct. Each has its own floor, and all six must pass. Scores are never averaged.
- Starting floors, from an earlier internal system: grounded 0.75, attribution 0.7, self-contained 0.65, atomic 0.4, useful 0.7, and
  distinct 0.6. Floors are calibrated on labeled data.
- A near miss gets one repair (a rewording), then is evaluated again.
- A project changes one floor or adds a fact eval without replacing the chain.

**Decided** (2026-11-17): how facts are written and checked is set per document class as well as per fact class.

- `Document` (so both `ProseDocument` and `StructuredDocument`) has `guidance`, `extract_prompt`, `repair_prompt`,
  `fact_evals`, and `evidence_context`. A structured document's `Text()` cells use its `guidance` and
  `extract_prompt`. `repair_prompt` and `fact_evals` default to None, which means the fact class's.
- Why on the document: how strict to be depends on the kind of source. A transcript sentence leans on earlier turns
  far more than a contract clause does, and fact classes are not tied to document types.
- `DecisionFloors` questions can be reworded, added, or dropped as well as floored:
  `DecisionFloors(questions={"useful": Noul(...), "atomic": None}, grounded=0.3)`. Every question needs a floor. Changed
  questions are part of the fact's fingerprint.
- The fact evals and repair see `text_before_passages`: the `evidence_context` characters (1,200 by default) of the
  document just before the fact's first cited passage. The extractor resolves "he" and "this aircraft" from earlier
  text, and without that text the grounded check rejected the resolved name as unsupported. 0 turns it off; it is 0
  for structured documents, whose earlier rows are not context.
- A fact that fails only questions a rewording or a split can fix (self-contained, atomic, and attribution) always
  gets one repair, however low its score. A "useful" failure rides along only within `repair_margin`.
- **Targets.** A question can have a target above its floor: `DecisionFloors(targets={"explicit": 0.5})`. A fact that
  passes the floor but scores below the target gets one repair, and the repair replaces it only when every repaired
  sentence reaches the target; otherwise the fact keeps its wording, and `scores["repair_missed"]` says what was
  tried. A floor of 0 makes a question that never rejects and only asks for repairs. Why: a strict question rejected
  useful facts whose repair did not work ("Tom Boeder said the case makes it difficult for Microsoft..."), and a
  lenient one kept "the death toll" and "yesterday". A target gets the strict wording's repairs without the
  rejections.
- Every eval run writes `rejected.jsonl`: each rejected fact with its scores, quotes, and repair attempts.

**Proposed** (Kyle, 2026-11-18): **retry after a rejection.** When a fact fails for a known reason, the extractor gets
one more try, with the rejected fact and the reason as context. It starts as an experiment on "grounded" failures,
where repair does not help today, and ships only if an eval shows more kept facts without lower QA accuracy or more
unresolved references.

**Decided** (Kyle, 2026-11-17): the default chain's second eval is `DecisionFloors` (`decision_floors`), named for
what it uses, a decision (System One) model, and not for one vendor's model. It was `JevFloors`.

- **Floors per decision model.** Two models give different scores for the same answer, so `MODEL_FLOORS` and
  `MODEL_TARGETS` hold floors and targets per model, keyed by the model's name (`fireworks/rune`). They fill in only
  the floors and targets a project did not set: a project's own `DecisionFloors(grounded=0.5)`, or a subclass's own
  `floors`, always wins. A target is never below its floor.
- Rune's floors were matched to Jev's pass rates on the same 1,450 requests from the iscrag dev run: grounded 0.25,
  self-contained 0.05 (target 0.95), atomic 0.08, useful 0.25, and distinct 0.05. On that run Rune answers 0.915,
  0.955, and 0.955 of the QA questions from facts at 512, 2,048, and 8,192 tokens, against Jev's 0.925, 0.965, and
  0.955.
- **The attribution question was reworded.** It asks whether the fact keeps the passages' speaker (or lack of one),
  subject, and certainty, and says that a passage with no speaker (narration, a report, a contract clause) needs none
  in the fact. Rune read the old wording as "does the fact name who said it" and scored correct contract facts near
  0. Jev scores the same with the new wording: 0.92, 0.955, and 0.95 on the same QA, within one or two questions of
  before.

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

None of the earlier systems we studied detects that a newer fact replaces or contradicts an older one, so this step is new
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
- Prompts are Jinja templates, set on a class as a string or with `template(path)`, and a project template can
  extend a built-in one and change a block. Prompts that write facts live on the document class: `extract_prompt`
  and `repair_prompt` (see "Fact evals").

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

**Decided** (Kyle, 2026-11-17). A project can run on OpenAI alone, or on Fireworks alone (experimental, decision
80). Fireworks has Rune and Qwen embeddings; OpenAI has its Decisions API and embeddings. `factoid init --models jev|fireworks|openai` writes one of
three presets, and Jev stays the default and the recommendation.

**Decided** (checked against the providers' docs, 2026-11-17). Request shapes for the decision models:

- Jev and Rune share System One: a JSON `state` and a map of named questions (`noul`, `choice`, and `score`, each with
  instructions and criteria), answered by a map of the same names. Jev is at `/v1/systemone` on `api.typesafe.ai`;
  Rune is `accounts/fireworks/models/rune` at `/systemone` under Fireworks' `/inference/v1`.
- OpenAI's Decisions API (`POST /v1/decisions`, `gpt-6-luna` only) takes an `input` and a list of questions
  (`predicate`, `choice` with `choices`, and `score` with `levels`), answered by a list in the same order. Factoid
  sends the state as an `input_json` part, folds a Noul's yes and no criteria into its instructions, names each
  question by its key, and reads answers back into System One's shape. A refusal is an error.
- Cloudflare's Clef has not been checked.

**Proposed.** Each provider lists the workloads it can serve, and `factoid models` and `factoid doctor` report an
assignment a provider cannot serve, before any call: TypeSafe serves `choose`; Fireworks serves `choose`, `generate`,
`embed`, and `rerank`; OpenAI serves `choose`, `generate`, and `embed`; OpenRouter serves `generate`.

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
- **v1 search: turbopuffer, or any endpoint compatible with its API.** (Superseded: the built-in local index is the
  default, and turbopuffer is optional; see section 17.) It serves vector, BM25, and
  hybrid search, and the nearest-neighbor queries that resolve and entity linking need. The endpoint's base URL is a
  setting, so a compatible server can stand in for turbopuffer.
- **No flat-file store for now.** Set aside: files with a SQLite index, and a bucket-only store
  (an event log in S3 or R2, with LanceDB tables as views).

**Proposed.**

- SQLite is the truth, and the turbopuffer namespace is a view. If the index is lost or its settings change,
  `factoid rebuild` repopulates it from SQLite.
- Three namespaces per project, named from the project id: one for facts, one for chunks, and one for entities (see
  section 7). They live in turbopuffer when it is set, and in the built-in `LocalIndex` otherwise. Each row is a
  fact or a chunk, with its vector, its text for BM25, and its entity ids, traits, and times as filterable attributes.
- Writes go to SQLite first, then to the index. A write the index has not confirmed is retried, so the index catches
  up with the truth.
- The SQLite file lives in a git-ignored folder in the project, unless `settings.py` points elsewhere.

**Decided** (Kyle, 2026-11-14): writing to SQLite.

- SQLite allows one writer at a time. In v1, model calls run in parallel, and every save goes through a single writer in
  the process. A document's rows (document, passages, and chunks) are saved in one transaction, and each fact and
  entity in its own short one. A document is marked ingested (its hash saved) only when its ingest finishes, so a
  failed run is ingested again next time.
- WAL mode is on, so reads and searches are not blocked by ingest.
- A second process writing to the same project waits its turn through SQLite's busy timeout.
- Many processes writing at once, or a hosted deployment, is the case for a Postgres backend. It is not built in v1.
- Later back ends behind the same interfaces: Postgres (pgvector and pgvectorscale) for the system of record and for
  search, and LanceDB on a bucket.

**Decided** (Kyle, 2026-11-18): **data warehouses are sources and export targets, not stores.**

- BigQuery, Snowflake, and similar warehouses can be where documents and rows come from (a source) and where finished
  facts, entities, and history go (an export), so analysts get facts in their own warehouse.
- A warehouse is never the system of record or the search index. Ingest makes thousands of small reads and writes per
  document (linking, resolving, and saving), and a warehouse is too slow for them and charges for each query.
- Order of work: put the remaining raw SQL in `app.py`, `cli.py`, and `entity.py` behind the `Store` interface, write
  the `Index` contract with tests every backend passes, then a Postgres backend, then warehouse export, then warehouse
  sources.
- Nobody has to know turbopuffer: the local index is the default, and turbopuffer stays an option for scale.

**Decided** (Kyle, 2026-11-18): **facts leave Factoid through exports, and two are standard.**

- **Parquet:** tables written to a local folder or an S3 bucket. BigQuery, Snowflake, DuckDB, Athena, and pandas all
  read Parquet, so one export reaches every warehouse through the warehouse's own load step, and Factoid holds no
  warehouse credentials.
- **A turbopuffer-compatible API:** facts written to a namespace an application searches. This is an output for other
  systems to read, separate from the optional turbopuffer search index Factoid itself uses.
- Other exports (a native warehouse, Postgres, or a queue) can be added behind the same interface later.
- **An export receives changes.** Each export keeps a cursor, the last event it sent, and each run sends what changed
  after it, read from the event log. Parquet writes a new file per run, with a view or compaction for the latest state
  of each fact; turbopuffer upserts the changed facts. A superseded fact is updated with its status and end date, never
  deleted, so as-of search works downstream. `--full` rebuilds an export from scratch. (Kyle, 2026-11-18)
- **Parquet tables:** `facts`, `entities`, `documents`, and `events`. A `facts` row holds the fact's own fields, with
  its mentions (entity id, role, and the text as written) and its quotes (document id, section, and quoted text) as
  nested list columns, not tables of their own. (Kyle, 2026-11-18)
- **Vectors in Parquet:** left out by default; an option includes each fact's vector. When included, `facts` gets a
  `vector` column (a list of 32-bit floats) and an `embedding_model` column naming the model that made it. Warehouses
  read the list as an array without a custom parser; Snowflake needs one cast to `VECTOR(FLOAT, N)`. (Kyle, 2026-11-18)
- **Setting up and running exports:** a project declares its exports by name in `settings.py`, such as `exports =
  {"warehouse": Parquet("s3://bucket/path/"), "search": Turbopuffer(namespace="facts")}`. `factoid export` runs every
  export, `factoid export <name>` runs one, and `--full` rebuilds one from scratch. Each export keeps its own cursor in
  the store, so one that falls behind holds up no other. Credentials come from the environment, never from
  `settings.py`. (Kyle, 2026-11-18)
- **Turbopuffer export rows:** one row per fact, keyed by the fact's id, with its vector and the attributes `text`,
  `class`, `traits`, `status`, `valid_from`, `valid_until`, `document_id`, and `entity_ids`. `text` has a BM25 index for
  hybrid search. Entities, documents, and quotes stay out; apps join them from Parquet or Factoid's API.
  (Kyle, 2026-11-18)
- **When exports run:** only on `factoid export` by default. `export_after_ingest = True` in `settings.py` runs them
  after each ingest; a failed export then warns and does not fail the ingest, and the next run catches up from the
  cursor.
  (Kyle, 2026-11-18)
- **Names:** these were first called sinks, run by `factoid sync`. Kyle renamed them because "sink" and "sync" sound
  too alike: `exports` in `settings.py`, `factoid export`, `export_after_ingest`, and the module `factoid.exports`.

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
  - A provider can set a base URL (`<PROVIDER>_BASE_URL`) and run with no key, for gateways that add credentials
    themselves. The framework knows no gateway by name (decision 83).
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
on.

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

**Decided** (Kyle, 2026-11-17). The docs from the single-YAML design (`mental-model.md`, `documents.md`, `facts.md`,
`config.md`, `plugins.md`, `evals.md`, `api.md`, and `open-questions.md`) moved to `docs/archive/`, with a note that
the code no longer follows them. `docs/` keeps `cli.md` (current) and `research/`. `docs/prior-art.md` and the CRM
note, which described internal Endgame systems, were removed on 2026-11-18 (decision 88).
The README's "Further reading" points at SPEC.md, `docs/cli.md`, and the example apps.

- README.md uses the legal example (Acme buying Orion, and Orion's supply agreement with Vega), and is checked against
  the code by a cold-start onboarding review (the last one on 2026-11-17).

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
  `prompts show`, `keys set`, `keys list`, `models`, `doctor`, and `eval`), the eval harness with `--vary`, and three
  decision models for `choose`: Jev, Fireworks' Rune, and OpenAI's Decisions API.
- **Search backend:** with no `search` setting, a project uses `LocalIndex`, a SQLite file with FTS5 for BM25 and
  exact vector search. `Turbopuffer` is built and used when set, and is optional. Decision 23 said a project needs
  turbopuffer; the local index replaced that, so tests and small projects work without it.
- **`Nli`** is in the default chain but no NLI model is wired up yet. With none set, it is skipped: `factoid eval`
  prints how many facts it skipped and `scorecard.json` has `skipped_fact_evals`. So the working default chain is
  `DecisionFloors`. The README marks it planned, and its Quickstart compares `none` and `decision_floors`.
- **Starting floors** for `DecisionFloors` are fixed values until calibration is built: grounded 0.45, attribution 0.3,
  self-contained 0.4, atomic 0.25, useful 0.45, and distinct 0.2. They were set from CUAD runs (2026-11-15). The
  first values (0.45 to 0.6) rejected most good facts; with these, and the grounded and attribution questions narrowed
  to the claim, the share of gold clauses quoted by a kept fact went from 0.61 to 0.96 on 20 contracts.
- **Structured documents** (2026-11-16): `StructuredDocument` with `Identity`, `Property`, template strings, `Text`,
  and `Ignore` columns; CSV, TSV, JSONL, JSON arrays, and `from_records`. Choices the spec left open:
  - A templated cell's fact skips the fact evals and resolve, since no model wrote it. A class that reports a
    changing state row by row (a series score after each game) sets `resolve_cells = True`, and its cell facts then
    go through resolve like extracted ones. It still runs classify,
    validate, and assess, so it gets traits and time properties. Its quote is the cell: the row number as the
    passage, the column as the section, and the row's span in the file.
  - The row key and column are kept in the fact's `scores["cell"]`, which is how a re-import finds the fact to
    supersede. An unchanged cell counts as a duplicate. A row missing from a re-import leaves its facts as they are;
    whether it should end them is Open.
  - Without `key`, a re-import retracts the document's facts and starts over, as for prose.
  - `Identity` looks the key up first. A new key joins the one entity of that class whose own name is exactly the
    cell's name (a company already found in a contract's text), with no model call; otherwise it creates the entity
    and runs `claim`, as linking does. `name=` is a template for that name. An alias match alone does not join, as
    in linking.
  - A `Text` cell is extracted alone, as its own chunk, with the row's identified entities in the extractor's
    context, and its facts get the row's entity as subject. Those facts take the full prose path.
  - A file matches a class when its header has every mapped column plus `key` and `when`. When several match, the
    class with the most columns wins; a tie goes to the decision model.
  - A row's date must carry a timezone, like every date in Factoid; `row_datetime` is the step to override for
    other formats.
  - A templated fact mentions the row's entity as subject, and each other identity the sentence names: its own
    column, or a column its `name=` template uses (a company identified by email and named by `{counterparty}`).
  - `factoid struct inspect` and `try` call no model. `inspect` guesses each column's role by rules (email, URL, and
    domain columns and unique ids are identities, long text is `Text()`, dates are `when`) and prints a starting
    class. `try` links identities in a throwaway store and prints each templated sentence with its file, row, and
    column; text cells are listed, since only extraction reads them. `parser` adds the model's class to the
    package's `documents.py` (or `--out`), and `--prompt` prints the prompt instead. On a contract register, the
    model's class used the legal app's `Agreement` and `Company` and a `name=` template without being told.
- **A replaced fact held until it was replaced** (2026-11-16). A superseded or ended fact is fully valid from
  `valid_from` to `valid_until`, with no lifetime decay inside that window: the replacement is the evidence it held
  that long. Before, a series standing with a lifetime of about a day scored 0.23 a day and a half in, though nothing
  had replaced it yet, and as-of search ranked it below other facts.
- **Speaker labels** (2026-11-16): `ProseDocument.speaker_pattern` is a regular expression for a speaker label at
  the start of a paragraph ("Q.", "STEPHEN CURRY:"). The label moves out of the passage text into `speaker`, and the
  paragraphs after it keep that speaker. It is how a transcript class fills in passage speakers without overriding
  `segment`, toward the built-in transcript class the spec plans. Off by default.
- **Fact eval tuning** (2026-11-17, decisions 73 to 77). Tuned on the first 30 ISC-RAG dev transcripts, checked on
  all 100 and on the legal and NBA apps. On the 100 transcripts, facts answered 0.925, 0.965, and 0.955 of 200
  questions at 512, 2,048, and 8,192 tokens (0.885, 0.915, and 0.92 before), and an independent model (Kimi K3.1
  Pro) flagged 14% of 450 sampled facts for an unresolved reference (25% before). Of those, about a third are as
  specific as the source allows ("Anna", "an unidentified man"), and about a third a better repair could resolve. NBA:
  11 of 11 checks, 4.7% unresolved (6.7%). CUAD 1 to 20: F1 0.81, dates 16/18, 13/14, and 8/9. Amendments: 15 of 16
  supersessions and 34 of 36 as-of answers. What was tried and dropped: a strict self-contained floor of 0.4 or 0.5
  (it threw away useful facts whose repair failed: 47 of 60 against 56), 2,400 characters of context (no gain), and
  more reasoning for repair (no gain). An extract prompt line telling the extractor not to repeat the document's date
  also stopped "The agreement is dated ..." facts (CUAD agreement dates 13/18) until it was reworded. Repair first
  lists each unclear reference and what the text says it means, then rewrites (11.6% against 15.3% unresolved on the
  30 tuning transcripts; even on all 100). Cost rose: about half the kept transcript facts are repairs, and a dev run
  with nothing replayed uses about 40 million tokens (21 million before).
- **Amendment supersession varies between runs** by one or two per suite with the same code, through extraction
  wording that resolve then does or does not connect (ScanSource's term extension). Open: a resolve that is stable
  to wording.
- **First install, by a new user** (2026-11-17). Fixed: `factoid models` and `doctor` work outside a project (they
  show the defaults); `keys set` checks a pasted key for control characters and the provider's prefix; with no key,
  an unreachable exe.dev integration host fails at once with an error naming the key to set (it was retried for
  minutes as a network error); the README installs from GitHub, says a TypeSafe key is needed for `choose`, says the
  local index needs no service, and marks `factoid setup` as planned. Still true: Factoid is not on PyPI.
- **First install, second pass** (2026-11-17). Fixed:
  - A file that ended in a newline lost its last paragraph: the paragraph pattern needed `\Z` right after the last
    non-space character. The sample contract's liability cap was never extracted, so the sample eval failed.
  - An exe.dev integration host off exe.dev resolves to an address that never answers, so the connection timed out
    instead of failing, and each call was retried 12 times at 180 seconds. A connect timeout now counts as an
    unreachable host, the connect timeout is 10 seconds, and later calls to that host fail at once. Only a host that
    has not answered yet counts: a connect error from one that has answered is a blip and is retried. Before that
    fix, one blip 50 minutes into a legal eval on exe.dev stopped the run with "no FIREWORKS_API_KEY is set".
  - `factoid init` writes a `[tool.uv.sources]` entry for the GitHub repository, so `uv sync` and `uv run` work in a
    new project.
  - `factoid keys set` with no provider asks for each key the project's models need and links to the page that
    creates it; `factoid keys list` shows every provider's key, its source, and its use. (TypeSafe's waitlist was named
    until 2026-11-18; the console now lets anyone sign up and create a key.)
  - "One provider key is enough to start" (section 9) is true with `--models openai`. `--models fireworks` is
    experimental: Rune keeps no facts on the sample contract, because it scores correct facts low on the attribution
    question (0.09 and 0.56 against Jev's 0.71 and 0.72) and cannot tell them from wrong ones. Fixed the same day
    (decision 81): with its own floors and the reworded attribution question, Rune keeps all three sample facts and
    the sample eval scores 1.0. The legal suites on Rune ran on 2026-11-18 (decision 92).
  - Resolve settings per decision model (`MODEL_RESOLVE`): `resolve_batch` (stored facts per request) and
    `resolve_verify` (a yes-or-no check on each supersession, end, or correction, which drops it below the bar). Rune
    gets `resolve_verify = 0.5` (decision 94). `--vary` reads `none` as None.
  - OpenAI generation sends `max_completion_tokens` and no `temperature`, which its reasoning models require.
  - The README marks `serve`, `mcp`, `rebuild`, and `contradictions` as planned.
  - Checked live on 2026-11-17: Rune answers under both `models/rune` and `routers/rune`; the Decisions API answers
    noul, choice, and score questions; `gpt-6-luna` generates with `max_completion_tokens`; and
    `text-embedding-3-small` returns 1,536 dimensions. `doctor` passes on both one-provider presets, and the sample
    eval scores 1.0 with `--models openai`.
- **From a first-run walkthrough (2026-11-17, version 0.1.1).** A new user ran the Quickstart twice, before and after
  the first-install fixes. What changed from it:
  - Re-ingesting an unchanged document (same text, class, and metadata) skips it; `--again` ingests it anyway. Before,
    every fact was retracted and re-added under a new id. The document's hash is saved only when its ingest finishes,
    so a run that fails halfway (a missing key, a timeout, or Ctrl+C) is ingested again next time.
  - Re-ingesting a changed document still retracts its facts, and a new fact that says the same thing takes the old
    id (event `fact.restored`): the same sentence, or the same traits, a shared quote, and embeddings at least 0.85
    alike (`Factoid.reuse_similarity`). Extraction rewords a sentence from run to run, so the same-sentence rule alone
    kept 2 of 6 ids on the sample after an edit; with embeddings it kept all 6. This is what `docs/archive/documents.md`
    promised; resolve against the old revision is still the longer-term plan.
  - `ingest` and `eval` say in words how many calls were replayed from `.factoid/calls.db`, and that `--fresh` calls
    the models again. `ingest` has `--fresh` too. The cache records which Factoid (version and commit) saved each
    answer, and the output says when replayed answers came from a different one.
  - `factoid --version` prints the commit (`0.1.1 (commit cb9aeb5)`), from the install record or the checkout.
  - New `factoid facts list` (by document, trait, and status). `facts list`, `search`, `read`, and `entities list`
    take `--data-dir`, so an eval run's store can be read.
  - `read` says how "still valid now" was worked out and prints event times in local time; `entities list` shows
    aliases; `search` says its score is a fused rank times validity; `stats --examples` says it picks one fact per
    document. Eval run folders are named in local time.
  - `docs/cli.md` describes the built commands, and the Quickstart says where fact ids come from and how the cache
    works.
- **From a cold-start onboarding review (2026-11-17).** Carbon, given only the repository, followed the Quickstart as a
  new user and toured the code as a new agent. What changed from it:
  - `--models openai` failed its first ingest: the sample `Contract` said "a signed contract", the sample has no
    signature block, and the classifier did not see the `.meta.json` metadata, so `gpt-6-luna` answered 0.01 to "is
    this one of these kinds". The sample says "a contract, an agreement, or an amendment", the classifier sees the
    metadata, and the sample eval yields a `Raw` document so it classifies the way `ingest` does. Checked live: all
    three presets ingest the sample and score 1.0 on `factoid eval --fresh`.
  - Ki's first-run passes on 897e408 (2026-11-18). In the `jev` preset, the extraction model (`glm-5p3-flash`)
    folded the signing date into the other two sample facts in 5 of 7 fresh runs, which left 2 facts, and the sample
    eval still scored 1.0 because it checked only traits. The sample eval now scores three facts: the signing (a fact
    with no trait that names March 1, 2025), the consent clause, and the cap. On a replay of a 2-fact run it scores
    recall 0.67. `factoid init --models <preset>` in an existing project switches the models block in `settings.py`
    when it matches a preset, and otherwise prints the lines to use. `factoid keys set` with no terminal says to run
    it in a terminal or pipe the key in, instead of "Aborted!". `stats --examples N` fills up to N facts from the same
    documents when there are fewer than N documents. The README's Quickstart leads with `factoid init` (jev), says
    an eval never reads the project's store, and no longer calls the repository private. Not bugs: `gpt-6-luna` rates
    the consent fact's lifetime shorter than Jev ("still valid now" 0.55 to 0.63, against 0.79 to 0.81), and the
    agreement entity's name follows how the extraction model wrote it.
  - Exports (first called sinks) are built (decisions 93 to 103), in `src/factoid/exports.py`, with `factoid export
    [name] [--full]` and `export_after_ingest`. Cursors live in an `export_cursors` table in the store. The event log
    now also records `document.saved`, `entity.aliased`, and `fact.updated` (set by `set_fields`, as when a supersession
    sets an end date), so every change an export needs is an event. Choices made while building, not decided by Kyle:
    Parquet writes one file per table per run, named `<from>-<to>.parquet` by event number, and each entity, document,
    and fact row has `exported_through`, so the current version of a row is the one with the highest; `--full` deletes
    the files this export wrote and writes everything again. pyarrow is an optional extra, `factoid[parquet]`. A
    relative Parquet path is under the project folder, and S3-compatible stores use `AWS_ENDPOINT_URL`. The turbopuffer
    export's `--full` deletes its namespace. Vectors come from the project's index (`Index.vectors`), and a fact the
    index does not hold is embedded. Checked on 2026-11-18 with a CUAD run's store (4,069 facts, 400 entities, 20
    documents, and 15,424 events): local Parquet with vectors in 2.2 seconds (27 MB of facts), DuckDB read the nested
    mentions and ran cosine search on the vectors, R2 took the files in 7 seconds and `--full` replaced them, and a
    turbopuffer namespace took all 4,069 rows in 28 seconds and answered BM25, status, and count queries. In a
    turbopuffer filter, a fact with no `valid_from` matches `valid_from < date`.
  - Ki's passes 10 to 12 on 7bca4fe (2026-11-18). `keys set` with no terminal reads a piped key directly instead of
    through getpass, so Python's "input may be echoed" warning is gone. `factoid init` in a project writes back any
    deleted sample file and never overwrites one, so an older project gets the current sample eval by deleting
    `evals/sample.py` and running `factoid init`. The eval's "fact eval skipped on N facts" line counts facts when
    they are saved, so a candidate that a repair replaced is not counted too. Section 7, section 11, and decision 39
    now say the entities namespace lives in whichever index the project uses.
  - Expected failures (`ModelError`, `DateError`, `ClassificationError`, `ExtractionError`, and `UnclaimedDocument`)
    print one line; `FACTOID_DEBUG=1` shows the traceback. An unclaimed file in a folder is skipped and listed.
  - Per-project keys are built as decided (decision 85): `factoid init` writes `id = "<package>-<8 hex>"` under
    `[tool.factoid]`, and `keys set --project` stores keys at `~/.factoid/projects/<id>/.env` (folder 0700, file
    0600), giving a project without an id one. Precedence: a real environment variable, the project's keys, an old
    in-project `.factoid/.env` (still read; the next `keys set --project` moves it out and deletes it, and `keys list`
    points at it), and then `~/.factoid/.env`.
  - `--vary` refuses a string that would replace a method (`--vary classify=decision` replaced `classify` with a
    string). The README's strategy example is replaced by `@module:NAME` values.
  - `Chunk.search(query, about=...)` exists, as the README showed. Searching facts and chunks in one list is planned.
  - The README documents `.meta.json` sidecars, eval suites (`Suite`, `prf`, and `aupr`), and marks `nli`, entity
    editing, and `entities retype` as planned. Its examples read metadata with `.get`.
  - `factoid init` installs Factoid from where `factoid` came from: the local checkout for an editable install, or
    GitHub pinned at the installed commit. Before, a project made from a checkout installed GitHub's main.
  - `pyproject.toml` has ruff settings, and `src`, `tests`, and `examples` pass. `AGENTS.md` has a Develop section:
    the commands, a module map, and a warning that example evals cost money.
- **Not built yet:** sources (`imap`, `mcp`), MCP and
  HTTP serving, `factoid setup`, fact-class trust and visibility, entity `merge`, `split`, and `retype` commands,
  and fingerprint-driven `rebuild`.
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
- **Search** weighs the best `search_candidates` hybrid matches (a `Settings` value, 150 by default) for freshness,
  then reranks them. It was 50, fixed (2026-11-16). A fact that names its document only by a short name ("the
  Financing Agreement as amended") ranked below a hundred sibling facts that name it in full, and never reached the
  reranker, which scored it 0.99. On the 36 as-of questions, 150 against 50: as-of search 34 against 33, facts
  answers 33 against 32 at 2k tokens and 32 against 33 at 8k, and outdated answers 2 against 3. That is within noise;
  150 is kept for the reason above, and the setting lets a project trade it for fewer rerank calls.
- **Sections:** passages and quotes carry section labels, and a section replaced in its entirety retires the older
  facts quoting it (see "Sections and replaced sections").
- **First try at replaced sections, removed** (2026-11-15): the extractor flagged which facts replace sections. It
  flagged the new section's facts instead of the instruction, so it missed, and a linking error (below) spread its
  changes across unrelated contracts. The current version finds the instruction with code instead.
- **Generic defined terms stay local.** An alias becomes an entity's alias only when the placeholder question says
  it is a specific name. Before, "Agreement" and "Amendment" from one contract became global aliases, and mentions
  in an unrelated contract linked to them, which led resolve to supersede facts across contracts.
- **A short alias alone does not link** (2026-11-16). Store-wide, a mention links on its own name; when only one of
  its aliases matches, the entity becomes a candidate for the yes-or-no question instead. "Amendment No. 3" passed
  the specific-name check, so a ScanSource amendment's facts linked to the Glu contract's Amendment No. 3. This
  follows "name and aliases (weak)" in the entity section. No suite moved (CUAD F1 0.81, every amendment suite
  unchanged). The ScanSource term extension is still missed: resolve gives "supersedes" about 0.6 against the
  two-year term, which says "unless extended", so the answer falls either side of the bar from run to run. Not
  tuned, since that chain is held out.
- **Claimed facts are indexed under the new entity** (2026-11-16). `claim` linked older facts to a new entity in
  the store but not in the search index, so `related_facts` never offered them to resolve. An extension could not
  supersede the date it extended when only the claim connected the two.
- **Repair sees the document** (2026-11-16): its title and `context()`, as the extractor does. A cited sentence like
  "The Purchase Expiration Date is extended to March 26, 2006" names no parties, so a fact failing self-contained
  could not be repaired from the passage alone, and was dropped.
- **Term extensions** (2026-11-16). Tuned on a new dev chain (`extensions_dev`: Navistar's certificate purchase
  agreement, five extensions from 2003 to 2007), not on the held-out chains: supersessions went from 2 of 4 to 4 of
  4, with no false changes. Then the held-out chains were scored once: fresh supersessions 3 of 4 (was 2 of 4; the
  ScanSource inventory claim window is now kept and superseded), NEON 2 of 2, SEC 4 of 4, CUAD F1 0.80 on contracts 1
  to 20 (0.81 before, within noise), and the sample deal 12 of 12. The one fresh miss left is the ScanSource term
  extension, still near resolve's bar.
- **Against plain RAG** (2026-11-16). The as-of questions of every chain, answered by one reader from facts and from
  plain hybrid search over 2,000-character windows, graded by one judge: on the 12 held-out questions, facts 11 at
  both 2k and 8k tokens of sources, chunks 7 and 10. Facts gave no outdated answer; chunks gave 2 of 17 at each
  budget. Details in `examples/legal/README.md`.
- **Against plain RAG, 36 questions** (2026-11-16): 19 more questions, labeled before any run. All 36: facts 33 and
  32 at 2k and 8k tokens, chunks 20 and 33; outdated answers 1 and 1 against 4 and 2. Facts win at small budgets;
  at 8k, chunks match them on accuracy. After full validity for replaced facts (below), facts are 33 and 34. One
  outdated fact answer comes from a fact that names its document only by a short name ("the Financing Agreement as amended"), so search matches the base clause it replaced. Indexing
  each fact with its document title fixed that question in a trial, but resolve shares the facts index, so it was not
  adopted without a full rerun. Kept as is for v1 (Kyle, 2026-11-16; decision 71).
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
- **Known limits** (2026-11-16), for the next round of design, not fixed in v1:
  - **End dates inside a schedule.** A fact holds one `valid_from` and one `valid_until`, so a clause that sets
    different values for different periods keeps one of its dates. Accepted for v1 (decision 69): the one try at
    splitting such clauses cost more than it fixed. Facts with several periods are a v2 design question.
  - **Restructured rewrites.** When an amendment rewrites a section and reorganizes it, `resolve` sees no single new
    fact replacing an old one. Replaced sections cover this only where the app sets the wording.
- **Held-out check** (2026-11-15). The values above were tuned on CUAD contracts 1 to 20 and three amendment
  chains. On CUAD contracts 21 to 40, never looked at while tuning, clause F1 was 0.85 (0.82 on the tuning set),
  coverage 0.93 (0.95), and expiration dates 5 of 5. On a held-out amendment chain, as-of search was 2 of 2 and
  supersession 1 of 2. Details are in `examples/legal/README.md`.
- **Not on PyPI yet:** `uv tool install factoid` does not work until a release is published. Install from the repo.
- **Keys:** a call needs the provider's key or its base URL (`<PROVIDER>_BASE_URL`, for a gateway that adds
  credentials). With neither, it fails at once and names both. The key is sent whenever it is set. The code names no
  hosting platform or gateway (decision 83): a machine behind one sets the base URLs in `~/.factoid/.env`.

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
    turbopuffer-compatible endpoint for search. (Superseded for search: a project with no `search` setting uses the
    built-in `LocalIndex`, and turbopuffer is optional. See section 17.)
24. Judges are renamed fact evals (`FactEval`).
25. Five levels of customization. Decision steps are worded as questions, and generation steps as prompts.
26. Current state is the source of truth. The event log is kept for audit and provenance, and is not replayed.

27. SQLite in v1 has one writer per process, with WAL mode on. Many writers or hosting means a Postgres backend later.
28. `FactoidDocument` splits into `FactoidProseDocument` and `FactoidStructuredDocument`. A structured parser is a
    Python class with a column map. Factoid can write it with a model, or print the prompt for any coding agent, and it
    has a dry run.
29. MIT license for Factoid and prosaic.
30. prosaic is a separate library and a dependency of Factoid.
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
    namespace in turbopuffer for search and linking. (Superseded in part: the entities namespace lives in whichever
    index the project uses, `LocalIndex` by default; see section 7.)
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
68. Replaced sections are built and kept: the framework holds the mechanism (`replacements`, `Replacement`, and three
    pattern settings) and ships no wording; the legal app's `Contract` sets the contract wording ("in its
    entirety"). (2026-11-16)
69. End dates inside a schedule are a known v1 limit, not fixed by splitting a clause into one fact per period.
    (2026-11-16)
70. Search reranks a pool of `search_candidates` hybrid matches, a `Settings` value, 150 by default (was a fixed 50).
    (2026-11-16)
71. Facts that name their document only by a short name are a known v1 limit: no stricter self-contained check and
    no title-aware index for now. (Kyle, 2026-11-16)
72. Structured documents are part of Factoid. There is no separate prosaic library; this reverses 30. (Kyle,
    2026-11-16)
73. How facts are written and checked is set per document class too: `guidance`, `extract_prompt`,
    `repair_prompt`, `fact_evals`, and `evidence_context` live on `Document`, so prose and structured documents share
    them. A document class's `fact_evals` wins over the fact class's. (2026-11-17)
74. `DecisionFloors` questions can be reworded, added, or dropped (`questions={...}`), and can have targets above their
    floors: below a target a fact gets one repair, kept only if it scores higher. (2026-11-17)
75. The fact evals and repair see the 1,200 characters before a fact's first cited passage. A fact that fails only
    repairable questions always gets one repair. (2026-11-17)
76. Default `self_contained`: a strict question (pronouns, unclear descriptions, and relative dates) with floor 0.1
    and target 0.5, replacing a lenient question with floor 0.4. Chosen on 30 ISC-RAG dev transcripts against five
    other wordings and floors. (2026-11-17)
77. `--vary` values can name a project object, `@module:name`. (2026-11-17)
78. Until Factoid is on PyPI, the README installs it from GitHub. Without a key, a call to an unreachable exe.dev
    integration host fails at once and names the key to set. (2026-11-17)
79. A project can run on one provider: `factoid init --models jev|fireworks|openai`. Fireworks' Rune and OpenAI's
    Decisions API serve `choose` beside Jev, which stays the default. Providers list the workloads they serve, and
    `factoid keys set` with no provider walks the keys a project needs. (2026-11-17)
80. The `fireworks` preset is experimental until Rune has its own fact eval questions or floors: with the floors set on
    Jev, Rune rejects every fact on the sample contract. `--models openai` is the one-key path, and the README's
    examples use it. (2026-11-17)
81. `JevFloors` is renamed `DecisionFloors` (`decision_floors`): code names the kind of model, not a vendor's model.
    Floors and targets can be set per decision model (`MODEL_FLOORS`, `MODEL_TARGETS`), and a project's own floors
    win. Rune has its own floors, and the attribution question is reworded so that a fact needs no speaker when its
    passage has none. The `fireworks` preset stays experimental until the legal suites pass on Rune. (2026-11-17)
82. Ingest skips a document that is stored with the same text, class, and metadata (`--again` overrides), and a
    re-ingested document's facts keep their ids when a new fact says the same thing. Replayed model calls are named
    as replays in the output, with `--fresh` beside them, and the cache records which Factoid saved each answer.
    (2026-11-17)
83. The framework code knows nothing about exe.dev or any other hosting platform (Kyle, 2026-11-17). Providers default
    to the vendor's API. A gateway that adds credentials is configured with `<PROVIDER>_BASE_URL` (and
    `TURBOPUFFER_BASE_URL`), in the environment or a `.env` file, and then no key is needed. A call with neither a key
    nor a base URL fails before any request. A host that never answers fails at once with its address; one that has
    answered before is retried. Replaces the integration-host defaults of decision 78. (2026-11-17)
84. The design docs from the single-YAML design move to `docs/archive/`, and the README points at SPEC.md,
    `docs/cli.md`, and the example apps. Fixes from a cold-start onboarding review: the sample classifies on every
    preset, expected errors print one line, project keys beat home keys, `--vary` cannot replace a method with a
    string, `Chunk.search` exists, and `factoid init` installs Factoid from where it came from. (2026-11-17)
85. Per-project keys are stored as decided in section 12: at `~/.factoid/projects/<id>/.env`, named by an `id` in the
    project's `pyproject.toml` that `factoid init` writes and the project commits. Keys stored inside a project by
    0.1.1 and earlier are still read, and the next `keys set --project` moves them out. (Kyle, 2026-11-17)
86. Data warehouses (BigQuery, Snowflake) are sources and export targets, never the system of record or the search
    index, which take ingest's many small reads and writes. Next storage work: the `Store` and `Index` interfaces,
    then Postgres, then warehouse export, then warehouse sources. (Kyle, 2026-11-18)
87. Retrying extraction after a rejection, with the rejected fact and the reason as context, is approved as an
    experiment, starting with "grounded" failures; it ships only if an eval shows it helps. (Kyle, 2026-11-18)
88. The repo does not describe Endgame's internal systems. `docs/prior-art.md` and the archived CRM note are removed,
    and SPEC names no internal system or private repository; it says "earlier internal fact systems" where a lesson came
    from one. Git history is not rewritten: older commits may mention those systems, which is acceptable as long as
    nothing in history is dangerous. gitleaks over all 240 commits, the pull request included, found no leaks.
    (Kyle, 2026-11-18)
89. TypeSafe keys are self-serve (checked 2026-11-18: the console offers sign-up with Google or email, and the quick
    start says to create a key there). The waitlist wording is gone, `jev` stays the default preset, and `keys set`
    links to `https://console.typesafe.ai/keys`. (Kyle, 2026-11-18)
90. Factoid is published to PyPI as `factoid` from the Endgame PyPI account (the name was free on 2026-11-18).
    Publishing a GitHub release runs `.github/workflows/release.yml`: one job checks that the tag matches the version,
    runs the tests, and builds with `uv build`; a second job in the `pypi` environment publishes through PyPI trusted
    publishing, so no token is stored. Tests and ruff run on every push to main. The sdist holds the library, its
    tests, the README, the license, and `pyproject.toml` only. A project made by a PyPI install depends on
    `factoid>=<version>` with no uv source; one made from a checkout or a git install points at that. The PyPI
    account is `endgame-labs`, and its trusted publisher for this repo is set up. Nothing is released until Kyle says
    so; until then, install from GitHub. (Kyle, 2026-11-18)
91. The repository is public as of 2026-11-18. Before the switch, gitleaks found no leaks in the 242 commits or the
    working tree, and no `.env` or `.local` file is tracked. GitHub secret scanning and push protection are on. (Kyle,
    2026-11-18)
92. The `fireworks` preset stays experimental after the legal suites on Rune (2026-11-18, every legal suite, with Jev's
    numbers from 2026-11-17 in brackets). Even or close: sample deal 15/15 (15/15), supersessions 15/16 (15/16), as-of
    search 33/36 (34/36), and questions answered from facts 34 and 33 of 36 at 2k and 8k tokens (33, 34). Worse: CUAD
    clause F1 0.79, 0.80, and 0.79 on tuning, held-out, and fresh (0.81, 0.84, 0.81), with recall at 0.97 and lower
    precision (0.67), mean AUPR 0.93 (0.95 to 0.97), untouched clauses kept 7/9 (9/9), and false changes to base facts
    4.5%, 7.8%, 7.7%, and 3.8% on tuning, NEON, fresh, and SEC (2.6%, 5.9%, 4.0%, 1.0%). Rune keeps more facts than
    it should and replaces base facts too readily. Next step, when wanted: floors for Rune's change and resolve
    decisions, tuned on the tuning chains and checked on the fresh and SEC chains.
93. Facts leave Factoid through sinks. Two are standard: Parquet files in a local folder or an S3 bucket, and a
    turbopuffer-compatible API. Warehouses load the Parquet files themselves; native warehouse sinks may come later.
    (Kyle, 2026-11-18)
94. Rune's false changes to base facts come from resolve: it calls a stored fact "superseded" when the fact only
    refers to what changed (an appointment "within the Territory" when the Territory changed, or one signing's parties
    when a later amendment is signed), at 0.57 to 0.95, where real supersessions also fall, so no floor separates them.
    Reworded answers moved the errors between chains. A second question on each change ("does the stored fact itself
    state the term the new fact sets differently?") fixes most of it; Rune gets it at 0.5 (`MODEL_RESOLVE`), chosen on
    the tuning chains. Comparing one stored fact per request did not help end to end and is off. Held-out chains, run
    once, with Jev in brackets: false changes 5.0%, 5.9%, and 2.4% on NEON, fresh, and SEC (5.9%, 4.0%, 1.0%; before
    the check 7.8%, 7.7%, and 3.8%); tuning chains 0.5% (2.6%). Supersessions 14/16 (15/16), as-of 32/36 (34/36),
    sample deal 15/15, untouched clauses kept 7/9 (9/9). CUAD on the same 20-contract slices as Jev (tuning, held out,
    fresh): F1 0.79, 0.82, and 0.79 (0.81, 0.84, 0.81), mean AUPR 0.97, 0.93, and 0.92 (0.97, 0.97, 0.95). Decision 92
    compared Rune on all contracts past each offset with Jev on 20 and overstated the F1 gap. The `fireworks`
    preset stays experimental until Kyle decides. (2026-11-18)
95. A sink receives changes since its cursor (the last event it sent), read from the event log; `--full` rebuilds it.
    A superseded fact is updated, never deleted. (Kyle, 2026-11-18)
96. The Parquet sink writes `facts`, `entities`, `documents`, and `events`. Mentions and quotes are nested list columns
    in `facts`. (Kyle, 2026-11-18)
97. The Parquet sink leaves vectors out by default; an option includes them. (Kyle, 2026-11-18)
98. When vectors are included, `facts` gets `vector` (a list of 32-bit floats) and `embedding_model`. (Kyle,
    2026-11-18)
99. Fixes from Ki's first-run report: the sample eval scores all three sample facts, `factoid init --models` switches an
    existing project's preset, and `keys set` explains what to do without a terminal. Decision 23's turbopuffer
    requirement is marked superseded. (Kyle, 2026-11-18)
100. Sinks are declared by name in `settings.py` and run with `factoid sync [name] [--full]`. Each keeps its own cursor,
     and credentials come from the environment. (Kyle, 2026-11-18)
101. The turbopuffer sink writes one row per fact: its vector, `text` (with BM25), `class`, `traits`, `status`,
     `valid_from`, `valid_until`, `document_id`, and `entity_ids`. (Kyle, 2026-11-18)
102. Sinks run on `factoid sync`. `sync_after_ingest = True` syncs after each ingest, and a failed sync there only
     warns. (Kyle, 2026-11-18)
103. Sinks are renamed exports, because "sink" and "sync" sound too alike: `exports` in `settings.py`,
     `factoid export [name] [--full]`, and `export_after_ingest`. Decisions 93 to 102 keep their old wording.
     (Kyle, 2026-11-18)
