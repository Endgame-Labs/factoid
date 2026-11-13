# Example: kestrel_robotics

`kestrel_robotics` tracks part prices, lead times, and thermal limits across supplier quotes, datasheets, and bench
test logs for a hardware purchasing and testing team.

## Fifteen minutes

Install Factoid on Ruby 3.4+. Run the CLI inside the project to ingest documents, search facts, and run evals.

```sh
gem install factoid
factoid new kestrel_robotics
cd kestrel_robotics
factoid ingest ./sample_docs
factoid search "motor_x12 price and thermal limit"
factoid read fact_01j9z4m8q
factoid eval
factoid eval --vary judge=none,nli,sustained_load
```

## Layout

```text
kestrel_robotics/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb
│   │   ├── vendor_quote.rb
│   │   ├── part_datasheet.rb
│   │   └── bench_test_log.rb
│   ├── facts/
│   │   ├── application_fact.rb
│   │   ├── unit_price.rb
│   │   ├── lead_time.rb
│   │   └── max_operating_temp.rb
│   ├── judges/
│   │   └── sustained_load_judge.rb
│   ├── sources/
│   │   └── supplier_inbox.rb
│   └── prompts/
│       ├── vendor_quote/
│       │   ├── _guidance.md.erb
│       │   └── quote_context.md.erb
│       └── sustained_load_judge/
│           └── sustained_load.md.erb
├── config/
│   └── application.rb
└── evals/purchasing_and_testing.jsonl
```

## Documents

`VendorQuote` summarizes header terms before extracting, and `PartDatasheet` classifies from the top and bottom text.

```ruby
# app/documents/vendor_quote.rb
class VendorQuote < ApplicationDocument
  definition "A price and delivery quote from a component supplier."
  segment :email
  extracts UnitPrice, LeadTime, MaxOperatingTemp

  def extract(passages)
    quote_context = generate("quote_context", passages:)
    super(passages, quote_context:)
  end
end

# app/documents/part_datasheet.rb
class PartDatasheet < ApplicationDocument
  definition "A manufacturer datasheet listing electrical, mechanical, and thermal ratings for a part."
  extracts MaxOperatingTemp
  classify_threshold 0.85

  def classify_view = head(500) + tail(300)
end

# app/documents/bench_test_log.rb
class BenchTestLog < ApplicationDocument
  definition "A hardware lab log recording measured part behavior during bench testing."
  extracts MaxOperatingTemp
end
```

## Facts

`ApplicationFact` sets shared judges and resolution steps. Fact types add typed slots, judges, and plain code hooks.

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factoid::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end

# app/facts/unit_price.rb
class UnitPrice < ApplicationFact
  definition "The per-unit price in US dollars quoted for a hardware part."
  slot :part, Entity
  slot :unit_price_usd, Float

  def supersedes?(prior) = part == prior.part && stated_at > prior.stated_at
end

# app/facts/lead_time.rb
class LeadTime < ApplicationFact
  definition "The delivery lead time in weeks quoted for a hardware part."
  slot :part, Entity
  slot :lead_time_weeks, Integer
end

# app/facts/max_operating_temp.rb
class MaxOperatingTemp < ApplicationFact
  definition "The maximum safe continuous operating temperature in degrees Celsius for a part."
  slot :part, Entity
  slot :max_temp_c, Integer
  judges SustainedLoadJudge
  after_contradict :flag_for_review

  private

  def flag_for_review(other) = HoldQueue.push(self, other)
end
```

## Sources and judges

`SupplierInbox` pulls quote emails over IMAP, and `SustainedLoadJudge` filters out transient thermal spikes.

```ruby
# app/sources/supplier_inbox.rb
class SupplierInbox < Factoid::Source
  adapter :imap, host: "imap.kestrel.example", password: ENV.fetch("IMAP_PASSWORD")
  yields VendorQuote
end

# app/judges/sustained_load_judge.rb
class SustainedLoadJudge < Factoid::Judge
  def judge(candidate)
    decide("sustained_load", candidate:) > 0.75 ? accept : reject("temperature is from a transient spike")
  end
end
```

## Prompts

```erb
<%# app/prompts/vendor_quote/quote_context.md.erb %>
List the supplier name, currency, and vendor SKU to part ID mappings in this quote:
<% passages.each do |passage| %>
[<%= passage.n %>] <%= passage.speaker %>: <%= passage.text %>
<% end %>

<%# app/prompts/vendor_quote/_guidance.md.erb %>
Quote context: <%= quote_context %>
Normalize vendor SKUs to internal part IDs. Skip freight lines, tooling fees, and expired promotional tiers.

<%# app/prompts/sustained_load_judge/sustained_load.md.erb %>
Quote from <%= candidate.speaker %>: <%= candidate.quote %>
Does this passage state a continuous thermal rating or steady-state test limit for <%= candidate.part %>?
```

## Settings

```ruby
# config/application.rb
class KestrelRobotics < Factoid::Application
  store :s3, bucket: "kestrel-facts", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"

  model :choice,   "typesafe/jev-1.13.0"
  model :generate, "fireworks/glm-5p3-flash"
  model :embed,    "openai/text-embedding-3-small"

  search retrieve: :hybrid_rrf, budget_tokens: 1500
end
```

## What happens as documents arrive

Four documents for `motor_x12` arrive in order:

1. **`motor_x12_datasheet.pdf` (`PartDatasheet`, March 1).** `classify_view` sends the top and bottom text to the
   choice model, which classifies the PDF above `0.85`. Factoid stores `("motor_x12", "max_temp_c", 85)`.
2. **`apex_quote_mar04.eml` (`VendorQuote`, March 4).** Apex Motion quotes SKU `APX-M12` at `$45.00` with a `10`-week
   lead time, and repeats the `85 C` rating. `VendorQuote#extract` maps `APX-M12` to `motor_x12` via `quote_context`.
   Factoid adds `UnitPrice` (`45.00`) and `LeadTime` (`10`), merges the `85 C` claim into `MaxOperatingTemp` as a
   duplicate, and attaches the email quote as a second source.
3. **`apex_quote_mar18.eml` (`VendorQuote`, March 18).** A revised quote drops `motor_x12` to `$42.50` and cuts lead
   time to `8` weeks. `UnitPrice#supersedes?` matches `:part` with a later `stated_at`, so
   `("motor_x12", "unit_price_usd", 42.50)` supersedes `45.00`. On `LeadTime`, `:vector_judge` resolves the update,
   and `("motor_x12", "lead_time_weeks", 8)` supersedes `10`.
4. **`bench_run_041.txt` (`BenchTestLog`, March 22).** A lab run logs a `91 C` startup surge and winding failure
   above `72 C` under continuous load. `SustainedLoadJudge` rejects `91 C` and accepts
   `("motor_x12", "max_temp_c", 72)`. `:vector_judge` flags a contradiction against `85 C`, and `after_contradict`
   pushes both facts to `HoldQueue`.

The design is described in [the Ruby README](../README.md).
