# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. The docs get updated to settle the design before code is written.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said
it, and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+. `factorial new` scaffolds `harbor_realty` with sample classes and evals.

```sh
uv tool install factorial
factorial new harbor_realty
cd harbor_realty
factorial ingest ./sample_docs
factorial search "Unit 4B heater"
factorial read fact_01j9x8k2m
factorial eval
factorial eval --vary judge=none,nli,jev_floors
```

`uv tool install` puts one `factorial` command on your path. Inside a project, that command finds the project's own
environment and runs there, so you never type `uv run` or activate anything.

## Classes hold the AI work

Factorial organizes your AI code and prompts around the types they work on. Each document type and each fact type is a
class. The class holds its definition, its prompts, its model choices, and any custom code for its steps.

```text
harbor_realty/
├── pyproject.toml
├── harbor_realty/
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # where documents come from
│   ├── documents.py   # LeaseAgreement, TenantEmail, and PlumberInvoice
│   ├── facts.py       # MonthlyRent, PetPolicy, and HeaterStatus
│   └── judges.py      # judges of your own
├── prompts/
│   ├── tenant_email/
│   │   ├── extract.md.j2          # this type's extract prompt
│   │   └── thread_summary.md.j2   # a prompt of your own
│   └── heater_status/
│       └── resolve.md.j2          # how two HeaterStatus facts are compared
└── evals/leases_and_repairs.jsonl
```

Each pipeline step is a hook on the class that owns it:

| Class | Hooks | What the hook decides |
| --- | --- | --- |
| `Document` | `classify`, `segment`, and `extract` | Is a document this type? How is it cut into passages? How are facts pulled from it? |
| `Fact` | `classify`, `judge`, `repair`, and `resolve` | Is a candidate this type? Is it good enough? How is it reworded? Does it repeat, replace, or disagree with a fact already stored? |

Every hook has the same three levels:

1. **Do nothing.** The base class has a working default.
2. **Add a prompt.** A file at `prompts/<class_name>/<hook>.md.j2` takes the place of the built-in prompt for that
   class.
3. **Override the method.** Write your own code for the step, and call `super()` to keep the default behavior around it.

```python
# documents.py
from factorial import Document
from harbor_realty.facts import HeaterStatus, PetPolicy

class TenantEmail(Document):
    """An email from a tenant to the leasing office."""
    facts = [HeaterStatus, PetPolicy]

    def extract(self, passages):
        # Summarize the quoted thread first, then extract with that summary as context.
        thread = self.generate("thread_summary.md.j2", passages=passages)
        return super().extract(passages, thread=thread)
```

```python
# facts.py
from typing import Literal
from factorial import Entity, Fact

class HeaterStatus(Fact):
    """Whether a unit's heater works, as reported by someone who checked it."""
    unit: Entity
    status: Literal["working", "leaking", "broken"]

    @property
    def resolve_neighbors(self) -> int:
        # Compare against more stored facts when the unit has a long repair history.
        return 40 if self.unit.fact_count > 200 else 20
```

A class's docstring is prompt text. It is the definition a model reads when it classifies into that type, so the
description lives on the thing it describes. Typed attributes are the fact's slot.

### Classifying

Classifiers are fast choice models by default. A choice model answers a typed question in one pass and writes no text:
it returns a probability for each option. To type a document, Factorial sends one request whose options are the
project's document classes, each described by its docstring. To type a candidate fact, Factorial does the same with the
fact classes that the document lists. One request covers every type, so adding types does not add calls.

```python
class PlumberInvoice(Document):
    """An invoice from a plumber for work done on a unit."""
    facts = [HeaterStatus]
    classify_threshold = 0.8          # the default threshold comes from calibration

    def classify_view(self) -> str:
        # What the classifier sees: the letterhead and the totals, which sit at the top and the bottom.
        return self.head(400) + self.tail(400)
```

Override `classify` itself to replace the model with your own code, such as a rule on a header.

### Calling models

Inside a hook, a class calls models through four methods. Factorial logs, prices, budgets, and replays every call made
this way, and each prompt is part of its step's fingerprint.

| Method | Returns | Model kind |
| --- | --- | --- |
| `self.choose(prompt, options)` | A probability for each option | Choice model |
| `self.decide(prompt)` | A probability that the answer is yes | Choice model |
| `self.score(prompt, rubric)` | A rubric level | Choice model |
| `self.generate(prompt)` | Text | Generative model |

Models are named once in `settings.py` and pinned to exact versions. Secrets come from environment variables.

```python
# settings.py
import os
from factorial import Model, Search, Settings
from factorial.indexes import SqliteFts
from factorial.stores import S3Store

class Project(Settings):
    store = S3Store(bucket="harbor-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),        # classify, judge, and resolve
        "generate": Model("fireworks/glm-5p3-flash"),  # extract and repair
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1500)
```

An eval run can swap any hook's strategy without touching your files. `factorial eval --vary classify=choice,llm,rules`
runs the same documents once per value and compares quality, cost, and latency.

## Prompts

Prompts are Jinja templates. Every hook that calls a model has a built-in template. A file in `prompts/` takes its
place: `prompts/extract.md.j2` for every document type, or `prompts/tenant_email/extract.md.j2` for `TenantEmail` only.
A project template can extend the built-in template and change one block, the same way a class overrides one method.

```jinja
{# factorial/extract.md.j2, the built-in extract template #}
Extract facts from this {{ document.type }}, dated {{ document.at }}.
{% block guidance %}{% endblock %}
{% for fact_type in fact_types %}
- {{ fact_type.name }}: {{ fact_type.doc }}
{% endfor %}
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker }}: {{ passage.text }}
{% endfor %}
Cite passages by number. Do not copy quote text.
```

```jinja
{# prompts/tenant_email/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}
Earlier messages in this thread: {{ thread }}
Skip greetings, signatures, and quoted replies.
{% endblock %}
```

## Plain code hooks

Some steps need no model. A fact class can override `validate` to reject a candidate in code, override `supersedes` to
change when a newer fact replaces an older one, and define `on_added`, `on_superseded`, `on_contradicted`,
`on_retracted`, and `on_restored` to run code when that event happens to a fact. Typed reads return values your code can
use: `HeaterStatus.current(unit="Unit 4B").status`.

## Three ways to use it

- **Standalone project with the CLI.** Manage a RAG corpus in its own directory, tune retrieval units, and evaluate
  prompt, extractor, and judge choices with `factorial ingest`, `factorial search`, and `factorial eval`.
- **Personal agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes,
  and chats, then expose fact search and writes to an agent over `factorial mcp` or the CLI.
- **Backend library or HTTP service.** Run `factorial serve` as an HTTP sidecar, or `import factorial` inside an
  existing service. Classes work anywhere in code when passed directly to `Factorial(...)`:

```python
from factorial import Document, Fact, Factorial, Model, Settings

class PlanTier(Fact):
    """The plan an account is on."""
    tier: str

class AccountNote(Document):
    """A note an account manager wrote about a customer."""
    facts = [PlanTier]

class ServiceSettings(Settings):
    models = {"generate": Model("fireworks/glm-5p3-flash"), "choice": Model("typesafe/jev-1.13.0")}

facts = Factorial(settings=ServiceSettings, documents=[AccountNote])
facts.ingest_text("Acme Corp upgraded to Enterprise.", document_type=AccountNote)
hits = facts.search("Acme Corp plan")               # sentences, with quotes
tier = PlanTier.current(entity="Acme Corp").tier   # a typed value
```

## Core ideas

- **Facts are what a reader reads.** Readers get short, self-contained sentences in a token budget. On dialogue, fact
  retrieval beat chunk retrieval at about a seventh of the read tokens ([docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and code attaches the exact quote, speaker,
  and timestamp.
- **History is the truth.** Writes append to an event log (`added`, `superseded`, `contradicted`, `retracted`, and
  `restored`). Current state and search indexes (`sqlite-fts`, `pgvectorscale`, and `turbopuffer`) are views rebuilt
  from that log.
- **Algorithm choices are made by evals.** Defaults across `classify`, `segment`, `extract`, `judge`, `repair`,
  `resolve`, and `tag` are eval results. `factorial eval` scores accuracy, cost, and latency on labeled data.
- **Pluggable seams.** Storage (local folders and S3-compatible buckets), sources (`folder`, `jsonl`, `imap`, and
  `mcp`), models, and judges share small base classes that projects subclass directly.

## Further reading

Start with [docs/mental-model.md](docs/mental-model.md), and then read [docs/README.md](docs/README.md).
Note that [docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML
design and will be updated.
See [docs/potential/README/](docs/potential/README/) for the other proposals that were considered.
