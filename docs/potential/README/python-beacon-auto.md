# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. These documents are updated before any code is written.

Factorial turns documents into short, self-contained sentences called facts. Every fact carries an exact source quote,
who said it, and when.

As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate facts, and
flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Core ideas

- **Facts are what a reader reads.** Queries return atomic sentences with provenance. On dialogue benchmarks, reading
  facts beat chunk retrieval at about a seventh of the read tokens (see [docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered source passages, and deterministic code attaches the
  exact quote, speaker, and timestamp.
- **History is the truth.** Deduplication, superseding, and contradiction run at ingest and append to an event log
  (`added`, `superseded`, `contradicted`, `retracted`, and `restored`). Current state and search indexes are views
  rebuilt from that log.
- **Algorithm choices are made by evals.** `factorial eval` scores a setup against labeled data and reports accuracy,
  cost, and latency. Built-in defaults are recorded eval winners.

## Fifteen minutes

Factorial requires Python 3.13+ and `uv`. Below is an auto insurance project named `beacon_auto` with user-defined
classes for incident files and policy documents:

```bash
uv tool install factorial
factorial new beacon_auto && cd beacon_auto
factorial generate document DriverStatement PoliceReport ShopEstimate
factorial generate fact TrafficLightColor RepairEstimate CollisionDeductible

uv run factorial ingest ./sample_files
uv run factorial search "case 8841 northbound light"
uv run factorial read fact_01j9x2k
uv run factorial eval
uv run factorial eval --vary judge=none,nli,jev_floors
```

## Project layout

A project is one flat Python package. Factorial imports these modules by convention, and subclassing a base class
registers your definition:

```text
beacon_auto/
  pyproject.toml
  beacon_auto/
    settings.py     # storage, indexes, search,judge chain, and pinned models
    sources.py      # where documents come from (folder, jsonl, imap, mcp)
    documents.py    # document classes: segmentation and extraction
    facts.py        # fact classes: typed slots and resolution rules
    judges.py       # custom verification passes
  evals/
    incidents.jsonl # labeled documents and expected facts
```

## Defining a project

Classes inherit sensible defaults from Factorial base classes, configure options with plain attributes, and reference
each other with standard Python imports. Any attribute can be replaced by a `@property` or an overridden method.

```python
# beacon_auto/facts.py
from typing import Literal
from factorial import Fact


class TrafficLightColor(Fact):
    """Example slot: ("case_8841", "northbound_light", "red")"""
    case_id: str
    direction: str
    color: Literal["red", "yellow", "green"]


class CollisionDeductible(Fact):
    """Example slot: ("policy_992", "deductible_usd", 500)"""
    policy_id: str
    field: Literal["deductible_usd"] = "deductible_usd"
    amount_usd: int


class RepairEstimate(Fact):
    """Example slot: ("case_8841", "repair_cost_usd", 4100)"""
    case_id: str
    field: Literal["repair_cost_usd"] = "repair_cost_usd"
    amount_usd: int

    def supersedes(self, prior: "RepairEstimate") -> bool:
        if self.document.is_teardown and not prior.document.is_teardown:
            return True
        return super().supersedes(prior)
```

```python
# beacon_auto/documents.py
from factorial import Document, extract, segment
from beacon_auto.facts import CollisionDeductible, RepairEstimate, TrafficLightColor


class DriverStatement(Document):
    segmenter = segment.Turns()
    fact_types = [TrafficLightColor]

    @property
    def extractor(self) -> extract.Extractor:
        if self.token_count > 6_000:
            return extract.Staged()
        return extract.Passages()


class PoliceReport(Document):
    segmenter = segment.Paragraphs()
    fact_types = [TrafficLightColor]


class ShopEstimate(Document):
    is_teardown: bool = False
    fact_types = [RepairEstimate, CollisionDeductible]
```

```python
# beacon_auto/settings.py
import os
from factorial import Settings, index, judge, model, search, store


class ProjectSettings(Settings):
    storage = store.S3Bucket(bucket="beacon-facts", key=os.environ["S3_KEY"])
    search_index = index.SQLiteFTS(path="./var/index.db")
    retrieval = search.HybridRRF(budget_tokens=1_500)

    extractor_model = model.Pinned("gemini-2.5-flash-2026-02-01")
    judges = [judge.NLI(), judge.JevFloors()]  # runs in order; stops on first rejection
```

When you run `factorial eval --vary judge=none,nli,jev_floors`, the runner clones `ProjectSettings` in memory for each
trial, binds `ProjectSettings.judges` to the listed built-in or local `Judge` subclass, and scores every variant against
`evals/`.

## Pluggable seams

Storage (`local`, `s3`), sources (`folder`, `jsonl`, `imap`, `mcp`), pinned models, indexes (`sqlite-fts`,
`pgvectorscale`, `turbopuffer`), and judges (`nli`, `jev-floors`, `llm`) are base classes with standard methods. You
extend any seam by subclassing its base class in your project files.

## Why this approach

- **What it is good at:** Every link between documents, facts, and settings is a real Python import, so type checkers,
  autocomplete, and jump-to-definition work everywhere. Custom logic such as dynamic extractors or domain supersede
  rules sits directly on the class it governs with a `@property` or method override.
- **What it costs:** Configuration requires importing and executing user Python code, so non-engineers cannot edit
  settings safely in a static form, and external tools cannot inspect a project without running a Python interpreter.

## Next steps

Start with [docs/mental-model.md](docs/mental-model.md), and then read [docs/README.md](docs/README.md). Note that
[docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML design.
