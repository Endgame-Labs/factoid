# Example: beacon_auto

`beacon_auto` tracks incident facts and policy terms for an auto insurer from emails, police reports, and shop quotes.

## Fifteen minutes

Install Factoid on Ruby 3.4+, create the project, ingest sample files, search facts, and run an eval.

```sh
gem install factoid
factoid new beacon_auto
cd beacon_auto
factoid ingest ./sample_docs
factoid search "case_8841 northbound light"
factoid read fact_01j9x8k2m
factoid eval
factoid eval --vary judge=none,nli,jev_floors
```

## Layout

```text
beacon_auto/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb
│   │   ├── driver_statement.rb
│   │   ├── police_report.rb
│   │   └── shop_estimate.rb
│   ├── facts/
│   │   ├── application_fact.rb
│   │   ├── traffic_light_color.rb
│   │   ├── repair_estimate.rb
│   │   └── collision_deductible.rb
│   ├── judges/
│   │   └── eyewitness_judge.rb
│   ├── sources/
│   │   └── statements_inbox.rb
│   └── prompts/
│       ├── driver_statement/
│       │   ├── _guidance.md.erb
│       │   └── scene_summary.md.erb
│       └── eyewitness_judge/
│           └── eyewitness.md.erb
├── config/
│   └── application.rb
└── evals/incidents_and_policies.jsonl
```

## Documents

Each document class subclasses `ApplicationDocument`, sets its `definition`, and declares the fact types it extracts.

```ruby
# app/documents/driver_statement.rb
class DriverStatement < ApplicationDocument
  definition "An email from an insured driver describing a crash and policy coverage."
  segment :email
  extracts TrafficLightColor, CollisionDeductible

  def extract(passages)
    scene = generate("scene_summary", passages:)
    super(passages, scene:)
  end
end

# app/documents/police_report.rb
class PoliceReport < ApplicationDocument
  definition "An officer's crash report containing scene notes and witness statements."
  extracts TrafficLightColor
end

# app/documents/shop_estimate.rb
class ShopEstimate < ApplicationDocument
  definition "A body shop repair quote listing the insurer assignment, deductible, and labor totals."
  extracts RepairEstimate, CollisionDeductible
  classify_threshold 0.85
  def classify_view = head(400) + tail(400)
end
```

## Facts

`ApplicationFact` sets shared judges and resolution steps. Subclasses declare slots, judges, and plain code hooks.

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factoid::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end

# app/facts/traffic_light_color.rb
class TrafficLightColor < ApplicationFact
  definition "The color of an intersection signal when a vehicle entered during an incident."
  slot :incident, Entity
  slot :signal, enum: %w[northbound_light southbound_light eastbound_light westbound_light]
  slot :color, enum: %w[red yellow green]
  judges EyewitnessJudge
  after_contradict :notify_adjuster

  private

  def notify_adjuster(other) = AdjusterQueue.push(self, other)
end

# app/facts/repair_estimate.rb
class RepairEstimate < ApplicationFact
  definition "A body shop's total estimated cost in US dollars to repair crash damage."
  slot :incident, Entity
  slot :repair_cost_usd, Integer
  def supersedes?(prior) = incident == prior.incident && stated_at > prior.stated_at
end

# app/facts/collision_deductible.rb
class CollisionDeductible < ApplicationFact
  definition "The collision deductible in US dollars that applies to an auto policy."
  slot :policy, Entity
  slot :deductible_usd, Integer
end
```

## Sources and judges

`StatementsInbox` pulls driver emails over IMAP. `EyewitnessJudge` rejects secondhand traffic signal reports.

```ruby
# app/sources/statements_inbox.rb
class StatementsInbox < Factoid::Source
  adapter :imap, host: "imap.beacon.example", password: ENV.fetch("IMAP_PASSWORD")
  yields DriverStatement
end

# app/judges/eyewitness_judge.rb
class EyewitnessJudge < Factoid::Judge
  def judge(candidate)
    decide("eyewitness", candidate:) > 0.7 ? accept : reject("the speaker did not see the signal")
  end
end
```

## Prompts

Files in `app/prompts/` supply custom model prompts or override named parts of built-in hook templates.

```erb
<%# app/prompts/driver_statement/scene_summary.md.erb %>
Summarize the crash location, travel directions, and policy numbers in two sentences:
<% passages.each do |passage| %>
[<%= passage.n %>] <%= passage.speaker %>: <%= passage.text %>
<% end %>

<%# app/prompts/driver_statement/_guidance.md.erb %>
Scene summary: <%= scene %>
Skip email signatures, claim portal footers, and insurer boilerplate.

<%# app/prompts/eyewitness_judge/eyewitness.md.erb %>
Candidate fact: <%= candidate %>
Did the speaker observe the traffic signal firsthand when the vehicle entered the intersection?
```

## Settings

```ruby
# config/application.rb
class BeaconAuto < Factoid::Application
  store :s3, bucket: "beacon-facts", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"

  model :choice,   "typesafe/jev-1.13.0"
  model :generate, "fireworks/glm-5p3-flash"
  model :embed,    "openai/text-embedding-3-small"

  search retrieve: :hybrid_rrf, budget_tokens: 1500
end
```

## What happens as documents arrive

Four files arrive in order for incident `case_8841` and policy `policy_992`:

1. **`driver_email.eml` (`DriverStatement`, May 2):** Dana Reyes reports `case_8841` under `policy_992` with a $500
   deductible and a green northbound light. Factoid adds `CollisionDeductible("policy_992", "deductible_usd", 500)`
   and `TrafficLightColor("case_8841", "northbound_light", "green")`.
2. **`prelim_quote.pdf` (`ShopEstimate`, May 3):** Harbor Body quotes $1,950 for `case_8841` and lists the $500
   deductible on `policy_992`. Factoid merges the duplicate `CollisionDeductible` with a second quote and adds
   `RepairEstimate("case_8841", "repair_cost_usd", 1950)`.
3. **`precinct_report.pdf` (`PoliceReport`, May 4):** Officer Patel quotes a corner witness who saw a red light.
   `EyewitnessJudge` accepts `TrafficLightColor("case_8841", "northbound_light", "red")`, which contradicts the
   green-light fact; Factoid flags both contradicted and runs `after_contradict` to queue them in `AdjusterQueue`.
4. **`teardown_quote.pdf` (`ShopEstimate`, May 6):** After bumper removal, Harbor Body submits a tear-down quote of
   $4,100 for `case_8841`. `RepairEstimate#supersedes?` sees a newer `stated_at` time, retires the $1,950 quote as
   superseded, and makes `RepairEstimate("case_8841", "repair_cost_usd", 4100)` current.

The design is described in [the Ruby README](../README.md).
