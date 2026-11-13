# Factorial 🧮

> **Status:** This is a design draft. Nothing is built yet, and the docs get updated before code is written.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Core ideas

- **Facts are what a reader reads.** Search returns short, self-contained sentences with provenance. On dialogue
  benchmarks, reading facts beat chunk retrieval at about a seventh of the read tokens
  ([docs/prior-art.md](docs/prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages from the segmented document, and Python code
  attaches the exact quote, speaker, and timestamp.
- **History is the truth.** Every write appends to an event log (`added`, `superseded`, `contradicted`, `retracted`, and
  `restored`). Current state and search indexes are views rebuilt from that log.
- **Algorithm choices are made by evals.** `factorial eval` scores a project setup against labeled data and reports
  accuracy, cost, and latency. Built-in defaults are eval results.

## Fifteen minutes

Factorial requires Python 3.13+ and [uv](https://docs.astral.sh/uv/). Generate a project and a domain app, ingest a
folder, search and inspect facts, and compare judge strategies:

```bash
uv tool install factorial
factorial new helpdesk && cd helpdesk
uv run factorial startapp tickets
uv run factorial ingest ./sample_emails
uv run factorial search "Acme plan tier"
uv run factorial read fact_01j8k2m9
uv run factorial eval
uv run factorial eval --vary judge=none,nli,jev_floors
```

## Project layout

A project follows Django conventions. Project-wide infrastructure lives in `settings.py`. Domain declarations live in
installed apps with standard module names, and classes register explicitly.

```text
helpdesk/
  pyproject.toml
  helpdesk/
    settings.py
  tickets/
    apps.py
    sources.py
    documents.py
    facts.py
    judges.py
    evals.py
```

## Declared in Python

`helpdesk/settings.py` declares installed apps, pinned models, storage, indexes, search defaults (`bm25`, `vector`, or
`hybrid-rrf`), and the judge chain. Cheap judges go first because the chain rejects at the first failure. Secrets come
from environment variables.

```python
import os
from factorial.conf import BucketStore, HybridRRF, PgVectorScale

INSTALLED_APPS = ["tickets"]

MODELS = {
    "extractor": "openai:gpt-4.1-mini-2025-04-14",
    "policy_llm": "anthropic:claude-haiku-4-5-20251001",
}
API_KEYS = {
    "openai": os.environ["OPENAI_API_KEY"],
    "anthropic": os.environ["ANTHROPIC_API_KEY"],
}

STORE = BucketStore(url="s3://helpdesk-facts", region="us-east-1")
INDEX = PgVectorScale(dsn=os.environ["DATABASE_URL"])
JUDGE_CHAIN = ["nli", "jev-floors", "tickets.PolicyJudge"]
SEARCH = {"retrieve": HybridRRF(), "rerank": True, "budget_tokens": 1200}
```

`tickets/sources.py` and `tickets/documents.py` declare how documents enter the pipeline (`classify`, `segment`,
`extract`, `judge`, `repair`, `resolve`, and `tag`):

```python
from factorial import documents, register, sources

@register
class SupportInbox(sources.ImapSource):
    host: str = "imap.acme.example"
    mailbox: str = "INBOX"
    document_type: str = "tickets.SupportEmail"

@register
class SupportEmail(documents.Document):
    class Meta:
        classify = "declared"
        segment = "email"
        extract = "passages"
        extract_model = "extractor"
```

`tickets/facts.py` declares fact types with optional typed slots (`entity`, `field`, and `value`). Deduplication,
superseding, and contradiction checks run at ingest, on write:

```python
from factorial import facts, fields, register, rules

@register
class AccountPlan(facts.Fact):
    entity: str = fields.CharField(max_length=120)
    value: str = fields.ChoiceField(choices=["free", "pro", "enterprise"])

    class Meta:
        slot_field = "plan_tier"
        resolve = ["hash", "slot", "vector-judge"]
        supersede = rules.NewerSlotWins()
```

`tickets/judges.py` defines custom judges that mix into `JUDGE_CHAIN` alongside built-ins:

```python
from factorial import judges, register

@register
class PolicyJudge(judges.LLMJudge):
    model: str = "policy_llm"
    prompt: str = "Reject speculative promises, unquoted numbers, and unverified dates."
```

When `factorial eval --vary` runs (for example, `--vary judge=none,nli,jev_floors` or `--vary
tickets.SupportEmail.extract=passages,staged`), the eval runner clones the loaded settings and app registry for each
trial and overrides the target setting or `Meta` attribute in memory.

## Pluggable seams

Core boundaries use subclassable base classes with built-in implementations:

- **Storage and indexes:** local folders or S3-compatible buckets, paired with `sqlite-fts`, `pgvectorscale`, or
  `turbopuffer`.
- **Sources:** `folder`, `jsonl`, `imap`, and `mcp`, plus custom `Source` subclasses.
- **Models:** named once in `MODELS` and pinned to exact snapshots (never `"latest"`).
- **Judges:** `nli`, `jev-floors`, `llm`, and custom `Judge` subclasses run in a short-circuiting chain.

## Why this approach

Splitting declarations across `settings.py` and domain apps keeps individual files short, readable, and easy to
navigate. Declarative Python classes give editors autocomplete, static type checking, standard imports, and normal
`pytest` tests. Built-in generators create the same file layout in every project, so readers know where every definition
lives. Users write Python classes, imports, and registration calls even when a project uses built-in strategies without
custom code. Tools that inspect or edit project configuration must also load a Python environment and import the project
modules.

## Further reading

Start with [docs/mental-model.md](docs/mental-model.md), then read [docs/README.md](docs/README.md).
Note: [docs/config.md](docs/config.md) and [docs/plugins.md](docs/plugins.md) still describe the older single-YAML
design.
