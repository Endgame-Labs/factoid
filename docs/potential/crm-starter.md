# The revenue starter in Factorial

Factorial is a fact system in the design stage, and nothing is built yet. This note walks through the default
"revenue starter" workspace from `endgame-wiki` and states how each piece maps onto Factorial, what fits, and what
Factorial lacks. Worked examples for the `revenue_desk` CRM project are in [Python](README/python/examples/crm.md)
and [Ruby](README/ruby/examples/crm.md).

## What the revenue starter does

`endgame-wiki init` creates a workspace over local markdown files, Salesforce, Gong, Granola, a calendar, Gmail,
Slack, GitHub, and Linear. Unstructured sources yield single-sentence facts with a named subject, one to three exact
quotes, speaker attribution (`yours`, `theirs`, or `unknown` from email domains), six judge scores against floors,
and every label scoring at least 0.5 in a 22-label taxonomy. Structured CRM fields yield code-written claim facts
whenever a synced value changes.

Curator agents admit, archive, and merge records across collections of accounts, opportunities, people, meetings,
calls, knowledge, and digests. Article agents query facts to write cited pages for those collections plus
open-pipeline, a pipeline report, and risk-radar. People can also retract a fact or state a fact in their own words.

| Starter piece | In Factorial | Fit |
| --- | --- | --- |
| Gong, Granola, Gmail, CRM, and local files | Sources for `Call`, `Email`, `CrmOpportunity`, and `Note` | Direct |
| Fact with quotes, speaker, and judge scores | Base `Fact` with the default judge chain | Direct |
| Six judge floors and one repair | The `judge` and `repair` hooks | Direct |
| Distinct from closest facts | `resolve` (duplicate, supersedes, and contradicts) | Direct, plus supersede |
| Claim facts from CRM fields | Code `extract` (`DealAmount`, `CloseDate`, and `DealStage`) | Fits; slot supersedes |
| 22-label class vector (score >= 0.5) | `tags` list on base `Fact` and a multi-label `tag` hook | New API |
| `speaker_side` (`yours`, `theirs`, `unknown`) | `our_domains` setting and `side` on passage speakers | New API |
| Accounts, people, and deals | `Entity` subclasses with `key` and `same_as` hook | New API (open question) |
| Curators (which accounts and deals to keep) | Out of scope; belongs in sources or reading apps | Not covered |
| Entity, class, window, and limit queries | `Fact.where(account=..., tags=[...], since=..., limit=...)` | New API |
| Changes since the reader's last run | `Fact.where(..., learned_since=last_run)` from event log | New API |
| Stakeholder roles across many facts | Done by the reader, or a derived fact over other facts | Open question |
| Articles, digests, risk radar, and publishing | Out of scope; readers built on Factorial reads | Not covered |
| Retract and "tell" by a person | Retract and restore exist; needs fact input from a person | Small addition |

## What maps directly

In `revenue_desk`, Harbor (`harbor.example`) is selling "Acme Corp Renewal 2027" to Acme Corp (`acme.example`),
where Priya Natarajan is VP Engineering and Tom Okafor works in procurement. Sources yield four document types:
`Call`, `Email`, `CrmOpportunity`, and `Note`. `Note` uses all defaults, so its class body is only its definition.
`Email` uses email segmentation with guidance to skip quoted replies and signatures. `Call` segments transcripts by
turns and guides extraction to record what Acme's side said, asked, and pushed back on, since a Harbor pitch is not
a fact about the account.

Factorial's base `Fact` handles self-contained sentences, exact quotes, speaker attribution, and the six starter
floors (`grounded`, `attribution`, `self_contained`, `atomic`, `useful`, and `distinct`) plus one repair through the
`judge` and `repair` hooks. Subclasses add typed slots and custom judges. `CloseDate` (opportunity and date) and
`DealAmount` (opportunity and USD) come from CRM records by code and from calls and emails by the model. `NextStep`
(account, owner side, and due date) adds `AgreedJudge`, which uses `decide` on a choice model to ask whether the
step was agreed to or only proposed, rejecting proposals.

The `resolve` hook handles duplicates, superseding values, and contradictions. `CloseDate.on_contradicted`
(`after_contradict` in Ruby) puts conflicting close dates into a review queue for the deal owner. Four documents in
`revenue_desk` show how these pieces run in order:

1. **October 1 (`CrmOpportunity`)**: Renewal 2027 arrives with amount 100,000, close date November 30, and stage
   Negotiation. Code writes `DealAmount`, `CloseDate`, and `DealStage`.
2. **October 8 (`Call`)**: Priya says, "we have to get through security before the board meets in November."
   Factorial adds "Acme's security review must finish before the November board meeting.", tagged `timeline` (0.91)
   and `decision_commitment` (0.74). A Harbor rep proposes a pricing workshop that nobody accepts, and `AgreedJudge`
   rejects it. Tom repeats that the renewal is "a hundred thousand", which merges into the CRM's `DealAmount` fact
   as a second quote.
3. **October 20 (`Email`)**: Priya writes that the board meeting moved to December 12 and Acme cannot sign before
   it. The model extracts a `CloseDate` after December 12 from their side, contradicting November 30. Both facts are
   flagged, and `CloseDate.on_contradicted` queues them for review.
4. **October 22 (`CrmOpportunity`)**: The deal owner moves the close date to December 19. The slot rule supersedes
   November 30, and the newer value clears the contradiction (how clearing works is an open design question).

## What needs new API

### Tags

The starter scores every fact against 22 labels (`action_item`, `commercial_terms`, `competitors`, `deal_risk`,
`decision_commitment`, `risk_objection`, `timeline`, and 15 others) and keeps every label scoring at least 0.5.
Factorial lacks multi-label classification, because a `Fact` subclass represents one type with one slot. Proposed
shape: a `tags` list and `tag_threshold` on a base fact class, scored in one choice-model call by a `tag` hook.

```python
class RevenueFact(Fact):
    tags = [
        "action_item", "commercial_terms", "competitors",
        "deal_risk", "decision_commitment", "risk_objection", "timeline",  # + 15 more
    ]
    tag_threshold = 0.5
```

### Sides

The starter marks each citation speaker with `speaker_side` (`yours`, `theirs`, or `unknown`) from the speaker's
email domain against workspace domains. Factorial lacks a notion of our side on speakers for hooks, prompts, and
judges to read. Proposed shape: set `our_domains` in settings and expose `side` (`"ours"`, `"theirs"`, or
`"unknown"`) on each passage's speaker.

```python
settings = Settings(our_domains=["harbor.example"])

class Call(Document):
    def extract(self, passages):
        turns = [f"[{p.speaker.name} ({p.speaker.side})] {p.text}" for p in passages]
        return self.model_extract(turns, guidance="Our pitch is not an account fact.")
```

### Entities

The starter keeps pages for accounts, people, and opportunities and pairs records of the same company across sources
by domain. Factorial lacks entities with identity keys and cross-source merging, which is already an open question.
Proposed shape: `Entity` subclasses (`Account` keyed by `domain`, `Person` by `email`, and `Opportunity` by
`crm_id`) with a `same_as` hook.

```python
class Account(Entity):
    key = "domain"
    def same_as(self, other): return self.domain == other.domain
```

### Filtered reads

Starter agents read facts filtered by entity, class, time window, and limit, such as an account's newest 30 risk
facts in the last 365 days. Factorial only provides `search` and `current`, lacking structured filtering. Proposed
shape: add `Fact.where(...)` beside `search` and `current`.

```python
risks = RevenueFact.where(account=acme, tags=["deal_risk", "risk_objection"], since="365d", limit=30)
close_date = CloseDate.current(opportunity=renewal)
```

### Reads of what changed

The starter's account overview leads with what changed since its last run. Factorial lacks a read of facts learned
since a given timestamp. Proposed shape: support `learned_since` on `Fact.where(...)`, served from the event log.

```python
new_facts = RevenueFact.where(account=acme, learned_since=last_run)
```

### Code-written facts

When Salesforce syncs amount, stage, or close date, the starter writes a claim fact in plain code with no model and
makes no new claim if a value repeats. Factorial lacks structured field citations and repeat suppression on plain
code extraction. Proposed shape: let `Document.extract` run plain code yielding typed slot facts (`DealAmount`,
`CloseDate`, and `DealStage`) citing fields, where unchanged values are ignored and changed values supersede.

```python
class CrmOpportunity(Document):
    def extract(self):
        yield DealAmount(opportunity=self.opp, usd=self.amount, cite=self.field("amount"))
        yield CloseDate(opportunity=self.opp, date=self.close_date, cite=self.field("close_date"))
        yield DealStage(opportunity=self.opp, stage=self.stage, cite=self.field("stage"))
```

### A person's own statement

The starter lets a person retract a fact or tell the wiki a fact in their own words. Retract and restore are already
events in Factorial, and Factorial lacks a way to add a fact with a person as its source. Proposed shape: add
`Fact.tell(...)` recording the person as the source and running `resolve`.

```python
Fact.tell(
    "Acme's legal team approved the standard MSA.",
    by=Person(email="rep@harbor.example"), account=acme,
)
```

## What stays out of Factorial

- **Curators**: Admission rules about which accounts, people, deals, and calls to keep are policies about corpus
  scope that belong in sources or reading applications. A downstream curator needs `Fact.where` by entity and
  speaker side to check rules such as replies going both ways.
- **Articles**: Account and call pages are prose documents written by sub-agents, and Factorial stops at facts.
  Those agents need `Fact.where` (by entity, tags, `since`, `learned_since`, and `limit`) and typed `current` reads
  so every sentence cites an accepted fact.
- **Digests**: Digests are scheduled summaries built in a reading layer outside the fact store. They need
  `Fact.where(learned_since=...)` across tracked entities along with recent supersede, contradiction, and retraction
  events.
- **Risk radar**: Flagging accounts whose close in the next 60 days a fact puts in doubt is a reader built over
  facts. It needs `CloseDate.current` to find deals closing within 60 days and `Fact.where` for `deal_risk` and
  `risk_objection` tags or unresolved contradictions.
- **Publishing**: Rendering wiki pages and pushing reports belong in delivery tooling outside Factorial. A publisher
  needs `Fact.where(..., learned_since=last_publish)` to see which pages have new, superseded, or retracted facts.

## Open questions

- **Derived facts**: The stakeholders sub-agent assigns each person a role (`decides`, `champions`, `connects`, or
  `blocks`) from what many facts show that person doing, so a single passage cannot yield it. Either the reading
  application computes roles at read time, or Factorial grows derived facts whose evidence is other facts.
- **How a contradiction gets cleared**: In the walk-through, Priya's October 20 email contradicts the CRM's November
  30 close date, and the October 22 CRM update supersedes November 30 with December 19. How a newer slot value
  clears an existing contradiction is still an open design question.
- **Whether tags and typed facts should be one concept or two**: The starter puts labels like `pricing`, `timeline`,
  and `next_step` in one 22-label vector, while `revenue_desk` uses both a `tags` list on `RevenueFact` and typed
  subclasses (`DealAmount`, `CloseDate`, and `NextStep`). Factorial needs to decide whether soft multi-label tags
  and typed slot facts stay separate mechanisms or unify into one concept.
