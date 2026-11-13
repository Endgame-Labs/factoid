# Example: harbor_realty

`harbor_realty` tracks apartment lease terms and repair reports from signed leases, tenant emails, and invoices.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+, ingest the sample files, search stored facts, and run the evals.

```sh
uv tool install factorial
cd harbor_realty
factorial ingest ./sample_docs
factorial search "Unit 4B heater"
factorial read fact_01j9x8k2m
factorial eval
factorial eval --vary judge=none,nli,direct_inspection
```

## Layout

```text
harbor_realty/
├── pyproject.toml
├── harbor_realty/
│   ├── settings.py    # storage, index, pinned models, and search
│   ├── sources.py     # lease folder and office inbox
│   ├── documents.py   # LeaseAgreement, TenantEmail, and PlumberInvoice
│   ├── facts.py       # MonthlyRent, PetPolicy, and HeaterStatus
│   └── judges.py      # DirectInspection judge
├── prompts/
│   ├── tenant_email/extract.md.j2
│   ├── tenant_email/thread_summary.md.j2
│   ├── heater_status/resolve.md.j2
│   └── direct_inspection/judge.md.j2
└── evals/leases_and_repairs.jsonl
```

## Documents

Each document class puts its classifier definition in its docstring and lists the fact types it yields. `TenantEmail`
summarizes quoted messages before extracting, and `PlumberInvoice` sends its header and totals to the classifier.

```python
# documents.py
from factorial import Document
from harbor_realty.facts import HeaterStatus, MonthlyRent, PetPolicy

class LeaseAgreement(Document):
    """A signed residential lease or renewal agreement for an apartment unit."""
    facts = [MonthlyRent, PetPolicy]

class TenantEmail(Document):
    """An email from a tenant to the leasing office about lease rules or unit repairs."""
    facts = [HeaterStatus, PetPolicy]

    def extract(self, passages):
        thread = self.generate("thread_summary.md.j2", passages=passages)
        return super().extract(passages, thread=thread)

class PlumberInvoice(Document):
    """An invoice from a plumbing contractor for repair work on an apartment unit."""
    facts = [HeaterStatus]
    classify_threshold = 0.8

    def classify_view(self) -> str:
        return self.head(400) + self.tail(400)
```

## Facts

Typed attributes define the slot; code reads active values with `PetPolicy.current(unit="Unit 4B").pets_allowed`.

```python
# facts.py
from typing import Literal
from factorial import Entity, Fact

class MonthlyRent(Fact):
    """The monthly rent in US dollars for an apartment unit under a signed lease."""
    unit: Entity
    monthly_rent_usd: int

    def validate(self) -> bool:
        return 500 <= self.monthly_rent_usd <= 25_000

class PetPolicy(Fact):
    """Whether tenants in an apartment unit are permitted to keep pets."""
    unit: Entity
    pets_allowed: bool

class HeaterStatus(Fact):
    """Whether a unit's heater is working, leaking, or broken according to someone who checked it."""
    unit: Entity
    heater_status: Literal["working", "leaking", "broken"]
```

## Sources and judges

Leases arrive in a local folder, and mail arrives over IMAP. `DirectInspection` checks for firsthand observation.

```python
# sources.py
import os
from factorial.sources import FolderSource, ImapSource

class LeaseFolder(FolderSource):
    """Directory where staff drop signed lease PDFs."""
    path = "./inbox/leases"

class OfficeInbox(ImapSource):
    """Mailbox receiving tenant emails and contractor invoices."""
    host = "imap.harborrealty.com"
    user = os.environ["IMAP_USER"]
    password = os.environ["IMAP_PASSWORD"]
```

```python
# judges.py
from factorial import Judge

class DirectInspection(Judge):
    """Accepts facts stated in a signed lease or reported by someone who inspected the unit."""

    def judge(self, fact) -> float:
        return self.decide("judge.md.j2", fact=fact)
```

## Prompts

Hook templates extend built-in templates and override named blocks. Helper templates called by custom code stand alone.

```jinja
{# prompts/tenant_email/thread_summary.md.j2 #}
Summarize earlier messages in two sentences, noting the unit and any open repair:
{% for p in passages %}[{{ p.n }}] {{ p.speaker }}: {{ p.text }}
{% endfor %}
```

```jinja
{# prompts/tenant_email/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}
Earlier thread: {{ thread }}. Extract from the newest message only; skip greetings, signatures, and quoted replies.
{% endblock %}
```

```jinja
{# prompts/heater_status/resolve.md.j2 #}
{% extends "factorial/resolve.md.j2" %}
{% block guidance %}
Repair invoices dated after a leak report supersede that report. Opposing claims on one visit are contradicted.
{% endblock %}
```

```jinja
{# prompts/direct_inspection/judge.md.j2 #}
Does the quote show firsthand inspection of the unit or text from a signed lease for "{{ fact.text }}"?
Quote: "{{ fact.quote }}"
```

## Settings

```python
# settings.py
import os
from factorial import Model, Search, Settings
from factorial.indexes import SqliteFts
from factorial.stores import S3Store

class Project(Settings):
    store = S3Store(bucket="harbor-realty-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),
        "generate": Model("fireworks/glm-5p3-flash"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1500)
```

## What happens as documents arrive

1. **`2025-09-01` (`lease_4b_2025.pdf`, `LeaseAgreement`).** Sets Unit 4B rent at $1,950 and forbids pets. `validate`
   passes, adding `("Unit 4B", "monthly_rent_usd", 1950)` and `("Unit 4B", "pets_allowed", False)`.
2. **`2026-09-01` (`lease_4b_2026.pdf`, `LeaseAgreement`).** Raises rent to $2,050 and repeats the no-pets clause.
   `resolve` marks the $1,950 `MonthlyRent` **superseded**, adds `("Unit 4B", "monthly_rent_usd", 2050)`, and merges
   `("Unit 4B", "pets_allowed", False)` as a **duplicate** backed by quotes from both leases.
3. **`2026-11-10` (`inv_8841.pdf`, `PlumberInvoice`).** Bay Plumbing bills for replacing a Unit 4B radiator valve and
   notes the heater was left working. `classify_view` sends the header and totals to the classifier, `DirectInspection`
   approves the quote, and Factorial adds `("Unit 4B", "heater_status", "working")`.
4. **`2026-11-10` (`email_412.eml`, `TenantEmail`).** That evening the tenant emails that water is pooling under the
   Unit 4B heater after the plumber left. `extract` summarizes the thread and pulls
   `("Unit 4B", "heater_status", "leaking")`. Per `heater_status/resolve.md.j2`, `resolve` flags both `HeaterStatus`
   facts as **contradicted**.

The design is described in [the Python README](../README.md).
