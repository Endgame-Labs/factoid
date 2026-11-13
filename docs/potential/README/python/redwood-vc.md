# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. We update the docs first to settle the design before writing code.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+. Below, we create `redwood_vc`, a startup diligence project covering
financial reports and legal records for companies such as Orbital Inc.

```bash
uv tool install factorial
factorial new redwood_vc && cd redwood_vc
factorial generate document PitchDeck AuditedStatement BoardMinutes
factorial generate fact AnnualRevenue CashRunway IncorporationState
factorial ingest ./dataroom
factorial search "Orbital revenue and runway"
factorial read fact_01j8x9q2
factorial eval
factorial eval --vary judge=none,nli,jev_floors
```

`uv tool install` puts one `factorial` command on your path. Inside a project, that command finds the project's own
environment and runs there, so you never type `uv run` or activate anything.

## Project layout

A project is one flat Python package with five conventional modules and an `evals/` folder. Subclassing a Factorial base
class declares a component with no registration step and no app list. Names like `redwood_vc`, `PitchDeck`,
`AnnualRevenue`, and `PolicyJudge` are your own classes.

```text
redwood_vc/
├── pyproject.toml
├── redwood_vc/
│   ├── __init__.py
│   ├── settings.py    # Pinned models, storage, index, search, and judge chain
│   ├── sources.py     # Input connectors (folder, jsonl, imap, and mcp)
│   ├── documents.py   # Document types, segmentation, and extraction
│   ├── facts.py       # Fact types, typed slots, and supersede rules
│   └── judges.py      # Custom verification judges
├── prompts/
│   └── pitch_deck/
│       └── extract.md.j2
└── evals/
    └── diligence.jsonl
```

## Defining a project

Every source, document type, fact type, judge, and setting is a Python class. Base classes provide eval-tested defaults,
class attributes set options, and real imports connect classes. Any constant attribute can become a `@property` or an
overridden method when behavior depends on runtime data.

**`redwood_vc/sources.py`**
```python
from factorial import Classifier, FolderSource

class DataRoom(FolderSource):
    path = "./dataroom"
    classifier = Classifier.llm  # Built-ins: declared, rules, systemone, and llm
```

**`redwood_vc/documents.py`**
```python
from factorial import Document, Extractor, Segmenter

class AuditedStatement(Document):
    segmenter = Segmenter.rows        # Built-ins: auto, turns, email, paragraphs, and rows
    extractor = Extractor.staged      # Built-ins: passages and staged

class BoardMinutes(Document):
    segmenter = Segmenter.turns

class PitchDeck(Document):
    segmenter = Segmenter.paragraphs

    @property
    def extractor(self) -> Extractor:
        return Extractor.staged if len(self.text) > 20_000 else Extractor.passages
```

**`redwood_vc/facts.py`**

A `Fact` pairs a sentence with an optional typed slot `(entity, field, value)`. On write at ingest, Factorial
deduplicates matching facts, supersedes older slot values for the same entity and field, and flags conflicting claims.
```python
from typing import Self
from factorial import Fact
from redwood_vc.documents import AuditedStatement, PitchDeck

class AnnualRevenue(Fact):
    arr_usd: int  # Slot example: ("Orbital Inc.", "arr_usd", 3900000)

    def supersedes(self, prior: Self) -> bool:
        if isinstance(prior.document, AuditedStatement) and isinstance(self.document, PitchDeck):
            return False
        return super().supersedes(prior)

class CashRunway(Fact):
    runway_months: int  # Slot example: ("Orbital Inc.", "runway_months", 14)

class IncorporationState(Fact):
    incorporation_state: str  # Slot example: ("Orbital Inc.", "incorporation_state", "Delaware")
```

**`redwood_vc/judges.py` and `redwood_vc/settings.py`**

A judge chain runs in order and rejects at the first failure, so cheap checks run first. Models are named once with
pinned snapshots, and secrets come from environment variables.
```python
from factorial import LLMJudge

class PolicyJudge(LLMJudge):
    template = "judges/policy.md.j2"   # prompts/judges/policy.md.j2
```

```python
import os
from factorial import JevFloorsJudge, Model, NLIJudge, Retriever, S3Store, Settings, SQLiteFTS
from redwood_vc.judges import PolicyJudge

class DiligenceSettings(Settings):
    extract_model = Model("claude-3-5-haiku-20241022", api_key=os.environ["ANTHROPIC_API_KEY"])
    judge_model = Model("claude-3-7-sonnet-20250219", api_key=os.environ["ANTHROPIC_API_KEY"])
    store = S3Store(bucket="redwood-vc-facts")
    index = SQLiteFTS(path="./var/facts.db")  # Built-ins: sqlite-fts, pgvectorscale, and turbopuffer
    judges = [NLIJudge, JevFloorsJudge, PolicyJudge]
    retrieve = Retriever.hybrid_rrf           # Built-ins: bm25, vector, and hybrid-rrf
    rerank = True
    budget_tokens = 4_000
```

## Core ideas

- **Facts are what a reader reads.** On dialogue benchmarks, returning self-contained facts beat chunk retrieval at
  about one-seventh of the read tokens (see [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and Factorial's code attaches the exact quote,
  speaker, and timestamp.
- **History is the truth.** Ingest writes to an append-only event log (`added`, `superseded`, `contradicted`,
  `retracted`, and `restored`). Current state and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** Every pipeline stage (`classify`, `segment`, `extract`, `judge`, `repair`,
  `resolve`, and `tag`) is scored by `factorial eval` against labeled data with cost and latency numbers. Built-in
  defaults are eval results.

## Pluggable seams and eval overrides

Storage (local folder or S3-compatible bucket), sources (`folder`, `jsonl`, `imap`, and `mcp`), models, and judges
(`nli`, `jev-floors`, and `llm`) are base classes with small method contracts. Subclass those base classes in your
project or distribute extensions as standard Python packages.

When you run `factorial eval --vary judge=none,nli,jev_floors` (or `--vary resolve=hash,slot,vector-judge`), the eval
runner constructs an in-memory subclass of your settings or document classes for each trial and overrides the target
attribute on that subclass. Your source files on disk never change.

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
every document type, and `prompts/pitch_deck/extract.md.j2` applies to `PitchDeck` only. A project template can extend
the built-in template and change one block, the same way a class overrides one method:

```jinja
{# prompts/pitch_deck/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}

{% block guidance %}
Extract only figures stated as actuals. Skip projections.
{% endblock %}
```

A class can add template variables by overriding `prompt_context()`. `factorial prompts copy extract` writes the
built-in template into `prompts/` as a starting point. A template's text is part of its step's fingerprint, so changing
a prompt marks the facts it produced as stale.

## Why this approach

Plain Python classes give projects IDE autocomplete, static type checking, real imports, and standard debugging without
a custom configuration language. Common declarations stay one-line class attributes, while custom domain rules live on
the same class as a `@property` or method override. The cost is that loading a project executes Python code, so external
tools cannot inspect or edit declarations as static data. Every person who edits project rules also has to read and
write Python.

## Further reading

Start with [docs/mental-model.md](docs/mental-model.md), and then read [docs/README.md](docs/README.md). Note that
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design.
