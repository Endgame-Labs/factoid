# Factoid 📚

> **Status: Design draft.** Nothing is built yet. These docs will settle the v1 design before we write code.

Factoid turns `Documents` into `Facts`.  A fact is a short, self-contained sentence, devoid of filler and explicit in its language (no pronouns, etc).
Each fact is tied to an exact location in the source document.
As new documents arrive, Factoid updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree.

It also extracts `Entities` from these documents, creating links between a given fact and the entities it affects.

Factoid is designed as a development framework. This makes it fully configurable, meaning you can map it to any domain
by extending the `Document`, `Fact`, and `Entity` base classes.

People, agents, and data pipelines can access these facts through a CLI, an HTTP API, and over MCP. This includes semantic,
bm25, and hybrid-reranked search.


## Quickstart

### Install

Factoid requires Python 3.13 or newer. You can install the `factoid` CLI in two ways.

Install with `uv`:

```sh
uv tool install factoid
```

Or run the install script, which installs `uv` if `uv` is missing and then installs Factoid:

```sh
curl -fsSL https://raw.githubusercontent.com/Endgame-Labs/factoid/main/install.sh | bash
```

Both methods put `factoid` on your `PATH`. Inside a project directory, `factoid` runs in that project's environment
without `uv run` or manual virtual environment activation.

### Setup

Factoid uses models for four kinds of work, and the fourth is optional:

| Workload | Kind of model | Used for |
| --- | --- | --- |
| `choose` | Decision model | Classifying, evaluating facts, assessing, linking, and resolving |
| `generate` | Generative model | Extracting facts and describing chunks |
| `embed` | Embedding model | Search |
| `rerank` | Reranking model (optional) | Reordering search results |

API keys belong to providers, and one provider can serve several workloads. One provider key is enough to start when
that provider offers all three required kinds of model. Fireworks and OpenAI both offer all three. Without a `rerank`
model, search returns results in their retrieval order. For the `choose` workload, Factoid recommends Jev from
TypeSafe. Jev is the best decision model and is cheap. Other decision models work too: OpenAI's decisions API,
Fireworks' Rune, and Cloudflare's Clef.

Factoid also needs a search index: turbopuffer, or any service with a turbopuffer-compatible API. Set its key the same
way, and choose a compatible service by setting its base URL in `settings.py`.

```sh
factoid keys set turbopuffer  # the search index
```

Guided setup is available as a terminal UI. The terminal UI adds providers, checks each key, and lets you pick a model
for each workload from the providers you have:

```sh
factoid setup
```

To do the same steps by hand, store keys and verify your setup with these commands:

```sh
factoid keys set fireworks    # one provider is enough to start
factoid keys set typesafe     # optional: Jev, the recommended decision model
factoid models                # each workload, its model, and whether its key works
factoid doctor                # makes one small call per workload and reports what works
```

The `factoid keys set` command prompts for the key and stores that key in `~/.factoid/.env`. Pass `--project` to store
the key for the current project only. An environment variable with the standard provider name, such as
`FIREWORKS_API_KEY`, takes precedence when that variable is set.

The `factoid models` command shows which model runs each workload. Here is the output with only a Fireworks key set.
`fireworks/rune` is Fireworks' decision model:

```text
workload   model                         key
choose     fireworks/rune                ok
generate   fireworks/glm-5p3-flash       ok
embed      fireworks/qwen3-embedding-8b  ok
rerank     fireworks/qwen3-reranker-8b   ok
```

Running `factoid keys set typesafe` moves `choose` to `typesafe/jev-1.13.0`, and the other workloads stay on Fireworks.

Every model name uses the `provider/model` format, so Factoid knows which provider key a workload needs and names the
missing key when that key is not set. Workload assignments live in the project's `settings.py` file. Edit `settings.py`
to change a model. Because `settings.py` is Python, a project can compute its model assignments, for example to select
different models in production.

### Use

`factoid init` sets up a project in the current directory with sample classes, sample documents, and an eval.

```sh
mkdir acme && cd acme
factoid init
factoid ingest ./sample_docs                     # documents in, facts and entities out
factoid search "Vega consent"
factoid read fact_01j9x8k2m                      # one fact, its quotes, its entities, and its history
factoid eval                                     # score the run against labeled data
factoid eval --vary fact_evals=none,nli,jev_floors  # compare fact eval chains on the same documents
```

## Documents, facts, and entities

Each document type, entity type, fact class, trait, and fact kind is a Python class. A class holds its definition,
prompt or question wording, model settings, and custom pipeline code. In the example below, a law firm advises its
client Acme on acquiring Orion and reviews Orion's contracts, including Orion's supply agreement with Vega:

```text
acme/
├── pyproject.toml
├── acme/
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # document sources
│   ├── documents.py   # Contract, CounselEmail, and ContractRegister
│   ├── entities.py    # Company, Agreement, and Person
│   ├── facts.py       # SourceFact, CounselFact, traits, and fact kinds
│   ├── fact_evals.py  # custom fact evals
│   └── prompts/
│       ├── counsel_email_extract.md.j2
│       └── thread_summary.md.j2
└── evals/diligence.jsonl
```

`Document` has two base subclasses: `ProseDocument` for text and `StructuredDocument` for tabular
rows. Every pipeline step is a classmethod or an instance method on the class that owns it:

| Class | Classmethods | Instance methods |
| --- | --- | --- |
| `Document` | `classify(raw, judgments)` | Prose: `segment`, `chunk`, `situate`, and `extract`. Structured: `read` and `row_facts`. Both: `discover`, `context`, the `source_datetime` property, and `ingest`, which runs the steps in order. |
| `Fact` | Reads, such as `search` | `validate`, `evaluate`, `repair`, `assess` (traits, kind, and lifetime, in one request), `expiration`, `link`, `resolve`, and `save`; outcomes `supersede`, `end`, `correct`, `contradict`, `retract`, and `restore`. |
| `Entity` | `identify(mention)`, `create`, and reads `find` and `where` | `claim`, `merge`, `split`, `retype`, `related`, and `facts`. |

Every step has `before_<step>` and `after_<step>` hooks, which do nothing by default and are always called.
`before_<step>` can raise `factoid.Skip` to skip the step for that item; `after_<step>` gets the result and can return
a replacement, or `None` to keep it. Overriding an outcome such as `supersede`, or defining `after_supersede`, is how a
project reacts to a change. `factoid steps show CounselEmail` lists the steps and where each is defined.

Every class supports incremental levels of customization, and every level is optional:

- **No classes, or plain declarations**: run on the defaults with no code, or subclass a base class and write a
  docstring.
- **Class settings**: set attributes for guidance, examples, traits, fact kinds, fact evals, thresholds, and models.
- **Step wording**: set a Jinja string or `template("...")` on the class (such as `extract_prompt` or `link_question`)
  to replace the default prompt or decision question for a step.
- **Step methods and hooks**: override a step method in Python (calling `super()` to keep the default), or define
  `before_` and `after_` hooks.

Here `CounselEmail` declares its timestamp from email metadata, overrides its extract prompt, and summarizes the quoted
thread before calling the built-in `extract` step:

```python
# documents.py
from factoid import ProseDocument, template

class CounselEmail(ProseDocument):
    """An email between our lawyers and the client or the other side."""
    extract_prompt = template("prompts/counsel_email_extract.md.j2")

    @property
    def source_datetime(self):
        return self.metadata["sent_at"]

    def extract(self, passages):
        # Summarize the quoted thread first, then extract with that summary as context.
        thread = self.generate(template("prompts/thread_summary.md.j2"), passages=passages)
        return super().extract(passages, thread=thread)
```

Every document has `source_datetime`, its own date from its metadata, such as an email's sent time, a contract's signing
date, or a wiki page's last edit. Factoid passes `source_datetime` to the extractor ahead of the passages so relative
dates in the text resolve against the document's date, never against ingest time. Accepted values are ISO-8601 strings
with a timezone offset or `Z`, epoch seconds, milliseconds, or microseconds, and timezone-aware `datetime` objects.

### Chunking

A long prose document does not fit in one extraction call, so Factoid cuts the document into chunks. First, `segment`
splits the document into passages, such as speaker turns or paragraphs. Next, `chunk` groups those passages into chunks.
A chunk never splits a passage.

Two settings on a prose document class control chunking:

- `chunk_size`: the largest chunk, in characters.
- `chunk_overlap`: how much of the previous chunk is repeated at the start of the next chunk. This setting takes a
  number of characters (`400`) or a share of `chunk_size` as a string (`"15%"`). Because `chunk_overlap` is one setting
  with two forms, the two forms can never disagree. Overlap is rounded to whole passages.

Overlap text is context only. A fact can cite a passage only from the chunk that owns that passage, so a passage in the
overlap does not yield the same fact twice.

After a chunk is made, the `situate` step writes a situation for that chunk: one or two sentences stating where the
chunk sits in the whole document and what the chunk is about. This follows Anthropic's [contextual
retrieval](https://www.anthropic.com/research/contextual-retrieval) technique. The model that writes the situation sees
the whole document and the chunk. Factoid stores the situation with the chunk and indexes the situation in front of the
chunk's text in a separate chunks search namespace. The extractor reads the situation before the chunk's passages, so it
can write self-contained facts that name the people and things the chunk only refers to.

The `situate` step is configurable like any other step: turn `situate` off with `situate = False`, replace the prompt
with `situate_prompt = template(...)`, or override the method. Running `situate` costs one generative call per chunk, so
whether `situate` is on by default is an eval result.

```python
# documents.py
class Contract(ProseDocument):
    """A signed contract or an amendment to one."""
    chunk_size = 4000        # characters
    chunk_overlap = "15%"    # or a number of characters, such as 400
    situate = True           # write a situation for each chunk

    @property
    def source_datetime(self):
        return self.metadata["signed_at"]
```

The built-in `situate` prompt passes the whole document and the chunk to the model:

```jinja
{# factoid/situate.md.j2, the built-in situate template #}
<document>
{{ document.text }}
</document>
<chunk>
{{ chunk.text }}
</chunk>
In one or two sentences, say where this chunk sits in the document and what it is about.
Name the people, organizations, and things it refers to. Answer with the situation only.
```

### Structured documents

`StructuredDocument` ingests CSV, JSONL, JSON arrays, and records from structured sources. Structured documents
are built on prosaic, a separate MIT library.

A structured document subclass defines a column map once per file layout. Each column is an entity identity (an exact
link, with no model call), an entity property, a value with a sentence template (one fact per cell, cited to the file,
row, and column), free text run through the prose pipeline with the row's entities already known, or ignored.
`row_entity` names the entity class each row represents, `key` names the column that identifies a row across re-imports,
and `when` names the column that dates the row. On re-import, a changed value for the same `key` and column supersedes
the old fact by rule, with no model call. Files that point to the same entity connect through that entity.

```python
# documents.py
from factoid import StructuredDocument, Identity, Ignore, Property, Text
from acme.entities import Agreement

class ContractRegister(StructuredDocument):
    """The data room's list of the target's contracts."""
    row_entity = Agreement
    key = "contract_id"
    when = "updated_at"
    columns = {
        "contract_id": Identity(Agreement, "contract_id"),
        "counterparty": Property(Agreement, "counterparty"),
        "governing_law": Property(Agreement, "governing_law"),
        "annual_value": "Agreement {contract_id} is worth ${annual_value} a year.",
        "notes": Text(),
        "internal_ref": Ignore(),
    }
```

Factoid matches a tabular file to a structured class by its header first, with the decision model as a fallback. The
`factoid struct` commands inspect a file, generate a parser class (or print the prompt for a coding agent), and dry-run
the parser before ingesting:

```sh
factoid struct inspect contract_register.csv                         # columns, sample values, and guessed identities
factoid struct parser contract_register.csv --name ContractRegister  # write a parser class (--prompt prints the prompt)
factoid struct try contract_register.csv --rows 20                   # dry-run on 20 rows and print facts and citations
factoid ingest contract_register.csv                                 # import facts and entity properties
```

### Facts, traits, and kinds

A fact is one self-contained sentence, exact source quotes (with who said each quote and when), links to one or more
entities, a fact kind with an expiration, and zero or more traits. A fact has no typed fields; the sentence carries the
meaning.

A trait is a `FactTrait` subclass whose docstring is the definition the model reads. With no `decide` method, the
trait is one yes-or-no question built from the docstring and compared against `threshold`; `decide` gets that answer
(such as `judgments.liability_cap`) plus any factor questions it declares with `@judge`. Traits can also define
`after_` hooks for facts that carry them. A fact can carry several traits, and a fact that matches no trait is kept.

In the same `assess` request, Factoid classifies each fact into a kind declared on `Fact.kinds` and estimates its
lifetime. The built-in kinds are `fixed`, `state`, `event`, `decision`, `plan`, `forecast`, and `rule`. Each kind is a
`FactKind` subclass whose docstring is the rubric the model reads and whose `expires` attribute sets how facts of
that kind age: `"never"` (`fixed`, `event`, and `decision`), `"estimated"` (`state` and `rule`), or `"at_deadline"`
(`plan` and `forecast`).

Expiration timing is set per fact. When the text gives an exact cutoff, such as `"next Friday"` resolved against
`source_datetime`, the extractor records that timestamp. Otherwise, a model chooses a lifetime range, from an hour to
longer than a few years, and Factoid keeps the distribution over ranges to compute the chance the fact is still valid at
a given time. Each confirmation restarts the clock.

Many projects need only one fact class, and running with one fact class and no subclass at all is fine. Here there are
two because a lawyer's conclusion is a different kind of evidence from what a contract says: a `CounselFact` cannot
contradict a `SourceFact`, and it can be hidden from readers outside the deal team. One document can produce both (an
email from our lawyer quotes a contract and states a view), and Factoid classifies each extracted fact before `assess`
runs.

```python
# facts.py
from factoid import Fact, FactKind, FactTrait, Noul, judge

class ChangeOfControl(FactTrait):
    """A consequence triggered by a change in who owns or controls a party."""

class ConsentRequired(FactTrait):
    """A named party must approve an action before it happens."""

class Deadline(FactTrait):
    """The latest time an action is allowed."""

class LiabilityCap(FactTrait):
    """A limit on how much a party can owe."""
    threshold = 0.8
    examples = ["Orion's liability under the Vega supply agreement is capped at $1M."]

    @classmethod
    @judge(states_amount=Noul("Does it state an amount of money?"))
    def decide(cls, fact, judgments):
        return judgments.liability_cap > cls.threshold and judgments.states_amount > 0.5

    @classmethod
    def after_supersede(cls, fact, older):
        notify(fact.deal_team, f"Liability cap changed: {older.text} → {fact.text}")

class ClosingRisk(FactTrait):
    """Something that could delay or block the deal from closing."""

class Allegation(FactKind):
    """A claim one party makes against another that has not been proven."""
    expires = "estimated"

class SourceFact(Fact):
    """What a contract, a client, or the other side says."""
    traits = [ChangeOfControl, ConsentRequired, Deadline, LiabilityCap]
    kinds = Fact.kinds + [Allegation]

class CounselFact(Fact):
    """What our own lawyers concluded."""
    traits = [ClosingRisk]
```

| Fact sentence | Class | Kind | Traits |
| --- | --- | --- | --- |
| Orion's supply agreement with Vega lets Vega terminate if a competitor of Vega acquires Orion. | `SourceFact` | `rule` | `ChangeOfControl` |
| Orion may not assign the Vega supply agreement without Vega's written consent. | `SourceFact` | `rule` | `ConsentRequired` |
| Vega must answer a consent request within 15 business days. | `SourceFact` | `rule` | `ConsentRequired`, `Deadline` |
| Amendment 2 raises the liability cap in the Vega supply agreement to $2M from January 1, 2027. | `SourceFact` | `rule` | `LiabilityCap` |
| Acme's deal counsel concluded that Vega's consent is a closing risk. | `CounselFact` | `state` | `ClosingRisk` |

Amendment 2's fact supersedes the old liability cap fact only, not the whole agreement. A clause with a future effective
date is still a `rule`, not a `forecast`.

### Entities

Each `Entity` subclass declares one kind of thing that facts are about. The docstring describes that kind in
plain language, and discovery uses it to route extracted entities to the class. Optional `unique_keys` lists the
identifiers that prove two records are the same entity; email, domain, and URL found in text count by default, and names
are always a weak match checked by the decision model.

Every entity, typed or untyped, carries a JSON `props` dictionary. A `Entity` subclass can declare typed
properties as class annotations; they are validated on write, stored in `props`, and queried with `Class.where(...)`.
Prose extraction writes facts only and never sets entity properties. Properties come from structured documents, source
records, and edits through the CLI, the API, and MCP. An entity class can also tune its AI steps: discovery guidance and
examples, link and merge thresholds, model selection, and custom link or merge questions.

```python
# entities.py
from factoid import Entity

class Company(Entity):
    """A company that is a party to a deal or a contract."""
    unique_keys = ["domain"]
    jurisdiction: str

class Agreement(Entity):
    """One contract and its amendments, as a whole."""
    unique_keys = ["contract_id"]
    counterparty: str
    governing_law: str

class Person(Entity):
    """A lawyer, a client contact, or someone at the other side."""
    unique_keys = ["email"]
    role: str
    link_threshold = 0.85
    link_question = "Is this mention the same person as {{ entity.name }}?"
```

Every entity link on a fact carries a role (`subject`, `about`, or `speaker`), the method that created the link, and a
confidence score. Linking proceeds from sure to unsure and stops at the first step that settles the mention:

1. Match an exact identifier from the source.
2. Match a unique key, such as `contract_id`, an email address, a domain, or a URL.
3. Match a name belonging to exactly one entity in the same document.
4. Match a name belonging to exactly one entity in the whole store.
5. Ask the decision model a yes-or-no question for what is left.

Entities enter the store from structured or record sources, or from per-document discovery. An entity does not need a
declared class: every extracted entity is kept and linked once the link ladder finds no existing match. When an
extracted entity matches no declared class, Factoid stores it as a plain `Entity` with a lowercase, singular
free-text `kind` written by discovery, such as `"court"`. Placeholder mentions such as `"the counterparty"` or
`"someone"` are refused; a mention that matches no entity stays on the fact as an unlinked mention, and the fact is
kept.

Untyped entities are searchable, editable, mergeable, and deletable through the CLI, the API, and MCP.
`factoid entities kinds` lists untyped kinds by entity and fact count, and
`factoid entities retype --kind "court" Court` promotes matching entities to a declared class, with the decision model
confirming each one and without re-extracting.

When a new entity is stored, Factoid runs a claiming step across existing facts, searching stored facts for the entity's
names and asking the decision model to confirm each hit. Two entities that share a unique key merge by rule, while two
entities that share only a weak name go to a yes-or-no question with a high floor. Merges and splits are logged as
events.

Relations between entities require no schema or relation class. Factoid counts co-mentions across shared facts and
identifies relation facts: current `fixed` or longer-lived `state` facts that link two or more entities. Calling
`entity.related()` returns connected entities with their co-mention counts and current relation facts, weighted by
freshness.

### Resolving facts

For each new fact, Factoid gathers the stored facts that share one or more linked entities with it and asks the decision
model one question with six answers: `duplicate`, `supersedes`, `ends`, `corrects`, `contradicts`, or `unrelated`.
`supersedes` replaces an older value that was true until then, `ends` marks that a state stopped without setting a new
value, and `corrects` marks an older fact as wrong from the start.

When two facts contradict, both are marked `contradicted` and point to each other. Reads show both, and search results
include contradicting facts by default: `contradictions=3` returns up to three contradicting facts in full plus the IDs
of any others, `contradictions=0` returns IDs only, and `contradictions=False` leaves them out. Contradictions are
settled by new evidence or through `factoid contradictions`, and go stale without auto-settling when their facts expire.

### Classification

A document's class normally comes from its source. Classification runs only when the class is unknown, such as a folder
of unmarked files.

Every document class registers itself when it is defined. `classify(raw, judgments)` is a classmethod that returns
`True`, `False`, `None` (not sure), or a score. For classes that declare nothing, the default asks one choice question
over the document classes' docstrings, plus a yes-or-no question asking whether any of them applies. Optional `not_for`
on a class describes its boundary with close classes.

A class can ask its own factor questions with `@judge` and decide in code with thresholds, with a middle band that goes
to review. This is the general pattern: steps ask the decision model several small questions in one request, and code
decides from the probabilities.

```python
from factoid import Choice, ProseDocument, Noul, judge

class Contract(ProseDocument):
    """A signed contract or an amendment to one."""

    @classmethod
    @judge(
        is_contract=Noul("Is this a contract or an amendment to one?"),
        status=Choice("What state is it in?", ["signed", "draft", "redline", "something else"]),
    )
    def classify(cls, raw, judgments):
        if judgments.is_contract > 0.9 and judgments.status["signed"] > 0.7:
            return True
        if judgments.is_contract < 0.3:
            return False
        return None   # the middle band goes to review
```

Two classes claiming one file is an error, and files that no class claims go to an unclassified list. `classify_view`
controls what the classifier sees, and `factoid classifiers show` lists the registry.

### Default fact evals

Every candidate fact passes a default chain of fact evals before being stored. A fact eval decides one thing: whether
a candidate fact is good enough to keep. A project gets this chain without writing any code, and custom fact evals run
on top of the default chain while keeping the built-in checks. The chain runs in order and rejects a candidate at the
first failure, so the cheap fact eval goes first.

| Fact eval | Responsibility |
| --- | --- |
| `nli` | Small entailment model. Checks that the cited passage entails the sentence. Cheap, so `nli` runs first. |
| `jev_floors` | Six yes-or-no questions in one decision-model call. Each probability has a floor; all six must pass. |

Each `jev_floors` answer is a probability that must clear the floor for that question:

- `grounded`: The cited passages support the sentence.
- `attribution`: Who said the sentence, and whether the sentence was certain or negated, match the source.
- `self_contained`: The sentence names its subject, with no unresolved pronouns.
- `atomic`: The sentence states one claim.
- `useful`: The fact is worth keeping.
- `distinct`: No stored fact already states the same claim.

Factoid calibrates these floors on labeled data; no floor uses a fixed `0.5`. A candidate that narrowly fails gets
one repair (a rewording), and Factoid evaluates the repaired candidate again. A project can change one floor or add a
custom fact eval without replacing the default chain:

```python
# facts.py
from factoid import Fact
from factoid.fact_evals import JevFloors, Nli
from acme.fact_evals import CitesSourceEval

class SourceFact(Fact):
    """What a contract, a client, or the other side says."""
    traits = [ChangeOfControl, ConsentRequired, Deadline, LiabilityCap]
    kinds = Fact.kinds + [Allegation]
    fact_evals = [Nli, JevFloors(useful=0.8)]               # the default chain, with one floor raised

class CounselFact(Fact):
    """What our own lawyers concluded."""
    traits = [ClosingRisk]
    fact_evals = [*Fact.fact_evals, CitesSourceEval]  # the chain, plus a check of our own
```

`CitesSourceEval` checks that the conclusion points to a source fact.

`factoid eval --vary fact_evals=none,nli,jev_floors` compares chains on the same documents.

### Model calls

Steps call models through four methods on `self`. Factoid logs, prices, budgets, and replays these calls, and includes
each prompt in the step's fingerprint.

| Method | Returns | Model kind |
| --- | --- | --- |
| `self.choose(prompt, options)` | A probability for each option | Decision model |
| `self.decide(prompt)` | A probability that the answer is yes | Decision model |
| `self.score(prompt, rubric)` | A rubric level | Decision model |
| `self.generate(prompt)` | Text | Generative model |

`@judge` with `Noul`, `Choice`, and `Score` declares a step's questions so they go in one request.

Define models once in `settings.py` with pinned versions. Keys come from `factoid keys`, never from the file.

```python
# settings.py
from factoid import Model, Settings
from factoid.search import Turbopuffer
from factoid.stores import Sqlite

class Project(Settings):
    store = Sqlite(path=".factoid/acme.db")            # the system of record
    models = {
        "choose": Model("typesafe/jev-1.13.0"),        # classify, evaluate facts, assess, and resolve
        "generate": Model("fireworks/glm-5p3-flash"),  # extract and repair
        "embed": Model("openai/text-embedding-3-small"),
        "rerank": Model("fireworks/qwen3-reranker-8b"),    # optional
    }
    search = Turbopuffer(
        base_url="https://gcp-us-central1.turbopuffer.com",  # or any turbopuffer-compatible endpoint
        retrieve="hybrid-rrf",
        budget_tokens=1500,
    )
```

Eval runs can swap step strategies from the CLI without modifying project files. `factoid eval --vary
classify=decision,llm,rules` runs the same documents under each strategy and compares quality, cost, and latency.

## Prompts

Prompts and decision questions are Jinja templates set explicitly on a class as a string or with `template(path)`,
resolved relative to the file that defines the class. Project templates can replace a built-in template or extend it and
override individual blocks. `factoid prompts show CounselEmail.extract` prints the wording in effect and where it came
from.

```jinja
{# factoid/extract.md.j2, the built-in extract template #}
Extract facts from this {{ document.type }}, dated {{ document.source_datetime }}.
{% block guidance %}{% endblock %}
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker }}: {{ passage.text }}
{% endfor %}
Cite passages by number. Do not copy quote text.
```

```jinja
{# prompts/counsel_email_extract.md.j2 #}
{% extends "factoid/extract.md.j2" %}
{% block guidance %}
Earlier messages in this thread: {{ thread }}
Skip greetings, signatures, and privilege footers.
{% endblock %}
```

## Reading facts

Reads look up entities by property, fetch facts or connected entities, and search facts or chunks.

```python
delaware = Agreement.where(governing_law="Delaware")              # query typed properties in props
vega = Company.find("Vega")
agreement = Agreement.find("ORN-0042")
agreement.facts(traits=[ConsentRequired], since="90d")            # facts linked to the agreement, newest first
agreement.facts(include_retired=True)                             # the agreement's full history
vega.related()                                                    # connected entities, co-mentions, and relation facts
facts.search("change of control", about=vega)                     # includes up to 3 contradicting facts by default
facts.search("liability cap", about=agreement, as_of="2027-02-01")  # weight relevance by validity as of a date
CounselFact.search("closing risk")                                # search scoped to one fact class
facts.unlinked(since="30d")                                       # facts with a mention that matched no entity
chunks.search("assignment consent", about=agreement)              # search source chunks, indexed with situations
```

Search weights each fact's score by the probability that the fact is still valid at `as_of=` (now by default), so stale
facts stay findable while ranking lower. Pass `freshness="any"` to disable freshness weighting for historical queries,
or `valid_at=` to filter to facts likely still valid. Source chunks live in their own namespace and are searched with
`chunks.search(...)`; searching facts and chunks together runs hybrid search in each namespace and reranks the combined
list.

`factoid stats` reports facts with no trait, unlinked mentions, single-fact entities, facts past their expected
validity, and open contradictions.

## Usage

- **Standalone CLI project.** Manage a RAG corpus in its own directory, tune chunking and extraction, and evaluate
  prompt, extractor, and fact eval choices with `factoid ingest`, `factoid search`, and `factoid eval`.
- **Agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes, and chats,
  then expose fact search and writes to an agent through `factoid mcp` or the CLI.
- **Python library or HTTP service.** Run `factoid serve` as an HTTP sidecar, or `import factoid` inside an
  application and pass classes to `Factoid(...)`:

```python
from factoid import Entity, Factoid, Model, ProseDocument, Settings

class Company(Entity):
    """A company that is a party to a deal or a contract."""
    unique_keys = ["domain"]

class DealMemo(ProseDocument):
    """A memo a lawyer wrote about a deal."""

class ServiceSettings(Settings):
    models = {"generate": Model("fireworks/glm-5p3-flash"), "choose": Model("typesafe/jev-1.13.0")}

facts = Factoid(settings=ServiceSettings, documents=[DealMemo], entities=[Company])
facts.ingest_text("Orion's lease in Austin ends in March 2027.", document_type=DealMemo)
hits = facts.search("Orion lease")     # fact sentences, source quotes, and any contradictions
orion = Company.find("Orion")
recent = orion.facts(since="30d")      # every recent fact linked to Orion
```

## Design

- **Fact-level retrieval.** Search returns short, self-contained sentences within a token budget. On dialogue, fact
  retrieval outperformed chunk retrieval while using about one-seventh of the read tokens
  ([docs/prior-art.md](docs/prior-art.md)).
- **Deterministic provenance.** Prose extraction cites numbered passages and structured extraction cites the file, row,
  and column; Factoid's code attaches the exact quote or cell, speaker, and timestamp.
- **Event log for history.** Current state in SQLite is the source of truth. Each change also writes a fact event
  (`added`, `superseded`, `ended`, `corrected`, `contradicted`, `retracted`, or `restored`) or an entity event
  (`linked`, `merged`, or `split`) to a log in the same database. The log records where each fact came from and how it
  changed, so a response can include the fact a newer one superseded.
- **Eval-selected defaults.** Default strategies across `classify`, `segment`, `extract`, `evaluate`, `repair`,
  `assess`, `link`, and `resolve` come from eval results. `factoid eval` measures accuracy, cost, and latency on labeled
  data.
- **Pluggable backends.** Storage, search, sources (`folder`, `jsonl`, `imap`, and `mcp`), models, and fact evals share
  small base classes that projects can subclass. In v1, Factoid stores data in SQLite and searches with turbopuffer or
  a compatible endpoint, and either can be replaced.
- **Emergent entities and kept facts.** Every extracted entity is kept and linked, even with no declared class, and a
  placeholder mention that matches nothing stays on the fact as an unlinked mention so the fact is still kept. When a
  new entity is stored, Factoid searches stored facts for the entity's names and asks the decision model to confirm each
  hit.
- **Fingerprints.** Each fact records a fingerprint of the prompts, questions, floors, and settings that produced the
  fact. When any of those inputs change, facts from the old version are stale, and `factoid rebuild --estimate` prices
  re-deriving those facts. The model is omitted from the fingerprint, so switching models for price does not force a
  rebuild.

## Further reading

Read [docs/mental-model.md](docs/mental-model.md) first, then [docs/README.md](docs/README.md).
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still cover the older single-YAML design and
will be updated.
