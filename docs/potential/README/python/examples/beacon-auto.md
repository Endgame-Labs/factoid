# Example: beacon_auto

`beacon_auto` turns auto insurance incident files and policy records into cited facts for adjusters and backend code.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+, create `beacon_auto`, and ingest a folder of sample incident files.

```sh
uv tool install factorial
factorial new beacon_auto
cd beacon_auto
factorial ingest ./sample_docs
factorial search "case_8841 northbound light"
factorial read fact_01j9z4m8q
factorial eval
factorial eval --vary judge=none,nli,firsthand
```

## Layout

Incident files and policy exports share one flat package of sources, documents, facts, and judges.

```text
beacon_auto/
├── pyproject.toml
├── beacon_auto/
│   ├── settings.py    # storage, index, pinned models, and search budget
│   ├── sources.py     # adjuster mail inbox and policy export folder
│   ├── documents.py   # DriverStatement, PoliceReport, and ShopEstimate
│   ├── facts.py       # TrafficLightColor, RepairEstimate, and CollisionDeductible
│   └── judges.py      # Firsthand judge for witness and inspection facts
├── prompts/
│   ├── police_report/
│   │   └── vehicles.md.j2         # maps report unit numbers to travel directions
│   ├── shop_estimate/
│   │   ├── stage.md.j2            # picks initial quote or teardown supplement
│   │   └── extract.md.j2          # pulls net repair totals and deductibles
│   ├── repair_estimate/
│   │   └── resolve.md.j2          # compares early quotes with supplements
│   └── firsthand/
│       └── judge.md.j2            # rejects hearsay and uninspected guesses
└── evals/incidents_and_policies.jsonl
```

## Documents

Each document class holds its docstring definition, the fact types that document yields, and any custom hook code.

```python
# documents.py
from factorial import Document
from beacon_auto.facts import CollisionDeductible, RepairEstimate, TrafficLightColor

class DriverStatement(Document):
    """A signed or emailed statement from a driver involved in a collision."""
    facts = [TrafficLightColor, CollisionDeductible]

class PoliceReport(Document):
    """An investigating officer's collision report with narrative, diagram notes, and citations."""
    facts = [TrafficLightColor]

    def extract(self, passages):
        vehicles = self.generate("vehicles.md.j2", passages=passages)
        return super().extract(passages, vehicles=vehicles)

class ShopEstimate(Document):
    """A repair estimate or tear-down supplement from an auto body shop."""
    facts = [RepairEstimate, CollisionDeductible]
    classify_threshold = 0.85

    def classify_view(self) -> str:
        return self.head(500) + self.tail(500)

    def extract(self, passages):
        probs = self.choose("stage.md.j2", options=["initial", "teardown"], passages=passages)
        return super().extract(passages, stage=max(probs, key=probs.get))
```

## Facts

Typed attributes define each fact's slot. `CollisionDeductible` uses `validate` to reject invalid deductible amounts.

```python
# facts.py
from typing import Literal
from factorial import Entity, Fact

class TrafficLightColor(Fact):
    """The color shown by a specific traffic light when vehicles entered the intersection."""
    case: Entity
    light: Literal["northbound_light", "southbound_light", "eastbound_light", "westbound_light"]
    color: Literal["green", "yellow", "red"]

class RepairEstimate(Fact):
    """The total estimated cost in US dollars to repair vehicle damage on a case."""
    case: Entity
    repair_cost_usd: int

class CollisionDeductible(Fact):
    """The collision deductible in US dollars set on an auto insurance policy."""
    policy: Entity
    deductible_usd: int

    def validate(self) -> bool:
        return self.deductible_usd in {250, 500, 1000, 2000}
```

## Sources and judges

`sources.py` reads adjuster mail and policy exports. `judges.py` checks whether a speaker had direct knowledge.

```python
# sources.py
import os
from factorial.sources import FolderSource, ImapSource

class IncidentInbox(ImapSource):
    """Adjuster mailbox receiving driver statements, police reports, and shop estimates."""
    host = "imap.beaconauto.example"
    password = os.environ["IMAP_PASSWORD"]

class PolicyExports(FolderSource):
    """Nightly folder export of policy declarations and endorsements from underwriting."""
    path = "./var/policy_exports"
```

```python
# judges.py
from factorial import Judge

class Firsthand(Judge):
    """Accepts facts backed by direct sight, camera video, policy text, or physical shop inspection."""

    def judge(self, fact) -> bool:
        return self.decide("judge.md.j2", fact=fact) >= 0.7
```

## Prompts

Templates in `prompts/` replace or extend Factorial's built-in Jinja prompts for a specific class and hook.

```jinja
{# prompts/shop_estimate/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}
Stage: {{ stage }}. Skip part numbers, labor tables, and tax subtotals.
Extract RepairEstimate from the grand total and CollisionDeductible from the policy header.
{% endblock %}
```

```jinja
{# prompts/repair_estimate/resolve.md.j2 #}
{% extends "factorial/resolve.md.j2" %}
{% block guidance %}
On the same case, a teardown supplement supersedes an earlier visual quote; competing initial quotes disagree.
{% endblock %}
```

## Settings

```python
# settings.py
import os
from factorial import Model, Search, Settings
from factorial.indexes import SqliteFts
from factorial.stores import S3Store

class Project(Settings):
    store = S3Store(bucket="beacon-auto-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),
        "generate": Model("fireworks/glm-5p3-flash"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1500)
```

## What happens as documents arrive

Four files arrive in order for `case_8841` and `policy_992`:

1. **`driver_maya_lin.txt` (`DriverStatement`, March 14).** Maya Lin writes that she entered on a green northbound
   light and carries a `$500` deductible on `policy_992`. `validate` accepts `500`, logging two `added` facts:
   `TrafficLightColor("case_8841", "northbound_light", "green")` and `CollisionDeductible("policy_992", 500)`.
2. **`apd_report_8841.pdf` (`PoliceReport`, March 15).** `PoliceReport.extract` maps vehicle numbers to directions
   and pulls Officer Ortiz's camera finding: `TrafficLightColor("case_8841", "northbound_light", "red")`. `resolve`
   compares that fact against Maya Lin's `"green"` fact; both stay active with their quotes, marked `contradicted`.
3. **`harbor_body_initial.pdf` (`ShopEstimate`, March 16).** Harbor Body Shop quotes `$1,950` for bumper repairs on
   `case_8841` and lists `policy_992`'s `$500` deductible. `resolve` merges `CollisionDeductible("policy_992", 500)`
   as a duplicate, adding the shop quote to the stored fact, and logs `RepairEstimate("case_8841", 1950)` as `added`.
4. **`harbor_body_supplement.pdf` (`ShopEstimate`, March 19).** After bumper removal, the shop sends a tear-down
   supplement at `$4,100`. `ShopEstimate.extract` sets `stage="teardown"`, `resolve` marks the `$1,950` visual quote
   `superseded`, and `RepairEstimate.current(case="case_8841").repair_cost_usd` returns `4100`.

The design is described in [the Python README](../README.md).
