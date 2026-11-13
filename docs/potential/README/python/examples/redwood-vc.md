# Example: redwood_vc

`redwood_vc` extracts financial metrics and corporate governance facts from deal data rooms during startup diligence.

## Fifteen minutes

Install Factoid with `uv` on Python 3.13+. Inside the project directory, `factoid` uses the project environment.

```sh
uv tool install factoid
factoid new redwood_vc
cd redwood_vc
factoid ingest ./data_room
factoid search "Orbital revenue"
factoid read fact_01j9z4m8p
factoid eval
factoid eval --vary judge=none,nli,policy_judge
```

## Layout

```text
redwood_vc/
├── pyproject.toml
├── redwood_vc/
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # deal data room folder source
│   ├── documents.py   # PitchDeck, AuditedStatement, and BoardMinutes
│   ├── facts.py       # AnnualRevenue, CashRunway, and IncorporationState
│   └── judges.py      # PolicyJudge for diligence rules
├── prompts/
│   ├── pitch_deck/
│   │   ├── extract.md.j2         # deck extraction rules
│   │   └── slide_context.md.j2   # slide units and footnote summary
│   └── policy_judge/
│       └── judge.md.j2           # diligence evidence check
└── evals/orbital_diligence.jsonl
```

## Documents

Each document class defines its type in the docstring, lists its fact classes, and overrides hooks when needed.

```python
# documents.py
from factoid import Document
from redwood_vc.facts import AnnualRevenue, CashRunway, IncorporationState

class PitchDeck(Document):
    """A founder presentation covering product, traction, financials, and fundraising terms."""
    facts = [AnnualRevenue, CashRunway, IncorporationState]

    def extract(self, passages):
        # Summarize chart units and slide footnotes before extracting candidate facts.
        slide_context = self.generate("slide_context.md.j2", passages=passages)
        return super().extract(passages, slide_context=slide_context)

class AuditedStatement(Document):
    """An independent auditor's report and financial statements for a completed fiscal period."""
    facts = [AnnualRevenue, CashRunway]
    classify_threshold = 0.85

    def classify_view(self) -> str:
        # Read the cover page, auditor opinion, and signature block.
        return self.head(500) + self.tail(300)

class BoardMinutes(Document):
    """Approved minutes from a meeting of a company's board of directors."""
    facts = [AnnualRevenue, CashRunway, IncorporationState]
```

## Facts

Each fact class defines one claim type and its typed slot. `AnnualRevenue` rejects negative amounts in Python code.

```python
# facts.py
from factoid import Entity, Fact

class AnnualRevenue(Fact):
    """Recognized annual recurring revenue in US dollars for a completed reporting period."""
    company: Entity
    arr_usd: int

    def validate(self) -> bool:
        return self.arr_usd >= 0

class CashRunway(Fact):
    """Months of operating cash remaining at the company's current burn rate."""
    company: Entity
    runway_months: int

class IncorporationState(Fact):
    """The US state or jurisdiction where the company is legally incorporated."""
    company: Entity
    incorporation_state: str
```

## Sources and judges

`DataRoom` watches exported files, and `PolicyJudge` calls the choice model to reject unbacked or speculative claims.

```python
# sources.py
from factoid.sources import FolderSource

class DataRoom(FolderSource):
    """PDFs, decks, and board packets exported from the deal data room."""
    path = "./data_room"
```

```python
# judges.py
from factoid import Judge

class PolicyJudge(Judge):
    """Reject unquoted numbers and speculative promises."""

    def judge(self, fact) -> bool:
        return self.decide("judge.md.j2", fact=fact) >= 0.85
```

## Prompts

Templates in `prompts/` back custom model calls or extend Factoid's built-in hook prompts for a specific class.

```jinja
{# prompts/pitch_deck/slide_context.md.j2 #}
List currency units, reporting periods, and footnote qualifiers across these slides:
{% for passage in passages %}
[{{ passage.n }}] {{ passage.text }}
{% endfor %}
```

```jinja
{# prompts/pitch_deck/extract.md.j2 #}
{% extends "factoid/extract.md.j2" %}
{% block guidance %}
Slide units and footnotes: {{ slide_context }}
Expand unit shorthand such as "$3.9M" when the slide states the unit. Skip pipeline targets and multi-year forecasts.
{% endblock %}
```

```jinja
{# prompts/policy_judge/judge.md.j2 #}
Candidate fact: {{ fact }}
Answer yes only when every number appears in the cited passage and describes a completed period, with no forecast
verbs, pipeline targets, or speculative promises.
```

## Settings

Storage, search indexes, and pinned model versions live in `settings.py`.

```python
# settings.py
import os
from factoid import Model, Search, Settings
from factoid.indexes import SqliteFts
from factoid.stores import S3Store

class Project(Settings):
    store = S3Store(bucket="redwood-diligence", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),
        "generate": Model("fireworks/glm-5p3-flash"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1500)
```

## What happens as documents arrive

Three files for Orbital Inc. arrive in `./data_room` in order:

1. **Q3 board minutes (`2026-10-15`, `BoardMinutes`).** The minutes state that Orbital Inc. is incorporated in
   Delaware, closed Q3 at $3,100,000 in ARR, and holds 18 months of runway. Factoid logs `added` events for
   `("Orbital Inc.", "incorporation_state", "Delaware")`, `("Orbital Inc.", "arr_usd", 3100000)`, and
   `("Orbital Inc.", "runway_months", 18)`.
2. **Series A pitch deck (`2027-01-12`, `PitchDeck`).** Slides report Delaware incorporation, Q4 ARR of $3,900,000, 14
   months of runway, and a projected $9,000,000 ARR next year. `PolicyJudge` drops the $9,000,000 projection.
   `IncorporationState` matches the stored `"Delaware"` fact and merges as a duplicate with a second quote. The Q4
   facts `("Orbital Inc.", "arr_usd", 3900000)` and `("Orbital Inc.", "runway_months", 14)` supersede the Q3 figures.
3. **FY2026 audit (`2027-02-08`, `AuditedStatement`).** The auditor reports 14 months of runway and $3,450,000 in Q4
   ARR. The 14-month `CashRunway` merges as a duplicate. `("Orbital Inc.", "arr_usd", 3450000)` disagrees with the
   deck's $3,900,000 Q4 figure, so `resolve` flags both Q4 revenue facts as `contradicted`.

After ingestion, `CashRunway.current(company="Orbital Inc.").runway_months` returns `14`, and
`factoid search "Orbital revenue"` returns both Q4 revenue sentences, their quotes, and the contradiction flag.

The design is described in [the Python README](../README.md).
