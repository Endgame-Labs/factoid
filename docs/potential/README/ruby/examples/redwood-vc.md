# Example: redwood_vc

`redwood_vc` uses Factorial to run startup diligence across financial statements, pitch decks, and legal records.

## Fifteen minutes

Install Factorial on Ruby 3.4+, create the project, ingest deal files, and query the extracted facts.

```sh
gem install factorial
factorial new redwood_vc
cd redwood_vc
factorial ingest ./deal_docs
factorial search "Orbital Inc. revenue and runway"
factorial read fact_01j9k4m8p
factorial eval
factorial eval --vary judge=none,nli,jev_floors
```

## Layout

```text
redwood_vc/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb
│   │   ├── pitch_deck.rb
│   │   ├── audited_statement.rb
│   │   └── board_minutes.rb
│   ├── facts/
│   │   ├── application_fact.rb
│   │   ├── annual_revenue.rb
│   │   ├── cash_runway.rb
│   │   └── incorporation_state.rb
│   ├── judges/
│   │   └── policy_judge.rb
│   ├── sources/
│   │   ├── founder_inbox.rb
│   │   └── legal_room.rb
│   └── prompts/
│       ├── pitch_deck/
│       │   ├── _guidance.md.erb
│       │   └── slide_notes.md.erb
│       └── policy_judge/
│           └── policy.md.erb
├── config/
│   └── application.rb
└── evals/diligence.jsonl
```

## Documents

Each document class defines what the classifier looks for, which facts it extracts, and any custom model steps.

```ruby
# app/documents/pitch_deck.rb
class PitchDeck < ApplicationDocument
  definition "A startup pitch deck presenting traction, revenue, and cash projections."
  extracts AnnualRevenue, CashRunway

  def extract(passages)
    slide_notes = generate("slide_notes", passages:)
    super(passages, slide_notes:)
  end
end

# app/documents/audited_statement.rb
class AuditedStatement < ApplicationDocument
  definition "An independent auditor's financial statement for a completed fiscal period."
  extracts AnnualRevenue, CashRunway
  classify_threshold 0.85
  def classify_view = head(500) + tail(500)
end

# app/documents/board_minutes.rb
class BoardMinutes < ApplicationDocument
  definition "Approved minutes of a board meeting covering cash, governance, and legal filings."
  extracts CashRunway, IncorporationState
end
```

## Facts

`ApplicationFact` sets shared judge and resolution chains, while subclasses declare slots, judges, and code hooks.

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factorial::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end

# app/facts/annual_revenue.rb
class AnnualRevenue < ApplicationFact
  definition "A company's annualized recurring revenue in US dollars for a stated period."
  slot :company, Entity
  slot :arr_usd, Integer
  judges PolicyJudge
  after_contradict :flag_diligence

  private def flag_diligence(other) = DiligenceQueue.push(self, other)
end

# app/facts/cash_runway.rb
class CashRunway < ApplicationFact
  definition "How many months of cash a company has left at its current burn rate."
  slot :company, Entity
  slot :runway_months, Integer
  judges PolicyJudge

  def supersedes?(prior) = company == prior.company && stated_at > prior.stated_at
end

# app/facts/incorporation_state.rb
class IncorporationState < ApplicationFact
  definition "The US state where a company is legally incorporated."
  slot :company, Entity
  slot :incorporation_state, String
end
```

## Sources and judges

Sources ingest the financial inbox and legal folder, while `PolicyJudge` rejects unquoted or speculative claims.

```ruby
# app/sources/founder_inbox.rb
class FounderInbox < Factorial::Source
  adapter :imap, host: "imap.redwood.example", password: ENV.fetch("IMAP_PASSWORD")
  yields PitchDeck
end

# app/sources/legal_room.rb
class LegalRoom < Factorial::Source
  adapter :folder, path: "./data_room/legal"
  yields BoardMinutes
end

# app/judges/policy_judge.rb
class PolicyJudge < Factorial::Judge
  def judge(candidate)
    decide("policy", candidate:) > 0.75 ? accept : reject("unquoted number or speculative promise")
  end
end
```

## Prompts

ERB files override built-in prompt parts or define the prompt for a custom model call.

```erb
<%# app/prompts/pitch_deck/slide_notes.md.erb %>
List currency units, dates, and footnotes across these slides:
<% passages.each do |passage| %>[<%= passage.n %>] <%= passage.text %> <% end %>

<%# app/prompts/pitch_deck/_guidance.md.erb %>
Slide units and footnotes: <%= slide_notes %>
Skip forecast, pipeline, and target columns. Extract historical figures with explicit dates.

<%# app/prompts/policy_judge/policy.md.erb %>
Candidate: <%= candidate.text %>
Source quote: <%= candidate.quote %>
Does the quote state a historical number verbatim without projections, targets, or unquoted estimates?
```

## Settings

```ruby
# config/application.rb
class RedwoodVc < Factorial::Application
  store :s3, bucket: "redwood-diligence", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"
  model :choice,   "typesafe/jev-1.13.0"
  model :generate, "fireworks/glm-5p3-flash"
  model :embed,    "openai/text-embedding-3-small"
  search retrieve: :hybrid_rrf, budget_tokens: 1500
end
```

## What happens as documents arrive

Four files for Orbital Inc. arrive over two quarters:

1. **`q3_minutes.pdf` (`BoardMinutes`, 2026-07-15).** Factorial extracts `IncorporationState` (`"Orbital Inc."`,
   `"incorporation_state"`, `"Delaware"`) and `CashRunway` (`"Orbital Inc."`, `"runway_months"`, `18`). Both pass the
   judges and enter the log as `added`.
2. **`series_a_deck.pdf` (`PitchDeck`, 2026-10-02).** `PitchDeck#extract` summarizes the slide footnotes first. A
   "$10M ARR next year" claim fails `PolicyJudge`, a footnote naming Delaware merges into `IncorporationState` as a
   duplicate quote, and Q3 ARR of $4,400,000 (`AnnualRevenue` with `arr_usd` set to `4400000`) logs as `added`.
3. **`q3_audit.pdf` (`AuditedStatement`, 2026-10-20).** Factorial extracts Q3 ARR of $3,900,000 (`AnnualRevenue` with
   `"Orbital Inc."`, `"arr_usd"`, `3900000`). During `resolve`, `:vector_judge` marks it `contradicted` against the
   deck's `4400000` figure for the same quarter, and `after_contradict` sends both facts to `DiligenceQueue`.
4. **`q4_minutes.pdf` (`BoardMinutes`, 2026-11-05).** Factorial extracts 14 months of runway (`CashRunway` with
   `"Orbital Inc."`, `"runway_months"`, `14`). `CashRunway#supersedes?` sees a newer `stated_at` date and retires `18`.
   `CashRunway.current(company: "Orbital Inc.").runway_months` returns `14`, and
   `CashRunway.history(company: "Orbital Inc.")` returns both versions with their quotes.

The design is described in [the Ruby README](../README.md).
