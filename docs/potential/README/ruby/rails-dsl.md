# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. The docs get updated to settle the design before code is written.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said
it, and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Fifteen minutes

Install Factorial on Ruby 3.4+. `factorial new` creates `harbor_realty` with sample classes and evals.

```sh
gem install factorial
factorial new harbor_realty
cd harbor_realty
factorial ingest ./sample_docs
factorial search "Unit 4B heater"
factorial read fact_01j9x8k2m
factorial eval
factorial eval --vary judge=none,nli,jev_floors
```

`gem install` puts one `factorial` command on your path. Inside a project, that command loads the project's own bundle,
so you never type `bundle exec`.

## Classes hold the AI work

Factorial organizes your AI code and prompts around the types they work on. Each document type and each fact type is a
class. The class holds its definition, its prompts, its model choices, and any custom code for its steps.

```text
harbor_realty/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb   # defaults shared by your document types
│   │   ├── lease_agreement.rb
│   │   ├── tenant_email.rb
│   │   └── plumber_invoice.rb
│   ├── facts/
│   │   ├── application_fact.rb       # defaults shared by your fact types
│   │   ├── monthly_rent.rb
│   │   ├── pet_policy.rb
│   │   └── heater_status.rb
│   ├── judges/                       # judges of your own
│   ├── sources/                      # where documents come from
│   └── prompts/
│       ├── tenant_email/
│       │   ├── _guidance.md.erb      # one part of this type's extract prompt
│       │   └── thread_summary.md.erb # a prompt of your own
│       └── heater_status/
│           └── resolve.md.erb        # how two HeaterStatus facts are compared
├── config/
│   ├── application.rb                # storage, indexes, pinned models, and search
│   └── environments/
│       ├── development.rb
│       └── production.rb
└── evals/leases_and_repairs.jsonl
```

One class goes in one file, and the file's name is the class's name. Classes are loaded by name, so no file needs a
`require`.

Each pipeline step is a hook on the class that owns it:

| Class | Hooks | What the hook decides |
| --- | --- | --- |
| `Document` | `classify`, `segment`, and `extract` | Is a document this type? How is it cut into passages? How are facts pulled from it? |
| `Fact` | `classify`, `judge`, `repair`, and `resolve` | Is a candidate this type? Is it good enough? How is it reworded? Does it repeat, replace, or disagree with a fact already stored? |

Every hook has the same three levels:

1. **Do nothing.** The base class has a working default.
2. **Add a prompt.** A file at `app/prompts/<class_name>/<hook>.md.erb` takes the place of the built-in prompt for that
   class.
3. **Override the method.** Write your own code for the step, and call `super` to keep the default behavior around it.

```ruby
# app/documents/tenant_email.rb
class TenantEmail < ApplicationDocument
  definition "An email from a tenant to the leasing office."
  segment :email
  extracts HeaterStatus, PetPolicy

  def extract(passages)
    # Summarize the quoted thread first, then extract with that summary as context.
    thread = generate("thread_summary", passages:)
    super(passages, thread:)
  end
end
```

```ruby
# app/facts/heater_status.rb
class HeaterStatus < ApplicationFact
  definition "Whether a unit's heater works, as reported by someone who checked it."
  slot :unit, Entity
  slot :status, enum: %w[working leaking broken]

  # Compare against more stored facts when the unit has a long repair history.
  def resolve_neighbors = unit.fact_count > 200 ? 40 : 20
end
```

A class's `definition` is prompt text. It is what a model reads when it classifies into that type, so the description
lives on the thing it describes. The `slot` lines are the fact's typed slot. A setting such as `resolve_neighbors` can be
a constant (`resolve_neighbors 20`) or a method that computes it.

Shared defaults go in the base classes, and every type inherits them:

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factorial::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end
```

### Classifying

Classifiers are fast choice models by default. A choice model answers a typed question in one pass and writes no text:
it returns a probability for each option. To type a document, Factorial sends one request whose options are the
project's document classes, each described by its `definition`. To type a candidate fact, Factorial does the same with
the fact classes that the document extracts. One request covers every type, so adding types does not add calls.

```ruby
# app/documents/plumber_invoice.rb
class PlumberInvoice < ApplicationDocument
  definition "An invoice from a plumber for work done on a unit."
  extracts HeaterStatus
  classify_threshold 0.8            # the default threshold comes from calibration

  # What the classifier sees: the letterhead and the totals, which sit at the top and the bottom.
  def classify_view = head(400) + tail(400)
end
```

Override `classify` itself to replace the model with your own code, such as a rule on a header.

### Calling models

Inside a hook, a class calls models through four methods. Factorial logs, prices, budgets, and replays every call made
this way, and each prompt is part of its step's fingerprint.

| Method | Returns | Model kind |
| --- | --- | --- |
| `choose(prompt, options)` | A probability for each option | Choice model |
| `decide(prompt)` | A probability that the answer is yes | Choice model |
| `score(prompt, rubric)` | A rubric level | Choice model |
| `generate(prompt)` | Text | Generative model |

Models are named once in `config/application.rb` and pinned to exact versions. Secrets come from environment variables.

```ruby
# config/application.rb
class HarborRealty < Factorial::Application
  store :s3, bucket: "harbor-facts", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"

  model :choice,   "typesafe/jev-1.13.0"            # classify, judge, and resolve
  model :generate, "fireworks/glm-5p3-flash"        # extract and repair
  model :embed,    "openai/text-embedding-3-small"

  search retrieve: :hybrid_rrf, budget_tokens: 1500
end
```

```ruby
# config/environments/development.rb
HarborRealty.configure do
  store :folder, path: "./data"
end
```

An eval run can swap any hook's strategy without touching your files. `factorial eval --vary classify=choice,llm,rules`
runs the same documents once per value and compares quality, cost, and latency.

## Sources and judges

A source is a class that names an adapter and the document type it yields. A judge is a class with one method.

```ruby
# app/sources/repair_inbox.rb
class RepairInbox < Factorial::Source
  adapter :imap, host: "imap.harbor.example", password: ENV.fetch("IMAP_PASSWORD")
  yields TenantEmail
end
```

```ruby
# app/judges/first_hand_judge.rb
class FirstHandJudge < Factorial::Judge
  # Accept a heater report only when the speaker checked the heater themselves.
  def judge(candidate)
    decide("first_hand", candidate:) > 0.7 ? accept : reject("the speaker did not check the heater")
  end
end
```

A fact class adds a judge of its own with `judges FirstHandJudge`, and the judge runs after the inherited chain. A chain
runs in order and rejects at the first failure, so cheap judges go first.

## Prompts

Prompts are ERB templates. Every hook that calls a model has a built-in template, and each built-in template is made
of named parts. A file in `app/prompts/` takes the place of a built-in template or of one part:
`app/prompts/extract.md.erb` replaces the extract prompt for every document type, and
`app/prompts/tenant_email/_guidance.md.erb` replaces only the guidance part, for `TenantEmail` only.

```erb
<%# factorial/extract.md.erb, the built-in extract template %>
Extract facts from this <%= document.type %>, dated <%= document.at %>.
<%= render "guidance" %>
<% fact_types.each do |fact_type| %>
- <%= fact_type.name %>: <%= fact_type.definition %>
<% end %>
<% passages.each do |passage| %>
[<%= passage.n %>] <%= passage.speaker %>: <%= passage.text %>
<% end %>
Cite passages by number. Do not copy quote text.
```

```erb
<%# app/prompts/tenant_email/_guidance.md.erb %>
Earlier messages in this thread: <%= thread %>
Skip greetings, signatures, and quoted replies.
```

## Plain code hooks

Some steps need no model. A fact class validates candidates in code, changes when a newer fact replaces an older one,
and runs code when an event happens to a fact.

```ruby
# app/facts/monthly_rent.rb
class MonthlyRent < ApplicationFact
  definition "The rent a tenant owes each month for one unit."
  slot :unit, Entity
  slot :usd, Integer

  validate { reject("rent must be positive") unless usd.positive? }
  after_contradict :flag_for_review

  def supersedes?(prior) = unit == prior.unit && stated_at > prior.stated_at

  private

  def flag_for_review(other) = ReviewQueue.push(self, other)
end
```

The callbacks are `after_add`, `after_supersede`, `after_contradict`, `after_retract`, and `after_restore`. Typed reads
return values your code can use: `HeaterStatus.current(unit: "Unit 4B").status` for the current value, and
`HeaterStatus.history(unit: "Unit 4B")` for every version with its quotes.

## Three ways to use it

- **Standalone project with the CLI.** Manage a RAG corpus in its own directory, tune retrieval units, and evaluate
  prompt, extractor, and judge choices with `factorial ingest`, `factorial search`, and `factorial eval`.
- **Personal agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes,
  and chats, then expose fact search and writes to an agent over `factorial mcp` or the CLI.
- **Backend library or HTTP service.** Run `factorial serve` as an HTTP sidecar, or `require "factorial"` inside an
  existing service. Classes work anywhere in code when passed directly to `Factorial.new`:

```ruby
require "factorial"

class PlanTier < Factorial::Fact
  definition "The plan an account is on."
  slot :account, Entity
  slot :tier, String
end

class AccountNote < Factorial::Document
  definition "A note an account manager wrote about a customer."
  extracts PlanTier
end

facts = Factorial.new(
  documents: [AccountNote],
  models: { generate: "fireworks/glm-5p3-flash", choice: "typesafe/jev-1.13.0" }
)
facts.ingest_text("Acme Corp upgraded to Enterprise.", as: AccountNote)
hits = facts.search("Acme Corp plan")               # sentences, with quotes
tier = PlanTier.current(account: "Acme Corp").tier  # a typed value
```

## Core ideas

- **Facts are what a reader reads.** Readers get short, self-contained sentences in a token budget. On dialogue, fact
  retrieval beat chunk retrieval at about a seventh of the read tokens ([docs/prior-art.md](../../../prior-art.md)).
- **Models never write evidence.** The extractor cites numbered passages, and code attaches the exact quote, speaker,
  and timestamp.
- **History is the truth.** Writes append to an event log (`added`, `superseded`, `contradicted`, `retracted`, and
  `restored`). Current state and search indexes (`sqlite_fts`, `pgvectorscale`, and `turbopuffer`) are views rebuilt
  from that log.
- **Algorithm choices are made by evals.** Defaults across `classify`, `segment`, `extract`, `judge`, `repair`,
  `resolve`, and `tag` are eval results. `factorial eval` scores quality, cost, and latency on labeled data.
- **Pluggable seams.** Storage (local folders and S3-compatible buckets), sources (`folder`, `jsonl`, `imap`, and
  `mcp`), models, and judges share small base classes that projects subclass directly.

## Why this approach

Class macros keep a declaration short: `definition`, `slot`, `extracts`, and `judges` read as a description of the
type. `ApplicationDocument` and `ApplicationFact` give a project one place for its own defaults. Callbacks, blocks, and
`super` make it easy to wrap a default step with custom code. Loading classes by file name removes every `require`.

The costs: Factorial needs a Ruby runtime, and the Python NLP and model libraries are not available in process. Ruby has
no docstrings and no typed attributes, so `definition` and `slot` are macros that Factorial has to supply. ERB has no
template inheritance, so a project overrides a named part of a prompt where the Python design overrides a block.
Configuration is code that runs at load time, so an outside tool has to load the project to read it.

## Further reading

Start with [docs/mental-model.md](../../../mental-model.md), and then read [docs/README.md](../../../README.md).
[docs/config.md](../../../config.md) and [docs/plugins.md](../../../plugins.md) still describe the older single-YAML
design and will be updated.
