# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. These docs settle the design before code is written.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Quickstart

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

`uv tool install` puts `factorial` on your `PATH`. Inside a project directory, `factorial` runs in that project's
environment without `uv run` or manual activation.

## Document and fact types

Each document type and each fact type is a Python class. A class holds its type definition, prompt overrides, model
settings, and custom pipeline code.

```text
harbor_realty/
├── pyproject.toml
├── harbor_realty/
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # document sources
│   ├── documents.py   # LeaseAgreement, TenantEmail, and PlumberInvoice
│   ├── facts.py       # MonthlyRent, PetPolicy, and HeaterStatus
│   └── judges.py      # custom judges
├── prompts/
│   ├── tenant_email/
│   │   ├── extract.md.j2          # extract prompt for TenantEmail
│   │   └── thread_summary.md.j2   # custom helper prompt
│   └── heater_status/
│       └── resolve.md.j2          # resolve prompt for HeaterStatus
└── evals/leases_and_repairs.jsonl
```

Each pipeline step is a hook on `Document` or `Fact`:

| Class | Hooks | Responsibility |
| --- | --- | --- |
| `Document` | `classify`, `segment`, and `extract` | Match a document to this type, split the document into passages, and extract candidate facts. |
| `Fact` | `classify`, `judge`, `repair`, and `resolve` | Match a candidate to this type, check quality, rewrite text, and detect duplicates, updates, or contradictions against stored facts. |

Hooks support three levels of customization:

1. **Use the default.** Inherit the base class implementation.
2. **Override the prompt.** Add `prompts/<class_name>/<hook>.md.j2` to replace the built-in prompt for that class.
3. **Override the method.** Implement the method in Python, and call `super()` to run the default step.

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

Models read each class docstring as the type definition during classification. Typed attributes on a `Fact` subclass
define its structured fields.

### Classification

By default, `classify` uses a choice model. A choice model scores a fixed set of options in one pass and returns a
probability per option with no generated text. To classify a document, Factorial sends one request containing all
document classes and their docstrings. To classify a candidate fact, Factorial sends one request containing the fact
classes listed on that document.

```python
class PlumberInvoice(Document):
    """An invoice from a plumber for work done on a unit."""
    facts = [HeaterStatus]
    classify_threshold = 0.8          # default threshold comes from calibration

    def classify_view(self) -> str:
        # Pass the header and footer, where letterhead and totals appear.
        return self.head(400) + self.tail(400)
```

Override `classify` to replace the model call with Python logic, such as a header check.

### Model calls

Hooks call models through four methods on `self`. Factorial logs, prices, budgets, and replays these calls, and includes
each prompt in the step's fingerprint.

| Method | Returns | Model kind |
| --- | --- | --- |
| `self.choose(prompt, options)` | A probability for each option | Choice model |
| `self.decide(prompt)` | A probability that the answer is yes | Choice model |
| `self.score(prompt, rubric)` | A rubric level | Choice model |
| `self.generate(prompt)` | Text | Generative model |

Define models once in `settings.py` with pinned versions. Read secrets from environment variables.

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

Eval runs can swap hook strategies from the CLI without modifying project files. `factorial eval --vary
classify=choice,llm,rules` runs the same documents under each strategy and compares quality, cost, and latency.

## Prompts

Prompts are Jinja templates. Every model-backed hook has a built-in template that a file in `prompts/` can replace:
`prompts/extract.md.j2` applies to all document types, and `prompts/tenant_email/extract.md.j2` applies to
`TenantEmail`. Project templates can also extend a built-in template and override individual blocks.

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

## Code hooks

Fact classes also support Python hooks that need no model. Override `validate` to reject candidates in code, override
`supersedes` to control when a newer fact replaces an older fact, and define `on_added`, `on_superseded`,
`on_contradicted`, `on_retracted`, or `on_restored` to run callbacks on lifecycle events. Read current typed values with
`HeaterStatus.current(unit="Unit 4B").status`.

## Usage

- **Standalone CLI project.** Manage a RAG corpus in its own directory, tune retrieval units, and evaluate prompt,
  extractor, and judge choices with `factorial ingest`, `factorial search`, and `factorial eval`.
- **Agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes, and chats,
  then expose fact search and writes to an agent through `factorial mcp` or the CLI.
- **Python library or HTTP service.** Run `factorial serve` as an HTTP sidecar, or `import factorial` inside an
  application and pass classes to `Factorial(...)`:

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
hits = facts.search("Acme Corp plan")               # fact sentences with source quotes
tier = PlanTier.current(entity="Acme Corp").tier   # typed attribute value
```

## Design

- **Fact-level retrieval.** Search returns short, self-contained sentences within a token budget. On dialogue, fact
  retrieval outperformed chunk retrieval while using about one-seventh of the read tokens
  ([docs/prior-art.md](../../../prior-art.md)).
- **Deterministic provenance.** The extractor cites numbered passages, and Factorial's code attaches the exact quote,
  speaker, and timestamp.
- **Append-only event log.** Writes append `added`, `superseded`, `contradicted`, `retracted`, and `restored` events to
  a log. Current state and search indexes (`sqlite-fts`, `pgvectorscale`, and `turbopuffer`) are views rebuilt from that
  log.
- **Eval-selected defaults.** Default strategies across `classify`, `segment`, `extract`, `judge`, `repair`, `resolve`,
  and `tag` come from eval results. `factorial eval` measures accuracy, cost, and latency on labeled data.
- **Pluggable backends.** Storage (local folders and S3-compatible buckets), sources (`folder`, `jsonl`, `imap`, and
  `mcp`), models, and judges share small base classes that projects can subclass.

## Further reading

Read [docs/mental-model.md](../../../mental-model.md) first, then [docs/README.md](../../../README.md).
[docs/config.md](../../../config.md) and [docs/plugins.md](../../../plugins.md) still cover the older single-YAML design and
will be updated. Earlier proposals are in [docs/potential/README/](../).
