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

## Project layout

`factorial new` creates one Python package with conventional module names. Classes connect through standard Python
imports with no registration step. When a project grows, split modules into plain Python sub-packages.

```text
harbor_realty/
├── pyproject.toml
├── harbor_realty/
│   ├── settings.py    # storage, indexes, pinned models, judge chain, and search
│   ├── sources.py     # folder, jsonl, imap, and mcp sources
│   ├── documents.py   # LeaseAgreement, TenantEmail, and PlumberInvoice
│   ├── facts.py       # MonthlyRent, PetPolicy, and HeaterStatus
│   └── judges.py      # custom judges alongside built-in judges
├── prompts/tenant_email/extract.md.j2
└── evals/leases_and_repairs.jsonl
```

A `Fact` subclass adds an optional typed slot (`entity`, field, and value). Dedup, supersede, and contradiction run on
write at ingest. By default, a newer value supersedes an older one for the same entity and field. Override a method
to change that rule.

```python
# facts.py
from typing import Self
from factorial import Fact

class MonthlyRent(Fact):
    monthly_rent_usd: int

    def supersedes(self, prior: Self) -> bool:
        return self.entity == prior.entity and self.stated_at > prior.stated_at

class PetPolicy(Fact):
    pets_allowed: bool

class HeaterStatus(Fact):
    heater_status: str
```

`Document` subclasses set options as attributes, import `Fact` classes, and compute dynamic options with `@property`.

```python
# documents.py
from factorial import Document, Extractor
from factorial.extractors import Passages, Staged
from factorial.segmenters import Auto, Email, Paragraphs
from harbor_realty.facts import HeaterStatus, MonthlyRent, PetPolicy

class LeaseAgreement(Document):
    segmenter = Paragraphs
    facts = [MonthlyRent, PetPolicy]

    @property
    def extractor(self) -> type[Extractor]:
        return Staged if len(self.text) > 15_000 else Passages

class TenantEmail(Document):
    segmenter = Email
    facts = [HeaterStatus, PetPolicy]

class PlumberInvoice(Document):
    segmenter = Auto
    facts = [HeaterStatus]
```

Sources and custom judges subclass `Source` and `Judge`. In `settings.py`, `Project` imports your classes, pins exact
model versions, reads secrets from environment variables, and orders the judge chain so cheap checks fail first.

```python
# judges.py
from factorial import CandidateFact, Judge

class SignedInvoiceJudge(Judge):
    def check(self, candidate: CandidateFact) -> bool:
        return "Authorized signature" in candidate.passage.text
```

```python
# settings.py
import os
from factorial import Model, Search, Settings
from factorial.indexes import SqliteFts
from factorial.judges import JevFloors, Nli
from factorial.retrievers import HybridRrf
from factorial.stores import S3Store
from harbor_realty.documents import LeaseAgreement, PlumberInvoice, TenantEmail
from harbor_realty.judges import SignedInvoiceJudge
from harbor_realty.sources import LeaseFolder, RepairInbox

class Project(Settings):
    store = S3Store(bucket="harbor-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    sources = [LeaseFolder, RepairInbox]
    documents = [LeaseAgreement, TenantEmail, PlumberInvoice]
    models = {
        "extract": Model("fireworks/glm-5p3-flash"),
        "judge": Model("typesafe/jev-1.13.0"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    judges = [Nli, JevFloors, SignedInvoiceJudge]
    search = Search(retriever=HybridRrf, rerank=True, budget_tokens=1500)
```

When you run `factorial eval --vary judge=none,nli,jev_floors`, the CLI clones `Project` in memory for each trial and
binds the varied attribute or property for that run, leaving your Python files untouched.

## Prompts

Every model step renders a built-in Jinja template with the document, numbered passages, and listed fact types.
Files in `prompts/` override built-in templates globally (`prompts/extract.md.j2`) or per document class, and
`{% extends %}` changes one block. Prompt text is fingerprinted, so edits mark older extracted facts as stale.

```jinja
{# factorial/extract.md.j2 #}
Extract facts from this {{ document.type }}, dated {{ document.at }}.
{% block guidance %}{% endblock %}
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker }}: {{ passage.text }}
{% endfor %}
Cite passages by number. Do not copy quote text.
```

```jinja
{# prompts/tenant_email/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}Skip greetings, signatures, and quoted replies.{% endblock %}
```

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
    tier: str

class AccountNote(Document):
    facts = [PlanTier]

class ServiceSettings(Settings):
    models = {"extract": Model("fireworks/glm-5p3-flash"), "judge": Model("typesafe/jev-1.13.0")}

facts = Factorial(settings=ServiceSettings, documents=[AccountNote])
facts.ingest_text("Acme Corp upgraded to Enterprise.", document_type=AccountNote)
hits = facts.search("Acme Corp plan")
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
