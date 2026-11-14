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
| `choose` | Decision model | Classifying, judging, labeling, linking, and resolving |
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

`factoid new` creates a project directory named `acme` with sample classes, sample documents, and an eval.

```sh
factoid new acme
cd acme
factoid ingest ./sample_docs                     # documents in, facts and entities out
factoid search "Unit 4B heater"
factoid read fact_01j9x8k2m                      # one fact, its quotes, its entities, and its history
factoid eval                                     # score the run against labeled data
factoid eval --vary judge=none,nli,jev_floors    # compare judge chains on the same documents
```

## Documents, facts, and entities

Each document type, entity type, and label is a Python class, and a class holds its definition, prompt overrides, model
settings, and custom pipeline code. A Factoid project is a Python package with a layout like this:

```text
acme/
├── pyproject.toml
├── acme/
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # document sources
│   ├── documents.py   # LeaseAgreement, TenantEmail, and PlumberInvoice
│   ├── entities.py    # Unit, Person, and Vendor
│   ├── facts.py       # labels, and the project's base fact class
│   └── judges.py      # custom judges
├── prompts/
│   └── tenant_email/
│       ├── extract.md.j2          # extract prompt for TenantEmail
│       └── thread_summary.md.j2   # custom helper prompt
└── evals/leases_and_repairs.jsonl
```

The three base classes expose hooks for each stage of the pipeline:

| Class | Hooks | Responsibility |
| --- | --- | --- |
| `FactoidDocument` | `classify`, `segment`, `chunk`, `situate`, `extract`, and `discover` | Match a document to this type, split it into passages, group passages into chunks, describe each chunk, extract candidate facts, and propose entities. |
| `FactoidFact` | `judge`, `repair`, `label`, `link`, and `resolve` | Check quality, rewrite a near miss, apply labels, link to entities, and compare against stored facts. |
| `FactoidEntity` | `identify`, `claim`, and `merge` | Match a mention to an entity of this type, claim stored facts, and decide whether two entities are the same. |

Every class supports three levels of customization:

- **Class definitions**: write a docstring and set class attributes for labels, judges, thresholds, and model settings.
- **Prompt files**: place a template at `prompts/<class_name>/<hook>.md.j2` to override the default prompt for a hook.
- **Hook methods**: override a hook method in Python to run custom code, render helper prompts, or call `super()`.

Here `TenantEmail` summarizes a quoted email thread first, then passes that summary into the built-in `extract` step:

```python
# documents.py
from factoid import FactoidDocument

class TenantEmail(FactoidDocument):
    """An email from a tenant to the leasing office."""

    def extract(self, passages):
        # Summarize the quoted thread first, then extract with that summary as context.
        thread = self.generate("thread_summary.md.j2", passages=passages)
        return super().extract(passages, thread=thread)
```

### Chunking

A long document does not fit in one extraction call, so Factoid cuts the document into chunks. First, `segment` splits
the document into passages, such as speaker turns, paragraphs, or rows. Next, `chunk` groups those passages into
chunks. A chunk never splits a passage.

Two settings on a document class control chunking:

- `chunk_size`: the largest chunk, in characters.
- `chunk_overlap`: how much of the previous chunk is repeated at the start of the next chunk. This setting takes a
  number of characters (`400`) or a share of `chunk_size` as a string (`"15%"`). Because `chunk_overlap` is one setting
  with two forms, the two forms can never disagree. Overlap is rounded to whole passages.

Overlap text is context only. A fact can cite a passage only from the chunk that owns that passage, so a passage in the
overlap does not yield the same fact twice.

After a chunk is made, the `situate` hook writes a situation for that chunk: one or two sentences stating where the
chunk sits in the whole document and what the chunk is about. This follows Anthropic's [contextual
retrieval](https://www.anthropic.com/research/contextual-retrieval) technique. The model that writes the situation sees
the whole document and the chunk. Factoid stores the situation with the chunk and indexes the situation with the chunk's
text for search. The extractor reads the situation before the chunk's passages. This context helps the extractor write
self-contained facts, naming the people and things that the chunk only refers to.

The `situate` step is a hook like any other: turn `situate` off with `situate = False`, change the prompt wording with
`prompts/<class_name>/situate.md.j2`, or override the method. Running `situate` costs one generative call per chunk, so
whether `situate` is on by default is an eval result.

```python
# documents.py
class LeaseAgreement(FactoidDocument):
    """A signed lease for one unit."""
    chunk_size = 4000        # characters
    chunk_overlap = "15%"    # or a number of characters, such as 400
    situate = True           # write a situation for each chunk
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

### Facts and labels

A fact is one self-contained sentence, exact source quotes (with who said each quote and when), links to one or more
entities, and zero or more labels. The sentence carries the meaning.

A label is a small `FactoidLabel` subclass with a docstring. The docstring is the definition the model reads. The tagger
asks one yes-or-no question per label. A fact can carry several labels, and a fact that matches no label is kept.

A `FactoidFact` subclass is optional, and many projects need none. A `FactoidFact` subclass exists for behavior only: a
custom definition, extraction guidance, shared labels, or custom judges.

```python
# facts.py
from factoid import FactoidFact, FactoidLabel

class RepairIssue(FactoidLabel):
    """A problem with a unit or its equipment that someone reported."""

class Commitment(FactoidLabel):
    """Something a person agreed to do, with or without a date."""

class Cost(FactoidLabel):
    """An amount of money that someone quoted, charged, or paid."""

class AcmeBaseFact(FactoidFact):
    """Shared defaults for this project's facts."""
    labels = [RepairIssue, Commitment, Cost]
```

### Entities

`FactoidEntity` is a first-class base class in a Factoid project. Each `FactoidEntity` subclass declares one kind of
thing that facts are about and defines how an entity of that kind is identified. The class docstring describes that kind
in plain language, and `identities` maps each identifier key to `"strong"` or `"weak"`. A subclass can also define a
`normalize` method so variant mentions reduce to one canonical string before matching.

```python
# entities.py
import re
from factoid import FactoidEntity

class Unit(FactoidEntity):
    """One rentable apartment in a building."""
    identities = {"unit_number": "strong"}

    @classmethod
    def normalize(cls, mention: str) -> str:
        # "Apt 4B", "#4b", and "unit 4-B" name the same unit.
        return re.sub(r"(apt|unit|[^0-9a-z])", "", mention.lower())

class Person(FactoidEntity):
    """A tenant, a staff member, or a contractor."""
    identities = {"email": "strong", "phone": "strong", "name": "weak"}

class Vendor(FactoidEntity):
    """A company that does work on the property."""
    identities = {"domain": "strong", "name": "weak"}
```

Every entity link on a fact carries a role (`subject`, `about`, or `speaker`), the method that created the link, and a
confidence score. Linking proceeds from sure to unsure and stops at the first step that settles the mention:

1. Match an exact identifier from the source.
2. Match a strong identity, such as an email address, a phone number, or a domain.
3. Match a name belonging to exactly one entity in the same document.
4. Match a name belonging to exactly one entity in the whole store.
5. Ask the decision model a yes-or-no question for what is left.

A mention that matches nothing stays on the fact as an unlinked mention. The fact is kept in the store, and a mention
inside a fact never creates an entity.

Entities enter the store from record sources or from document discovery. Sources that carry records with identifiers,
such as a CRM or a directory, create entities directly. For all other documents, a discovery step runs per document and
proposes candidate entities. Placeholder names such as "unknown" or "the tenant" are refused. Factoid stores a proposed
entity only when that candidate has a strong identity or is named in two or more separate documents.

When a new entity is stored, Factoid runs a claiming step across existing facts. Factoid searches the stored facts for
the new entity's names and asks the decision model to confirm each hit. Facts that arrived before the entity existed get
linked during this claiming step.

Stored entities can also merge as new evidence arrives. Two entities that share a strong identity merge by rule. Two
entities that share only a weak identity, such as a name, go to a yes-or-no question with a high confidence floor.
Merges and splits are recorded as events in the log, so either event can be undone.

### Resolving facts

Resolve works the same way for every new fact that enters the store. Factoid gathers the stored facts that share one or
more linked entities with the new fact, and those entity links are what keep that comparison small. For each stored fact
in that set, Factoid asks the decision model one question with four answers: duplicate, supersedes, contradicts, or
unrelated. This resolution step is what retires outdated facts, merges duplicates, and flags facts that disagree.

### Classification

By default, `classify` uses a decision model. A decision model scores a fixed set of options in one pass and returns a
probability per option with no generated text. To classify a document, Factoid sends one request containing all
document classes and their docstrings. Labeling and entity discovery use the same kind of model.

```python
class PlumberInvoice(FactoidDocument):
    """An invoice from a plumber for work done on a unit."""
    classify_threshold = 0.8          # default threshold comes from calibration

    def classify_view(self) -> str:
        # Pass the header and footer, where letterhead and totals appear.
        return self.head(400) + self.tail(400)
```

Override `classify` to replace the model call with Python logic, such as a header check.

### Default judges

Every candidate fact passes a default chain of judges before being stored. A project gets this chain without writing
any code, and custom judges run on top of the default chain while keeping the built-in checks. The chain runs in order
and rejects a candidate at the first failure, so the cheap judge goes first.

| Judge | Responsibility |
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
one repair (a rewording), and Factoid judges the repaired candidate again. A project can change one floor or add a
custom judge without replacing the default chain:

```python
# facts.py
from factoid import FactoidFact
from factoid.judges import JevFloors, Nli
from acme.judges import FirstHandJudge

class AcmeBaseFact(FactoidFact):
    """Shared defaults for this project's facts."""
    labels = [RepairIssue, Commitment, Cost]
    judges = [Nli, JevFloors(useful=0.8)]             # the default chain, with one floor raised

class RepairReport(AcmeBaseFact):
    """A statement about the condition of a unit, from someone who checked it."""
    judges = [*AcmeBaseFact.judges, FirstHandJudge]  # the chain, then a judge of our own
```

`RepairReport` is a `FactoidFact` subclass that exists only to carry an extra judge.

`factoid eval --vary judge=none,nli,jev_floors` compares chains on the same documents.

### Model calls

Hooks call models through four methods on `self`. Factoid logs, prices, budgets, and replays these calls, and includes
each prompt in the step's fingerprint.

| Method | Returns | Model kind |
| --- | --- | --- |
| `self.choose(prompt, options)` | A probability for each option | Decision model |
| `self.decide(prompt)` | A probability that the answer is yes | Decision model |
| `self.score(prompt, rubric)` | A rubric level | Decision model |
| `self.generate(prompt)` | Text | Generative model |

Define models once in `settings.py` with pinned versions. Keys come from `factoid keys`, never from the file.

```python
# settings.py
from factoid import FactoidSettings, Model
from factoid.search import Turbopuffer
from factoid.stores import Sqlite

class Project(FactoidSettings):
    store = Sqlite(path=".factoid/acme.db")            # the system of record
    models = {
        "choose": Model("typesafe/jev-1.13.0"),        # classify, judge, and resolve
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

Eval runs can swap hook strategies from the CLI without modifying project files. `factoid eval --vary
classify=decision,llm,rules` runs the same documents under each strategy and compares quality, cost, and latency.

## Prompts

Prompts are Jinja templates. Every model-backed hook has a built-in template that a file in `prompts/` can replace:
`prompts/extract.md.j2` applies to all document types, and `prompts/tenant_email/extract.md.j2` applies to
`TenantEmail`. Project templates can also extend a built-in template and override individual blocks.

```jinja
{# factoid/extract.md.j2, the built-in extract template #}
Extract facts from this {{ document.type }}, dated {{ document.at }}.
{% block guidance %}{% endblock %}
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker }}: {{ passage.text }}
{% endfor %}
Cite passages by number. Do not copy quote text.
```

```jinja
{# prompts/tenant_email/extract.md.j2 #}
{% extends "factoid/extract.md.j2" %}
{% block guidance %}
Earlier messages in this thread: {{ thread }}
Skip greetings, signatures, and quoted replies.
{% endblock %}
```

## Code hooks

Override `validate` on a fact class to reject candidates in code, and define `on_added`, `on_superseded`,
`on_contradicted`, `on_retracted`, or `on_restored` to run callbacks on lifecycle events. Entity classes have
`on_merged` and `on_split` for merge and split events.

## Reading facts

Reads query facts by entity and label, or by search.

```python
unit = Unit.find("4B")
unit.facts(labels=[RepairIssue], since="90d")     # facts linked to the unit, newest first
unit.facts(role="subject", include_retired=True)  # the unit's full history
facts.search("heater leaking", about=unit)        # search within one entity's facts
facts.unlinked(since="30d")                       # facts with a mention that matched no entity
```

`factoid stats` reports the share of facts with no label, the share of mentions with no entity, and the largest groups
of each.

## Usage

- **Standalone CLI project.** Manage a RAG corpus in its own directory, tune retrieval units, and evaluate prompt,
  extractor, and judge choices with `factoid ingest`, `factoid search`, and `factoid eval`.
- **Agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes, and chats,
  then expose fact search and writes to an agent through `factoid mcp` or the CLI.
- **Python library or HTTP service.** Run `factoid serve` as an HTTP sidecar, or `import factoid` inside an
  application and pass classes to `Factoid(...)`:

```python
from factoid import Factoid, FactoidDocument, FactoidEntity, FactoidSettings, Model

class Account(FactoidEntity):
    """A customer company."""
    identities = {"domain": "strong", "name": "weak"}

class AccountNote(FactoidDocument):
    """A note an account manager wrote about a customer."""

class ServiceSettings(FactoidSettings):
    models = {"generate": Model("fireworks/glm-5p3-flash"), "choose": Model("typesafe/jev-1.13.0")}

facts = Factoid(settings=ServiceSettings, documents=[AccountNote], entities=[Account])
facts.ingest_text("Globex upgraded to Enterprise.", document_type=AccountNote)
hits = facts.search("Globex plan")     # fact sentences with source quotes
globex = Account.find("Globex")
recent = globex.facts(since="30d")     # every recent fact linked to Globex
```

## Design

- **Fact-level retrieval.** Search returns short, self-contained sentences within a token budget. On dialogue, fact
  retrieval outperformed chunk retrieval while using about one-seventh of the read tokens
  ([docs/prior-art.md](docs/prior-art.md)).
- **Deterministic provenance.** The extractor cites numbered passages, and Factoid's code attaches the exact quote,
  speaker, and timestamp.
- **Append-only event log.** Writes append fact events (`added`, `superseded`, `contradicted`, `retracted`, and
  `restored`) and entity events (`linked`, `merged`, and `split`) to a log kept in the project's SQLite database.
  Current state and the search index are views rebuilt from that log.
- **Eval-selected defaults.** Default strategies across `classify`, `segment`, `extract`, `judge`, `repair`, `label`,
  `link`, and `resolve` come from eval results. `factoid eval` measures accuracy, cost, and latency on labeled data.
- **Pluggable backends.** Storage, search, sources (`folder`, `jsonl`, `imap`, and `mcp`), models, and judges share
  small base classes that projects can subclass. In v1, Factoid stores data in SQLite and searches with turbopuffer or
  a compatible endpoint, and either can be replaced.
- **Unlinked facts are kept.** A mention that matches no entity stays on the fact as an unlinked mention, and a
  mention in a fact never creates an entity. When a new entity is stored, Factoid searches stored facts for the
  entity's names and asks the decision model to confirm each hit, linking facts that arrived before the entity existed.
- **Fingerprints.** Each fact records a fingerprint of the prompts, questions, floors, and settings that produced the
  fact. When any of those inputs change, facts from the old version are stale, and `factoid rebuild --estimate` prices
  re-deriving those facts. The model is omitted from the fingerprint, so switching models for price does not force a
  rebuild.

## Further reading

Read [docs/mental-model.md](docs/mental-model.md) first, then [docs/README.md](docs/README.md).
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still cover the older single-YAML design and
will be updated. Earlier proposals are in [docs/potential/README/](docs/potential/README/).
