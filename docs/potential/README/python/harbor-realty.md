# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. We update the documentation to settle the design before writing code.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+, scaffold an example property management project named `harbor_realty`,
ingest sample leases and repair emails, and run an evaluation.

```sh
uv tool install factorial
factorial new harbor_realty
cd harbor_realty

uv run factorial generate document LeaseAgreement TenantEmail PlumberInvoice
uv run factorial generate fact MonthlyRent PetPolicy HeaterStatus

uv run factorial ingest ./sample_docs
uv run factorial search "Unit 4B heater"
uv run factorial read fact_01j9x8k2m
uv run factorial eval
uv run factorial eval --vary judge=none,nli,jev_floors
```

## Project layout

`factorial new` creates one flat Python package with conventional module names. Factorial imports these modules at
startup, and subclassing a base class registers your definition. Your domain classes (`LeaseAgreement`, `MonthlyRent`,
`HeaterStatus`, and the rest) live directly in these files with no app folders or registration lists.

```text
harbor_realty/
├── pyproject.toml
├── harbor_realty/
│   ├── __init__.py
│   ├── settings.py    # storage, indexes, pinned models, judge chain, search
│   ├── sources.py     # folders, IMAP mailboxes, JSONL streams, MCP sources
│   ├── documents.py   # LeaseAgreement, TenantEmail, PlumberInvoice
│   ├── facts.py       # MonthlyRent, PetPolicy, HeaterStatus
│   └── judges.py      # custom judges alongside built-in judges
└── evals/
    └── leases_and_repairs.jsonl
```

### Facts and typed slots (`facts.py`)

A fact type is a subclass of `Fact` with an optional typed slot (`entity`, field name, and typed value). Deduplication,
supersede checks, and contradiction checks run on write during ingest. Built-in slot resolution supersedes older values
for the same entity and field, and you can override methods when domain rules need custom logic.

```python
from typing import Self
from factorial import Fact


class MonthlyRent(Fact):
    """Example slot: ("Unit 4B", "monthly_rent_usd", 1950)"""
    monthly_rent_usd: int

    def supersedes(self, prior: Self) -> bool:
        return self.entity == prior.entity and self.stated_at > prior.stated_at


class PetPolicy(Fact):
    """Example slot: ("Unit 4B", "pets_allowed", False)"""
    pets_allowed: bool


class HeaterStatus(Fact):
    """Example slot: ("Unit 4B", "heater_status", "leaking")"""
    heater_status: str
```

### Documents and computed settings (`documents.py`)

Document types inherit defaults from `Document`, reference fact classes through standard Python imports, and can replace
any static attribute with a `@property` or method.

```python
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

### Sources, judges, and settings (`sources.py`, `judges.py`, `settings.py`)

Sources and custom judges follow the same subclass pattern. In `settings.py`, models are named once and pinned to exact
versions, secrets come from environment variables, and the judge chain runs cheap checks first, rejecting a candidate
fact at the first failure.

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
from harbor_realty.judges import SignedInvoiceJudge


class Project(Settings):
    store = S3Store(bucket="harbor-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "extract": Model("claude-3-5-haiku-20241022"),
        "judge": Model("gpt-4o-mini-2024-07-18"),
    }
    judges = [Nli, JevFloors, SignedInvoiceJudge]
    search = Search(retriever=HybridRrf, rerank=True, budget_tokens=1500)
```

When you run `factorial eval --vary judge=none,nli,jev_floors`, the CLI runner clones `Project` in memory for each trial
and binds the varied attribute or property for that run, leaving your Python files untouched.

## Core ideas

- **Facts are what a reader reads.** Readers and agents receive short, self-contained sentences within a token budget.
  On dialogue benchmarks, fact retrieval beat chunk retrieval at about a seventh of the read tokens (see
  [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** During extraction, the model cites numbered passages from the segmented document, and
  Factorial's own code attaches the exact quote, speaker, and timestamp.
- **History is the truth.** Every write appends to an immutable event log (`added`, `superseded`, `contradicted`,
  `retracted`, and `restored`). Current fact state and search indexes (`sqlite-fts`, `pgvectorscale`, and `turbopuffer`)
  are views rebuilt from that log.
- **Algorithm choices are made by evals.** Pipeline stages (`classify`, `segment`, `extract`, `judge`, `repair`,
  `resolve`, and `tag`) have built-in strategies whose defaults come from benchmark runs. `factorial eval` scores your
  classes against labeled data and reports accuracy, cost, and latency.
- **Pluggable seams.** Storage (local folders and S3-compatible buckets), sources (`folder`, `jsonl`, `imap`, and
  `mcp`), pinned models, and judges all share small base classes that you can subclass in your project.

## Why this approach

Plain Python classes give users autocomplete, type checking, real imports, debugger breakpoints, and custom logic
through standard inheritance, `@property` descriptors, and method overrides. Keeping five conventional files in one flat
package avoids boilerplate registration and nested directories. The cost is that configuration is executable code:
external tools cannot parse project declarations as static data without importing the package, and authors must avoid
slow work at import time.

## Further reading

Start with [docs/mental-model.md](docs/mental-model.md), and then read [docs/README.md](docs/README.md). Note that
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design and
will be updated next.
