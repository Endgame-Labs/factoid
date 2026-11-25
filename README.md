# Factoid 📚

[![Website](https://img.shields.io/badge/website-open.endgame.io%2Ffactoid-2563eb.svg)](https://open.endgame.io/factoid)
[![PyPI](https://img.shields.io/pypi/v/factoid.svg)](https://pypi.org/project/factoid/)
[![tests](https://github.com/Endgame-Labs/factoid/actions/workflows/test.yml/badge.svg)](https://github.com/Endgame-Labs/factoid/actions/workflows/test.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/Endgame-Labs/factoid/blob/main/LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-2608.20845-b31b1b.svg)](https://arxiv.org/abs/2608.20845)
[![arXiv](https://img.shields.io/badge/arXiv-2609.29661-b31b1b.svg)](https://arxiv.org/abs/2609.29661)

**Website:** https://open.endgame.io/factoid, with an interactive
[What is a fact?](https://endgame-labs.github.io/factoid/what-is-a-fact.html) page.

> **Status: Version 0.1.29.** Factoid runs end to end, and five example apps publish their eval results. It covers
> ingest, fact extraction with evals, entities, supersession and as-of search, settling contradictions, eval suites,
> exports, an HTTP API, and an MCP server. [SPEC.md](https://github.com/Endgame-Labs/factoid/blob/main/SPEC.md) section 17 lists what is built.
> [CHANGELOG.md](https://github.com/Endgame-Labs/factoid/blob/main/CHANGELOG.md) lists what changed in each version.

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

This takes about five minutes: install Factoid, start a project, add one or two API keys, and ingest the sample
contract.

### Install

Factoid requires Python 3.13 or newer and [uv](https://docs.astral.sh/uv/). Install it from PyPI:

```sh
uv tool install factoid
```

For the latest unreleased changes, install from GitHub, or clone the repository and run `uv tool install .` in it:

```sh
uv tool install git+https://github.com/Endgame-Labs/factoid
```

Inside a project directory, `factoid` runs in that project's environment without `uv run`.

### Pick your models

Factoid uses models for four kinds of work, and the fourth is optional:

| Workload | Kind of model | Used for |
| --- | --- | --- |
| `choose` | Decision model | Classifying, evaluating facts, assessing, linking, and resolving |
| `generate` | Generative model | Extracting facts and describing chunks |
| `embed` | Embedding model | Search |
| `rerank` | Reranking model (optional) | Reordering search results |

`factoid init --models <preset>` writes a `settings.py` that uses one of three sets of providers:

| Preset | `choose` | `generate` | `embed` | Keys you need |
| --- | --- | --- | --- | --- |
| `jev` (the default) | TypeSafe `jev-1.14.0` | Fireworks `glm-5p3-flash` | Fireworks `qwen3-embedding-8b` | TypeSafe and Fireworks |
| `fireworks` (experimental) | Fireworks `rune` | Fireworks `glm-5p3-flash` | Fireworks `qwen3-embedding-8b` | Fireworks |
| `openai` | OpenAI `gpt-6-luna` (Decisions API) | OpenAI `gpt-6-luna` | OpenAI `text-embedding-3-small` | OpenAI |

Jev is the recommended decision model. A TypeSafe key is self-serve: sign up at the console and create one. To start
with one key in all, use `--models openai`. Rune now has its own fact eval floors. On a
news-transcript eval, it answers about as many questions as Jev. The `fireworks` preset stays experimental until the
contract evals have been run on Rune.

You can mix providers by editing `settings.py`. Model names use `provider/model`, so Factoid knows which key a workload
needs. Not every provider serves every workload:

| Provider | Workloads | Get a key |
| --- | --- | --- |
| `typesafe` | `choose` | <https://console.typesafe.ai/keys> |
| `fireworks` | `choose`, `generate`, `embed`, and `rerank` | <https://app.fireworks.ai/settings/users/api-keys> |
| `openai` | `choose`, `generate`, and `embed` | <https://platform.openai.com/api-keys> |
| `openrouter` | `generate` | <https://openrouter.ai/settings/keys> |

`factoid models` and `factoid doctor` name any workload whose provider cannot serve it. Cloudflare's Clef, as a
decision model, is planned and not built yet.

Search needs no service to start. With no `search` setting, Factoid keeps a local index in the project's SQLite store.
Using turbopuffer, or a turbopuffer-compatible endpoint, is optional. Factoid works with
[blowfish](https://open.endgame.io/blowfish), our self-hostable search engine that speaks the turbopuffer API on
any S3-compatible bucket, so a project can run turbopuffer search without an account. Configure either one in
`settings.py`, and set its key with `factoid keys set turbopuffer` (keys at <https://turbopuffer.com/dashboard>), or point
`TURBOPUFFER_BASE_URL` at a blowfish server.

### Start a project and add keys

```sh
mkdir acme && cd acme
factoid init                       # the jev models; or --models openai, or --models fireworks (experimental)
factoid keys set                   # asks for each key settings.py needs, and says where to get it
factoid doctor                     # one small call per workload
```

`factoid init` uses the jev models unless you pass `--models`. In an existing project, run `factoid init --models
<preset>` to switch `settings.py` to another preset. If you edited its models, init leaves the file alone and prints the
lines to use instead. `factoid init` never overwrites existing files, but it recreates deleted sample files. To get the
current sample eval after an upgrade, delete `evals/sample.py` and run `factoid init`. `factoid keys set` needs a
terminal to prompt for a key. Without one, such as under a coding agent's `!` prompt, run it in your own terminal or
pipe the key in: `factoid keys set openai < key.txt`.

`factoid keys set` with no provider lists the keys the project's models need and whether each is set. It then asks for
each missing one, with a link to the page where you create it. Press Enter to skip a key. `factoid keys set fireworks`
sets a single key. `factoid keys list` shows every provider, whether its key is set and where it comes from, what in
the project uses it, and where to get one.

Keys are checked for spaces, control characters, and terminal escape codes, and against the provider's prefix
(Fireworks keys start with `fw_`). They are stored in `~/.factoid/.env`. With `--project`, a key is for one project
only, and is stored at `~/.factoid/projects/<id>/.env`, where `<id>` is the project's `id` in `pyproject.toml`; keys
never go in the project folder. A project's keys beat `~/.factoid/.env`. An environment variable with the standard name, such as `FIREWORKS_API_KEY`, takes precedence.

Each provider has a base URL variable, like `FIREWORKS_BASE_URL`. Base URLs can go in the same `.env` files as keys.
Setting one sends that provider's calls to another address, like a gateway or proxy that adds credentials itself. With a
base URL set, a key is optional; if set, it is still sent. Calls without a key or base URL fail at once with an error
naming the missing key and `factoid keys set`.

An app that keeps keys in a secrets store can pass one to a model in code instead:
`Model("fireworks/glm-5p3-flash", api_key=lambda: vault.read("fireworks"))`. The key can be a string or a function.
A function is called for each request, so a rotated key is picked up. `base_url=` sets the address the same way.
Neither one goes into a request body, the call cache, or the model's repr.

Here is `factoid doctor` for a project made with `--models openai`, with its key set:

```text
choose     ok
generate   ok
embed      ok
search     ok (LocalIndex)
```

`rerank` is optional, and a new project has none. Without it, search returns results in retrieval order. Add one in
`settings.py`, such as `fireworks/qwen3-reranker-8b`. Workload assignments live in `settings.py`, which is Python, so a
project can compute them. `factoid models` shows each workload, its model, and whether its key is set. It and
`factoid doctor` work anywhere: outside a project, they use the default models.

### Use

`factoid init` wrote sample classes, a sample contract, and an eval. Run these commands to ingest the sample contract,
inspect what came out, and score the project:

```sh
factoid ingest ./sample_docs                     # documents in, facts and entities out
factoid facts list                               # every fact, with its id
factoid search "Vega consent"
factoid read <fact id>                           # one fact, its quotes, its entities, and its history
factoid entities list
factoid eval                                     # score the project against labeled data
factoid eval --vary fact_evals=none,decision_floors  # compare fact eval chains on the same documents
```

The sample contract has three facts: the signing, the consent clause, and the liability cap. The sample eval checks that
all three are extracted as separate facts, that the consent fact has the `consent_required` trait, and that the cap fact
has `liability_cap`. Get `<fact id>` from `factoid facts list` or `factoid search`. Pass `--data-dir
runs/<time>/<suite>/<variant>` to `facts list`, `search`, `read`, `stats`, or `entities list` to read an eval run's
store.

Ingesting a file that has not changed skips it. Pass `--again` to ingest it anyway. When a changed file is ingested
again, facts that say the same thing keep their ids.

Model calls are cached in `.factoid/calls.db`. A request identical to one made before replays the saved answer, costs
nothing, and gives the same result. Both `ingest` and `eval` print how many calls were replayed. Right after `ingest`,
`eval` replays almost everything, so its first score is a rescoring of saved answers. Pass `--fresh` on either command
to call the models again.

The cache holds the text of every request and answer, document text included. A project that must not keep third-party
text sets `call_log = "metadata"` in its settings, which keeps only the model, step, and tokens of each call, or
`call_log = "none"`, which keeps nothing. Either way, nothing replays.

The store keeps each document's text too, in its documents, chunks, revisions, and quotes. Set
`keep_document_text = False` to keep none of it. The store then keeps each document's uri, title, metadata, and content
hash, the offsets of its passages and quotes, a hash of each quote's text, its chunks' situations and vectors, and all
facts and entities. Chunk search works by vector only. Ingest still reads the whole text while it runs, so it makes the
same facts. Factoid warns at start when `call_log` is still "full", because the call log then keeps the text of every
request; a project that must keep no third-party text sets both. The setting applies to what is saved after it
changes: text saved before stays, and a document ingested again drops it from that document's row, chunks, and new
quotes.

With no text kept, a read that shows quotes (`factoid read`, the HTTP API, and MCP) calls the document class's
`fetch_text(uri)`, if it defines one, to get the text from its source:

```python
class Ticket(ProseDocument):
    @classmethod
    def fetch_text(cls, uri: str) -> str | None:
        return helpdesk.ticket_body(uri)  # None when the source no longer has it
```

When the text's hash matches the stored document's, quotes are cut from it by their offsets. Otherwise a quote's text is
null, and `factoid read` prints its offsets. The Parquet export does not call `fetch_text`: it writes null for quote and
document text.

An eval never reads the project store. Each run builds its own store under `runs/` from the same documents. Evals replay
saved answers, including those from a `--fresh` run. Because of this, an eval after `eval --fresh` scores that run's
answers. Those results can differ from the facts `ingest` stored in the project.

### Commands

Built today: `init`, `keys set`, `keys list`, `models`, `doctor`, `ingest`, `facts list`, `search`, `read`,
`stats`, `entities list`, `entities kinds`, `eval`, `export`, `serve`, `mcp`, `steps show`, `classifiers show`, `prompts show`, and
`struct`.

The rest of this README also describes a command that is planned and not built yet: `rebuild`. It is marked "(planned)" where it appears. A guided terminal UI, `factoid setup`, is planned too.
`SPEC.md` section 17 lists what is built.

## Documents, facts, and entities

Each document type, entity type, fact class, and trait is a Python class. A class holds its definition, prompt or
question wording, model settings, and custom pipeline code. In the example below, a law firm advises its
client Acme on acquiring Orion and reviews Orion's contracts, including Orion's supply agreement with Vega:

```text
acme/
├── pyproject.toml
├── app/             # the project's code; `factoid init` names it app
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # document sources
│   ├── documents.py   # Contract, CounselEmail, and ContractRegister
│   ├── entities.py    # Company, Agreement, and Person
│   ├── facts.py       # SourceFact, CounselFact, and traits
│   ├── fact_evals.py  # custom fact evals
│   └── prompts/
│       ├── counsel_email_extract.md.j2
│       └── thread_summary.md.j2
└── evals/diligence.py
```

`Document` has two base subclasses: `ProseDocument` for text and `StructuredDocument` for tabular
rows. Every pipeline step is a classmethod or an instance method on the class that owns it:

| Class | Classmethods | Instance methods |
| --- | --- | --- |
| `Document` | `classify(raw, judgments)` | Prose: `segment`, `chunk`, `situate`, and `extract`. Structured: `read`, `identify`, `row_facts`, and `text_facts`. Both: `discover`, `context`, the `source_datetime` property, and `ingest`, which runs the steps in order. |
| `Fact` | Reads, such as `search` | `validate`, `evaluate`, `repair`, `assess` (traits and time properties, in one request), `expiration`, `link`, `resolve`, and `save`; outcomes `supersede`, `end`, `correct`, `contradict`, `retract`, and `restore`. |
| `Entity` | `identify(mention)`, `create`, and reads `find` and `where` | `claim`, `merge`, `split`, `retype`, `related`, and `facts`. |

Every step has `before_<step>` and `after_<step>` hooks, which do nothing by default and are always called.
`before_<step>` can raise `factoid.Skip` to skip the step for that item; `after_<step>` gets the result and can return
a replacement, or `None` to keep it. Overriding an outcome such as `supersede`, or defining `after_supersede`, is how a
project reacts to a change. `factoid steps show CounselEmail` lists the steps and where each is defined.

A class is stored under its Python name. When two classes in one app share a name, the app refuses to start; set
`class_name = "DealRisk"` on one of them to store it under another name. Two apps in one process can each have their
own `Risk`: pass each app its own lists (`Factoid(facts=[...], entities=[...], documents=[...])`).

Every class supports incremental levels of customization, and every level is optional:

- **No classes, or plain declarations**: run on the defaults with no code, or subclass a base class and write a
  docstring.
- **Class settings**: set attributes for guidance, examples, traits, fact evals, thresholds, and models.
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
        return self.metadata.get("sent_at")

    def extract(self, chunk):
        # Summarize the quoted thread first, then extract with that summary as context.
        thread = self.generate(template("prompts/thread_summary.md.j2"), passages=chunk.passages)
        return super().extract(chunk, thread=thread)
```

Every document has `source_datetime`, its own date from its metadata, such as an email's sent time, a contract's signing
date, or a wiki page's last edit. Factoid passes `source_datetime` to the extractor ahead of the passages so relative
dates in the text resolve against the document's date, never against ingest time. Accepted values are ISO-8601 strings
with a timezone offset or `Z`, epoch seconds, milliseconds, or microseconds, and timezone-aware `datetime` objects.

When `factoid ingest` reads a file, it also reads a JSON file next to it named `<file>.meta.json`, such as
`supply.txt.meta.json`, if one exists. Its keys become the document's metadata: a date like `signed_at` or `sent_at`, a
title, parties, or anything a class reads. The classifier sees the metadata too. A class should read metadata with
`self.metadata.get("signed_at")`, so a file without a sidecar still ingests; `source_datetime` is then `None`, and
relative dates stay unresolved. In Python, `app.ingest(path, metadata={...})` adds or overrides keys.

### Chunking

A long prose document does not fit in one extraction call, so Factoid cuts the document into chunks. First, `segment`
splits the document into passages, such as speaker turns or paragraphs. Next, `chunk` groups those passages into chunks.
A chunk never splits a passage.

Two settings on a prose document class control chunking:

- `chunk_size`: the largest chunk, in characters.
- `chunk_overlap`: how much of the previous chunk is repeated at the start of the next chunk. This setting takes a
  number of characters (`400`) or a share of `chunk_size` as a string (`"15%"`). Because `chunk_overlap` is one setting
  with two forms, the two forms can never disagree. Overlap is rounded to whole passages.

A passage is a paragraph or a speaker turn, split into sentences when it is longer than `max_passage` (1,200
characters). Every fact from a short paragraph quotes the whole paragraph. To quote single sentences instead, set
`sentence_passages = True` on the document class. It is off by default because the evals were run with paragraphs.

A `segment` override can put other details about a passage in `passage.attrs`. For example, it can note which side of
a call spoke (`{"side": "customer"}`). Each quote of that passage keeps a copy in Python, the HTTP results, and the
MCP results.

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
        return self.metadata.get("signed_at")
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

`StructuredDocument` ingests CSV, JSONL, JSON arrays, and records from structured sources.

A structured document subclass defines a column map once per file layout. Each column is an entity identity (an exact
link, with no model call), an entity property, a value with a sentence template (one fact per cell, cited to the file,
row, and column), free text run through the prose pipeline with the row's entities already known, or ignored.
`row_entity` names the entity class each row represents, `key` names the column that identifies a row across re-imports,
and `when` names the column that dates the row. On re-import, a changed value for the same `key` and column supersedes
the old fact by rule, with no model call. Files that point to the same entity connect through that entity.

```python
# documents.py
from factoid import Identity, Ignore, Property, StructuredDocument, Text
from app.entities import Agreement

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

A templated cell comes from the data with no model call, so its fact skips fact evals and resolve. The fact still gets
traits and time properties. A row's date comes from the `when` column, or from the document's `source_datetime` if that
column is empty. `key` and `when` do not need to be in `columns`. `Identity` takes an optional `name` template for
entities Factoid creates, such as `Identity(Company, "company_id", name="{company_name}")`. Without `name`, Factoid uses
the cell's value as the entity's name. To turn records from an API or a database into a document, call
`ContractRegister.from_records(records, uri="crm:contracts")`.

Factoid matches a tabular file to a structured class by its header first, with the decision model as a fallback. The
`factoid struct` commands inspect a file, generate a parser class (or print the prompt for a coding agent), and dry-run
the parser before ingesting:

```sh
factoid struct inspect contract_register.csv                         # columns, sample values, and guessed identities
factoid struct parser contract_register.csv --name ContractRegister  # write a parser class (--prompt prints the prompt)
factoid struct try contract_register.csv --rows 20                   # dry-run on 20 rows and print facts and citations
factoid ingest contract_register.csv                                 # import facts and entity properties
```

### Facts, traits, and time

A fact is one self-contained sentence, exact source quotes (with who said each quote and when), links to one or more
entities, zero or more traits, and properties that say how it ages. A fact has no typed fields; the sentence carries the
meaning.

A trait is a `FactTrait` subclass whose docstring is the definition the model reads. With no `decide` method, the trait
is one yes-or-no question built from the docstring and compared against `threshold` (0.5 unless the class or the
decision model sets another; `cls.bar()` gives it); `decide` gets that answer (such as `judgments.liability_cap`) plus
any factor questions it declares with `@judge`. Traits can also define `after_` hooks for facts that carry them. A fact
can carry several traits, and a fact that matches no trait is kept.

In the same `assess` request, Factoid fills in each fact's time properties:

- `valid_from`: when the fact became true or happened, from the text resolved against `source_datetime`. A future date
  is allowed.
- `expires`: `"never"` (history, such as a signing), `"estimated"` (true until something changes it, such as a contract
  clause), or `"at_deadline"` (settled by a date, such as a promised reply).
- `valid_until`: the exact end or due time, when the text gives one.
- `lifetime`: for an estimated fact, a distribution over ranges from an hour to longer than a few years. Factoid uses it
  to compute the chance the fact is still true at a given time. Each confirmation restarts the clock.

The base `Fact` class holds the default questions and ranges that fill these in, and a fact class can change them.

Many projects need only one fact class, and running with one fact class and no subclass at all is fine. Here there are
two because a lawyer's conclusion is a different kind of evidence from what a contract says: a `CounselFact` cannot
contradict a `SourceFact`, and it can be hidden from readers outside the deal team. One document can produce both (an
email from our lawyer quotes a contract and states a view), and Factoid classifies each extracted fact before `assess`
runs.

```python
# facts.py
from factoid import Fact, FactTrait, Noul, judge

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

class SourceFact(Fact):
    """What a contract, a client, or the other side says."""
    traits = [ChangeOfControl, ConsentRequired, Deadline, LiabilityCap]

class CounselFact(Fact):
    """What our own lawyers concluded."""
    traits = [ClosingRisk]
```

| Fact sentence | Class | Traits | Time |
| --- | --- | --- | --- |
| Orion's supply agreement with Vega lets Vega terminate if a competitor of Vega acquires Orion. | `SourceFact` | `ChangeOfControl` | estimated, years |
| Orion may not assign the Vega supply agreement without Vega's written consent. | `SourceFact` | `ConsentRequired` | estimated, years |
| Vega must answer a consent request within 15 business days. | `SourceFact` | `ConsentRequired`, `Deadline` | estimated, years |
| Amendment 2 raises the liability cap in the Vega supply agreement to $2M from January 1, 2027. | `SourceFact` | `LiabilityCap` | valid from January 1, 2027; estimated, years |
| Acme's deal counsel concluded that Vega's consent is a closing risk. | `CounselFact` | `ClosingRisk` | estimated, weeks |

Amendment 2's fact supersedes the old liability cap fact from January 1, 2027, and leaves the rest of the agreement
alone.

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

Every entity link on a fact carries a role (`subject`, `about`, `speaker`, or `context`), the method that created the
link, and a confidence score. Linking proceeds from sure to unsure and stops at the first step that settles the mention:

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

A fact from a call note often does not name the account the note is about ("The rep agreed to send a pilot plan."). A
document class can say what it is about with `context_entities()`. It returns mentions with a name, a kind, and keys,
such as `Mention("Brightwater Logistics", kind="Account", keys={"crm_id": "001A"})`. Each mention is linked by key,
then by exact name, or created. No model call is made. Every fact from the document gets the entity as a `context`
link. The extractor is asked to name the entity in facts about it.

Untyped entities are kept, linked, and searchable. `factoid entities kinds` lists untyped kinds by entity and fact
count. `factoid entities merge KEEP GONE` folds one entity into another. `factoid entities split` moves chosen facts to
a new entity. `entity.merge(other)` and `entity.split(facts, name)` do the same in Python. Editing entities, deleting
entities, and merging over HTTP and MCP are planned.
`factoid entities retype --kind "court" Court` is also planned: it will promote matching entities to a declared class
with the decision model confirming each one and without re-extracting.

When a new entity is stored, Factoid runs a claiming step across existing facts, searching stored facts for the entity's
names and asking the decision model to confirm each hit. Two entities that share a unique key merge by rule, while two
entities that share only a weak name go to a yes-or-no question with a high floor. Merges and splits are logged as
events.

Entities are optional. An app may already keep its own records (accounts, people, and projects) and link names to them
itself. It can ignore Factoid's entities and read each fact's mentions as plain text, with their roles. An app that
wants Factoid's links to follow its records can keep them in step with
`Account.upsert(name, keys={"crm_id": "001A"}, aliases=[...])`. This finds the entity by key and renames or updates it,
or creates it, with no model call. A renamed entity keeps its old name as an alias. Merges and splits made in the app's
own system map to `merge` and `split`.

Relations between entities require no schema or relation class. Factoid counts co-mentions across shared facts and
identifies relation facts: current facts that never expire or last months or longer and link two or more entities.
Calling `entity.related()` returns connected entities with their co-mention counts and current relation facts,
weighted by freshness.

### Resolving facts

For each new fact, Factoid gathers the stored facts that share one or more linked entities with it and asks the decision
model one question with six answers: `duplicate`, `supersedes`, `ends`, `corrects`, `contradicts`, or `unrelated`.
`supersedes` replaces an older value that was true until then, `ends` marks that a state stopped without setting a new
value, and `corrects` marks an older fact as wrong from the start.

When two facts contradict, both are marked `contradicted` and point to each other. Reads show both. Search results
include contradicting facts by default: `contradictions=3` returns up to three in full plus the IDs of any others,
`contradictions=0` returns IDs only, and `contradictions=False` leaves them out.

There are two ways to settle a contradiction. When a newer fact supersedes, ends, or corrects one side, the other side
stands. Otherwise, a person or agent chooses what to keep:

```sh
factoid contradictions                  # open pairs, newest first; --json for scripts
factoid contradictions settle FACT_A FACT_B --keep FACT_A --reason "the signed copy says $3M"
```

`--keep` takes one of the two IDs, retracting the other, or `both` when the facts turn out not to conflict. Either way,
both facts get a `fact.settled` event with the reason and who settled it. An unsettled contradiction goes stale when its
facts pass `valid_until`. It is listed as stale and is never settled automatically. The HTTP API and the MCP server can
list and settle contradictions too.

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
from factoid import Choice, Noul, ProseDocument, judge

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

Two classes claiming one file is an error. `factoid ingest` skips a file that no class claims, lists it at the end,
and suggests `--as <Class>`. `classify_view`
controls what the classifier sees, and `factoid classifiers show` lists the registry.

### Default fact evals

Every candidate fact passes a default chain of fact evals before being stored. A fact eval decides one thing: whether
a candidate fact is good enough to keep. A project gets this chain without writing any code, and custom fact evals run
on top of the default chain while keeping the built-in checks. The chain runs in order and rejects a candidate at the
first failure, so the cheap fact eval goes first.

| Fact eval | Responsibility |
| --- | --- |
| `nli` | Small entailment model that checks that the cited passage entails the sentence (planned: no NLI model is wired up yet, so it is skipped, and `factoid eval` says so). |
| `decision_floors` | Six yes-or-no questions in one decision-model call. Each probability has a floor; all six must pass. |

Each `decision_floors` answer is a probability that must clear the floor for that question:

- `grounded`: The cited passages support the sentence.
- `attribution`: Who said the sentence, and whether the sentence was certain or negated, match the source.
- `self_contained`: The sentence names its subject and what it refers to, with no unresolved pronouns or relative
  dates.
- `atomic`: The sentence states one claim.
- `useful`: The fact is worth keeping.
- `distinct`: No stored fact already states the same claim.

The floors are starting values set from eval runs, and calibration from labeled data is planned. A candidate that fails
only checks a rewording or a split can fix (`self_contained`, `atomic`, and `attribution`) gets one repair, and Factoid
evaluates the repaired sentences again. The repair names what pronouns and relative dates refer to, or splits a compound
fact. `repair_guidance` on a document or fact class adds rules to the repair prompt, and the prompt's `guidance` and
`references` blocks can be replaced by a project template that extends `factoid/repair.md.j2`. A fact that fails
`grounded` gets one repair too, which trims it to what its passages say; `DecisionFloors(repair_grounded=False)` turns
that off. The trait and time questions ride in the fact evals' request, which saves one decision request per fact;
`assess_with_evaluate = False` on a fact class asks them in a request of their own. The fact evals and repair see the
document text just before the fact's first cited passage (`evidence_context`, 1,200 characters by default; 0 for
structured documents). The extractor resolves "he" or "this aircraft" from earlier text, so the checks need that text to
confirm the name. A project can change one floor or add a custom fact eval without replacing the default chain:

```python
# facts.py
from factoid import Fact
from factoid.fact_evals import DecisionFloors, Nli
from app.fact_evals import CitesSourceEval

class SourceFact(Fact):
    """What a contract, a client, or the other side says."""
    traits = [ChangeOfControl, ConsentRequired, Deadline, LiabilityCap]
    fact_evals = [Nli(), DecisionFloors(useful=0.8)]             # the default chain, with one floor raised

class CounselFact(Fact):
    """What our own lawyers concluded."""
    traits = [ClosingRisk]
    fact_evals = [*Fact.fact_evals, CitesSourceEval]  # the chain, plus a check of our own
```

`CitesSourceEval` checks that the conclusion points to a source fact.

Both prose and structured document classes can set their own `fact_evals` chain, because how strict to be depends on
the source: a transcript sentence leans on earlier turns more than a contract clause does. `fact_evals` on a document
class wins over the fact class's chain for facts from that document, and `None` (the default) means the fact class's
chain. `DecisionFloors` questions can also be reworded, added, or dropped, as well as given a floor. Every question
needs a floor:

```python
# documents.py
from factoid import DecisionFloors, Nli, Noul, ProseDocument

class Transcript(ProseDocument):
    """A broadcast interview or news segment transcript."""
    fact_evals = [Nli(), DecisionFloors(
        useful=0.5,
        questions={
            "useful": Noul("Would a reporter look this claim up later? Greetings and program promos are not useful."),
            "on_topic": Noul("Is the fact about the segment's story?"),
        },
        on_topic=0.4,
    )]
```

`factoid eval --vary fact_evals=none,decision_floors` compares chains on the same documents. A value written
`@module:name` uses a chain the project defines, such as `--vary fact_evals=@evals.variants:STRICT`.

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

Factoid prices calls from list prices in `src/factoid/prices.json` (dollars per million tokens, for Jev, Rune, GLM, and
the Fireworks embedders and reranker). `Model(name, price_in=, price_out=)` overrides them. After `ingest` and `eval`,
the model calls line shows the cost at list prices, what it would be with nothing replayed, and the cost by step. Jev
and Rune charge for input tokens only.

```python
# settings.py
from factoid import Model, Settings
from factoid.search import Turbopuffer
from factoid.stores import Sqlite

class Project(Settings):
    store = Sqlite(path=".factoid/acme.db")            # the system of record
    models = {
        "choose": Model("typesafe/jev-1.14.0"),        # classify, evaluate facts, assess, and resolve
        "generate": Model("fireworks/glm-5p3-flash"),  # extract and repair, unless a step has its own model
        "situate": Model("fireworks/glm-5p3-flash"),   # optional: a model for one generation step
        "embed": Model("openai/text-embedding-3-small"),
        "rerank": Model("fireworks/qwen3-reranker-8b"),    # optional
    }
    search = Turbopuffer(
        base_url="https://gcp-us-central1.turbopuffer.com",  # or a turbopuffer-compatible one, like blowfish
        retrieve="hybrid-rrf",
        budget_tokens=1500,
    )
    model_attempts = 3                                 # tries per model call (12 by default, for big evals)
    model_deadline = 120                               # seconds one call may take in all, waits included
```

`--vary` sets a class attribute or setting for each value on the same documents, such as
`--vary fact_evals=none,decision_floors` or `--vary situate=true,false`. For a Python value (a chain of fact evals, a
set of models, or a replacement method), define it in a module and name it with `@module:NAME`, such as
`--vary models=@evals.variants:RUNE`. A plain string that would replace a method is refused with an error.

### Eval suites

An eval suite is a Python class in the project's `evals/` folder that subclasses `factoid.evals.Suite`. `documents()`
yields what to ingest: a `Raw` document (`text`, `metadata`, `uri`, and `title`) goes through classification the way
`factoid ingest` does, and a `Document` instance skips it. `score(app, results)` gets the app and one `IngestResult`
per document (each has `.document`, `.facts`, and `.rejected`) and returns a dict of metrics, which becomes the
scorecard. `factoid.evals` has `prf(tp, fp, fn)` for precision, recall, and F1, plus `aupr(scores, labels)` and
`precision_at_recall(scores, labels, recall)` for scores.

`factoid eval` runs every suite, or the ones named. Each run gets a fresh store under `runs/<time>/<suite>/<variant>/`.
`parallel = N` ingests `N` documents at once when they are independent. `factoid init` writes `evals/sample.py` as a
starting point.

```python
# evals/diligence.py
import json
from pathlib import Path

from factoid import Raw
from factoid.evals import Suite, prf

DOCS = Path(__file__).parent.parent / "sample_docs"


class Diligence(Suite):
    name = "diligence"

    def documents(self, limit=None):
        for path in sorted(DOCS.glob("*.txt"))[:limit]:
            meta_file = path.with_name(path.name + ".meta.json")
            meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
            yield Raw(path.read_text(), meta, uri=str(path), title=meta.get("title"))

    def score(self, app, results):
        expected = {"consent_required", "liability_cap"}
        found = {t for r in results for f in r.facts for t in f.trait_names}
        return {"traits": prf(len(expected & found), len(found - expected), len(expected - found))}
```

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
Fact.search("change of control", about=vega)                      # includes up to 3 contradicting facts by default
Fact.search("liability cap", about=agreement, as_of="2027-02-01")   # weight relevance by validity as of a date
CounselFact.search("closing risk")                                # search scoped to one fact class
Fact.unlinked(since="30d")                                        # facts with a mention that matched no entity
Chunk.search("assignment consent", about=agreement)               # search source chunks, indexed with situations
```

Search weights each fact's score by the probability that the fact is still valid at `as_of=` (now by default), so stale
facts stay findable while ranking lower. Pass `freshness="any"` to disable freshness weighting for historical queries,
or `valid_at=` to filter to facts likely still valid. Source chunks live in their own namespace and are searched with
`Chunk.search(...)`. Searching facts and chunks together in one ranked list is planned.

`factoid stats` counts documents, facts, and entities by class and counts facts by status. It also reports facts with
no trait, unlinked mentions, single-fact entities, facts past their expected validity, and open contradictions. Pass
`--examples 3` to add up to three sample facts per fact class, from different documents where it can, and the three
entities with the most facts per entity class.
Use `--data-dir` to point `factoid stats` at another store, such as an eval run's folder.

Class reads such as `Fact.search` and `Company.find` use the active app: the last `Factoid` made, unless a block sets
another. With several apps in one process, wrap class reads in `with app.active():`. App methods (`app.ingest`,
`app.search_facts`, and the rest) always use their own app in every worker thread.

## Postgres

A project keeps its facts in a SQLite file by default. For many processes writing at once, or a hosted service, keep
them in Postgres instead. Install `factoid[postgres]` (psycopg 3) and set the store in `settings.py`:

```python
from factoid import Settings
from factoid.stores import Postgres

class Project(Settings):
    store = Postgres()                  # the URL comes from FACTOID_POSTGRES_URL
    # store = Postgres(schema="acme")   # one schema per project, so projects can share a database
```

Put the URL in the environment, not in `settings.py`: `FACTOID_POSTGRES_URL=postgresql://user:pass@host/db`. With no
URL at all, libpq's own variables (`PGHOST`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`) and `~/.pgpass` apply.
Factoid creates the schema (`factoid` unless you name one) and its tables on first use.

Postgres holds the same tables as SQLite: documents, facts, quotes, mentions, entities, relations, and the event log.
Every write takes a lock for the schema before it starts, so writes from all processes apply one at a time. Each write
is short, and model calls happen outside it, so ingest from several processes still runs side by side. Events are
numbered under the same lock, so an export never skips an event that committed late, and two runs of one export take
turns. The call cache (`.factoid/calls.db`) and the local search index (`.factoid/index.db`) stay in the project
folder. An eval run, or a command given `--data-dir`, uses a SQLite file in its own folder, so it never writes to the
shared store.

Search can live in Postgres too, with `search = PostgresIndex()` from `factoid.postgres`. It needs the pgvector
extension. Vector search is exact cosine search, as in the local index. The keyword side is Postgres full text search
ranked with `ts_rank`, which ranks close to BM25 but not the same, so a project that moves its index can see different
search results and decisions.

To run the store and index tests against Postgres, set `FACTOID_TEST_POSTGRES_URL` to a database they may create
schemas in. `FACTOID_TEST_STORE=postgres` and `FACTOID_TEST_SEARCH=postgres` also run the rest of the suite with a
Postgres store and index.

## Exports

An export sends a project's facts to another system. There are two kinds. `Parquet` writes files to a local folder or
to S3 for a data warehouse. `Turbopuffer` writes to a turbopuffer namespace for an app to search. Declare exports by
name in `settings.py`:

```python
from factoid import Settings
from factoid.exports import Parquet, Turbopuffer


class Project(Settings):
    exports = {
        "warehouse": Parquet("s3://my-bucket/facts/"),
        "search": Turbopuffer(namespace="acme-facts"),
    }
    export_after_ingest = False  # True runs every export after each ingest
```

```sh
factoid export                 # every export
factoid export warehouse       # one export
factoid export search --full   # send everything again
```

Each run reads the event log and sends what changed since that export's last run. A superseded or retracted fact is
sent again with its new status and dates. It is never deleted. Each export tracks its own position in the log, so an
export that falls behind does not block the others. When `export_after_ingest = True`, `factoid ingest` runs every
export at the end. A failed export prints a warning without failing the ingest. The next run catches up.

### Parquet

The Parquet export needs pyarrow. Install `factoid[parquet]` or add `pyarrow` to the project's dependencies. It writes
four folders: `facts`, `entities`, `documents`, and `events`. Relative paths resolve under the project folder. Each run
adds one file per folder, named after the events it covers. When a row changes again, the new version appears in a later
file. The current version of a row is the one with the highest `exported_through`. Each `facts` row stores its mentions
and quotes as nested lists. Passing `--full` removes the files this export wrote earlier and writes every row again.

`Parquet(path, vectors=True)` adds a `vector` column (a list of 32-bit floats) and an `embedding_model` column.
Warehouses read this list as an array without a custom parser. BigQuery reads it as `ARRAY<FLOAT64>` with list inference
on, Databricks reads it as `array<float>`, and DuckDB and ClickHouse read it natively. Snowflake needs one cast to
`VECTOR(FLOAT, N)`.

S3 credentials come from standard AWS environment variables and files. For an S3-compatible store such as R2 or MinIO,
set `AWS_ENDPOINT_URL`.

DuckDB reads the current version of each fact like this:

```sql
select * from 'exports/facts/*.parquet'
qualify row_number() over (partition by id order by exported_through desc) = 1;
```

### Turbopuffer

The turbopuffer export writes one row per fact, keyed by the fact's id. Each row includes its vector, `text` (with a
BM25 index), `class`, `traits`, `status`, `valid_from`, `valid_until`, `document_id`, and `entity_ids`. Entities,
documents, and quotes are not included. Join them from the Parquet files or Factoid's API. This namespace is separate
from the index Factoid searches itself. The export uses `TURBOPUFFER_API_KEY` or `TURBOPUFFER_BASE_URL`. Passing
`--full` deletes the namespace and writes every fact again. In a turbopuffer filter, a fact with no `valid_from` still
matches `valid_from < date`. Add `["valid_from", "NotEq", null]` when you need to exclude those facts.

## HTTP API

`factoid serve` makes a project's facts available as JSON over HTTP for apps and pipelines not written in Python.

```sh
factoid serve                         # http://127.0.0.1:8765
factoid serve --port 9000 --data-dir runs/20261118-034725/cuad/default
```

| Route | Returns |
|---|---|
| `GET /search?q=...` | Facts that match, best first. Also `about` (an entity), `as_of` (a date), `top_k`, `min_score` (with a reranker), and `chunks=true`. |
| `GET /facts` | Facts in the order they were added. Also `document`, `trait`, `status`, and `limit`. |
| `GET /facts/<id>` | One fact with its quotes, mentions, relations, and history. |
| `GET /entities` | Entities with their fact counts. Also `class`, `name`, and `limit`. |
| `GET /entities/<name or id>` | One entity, its current facts, and the entities it appears with most. |
| `GET /stats` | Counts by class and status. |
| `GET /documents/<id>` | One document's uri, title, date, metadata, and number of earlier revisions. |
| `GET /events?after=N` | Events after sequence number `N`, oldest first, to read what changed. Also `limit`. |
| `GET /contradictions` | Open contradictions, newest first, with both facts. Also `stale=false` and `limit`. |
| `POST /contradictions/settle` | Settles one with `{"fact_id", "other_id", "keep", "reason", "by"}`. `keep` is one of the two IDs or `both`. |
| `POST /ingest` | Ingests `{"text": ..., "document_type", "uri", "title", "metadata"}` and returns the facts kept and rejected. |
| `GET /health` | `{"ok": true, "version": ...}` |

```sh
curl "http://127.0.0.1:8765/search?q=liability%20cap&as_of=2026-06-01"
```

Each fact includes its text, status, traits, dates, quotes, mentions, its document's uri and metadata, and the
probability that it still holds now (`still_valid`). A bare date in `as_of` means midnight UTC. Errors return `{"error": ...}` with a 400, 401, or 404
status.

The server listens on 127.0.0.1 by default. To serve other machines, set `FACTOID_API_TOKEN` and pass `--host`. Every
request then requires `Authorization: Bearer <token>`. Writes run one at a time; reads do not wait for them. The
server uses only the standard library.

## MCP

`factoid mcp` serves a project's facts to an agent as MCP tools over stdio. To add it to Claude Code, run this in the
project folder:

```sh
claude mcp add factoid -- factoid mcp                # or: factoid mcp --read-only
```

| Tool | What it does |
|---|---|
| `search_facts` | Searches facts, with `about` (an entity), `as_of` (a date), `top_k`, and `min_score`. |
| `read_fact` | One fact with its quotes, mentions, relations, and history. |
| `list_facts` | Facts from one document, with one trait, or with one status. |
| `find_entities` | Entities by part of a name or by class, with their fact counts. |
| `read_entity` | One entity, its current facts, and the entities it appears with most. |
| `stats` | Counts by class and status. |
| `read_events` | Events after a sequence number, to read what changed. |
| `list_contradictions` | Open contradictions, newest first, with both facts. |
| `settle_contradiction` | Settles one by keeping one fact or both, with a reason. `--read-only` leaves it out. |
| `ingest_text` | Adds a document's text and returns the facts kept and rejected. `--read-only` leaves it out. |

The tools return the same JSON as the HTTP API. A failed call returns an error the agent can read, and the server keeps
running. Pass `--data-dir` to serve another store, such as an eval run's folder. The server uses only the standard
library.

## Usage

- **Standalone CLI project.** Manage a RAG corpus in its own directory, tune chunking and extraction, and evaluate
  prompt, extractor, and fact eval choices with `factoid ingest`, `factoid search`, and `factoid eval`.
- **Agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes, and chats,
  then expose fact search and writes to an agent through `factoid mcp` ([MCP](#mcp)) or the CLI.
- **Python library or HTTP service.** Run `factoid serve` as an HTTP sidecar ([HTTP API](#http-api)), or use Factoid
  as a library inside an application and pass classes to `Factoid(...)`:

```python
from factoid import Entity, Fact, Factoid, Model, ProseDocument, Settings

class Company(Entity):
    """A company that is a party to a deal or a contract."""
    unique_keys = ["domain"]

class DealMemo(ProseDocument):
    """A memo a lawyer wrote about a deal."""

class ServiceSettings(Settings):
    models = {"generate": Model("fireworks/glm-5p3-flash"), "choose": Model("typesafe/jev-1.14.0")}

factoid = Factoid(settings=ServiceSettings, documents=[DealMemo], entities=[Company])
factoid.ingest_text("Orion's lease in Austin ends in March 2027.", document_type=DealMemo)
hits = Fact.search("Orion lease")      # fact sentences, source quotes, and any contradictions
orion = Company.find("Orion")
recent = orion.facts(since="30d")      # every recent fact linked to Orion
```

## Design

- **Fact-level retrieval.** Search returns short, self-contained sentences within a token budget. On 200 questions about
  news transcripts, facts read at 512 tokens score 0.92, and chunks read at 2,048 tokens score 0.87. At 8,192 tokens,
  the two are even ([examples/mediasum](https://github.com/Endgame-Labs/factoid/blob/main/examples/mediasum/README.md),
  after [RAG Deserves an Index](https://arxiv.org/abs/2608.20845)). On contract questions about the terms in force on a
  date, facts and reranked chunks tie at 2,000 tokens
  ([examples/legal](https://github.com/Endgame-Labs/factoid/blob/main/examples/legal/README.md)).
- **Deterministic provenance.** Prose extraction cites numbered passages and structured extraction cites the file, row,
  and column; Factoid's code attaches the exact quote or cell, speaker, and timestamp.
- **Event log for history.** Current state in SQLite is the source of truth. Each change also writes a fact event
  (`added`, `restated`, `superseded`, `ended`, `corrected`, `contradicted`, `replaced`, `retracted`, or `restored`)
  or an entity event (`linked`, `merged`, or `split`) to a log in the same database. The log records where each fact came from and how it
  changed, so a response can include the fact a newer one superseded.
- **Eval-selected defaults.** Default strategies across `classify`, `segment`, `extract`, `evaluate`, `repair`,
  `assess`, `link`, and `resolve` come from eval results. `factoid eval` measures accuracy, cost, and latency on labeled
  data.
- **Pluggable backends.** Storage, search, sources (`folder`, `jsonl`, `imap`, and `mcp`), models, and fact evals share
  small base classes that projects can subclass. Today, Factoid stores data in SQLite or Postgres and searches with a
  local index or turbopuffer, and either can be replaced.
- **Emergent entities and kept facts.** Every extracted entity is kept and linked, even with no declared class, and a
  placeholder mention that matches nothing stays on the fact as an unlinked mention so the fact is still kept. When a
  new entity is stored, Factoid searches stored facts for the entity's names and asks the decision model to confirm each
  hit.
- **Fingerprints.** Each fact records a fingerprint of the prompts, questions, floors, and settings that produced the
  fact. When any of those inputs change, facts from the old version are stale, and `factoid rebuild --estimate`
  (planned) prices re-deriving those facts. The model is omitted from the fingerprint, so switching models for price
  does not force a rebuild.

## Research

Most of Factoid comes from internal research and production experience at Endgame. A smaller part builds on three
published papers by Kyle Wild, Yusuke Takahashi, and Asako Uraki.

- [*RAG Deserves an Index: Why Ingest-Time Compilation Beats Query-Time
  Interpretation*](https://arxiv.org/abs/2608.20845) (2026). Most RAG systems retrieve raw chunks and have a model
  interpret them on every query. The paper extracts single-claim sentences once at ingest time and checks each one
  against its source passage. On 500 held-out interview transcripts, compiled claims scored higher than every chunk
  configuration: 85.2% correct from about 2.2k reader tokens, against 72.5% from 16.3k.
  [examples/mediasum](https://github.com/Endgame-Labs/factoid/blob/main/examples/mediasum/README.md) reruns this benchmark
  with Factoid.
- [*Ingest-Time Fact Compilation for Cost-Efficient and Reliable Question Answering over Revised Corpora*](https://arxiv.org/abs/2609.29661)
  (2026). This paper resolves revisions, deletions, effective dates, and differences in source authority once at ingest
  time. At query time, an inexpensive model reads the current state without rebuilding it per question. In its
  controlled experiment, the compiled path was right in 30 of 30 trials, against 1 of 30, at 12.89 times lower read
  cost. Factoid does this with supersession, end dates, and as-of search.
- [*Cost Scales with Change, Not Corpus Size: Incrementally Maintaining an Evolving Semantic Substrate*](https://arxiv.org/abs/2608.16621)
  (2026). When documents are added or revised, incremental updates process only what changed. They ran 33.7 times
  cheaper than a full rebuild and produced the same result.

<details>
<summary>BibTeX</summary>

```bibtex
@misc{wild2026ragindex,
  title         = {RAG Deserves an Index: Why Ingest-Time Compilation Beats Query-Time Interpretation},
  author        = {Wild, Kyle and Takahashi, Yusuke and Uraki, Asako},
  year          = {2026},
  eprint        = {2608.20845},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  doi           = {10.48550/arXiv.2608.20845}
}

@misc{wild2026factcompilation,
  title         = {Ingest-Time Fact Compilation for Cost-Efficient and Reliable Question Answering over Revised Corpora},
  author        = {Wild, Kyle and Takahashi, Yusuke and Uraki, Asako},
  year          = {2026},
  eprint        = {2609.29661},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  doi           = {10.48550/arXiv.2609.29661}
}

@misc{takahashi2026costscales,
  title         = {Cost Scales with Change, Not Corpus Size: Incrementally Maintaining an Evolving Semantic Substrate},
  author        = {Takahashi, Yusuke and Wild, Kyle and Uraki, Asako},
  year          = {2026},
  eprint        = {2608.16621},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  doi           = {10.48550/arXiv.2608.16621}
}
```

</details>

## Further reading

- [SPEC.md](https://github.com/Endgame-Labs/factoid/blob/main/SPEC.md) has every design decision, how settled each one
  is, and what is built (section 17).
- [docs/cli.md](https://github.com/Endgame-Labs/factoid/blob/main/docs/cli.md) is the command reference.
- [examples/](https://github.com/Endgame-Labs/factoid/tree/main/examples/) has five apps: `demo` (a sales call and two
  emails, the place to start: it runs in a minute for under a cent), `rag` (a docs assistant for Python's standard
  library: a whole RAG pipeline in one file, with facts, chunks, or both as the retriever), `legal` (contracts and
  amendments), `nba` (game recaps and box scores), and `mediasum` (news transcripts, with a question-answering eval).
  Each has a README.
- [docs/archive/](https://github.com/Endgame-Labs/factoid/tree/main/docs/archive/) holds docs from an earlier design; do
  not follow them.
