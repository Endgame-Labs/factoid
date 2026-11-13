# Example: harbor_realty

Harbor Realty is a property management project that tracks unit leases, rent renewals, pet rules, and repairs.

## Fifteen minutes

Install Factorial on Ruby 3.4+, ingest sample files, search facts, and run evals (`factorial` loads the project bundle):

```sh
gem install factorial
factorial new harbor_realty
cd harbor_realty
factorial ingest ./sample_docs
factorial search "Unit 4B heater"
factorial read fact_01j9x8k2m
factorial eval
factorial eval --vary judge=none,nli,first_hand
```

## Layout

```text
harbor_realty/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb
│   │   ├── lease_agreement.rb
│   │   ├── tenant_email.rb
│   │   └── plumber_invoice.rb
│   ├── facts/
│   │   ├── application_fact.rb
│   │   ├── monthly_rent.rb
│   │   ├── pet_policy.rb
│   │   └── heater_status.rb
│   ├── judges/
│   │   └── first_hand_judge.rb
│   ├── sources/
│   │   ├── lease_folder.rb
│   │   └── repair_inbox.rb
│   └── prompts/
│       ├── tenant_email/_guidance.md.erb
│       ├── tenant_email/thread_summary.md.erb
│       ├── first_hand_judge/first_hand.md.erb
│       └── heater_status/resolve.md.erb
├── config/application.rb
└── evals/leases_and_repairs.jsonl
```

## Documents

Harbor Realty handles leases, tenant emails, and plumber invoices. `TenantEmail#extract` summarizes prior replies first,
and `PlumberInvoice#classify_view` sends the letterhead and the invoice totals to the choice classifier.

```ruby
# app/documents/application_document.rb
class ApplicationDocument < Factorial::Document; end

# app/documents/lease_agreement.rb
class LeaseAgreement < ApplicationDocument
  definition "A signed lease or renewal addendum between Harbor Realty and a tenant."
  extracts MonthlyRent, PetPolicy
end

# app/documents/tenant_email.rb
class TenantEmail < ApplicationDocument
  definition "An email from a tenant to the leasing or maintenance office."
  segment :email
  extracts HeaterStatus, PetPolicy

  def extract(passages)
    thread = generate("thread_summary", passages:)
    super(passages, thread:)
  end
end

# app/documents/plumber_invoice.rb
class PlumberInvoice < ApplicationDocument
  definition "An invoice from a plumbing contractor for repair work on a unit."
  extracts HeaterStatus
  classify_threshold 0.8
  def classify_view = head(400) + tail(400)
end
```

## Facts

Every fact class inherits `:nli` and `:jev_floors` judging plus `:hash`, `:slot`, and `:vector_judge` resolution.

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factorial::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end

# app/facts/monthly_rent.rb
class MonthlyRent < ApplicationFact
  definition "The monthly rent in US dollars owed for a unit."
  slot :unit, Entity
  slot :monthly_rent_usd, Integer
  def supersedes?(prior) = unit == prior.unit && stated_at > prior.stated_at
end

# app/facts/pet_policy.rb
class PetPolicy < ApplicationFact
  definition "Whether tenants are allowed to keep pets in a unit."
  slot :unit, Entity
  slot :pets_allowed, enum: %w[true false]
end

# app/facts/heater_status.rb
class HeaterStatus < ApplicationFact
  definition "Whether a unit's heater is working, leaking, or broken after inspection."
  slot :unit, Entity
  slot :heater_status, enum: %w[working leaking broken]
  judges FirstHandJudge
  after_contradict :flag_for_dispatch
  private def flag_for_dispatch(other) = MaintenanceQueue.push(self, other)
end
```

## Sources and judges

Leases arrive in a local folder, emails arrive over IMAP, and `FirstHandJudge` rejects second-hand heater remarks.

```ruby
# app/sources/lease_folder.rb
class LeaseFolder < Factorial::Source
  adapter :folder, path: "./incoming/leases"
  yields LeaseAgreement
end

# app/sources/repair_inbox.rb
class RepairInbox < Factorial::Source
  adapter :imap, host: "imap.harbor.example", password: ENV.fetch("IMAP_PASSWORD")
  yields TenantEmail
end

# app/judges/first_hand_judge.rb
class FirstHandJudge < Factorial::Judge
  def judge(candidate) = decide("first_hand", candidate:) > 0.7 ? accept : reject("speaker did not inspect heater")
end
```

## Prompts

Templates in `app/prompts/` back custom model calls or replace named parts of built-in hooks.

```erb
<%# app/prompts/tenant_email/thread_summary.md.erb %>
Summarize earlier messages in one sentence naming the unit and the repair issue:
<% passages.each do |p| %>[<%= p.n %>] <%= p.speaker %>: <%= p.text %><% end %>

<%# app/prompts/tenant_email/_guidance.md.erb %>
Earlier messages: <%= thread %>. Skip greetings, signatures, and quoted replies.

<%# app/prompts/first_hand_judge/first_hand.md.erb %>
Did the speaker directly inspect or service the heater in "<%= candidate.quote %>"?

<%# app/prompts/heater_status/resolve.md.erb %>
Stored (<%= prior.stated_at %>): <%= prior.text %> | New (<%= candidate.stated_at %>): <%= candidate.text %>
Choose contradicted when a leak or failure is reported within 48 hours of a completed repair.
```

## Settings

```ruby
# config/application.rb
class HarborRealty < Factorial::Application
  store :s3, bucket: "harbor-realty-facts", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"
  model :choice,   "typesafe/jev-1.13.0"
  model :generate, "fireworks/glm-5p3-flash"
  model :embed,    "openai/text-embedding-3-small"
  search retrieve: :hybrid_rrf, budget_tokens: 1500
end
```

## What happens as documents arrive

Four documents arrive in order for Unit 4B:

1. **2025-05-01, `lease_4b_2025.pdf` (`LeaseAgreement`):** Extracts `MonthlyRent` (`unit: "Unit 4B"`,
   `monthly_rent_usd: 1950`) and `PetPolicy` (`unit: "Unit 4B"`, `pets_allowed: "false"`). Both facts are `added`.
2. **2026-05-01, `renewal_4b_2026.pdf` (`LeaseAgreement`):** States $2,050 rent and repeats the no-pets clause.
   `MonthlyRent#supersedes?` marks $1,950 `superseded` and adds $2,050; `:slot` merges the duplicate `PetPolicy`.
3. **2026-11-10, `bay_plumbing_884.pdf` (`PlumberInvoice`):** Clears the 0.8 `classify_threshold` on
   `classify_view`, passes `FirstHandJudge`, and adds `HeaterStatus` (`heater_status: "working"`).
4. **2026-11-11, `re_unit_4b_heat.eml` (`TenantEmail`):** Summarizes the thread and extracts `HeaterStatus`
   (`heater_status: "leaking"`). Resolution marks both facts `contradicted`, and `after_contradict` queues dispatch.

Afterwards, `MonthlyRent.current(unit: "Unit 4B").monthly_rent_usd` is `2050`, `PetPolicy.current(unit: "Unit 4B")`
carries quotes from both leases, and `HeaterStatus.history(unit: "Unit 4B")` lists both conflicting inspections.

The design is described in [the Ruby README](../README.md).
