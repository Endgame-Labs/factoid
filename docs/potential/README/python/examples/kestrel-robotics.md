# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. We update these docs to settle the design before writing code.

Factorial turns documents into short, self-contained sentences called facts. Each fact is tied to an exact source quote,
who said it, and when.

As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate facts, and
flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Core ideas

- **Facts are what a reader reads.** Queries return reconciled sentences with citations. On dialogue benchmarks, reading
  facts beat chunk retrieval at about a seventh of the read tokens (see [docs/prior-art.md](../../../../prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and Factorial code attaches the exact quote,
  speaker, and timestamp.
- **History is the truth.** Ingest writes to an append-only event log (`added`, `superseded`, `contradicted`,
  `retracted`, and `restored`). Current state and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** `factorial eval` scores a setup against labeled data and reports accuracy,
  cost, and latency. Built-in defaults come from eval results.

## Fifteen minutes

Factorial requires Python 3.13+ and `uv`. Below is `kestrel_robotics`, an example project defined for a hardware team's
supplier purchasing and bench testing.

```bash
uv tool install factorial
factorial new kestrel_robotics
cd kestrel_robotics

factorial generate document VendorQuote PartDatasheet BenchTestLog
factorial generate fact UnitPrice LeadTime MaxOperatingTemp

factorial ingest ./sample_docs
factorial search "motor_x12 operating temp and unit price"
factorial read fact_01j9x8k2
factorial eval
factorial eval --vary judge=none,nli,jev_floors
```

`uv tool install` puts one `factorial` command on your path. Inside a project, that command finds the project's own
environment and runs there, so you never type `uv run` or activate anything.

## Project layout

A project is one flat Python package with conventional module names. Factorial imports these files automatically, and
subclassing a base class declares a component without an app list or a registration step.

```text
kestrel_robotics/
  pyproject.toml
  kestrel_robotics/        # user project package
    settings.py            # pinned models, storage, indexes, and search
    sources.py             # document inputs (SupplierInbox)
    documents.py           # user document types (VendorQuote, PartDatasheet, BenchTestLog)
    facts.py               # user fact types (UnitPrice, LeadTime, MaxOperatingTemp)
    judges.py              # custom judges and the judge chain
  prompts/
    vendor_quote/
      extract.md.j2   # Jinja template for VendorQuote extraction
  evals/
    purchasing.jsonl       # labeled eval suites
```

## Declaring a project

Every declaration is a Python class that inherits defaults from its Factorial base class. Options are class attributes,
references between declarations use standard Python imports, dynamic settings use `@property`, and custom behaviors
override methods.

```python
# kestrel_robotics/settings.py
import os
from factorial import S3Store, Settings, SqliteFtsIndex

class KestrelSettings(Settings):
    models = {"fast": "gemini-2.5-flash-001", "extract": "claude-sonnet-4-20250514"}
    store = S3Store(bucket="kestrel-facts", secret_key=os.environ["S3_SECRET_KEY"])
    index = SqliteFtsIndex(path="var/facts.db")
    retrieve = "hybrid-rrf"  # bm25, vector, or hybrid-rrf
    rerank = True
    budget_tokens = 1200
```

```python
# kestrel_robotics/sources.py
import os
from factorial import ImapSource

class SupplierInbox(ImapSource):
    host = "imap.kestrel.internal"
    password = os.environ["IMAP_PASSWORD"]
```

```python
# kestrel_robotics/facts.py
from factorial import Fact

class UnitPrice(Fact):
    unit_price_usd: float  # slot: ("motor_x12", "unit_price_usd", 42.50)

    def supersedes(self, prior: "UnitPrice") -> bool:
        return self.entity == prior.entity and self.dated_at > prior.dated_at

class LeadTime(Fact):
    lead_time_weeks: int   # slot: ("motor_x12", "lead_time_weeks", 8)

class MaxOperatingTemp(Fact):
    max_temp_c: int        # slot: ("motor_x12", "max_temp_c", 72)
```

```python
# kestrel_robotics/judges.py
from factorial import JevFloors, Judge, NliJudge

class PositivePrice(Judge):
    def check(self, fact) -> bool:
        return getattr(fact, "unit_price_usd", 1.0) > 0

DEFAULT_JUDGES = [PositivePrice, NliJudge, JevFloors]
```

```python
# kestrel_robotics/documents.py
from factorial import Document
from .facts import LeadTime, MaxOperatingTemp, UnitPrice
from .judges import DEFAULT_JUDGES
from .sources import SupplierInbox

class VendorQuote(Document):
    source = SupplierInbox
    segment = "email"
    facts = [UnitPrice, LeadTime, MaxOperatingTemp]
    judges = DEFAULT_JUDGES

class PartDatasheet(Document):
    segment = "paragraphs"
    facts = [MaxOperatingTemp]

    @property
    def extract(self) -> str:
        return "staged" if len(self.text) > 20_000 else "passages"

class BenchTestLog(Document):
    segment = "rows"
    facts = [MaxOperatingTemp]
```

A judge chain runs in order and rejects at the first failure, so cheap checks run before model calls. When `factorial
eval --vary judge=none,nli,jev_floors` runs, the runner creates a temporary subclass of each affected declaration in
memory and binds the varied attribute for that trial, overriding constants and `@property` descriptors alike.

## Pipeline and pluggable seams

On write, every document moves through `classify` (`declared`, `rules`, `systemone`, or `llm`), `segment` (`auto`,
`turns`, `email`, `paragraphs`, or `rows`), `extract` (`passages` or `staged`), `judge`, `repair`, `resolve` (`hash`,
`slot`, or `vector-judge`), and `tag`. Dedup, supersede, and contradiction happen at ingest: fresh quotes supersede
prices and lead times by slot, vendor emails repeating datasheet specs merge as duplicates, and bench logs that disagree
with overrated part specs flag contradictions.

- **Storage and indexes:** local folders or S3-compatible buckets, with `sqlite-fts`, `pgvectorscale`, or `turbopuffer`
  indexes.
- **Sources:** `folder`, `jsonl`, `imap`, `mcp`, or a custom `Source` subclass.
- **Models:** named once in `settings.py` and pinned to exact versions, never `"latest"`.
- **Judges:** `nli`, `jev-floors`, `llm`, or a custom `Judge` subclass.

## Prompts

Prompts are Jinja templates. Every step that calls a model has a built-in template, and Factorial fills it with the
document, its numbered passages, and the fact types that the document class lists:

```jinja
{# factorial/extract.md.j2, the built-in extract template #}
Extract facts from this {{ document.type }}, dated {{ document.at }}.

{% block guidance %}{% endblock %}

Fact types:
{% for fact_type in fact_types %}
- {{ fact_type.name }}: {{ fact_type.description }}
{% endfor %}

Passages:
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker }}: {{ passage.text }}
{% endfor %}

Cite passages by number. Do not copy quote text.
```

A file in your project's `prompts/` folder takes the place of a built-in template. `prompts/extract.md.j2` applies to
every document type, and `prompts/vendor_quote/extract.md.j2` applies to `VendorQuote` only. A project template can
extend the built-in template and change one block, the same way a class overrides one method:

```jinja
{# prompts/vendor_quote/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}

{% block guidance %}
Skip boilerplate terms and conditions.
{% endblock %}
```

A class can add template variables by overriding `prompt_context()`. `factorial prompts copy extract` writes the
built-in template into `prompts/` as a starting point. A template's text is part of its step's fingerprint, so changing
a prompt marks the facts it produced as stale.

## Why this approach

Plain classes keep small declarations short and let custom rules live as methods in the same file. Real imports give you
editor navigation, autocomplete, static type checking, and ordinary unit tests. The cost is that loading configuration
executes Python code, which rules out untrusted project files. External tools also cannot safely rewrite your Python
files to persist a setting change from a UI or CLI.

## Where to read next

Start with [docs/mental-model.md](../../../../mental-model.md), and then read [docs/README.md](../../../../README.md). Note that
[docs/config.md](../../../../config.md) and [docs/plugins.md](../../../../plugins.md) still describe the older single-YAML design.
