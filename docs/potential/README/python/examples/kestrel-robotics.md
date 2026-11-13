# Example: kestrel_robotics

Kestrel Robotics tracks part quotes and datasheets from suppliers alongside bench test logs from its hardware lab.

## Fifteen minutes

Install Factoid with `uv` on Python 3.13+, ingest purchasing and lab files, and query the extracted facts.

```sh
uv tool install factoid
cd kestrel_robotics
factoid ingest ./sample_docs
factoid search "motor_x12 max operating temp"
factoid read fact_01j9z4m8p
factoid eval
factoid eval --vary judge=none,nli,continuous_rating
```

## Layout

```text
kestrel_robotics/
├── pyproject.toml
├── kestrel_robotics/
│   ├── settings.py    # storage, index, pinned models, and search
│   ├── sources.py     # supplier mailbox and lab drop folder
│   ├── documents.py   # VendorQuote, PartDatasheet, and BenchTestLog
│   ├── facts.py       # UnitPrice, LeadTime, and MaxOperatingTemp
│   └── judges.py      # custom fact quality checks
├── prompts/
│   ├── vendor_quote/
│   │   ├── extract.md.j2          # quote extraction rules
│   │   └── part_aliases.md.j2     # maps vendor SKUs to internal part IDs
│   ├── max_operating_temp/
│   │   └── resolve.md.j2          # compares supplier specs and lab limits
│   └── continuous_rating/
│       └── judge.md.j2            # separates continuous limits from spikes
└── evals/purchasing_and_lab.jsonl
```

## Documents

```python
# documents.py
from factoid import Document
from kestrel_robotics.facts import LeadTime, MaxOperatingTemp, UnitPrice

class VendorQuote(Document):
    """A price and lead-time quote or email from a component supplier."""
    facts = [UnitPrice, LeadTime, MaxOperatingTemp]

    def extract(self, passages):
        # Map supplier catalog numbers to internal part IDs before extracting facts.
        part_map = self.generate("part_aliases.md.j2", passages=passages)
        return super().extract(passages, part_map=part_map)

class PartDatasheet(Document):
    """A manufacturer specification sheet listing rated limits for a hardware part."""
    facts = [MaxOperatingTemp]
    classify_threshold = 0.85

    def classify_view(self) -> str:
        # Read the title block and maximum ratings table near the top of the sheet.
        return self.head(600)

class BenchTestLog(Document):
    """A hardware lab log recording measured thermal limits on a test bench."""
    facts = [MaxOperatingTemp]
```

## Facts

```python
# facts.py
import json
from pathlib import Path
from factoid import Entity, Fact

class UnitPrice(Fact):
    """The quoted price in USD for one unit of a hardware part."""
    part: Entity
    unit_price_usd: float

    def validate(self) -> bool:
        return self.unit_price_usd > 0

class LeadTime(Fact):
    """The supplier delivery lead time in weeks for a hardware part."""
    part: Entity
    lead_time_weeks: int

class MaxOperatingTemp(Fact):
    """The maximum continuous operating temperature in degrees Celsius for a part."""
    part: Entity
    max_temp_c: int

    def on_contradicted(self, other: "MaxOperatingTemp") -> None:
        row = {"part": str(self.part), "temps_c": [self.max_temp_c, other.max_temp_c]}
        with Path("./var/part_holds.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
```

## Sources and judges

```python
# sources.py
import os
from factoid.sources import FolderSource, ImapSource

class SupplierInbox(ImapSource):
    """Mailbox receiving price quotes and availability emails from vendors."""
    host = "imap.kestrelrobotics.internal"
    user = "purchasing@kestrelrobotics.internal"
    password = os.environ["IMAP_PASSWORD"]

class LabAndSpecDrop(FolderSource):
    """Directory where engineers place supplier datasheets and bench test logs."""
    path = "./incoming"
```

```python
# judges.py
from factoid import Judge

class ContinuousRating(Judge):
    """Accepts continuous operating limits and rejects storage limits or brief spikes."""

    def judge(self, fact) -> bool:
        level = self.score("judge.md.j2", rubric=["storage_or_spike", "ambiguous", "continuous"], fact=fact)
        return level == "continuous"
```

## Prompts

```jinja
{# prompts/vendor_quote/part_aliases.md.j2 #}
Map vendor catalog codes in these passages to Kestrel part IDs (for example, APX-X12 -> motor_x12).
{% for passage in passages %}[{{ passage.n }}] {{ passage.text }}{% endfor %}
```

```jinja
{# prompts/vendor_quote/extract.md.j2 #}
{% extends "factoid/extract.md.j2" %}
{% block guidance %}
Normalize part identifiers with this mapping: {{ part_map }}
Extract standard single-unit pricing and lead times. Skip expired promotional tiers and freight fees.
{% endblock %}
```

```jinja
{# prompts/max_operating_temp/resolve.md.j2 #}
{% extends "factoid/resolve.md.j2" %}
{% block guidance %}
Mark a vendor quote repeating an existing datasheet temperature for the same part as a duplicate.
Mark a newer manufacturer datasheet revision as superseding an older datasheet temperature.
Mark a bench test temperature limit below the supplier rating as a contradiction.
{% endblock %}
```

## Settings

```python
# settings.py
import os
from factoid import Model, Search, Settings
from factoid.indexes import SqliteFts
from factoid.stores import S3Store

class Project(Settings):
    store = S3Store(bucket="kestrel-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),
        "generate": Model("fireworks/glm-5p3-flash"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1500)
```

## What happens as documents arrive

1. **March 3, `x12_datasheet_rev2.pdf` (`PartDatasheet`):** Lists a 72 °C continuous limit for `motor_x12`.
   `ContinuousRating` accepts the value, and Factoid adds `("motor_x12", "max_temp_c", 72)`.
2. **March 5, `apex_quote_104.eml` (`VendorQuote`):** Quotes SKU `APX-X12` at $42.50 with an 8-week lead time and
   repeats the 72 °C limit. `VendorQuote.extract` maps `APX-X12` to `motor_x12`. Factoid adds
   `("motor_x12", "unit_price_usd", 42.50)` and `("motor_x12", "lead_time_weeks", 8)`, and merges the 72 °C claim as
   a duplicate citation on the March 3 datasheet fact.
3. **March 18, `apex_quote_109.eml` (`VendorQuote`):** Updates `motor_x12` to $39.00 and a 10-week lead time.
   Factoid adds `("motor_x12", "unit_price_usd", 39.00)` and `("motor_x12", "lead_time_weeks", 10)`, and marks both
   March 5 facts `superseded`. `UnitPrice.current(part="motor_x12").unit_price_usd` returns `39.0`.
4. **March 22, `bench_log_044.md` (`BenchTestLog`):** Logs a thermal chamber run on `motor_x12` where winding
   insulation fails above 64 °C continuous load. Factoid extracts `("motor_x12", "max_temp_c", 64)`, flags both
   temperature facts `contradicted`, and runs `on_contradicted` to write `motor_x12` to `./var/part_holds.jsonl`.

The design is described in [the Python README](../README.md).
