# Example: revenue_desk

`revenue_desk` is a B2B sales workspace that turns CRM records, call transcripts, emails, and notes into typed facts
about accounts, people, and deals. It is modeled on `endgame-wiki`'s default revenue starter workspace.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+, enter the example directory, ingest the sample fixture set, and run a
query and an eval.

```sh
uv tool install factorial
cd examples/revenue_desk
factorial ingest ./sample_docs
factorial search "Acme security review"
factorial read fact_01j9z4m8p
factorial eval
factorial eval --vary tag=choice,llm
```

`factorial` finds `revenue_desk`'s project environment automatically and runs inside it.

## Layout

```text
revenue_desk/
├── pyproject.toml
├── revenue_desk/
│   ├── settings.py    # storage, indexes, pinned models, search, and our_domains
│   ├── entities.py    # Account, Person, and Opportunity
│   ├── sources.py     # Salesforce, Gong, IMAP mail, and local markdown notes
│   ├── documents.py   # Call, Email, CrmOpportunity, and Note
│   ├── facts.py       # RevenueFact, DealAmount, CloseDate, DealStage, and NextStep
│   └── judges.py      # AgreedJudge
├── prompts/
│   ├── call/
│   │   ├── speaker_brief.md.j2
│   │   └── extract.md.j2
│   ├── email/
│   │   └── extract.md.j2
│   └── agreed_judge/
│       └── judge.md.j2
└── evals/acme_renewal.jsonl
```

## Entities

Accounts, people, and deals arrive from four sources under different internal IDs. Each `Entity` subclass declares a
`key` attribute so records from Gong, mail, notes, and the CRM resolve to the same entity, and `Person` overrides
`same_as` to ask the choice model when an email address is missing.

```python
# entities.py
from factorial import Entity

class Account(Entity):
    """A customer or prospect company."""
    key = "domain"
    name: str
    domain: str

class Person(Entity):
    """A person at our company or at an account."""
    key = "email"
    name: str
    email: str | None = None
    role_title: str | None = None
    account: Account | None = None

    def same_as(self, other: "Person") -> float:
        if self.email and other.email:
            return 1.0 if self.email == other.email else 0.0
        return self.decide("same_as.md.j2", other=other)

class Opportunity(Entity):
    """A commercial deal tracked in the CRM."""
    key = "crm_id"
    crm_id: str
    name: str
    account: Account
    owner: Person
```

## Documents

`Call` summarizes who is in the room before running extraction, `Email` uses a prompt override, `CrmOpportunity` emits
typed facts in plain code with no model call, and `Note` relies on all base defaults.

```python
# documents.py
from datetime import date
from factorial import Document, FieldCitation
from revenue_desk.entities import Opportunity
from revenue_desk.facts import CloseDate, DealAmount, DealStage, NextStep, RevenueFact

class Call(Document):
    """A recorded sales or customer call transcript from Gong or Granola."""
    segment_by = "turns"
    facts = [RevenueFact, CloseDate, DealAmount, NextStep]

    def extract(self, passages):
        brief = self.generate("speaker_brief.md.j2", passages=passages)
        return super().extract(passages, speaker_brief=brief)

class Email(Document):
    """An email message between Harbor and an account."""
    segment_by = "email"
    facts = [RevenueFact, CloseDate, DealAmount, NextStep]

class CrmOpportunity(Document):
    """A structured opportunity record synced from the CRM."""
    facts = [DealAmount, CloseDate, DealStage]

    def extract(self, passages):
        opp = Opportunity.by_key(self.fields["id"], name=self.fields["name"])
        return [
            DealAmount(
                opportunity=opp,
                usd=int(self.fields["amount"]),
                cite=FieldCitation("amount", self.fields["amount"]),
            ),
            CloseDate(
                opportunity=opp,
                date=date.fromisoformat(self.fields["close_date"]),
                cite=FieldCitation("close_date", self.fields["close_date"]),
            ),
            DealStage(
                opportunity=opp,
                stage=self.fields["stage"],
                cite=FieldCitation("stage", self.fields["stage"]),
            ),
        ]

class Note(Document):
    """A local markdown note written about an account, call, or deal."""
```

When `CrmOpportunity` syncs unchanged fields on a later run, `resolve` merges identical claims into the stored fact and
adds nothing new. A changed field yields a new fact for the same slot and supersedes the previous value.

## Facts

`RevenueFact` is the workspace's base fact class. It attaches a closed 22-label taxonomy so the default `tag` hook can
score every label in one choice-model call and keep every label at or above `0.5`.

```python
# facts.py
from datetime import date
from typing import Literal
from factorial import Fact
from revenue_desk.entities import Account, Opportunity
from revenue_desk.judges import AgreedJudge
from revenue_desk.queues import review_queue

class RevenueFact(Fact):
    """A standalone factual statement about an account, its people, or an active deal."""
    account: Account
    tags = [
        "action_item",
        "commercial_terms",
        "deal_risk",
        "decision_commitment",
        "next_step",
        "risk_objection",
        "timeline",
        # ... 15 more labels in the 22-label revenue taxonomy
    ]
    tag_threshold = 0.5

class DealAmount(RevenueFact):
    """The annual contract value of an opportunity in US dollars."""
    opportunity: Opportunity
    usd: int

class DealStage(RevenueFact):
    """The pipeline stage of an opportunity."""
    opportunity: Opportunity
    stage: str

class CloseDate(RevenueFact):
    """The expected signature or close date of an opportunity."""
    opportunity: Opportunity
    date: date

    def on_contradicted(self, other: "CloseDate") -> None:
        review_queue.put(owner=self.opportunity.owner, pair=(self, other))

class NextStep(RevenueFact):
    """A concrete follow-up action with an owner side and an optional due date."""
    account: Account
    owner_side: Literal["ours", "theirs"]
    due: date | None = None
    judges = [*Fact.judges, AgreedJudge]
```

## Sources and judges

`sources.py` maps external systems onto the four document types. `AgreedJudge` calls `self.decide` with its own prompt
so an unaccepted pitch on a call does not become a `NextStep`.

```python
# sources.py
import os
from factorial.sources import FolderSource, ImapSource, JsonlSource
from revenue_desk.documents import Call, CrmOpportunity, Email, Note

crm = JsonlSource(path="./var/salesforce_opps.jsonl", document_type=CrmOpportunity)
calls = JsonlSource(path="./var/gong_calls.jsonl", document_type=Call)
mail = ImapSource(host="imap.harbor.example", password=os.environ["IMAP_PASSWORD"], document_type=Email)
notes = FolderSource(path="./notes", glob="**/*.md", document_type=Note)
```

```python
# judges.py
from factorial import Judge

class AgreedJudge(Judge):
    """Accepts a NextStep only when the other party agreed to it."""
    floor = 0.7

    def judge(self, candidate, passages) -> float:
        return self.decide("judge.md.j2", candidate=candidate, passages=passages)
```

## Prompts

Prompt templates sit under `prompts/<class_name>/<hook>.md.j2`. `Call` overrides the passage block so the extractor sees
whether each speaker is on `"ours"`, `"theirs"`, or `"unknown"` side.

```jinja
{# prompts/call/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}
Participants: {{ speaker_brief }}
Record what their side stated, asked for, committed to, or pushed back on.
Statements from our side pitching features or suggesting ideas are not account facts.
{% endblock %}
{% block passages %}
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker.name }} ({{ passage.speaker.side }}): {{ passage.text }}
{% endfor %}
{% endblock %}
```

```jinja
{# prompts/email/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}
Skip greetings, legal footers, signatures, and quoted replies from earlier messages.
{% endblock %}
```

```jinja
{# prompts/agreed_judge/judge.md.j2 #}
Candidate next step: {{ candidate.text }}
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker.name }} ({{ passage.speaker.side }}): {{ passage.text }}
{% endfor %}
Did both sides agree to take this step, as opposed to one speaker floating a proposal?
```

## Settings

`our_domains` tells Factorial which email domains belong to Harbor so every passage speaker gets a `side` attribute
before hooks, prompts, and judges run.

```python
# settings.py
import os
from factorial import Model, Search, Settings
from factorial.indexes import SqliteFts
from factorial.stores import S3Store

class Project(Settings):
    our_domains = ["harbor.example"]
    store = S3Store(bucket="harbor-revenue-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),
        "generate": Model("fireworks/glm-5p3-flash"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1800)
```

## Reading facts

Downstream readers, such as an account brief or a pipeline risk report, query facts by entity, tag, window, and event
time, or read current slot values directly.

```python
from revenue_desk.entities import Account, Opportunity
from revenue_desk.facts import CloseDate, RevenueFact

acme = Account.by_key("acme.example")
renewal = Opportunity.by_key("opp_0192a")

risks = RevenueFact.where(
    account=acme,
    tags=["deal_risk", "risk_objection"],
    since="365d",
    limit=30,
)
close_on = CloseDate.current(opportunity=renewal).date
delta = RevenueFact.where(account=acme, learned_since=last_run_at)
```

## What happens as documents arrive

Harbor (`harbor.example`) is working `"Acme Corp Renewal 2027"` with Priya Natarajan (VP Engineering) and Tom Okafor
(procurement) at Acme Corp (`acme.example`). Four documents arrive in October:

1. **CRM record, October 1.** Salesforce syncs the opportunity with amount `100000`, close date `2026-11-30`, and stage
   `Negotiation`. `CrmOpportunity.extract` runs in Python and writes `DealAmount`, `CloseDate`, and `DealStage`.
2. **Gong call, October 8.** Priya (`theirs`) says, "we have to get through security before the board meets in
   November." A Harbor rep (`ours`) proposes a pricing workshop that nobody accepts, and Tom (`theirs`) mentions that
   the renewal is "a hundred thousand." Factorial stores the security review fact on `acme.example` with tags
   `timeline` (`0.91`) and `decision_commitment` (`0.74`), rejects the workshop in `AgreedJudge`, and merges Tom's
   quote into the existing `100000` `DealAmount` fact as a second citation.
3. **Email, October 20.** Priya writes that the board meeting moved to December 12 and Acme cannot sign before it. The
   extractor pulls a `CloseDate` after `2026-12-12` for the renewal from `theirs`. `resolve` marks it as contradicting
   the CRM's `2026-11-30` `CloseDate`, flags both facts, and fires `CloseDate.on_contradicted` to queue the pair for
   the deal owner.
4. **CRM record, October 22.** The deal owner updates the close date in Salesforce to `2026-12-19`. The new `CloseDate`
   supersedes the CRM's `2026-11-30` claim by slot rule, and the contradiction clears once the older claim is retired.
   How a contradiction gets cleared in general (automatically on supersede, by a resolution rule, or by explicit review)
   is still an open design question.

## New API this example needs

- `Entity` subclasses with `key`, `by_key()`, and an optional `same_as` hook to merge records across sources.
- `tags`, `tag_threshold`, and a default `tag` hook on `Fact` for multi-label classification in one choice-model call.
- `Settings.our_domains` and `passage.speaker.side` (`"ours"`, `"theirs"`, or `"unknown"`) derived from email domains.
- `Fact.where()` supporting entity filters, `tags`, `since`, `limit`, and `learned_since` over the event log.
- Plain-code `Document.extract` returning `Fact` instances attached to `FieldCitation` values with no model call.

The design is described in [the Python README](../README.md), and the mapping from the revenue starter is in
[crm-starter.md](../../../crm-starter.md).
