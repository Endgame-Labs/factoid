# Example: revenue_desk

`revenue_desk` is a Factoid project for B2B sales and account teams that turns CRM records, call transcripts, emails,
and notes into typed, cited facts. It is modeled on the default revenue starter workspace in `endgame-wiki`.

## Fifteen minutes

Enter the project on Ruby 3.4+ with the `factoid` gem installed, ingest the sample Harbor and Acme Corp files, and
inspect the extracted facts.

```sh
cd revenue_desk
factoid ingest ./sample_docs
factoid search "Acme Corp security review"
factoid read fact_01ja9m4k8
factoid eval
factoid eval --vary judge=nli,jev_floors
```

## Layout

Each entity, document, fact, judge, and source lives in its own file under `app/`, matched by file name.

```text
revenue_desk/
├── Gemfile
├── app/
│   ├── entities/
│   │   ├── account.rb
│   │   ├── opportunity.rb
│   │   └── person.rb
│   ├── documents/
│   │   ├── application_document.rb
│   │   ├── call.rb
│   │   ├── crm_opportunity.rb
│   │   ├── email.rb
│   │   └── note.rb
│   ├── facts/
│   │   ├── application_fact.rb
│   │   ├── close_date.rb
│   │   ├── deal_amount.rb
│   │   ├── deal_stage.rb
│   │   └── next_step.rb
│   ├── judges/
│   │   └── agreed_judge.rb
│   ├── sources/
│   │   ├── gong_calls.rb
│   │   └── salesforce_crm.rb
│   └── prompts/
│       ├── agreed_judge/
│       │   └── agreed_step.md.erb
│       ├── call/
│       │   └── _guidance.md.erb
│       └── email/
│           └── _guidance.md.erb
├── config/
│   └── application.rb
└── evals/acme_renewal.jsonl
```

## Entities

Entities give facts stable subjects across Gong, email, and the CRM. Each entity class declares an identity `key` so
records with the same domain, email address, or CRM identifier resolve to one entity.

```ruby
# app/entities/account.rb
class Account < Factoid::Entity
  definition "A customer or prospect company."
  key :domain
end
```

```ruby
# app/entities/person.rb
class Person < Factoid::Entity
  definition "A person at a customer or on our own team."
  key :email
end
```

```ruby
# app/entities/opportunity.rb
class Opportunity < Factoid::Entity
  definition "A commercial deal tracked in the CRM."
  key :crm_id
  slot :account, Account
  slot :owner, Person
end
```

## Documents

`ApplicationDocument` sets the default extraction list for unstructured text. `Call`, `Email`, and `Note` inherit those
targets, while `CrmOpportunity` overrides `extract` in plain Ruby.

```ruby
# app/documents/application_document.rb
class ApplicationDocument < Factoid::Document
  extracts ApplicationFact, CloseDate, DealAmount, NextStep
end
```

```ruby
# app/documents/call.rb
class Call < ApplicationDocument
  definition "A Gong or Granola transcript of a call with an account."
  segment :turns

  def extract(passages)
    roster = passages.map(&:speaker).uniq.map { |s| "#{s.name} (#{s.side})" }
    super(passages, roster:)
  end
end
```

```ruby
# app/documents/email.rb
class Email < ApplicationDocument
  definition "An email message sent to or from an account."
  segment :email
end
```

```ruby
# app/documents/crm_opportunity.rb
class CrmOpportunity < ApplicationDocument
  definition "A structured opportunity snapshot synced from the CRM."
  extracts DealAmount, CloseDate, DealStage

  def extract(passages)
    opp = Opportunity.resolve(crm_id: fields[:id], name: fields[:name], account: fields[:account])
    [
      emit(DealAmount, opportunity: opp, account: opp.account, usd: fields[:amount], cite: :amount),
      emit(CloseDate, opportunity: opp, account: opp.account, date: fields[:close_date], cite: :close_date),
      emit(DealStage, opportunity: opp, account: opp.account, stage: fields[:stage], cite: :stage)
    ]
  end
end
```

```ruby
# app/documents/note.rb
class Note < ApplicationDocument
  definition "A local markdown note about an account or deal."
end
```

## Facts

`ApplicationFact` carries the six-floor judge chain, resolution rules, and a closed 22-label taxonomy. During the `tag`
step, one choice-model call scores every label and keeps each label at or above `0.5`.

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factoid::Fact
  definition "A standalone statement about an account, person, or opportunity."
  slot :account, Account

  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge

  # Six shown; the other 16 of the 22 starter labels follow in this list.
  tags %w[commercial_terms deal_risk decision_commitment pricing risk_objection timeline]
  tag_threshold 0.5
end
```

```ruby
# app/facts/close_date.rb
class CloseDate < ApplicationFact
  definition "The date an opportunity is expected to sign or close."
  slot :opportunity, Opportunity
  slot :date, Date

  after_contradict :queue_for_owner

  def supersedes?(prior)
    opportunity == prior.opportunity && speaker.side == prior.speaker.side && stated_at > prior.stated_at
  end

  private

  def queue_for_owner(other) = ReviewQueue.push(opportunity.owner, self, other)
end
```

```ruby
# app/facts/deal_amount.rb
class DealAmount < ApplicationFact
  definition "The contract value of an opportunity in US dollars."
  slot :opportunity, Opportunity
  slot :usd, Integer
end
```

```ruby
# app/facts/deal_stage.rb
class DealStage < ApplicationFact
  definition "The current sales stage of an opportunity in the CRM."
  slot :opportunity, Opportunity
  slot :stage, String
end
```

```ruby
# app/facts/next_step.rb
class NextStep < ApplicationFact
  definition "A concrete follow-up action agreed to during a call or email thread."
  slot :owner_side, enum: %w[ours theirs]
  slot :due_on, Date

  judges AgreedJudge
end
```

## Sources and judges

Sources connect external systems to document classes. Custom judges run after the base judge chain on the fact types
that declare them.

```ruby
# app/sources/gong_calls.rb
class GongCalls < Factoid::Source
  adapter :gong, api_key: ENV.fetch("GONG_API_KEY")
  yields Call
end

# app/sources/salesforce_crm.rb
class SalesforceCrm < Factoid::Source
  adapter :salesforce, token: ENV.fetch("SFDC_TOKEN")
  yields CrmOpportunity
end
```

```ruby
# app/judges/agreed_judge.rb
class AgreedJudge < Factoid::Judge
  def judge(candidate)
    decide("agreed_step", candidate:) > 0.6 ? accept : reject("step was proposed without agreement")
  end
end
```

## Prompts

Prompt parts customize extraction for calls and emails, and give `AgreedJudge` its rubric.

```erb
<%# app/prompts/call/_guidance.md.erb %>
Participants on this call: <%= roster.join(", ") %>.
Record what speakers on `theirs` stated, asked, and pushed back on.
Treat pitches from `ours` as context, never as facts about the customer account.
```

```erb
<%# app/prompts/email/_guidance.md.erb %>
Skip greetings, legal footers, signatures, and quoted replies from earlier messages.
```

```erb
<%# app/prompts/agreed_judge/agreed_step.md.erb %>
Candidate next step: <%= candidate.text %>
Source quote (<%= candidate.speaker.name %>, <%= candidate.speaker.side %>): "<%= candidate.quote %>"
Did the other side accept or confirm this action in the surrounding exchange?
```

## Settings

`our_domains` tells Factoid which email domains belong to Harbor (`ours`), so every speaker gets a `side` of `ours`,
`theirs`, or `unknown`.

```ruby
# config/application.rb
class RevenueDesk < Factoid::Application
  our_domains ["harbor.example"]

  store :s3, bucket: "harbor-revenue-facts", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"

  model :choice,   "typesafe/jev-1.13.0"
  model :generate, "fireworks/glm-5p3-flash"
  model :embed,    "openai/text-embedding-3-small"

  search retrieve: :hybrid_rrf, budget_tokens: 1500
end
```

## Reading facts

Downstream readers, such as an account brief or a risk digest, query typed slots and filtered fact lists.

```ruby
acme = Account.find(domain: "acme.example")
renewal = Opportunity.find(crm_id: "opp_2027_acme")

risks = ApplicationFact.where(
  account: acme,
  tags: %w[deal_risk risk_objection],
  since: "365d",
  limit: 30
)
close_on = CloseDate.current(opportunity: renewal).date
deltas = ApplicationFact.where(account: acme, learned_since: last_run)
```

## What happens as documents arrive

Harbor (`harbor.example`) is working on "Acme Corp Renewal 2027" with Priya Natarajan (VP Engineering) and Tom Okafor
(procurement) at Acme Corp (`acme.example`). Four documents arrive in October:

1. **CRM record, October 1.** `SalesforceCrm` syncs `amount: 100000`, `close_date: 2026-11-30`, and `stage:
   "Negotiation"`. `CrmOpportunity#extract` writes one `DealAmount`, one `CloseDate`, and one `DealStage` with no model
   calls.
2. **Gong call, October 8.** Priya (`theirs`) says, `"we have to get through security before the board meets in
   November"`, and a Harbor rep (`ours`) suggests a pricing workshop that nobody confirms. Factoid adds `"Acme Corp's
   security review must finish before the November board meeting."` with tags `timeline` and `decision_commitment`.
   `AgreedJudge` rejects the workshop candidate. Tom (`theirs`) mentions `"a hundred thousand"`, which resolves into the
   existing `DealAmount` fact as a second quote.
3. **Email, October 20.** Priya writes that the board meeting moved to December 12 and Acme cannot sign before it.
   Factoid extracts a `CloseDate` after December 12 from `theirs`. Because the speaker side differs from the CRM
   record, it contradicts November 30, flags both facts, and runs `CloseDate#queue_for_owner`.
4. **CRM record, October 22.** The Harbor deal owner moves `close_date` to December 19. `CloseDate#supersedes?` replaces
   the October 1 November 30 claim, and the newer value clears the contradiction. How a contradiction gets cleared when
   one side updates its claim remains an open design question.

## New API this example needs

- `Factoid::Entity` subclasses with `key`, `resolve`, and `find` to unify accounts, people, and deals across sources.
- `tags` and `tag_threshold` on `Factoid::Fact`, backed by a `tag` hook that scores multi-label taxonomies in one
  pass.
- `our_domains` on `Factoid::Application` and `speaker.side` (`ours`, `theirs`, or `unknown`) on passages and quotes.
- `Fact.where` filtering by entity slots, `tags`, `since`, `limit`, and `learned_since` from the event log.
- `Document#emit` and `fields` so a plain-code `extract` method can return typed facts cited to structured record
  fields.

The design is described in [the Ruby README](../README.md), and the mapping from the revenue starter is in
[crm-starter.md](../../../crm-starter.md).
