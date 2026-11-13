# Factorial 🧮

> **Status:** Design draft. Nothing is built yet. We update the documentation to settle the design before writing code.

Factorial turns documents into short, self-contained sentences called facts. Every fact carries an exact source quote,
who said it, and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges
duplicate facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and
MCP.

## Core ideas

- **Facts are what a reader reads.** Queries return compact sentences with provenance. On dialogue benchmarks, fact
  retrieval beat chunk retrieval at about a seventh of the read tokens (see [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** An extractor cites numbered passages from the segmented document, and deterministic
  code attaches the exact quote, speaker, and timestamp.
- **History is the truth.** Ingest writes to an append-only event log (`added`, `superseded`, `contradicted`,
  `retracted`, `restored`). Current state and search indexes are views rebuilt from that log. Deduplication,
  superseding, and contradiction checks happen on write.
- **Algorithm choices are made by evals.** `factorial eval` scores your pipeline against labeled data and reports
  accuracy, cost, and latency. Built-in defaults are the winners of previous eval runs.

## Fifteen minutes

Install Factorial with `uv` (requires Python 3.13+) and scaffold an example clinic project named `cedar_clinic`:

```sh
uv tool install factorial
factorial new cedar_clinic
cd cedar_clinic
factorial generate document IntakeForm DoctorNote LabReport
factorial generate fact MedicationDose BloodType SmokingStatus
```

Drop sample intake forms, visit notes, and lab exports into `./inbox`, then ingest, query, and evaluate:

```sh
uv run factorial ingest
uv run factorial search "patient_402 blood pressure medication"
uv run factorial read fact_01j9z8k2
uv run factorial eval
uv run factorial eval --vary judge=none,nli,jev_floors
```

## Project layout

A project is one flat Python package. Factorial imports these module names by convention, and subclassing a base class
registers your definition:

```text
cedar_clinic/
├── pyproject.toml
├── cedar_clinic/
│   ├── __init__.py
│   ├── settings.py    # storage, indexes, pinned models, judge chain, search
│   ├── sources.py     # where documents arrive from
│   ├── documents.py   # document classes, segmentation, and extraction
│   ├── facts.py       # fact classes, typed slots, and resolution methods
│   └── judges.py      # custom verification steps
├── prompts/
│   └── doctor_note/
│       └── extract.md.j2
└── evals/
    └── clinic_gold.jsonl
```

The package name `cedar_clinic` and classes like `DoctorNote` or `MedicationDose` are your own domain code, covering
both clinic visits and lab records in one place.

## Declaring a project

Classes inherit sensible defaults from Factorial base classes, link to one another through standard Python imports, and
override attributes or methods where clinic rules require custom logic.

```python
# cedar_clinic/settings.py
import os
from factorial import Settings, S3Store, PgVectorScaleIndex
from factorial.judges import NLIJudge, JEVFloorsJudge
from cedar_clinic.judges import SpeakerDateJudge

class ClinicSettings(Settings):
    store = S3Store(bucket="cedar-facts", key=os.environ["S3_KEY"])
    index = PgVectorScaleIndex(dsn=os.environ["DATABASE_URL"])
    models = {
        "fast": "gemini-2.5-flash-2026-05-01",
        "extract": "claude-sonnet-4-20250514",
    }
    judges = [NLIJudge, JEVFloorsJudge, SpeakerDateJudge]  # cheap checks run first
    retrieve = "hybrid-rrf"
    budget_tokens = 1200
```

Any setting can be a `@property` computed per instance:

```python
# cedar_clinic/documents.py
from factorial import Document
from cedar_clinic.facts import BloodType, MedicationDose, SmokingStatus

class IntakeForm(Document):
    segment = "paragraphs"
    facts = [MedicationDose, BloodType, SmokingStatus]

class DoctorNote(Document):
    segment = "turns"
    facts = [MedicationDose, SmokingStatus]

    @property
    def extract(self) -> str:
        return "staged" if len(self.text) > 4_000 else "passages"

class LabReport(Document):
    segment = "rows"
    facts = [BloodType]
```

Typed class attributes define a fact's `(entity, field, value)` slot, such as `("patient_402", "lisinopril_daily_mg",
20)`, `"O-"`, or `"former"`. Overriding a method customizes how conflicts resolve when an intake sheet disagrees with a
physician's chart note:

```python
# cedar_clinic/facts.py
from typing import Literal, Self
from factorial import Fact

class BloodType(Fact):
    patient: str
    field: Literal["blood_type"] = "blood_type"
    abo_rh: str
    resolve = "slot"

class SmokingStatus(Fact):
    patient: str
    field: Literal["smoking_status"] = "smoking_status"
    status: Literal["never", "former", "current"]

class MedicationDose(Fact):
    patient: str
    drug_metric: str
    daily_mg: int

    def supersedes(self, prior: Self) -> bool:
        if self.speaker_role == "patient" and prior.speaker_role == "doctor":
            return False  # flags a contradiction when an intake form disagrees
        return self.observed_at > prior.observed_at
```

```python
# cedar_clinic/sources.py
from factorial.sources import FolderSource
from cedar_clinic.documents import DoctorNote, IntakeForm, LabReport

class ChartDrop(FolderSource):
    path = "./inbox"
    classify = "llm"
    documents = [IntakeForm, DoctorNote, LabReport]
```

When you run `factorial eval --vary judge=none,nli,jev_floors`, the eval runner patches the target attribute or property
on your classes in memory for each trial and leaves your source files untouched.

## Pluggable seams

Every pipeline stage (`classify`, `segment`, `extract`, `judge`, `repair`, `resolve`, and `tag`) and infrastructure
boundary is a Python base class you can subclass:

- **Storage and indexes:** local folder or S3-compatible bucket for the event log; `sqlite-fts`, `pgvectorscale`, or
  `turbopuffer` for search (`bm25`, `vector`, or `hybrid-rrf` with optional reranking).
- **Sources:** `folder`, `jsonl`, `imap`, `mcp`, or custom `Source` subclasses.
- **Models and judges:** pinned model aliases (`never "latest"`), plus `nli`, `jev-floors`, `llm`, and custom `Judge`
  classes that halt the chain on the first rejection.

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
every document type, and `prompts/doctor_note/extract.md.j2` applies to `DoctorNote` only. A project template can extend
the built-in template and change one block, the same way a class overrides one method:

```jinja
{# prompts/doctor_note/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}

{% block guidance %}
Skip template headings and any section left blank.
{% endblock %}
```

A class can add template variables by overriding `prompt_context()`. `factorial prompts copy extract` writes the
built-in template into `prompts/` as a starting point. A template's text is part of its step's fingerprint, so changing
a prompt marks the facts it produced as stale.

## Why this approach

Standard Python classes give you editor autocomplete, type checking, real imports, and a debugger with zero
configuration DSL to learn. Static constants cover common cases cleanly, while `@property` definitions and method
overrides handle messy domain rules in the exact place they belong. The cost is that configuration is executable code:
loading a project imports user modules, static tooling cannot inspect every computed setting without running Python, and
teams must keep heavy business logic out of class definitions.

## Further reading

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md). Note that
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design and
have not been updated yet.
