# Factorial 🧮

> **Status: Design draft.** Nothing is built yet. These docs are updated to settle the design before code is written.

Factorial turns documents into facts: short, self-contained sentences, each tied to an exact source quote, who said it,
and when. As new documents arrive, Factorial updates its set of facts. It retires outdated facts, merges duplicate
facts, and flags facts that disagree. People and agents can access these facts through a CLI, an HTTP API, and MCP.

## Getting started

Install the gem on Ruby 3.4+. `factorial new` creates `harbor_realty` with sample classes and evals.

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

`gem install` adds the `factorial` executable to your path. Inside a project directory, `factorial` loads that
project's bundle without `bundle exec`.

## Document and fact types

Each document type and each fact type is a Ruby class. A class holds the type's definition, prompts, model choices, and
custom step code.

```text
harbor_realty/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb   # defaults shared by document types
│   │   ├── lease_agreement.rb
│   │   ├── tenant_email.rb
│   │   └── plumber_invoice.rb
│   ├── facts/
│   │   ├── application_fact.rb       # defaults shared by fact types
│   │   ├── monthly_rent.rb
│   │   ├── pet_policy.rb
│   │   └── heater_status.rb
│   ├── judges/                       # custom judges
│   ├── sources/                      # document sources
│   └── prompts/
│       ├── tenant_email/
│       │   ├── _guidance.md.erb      # one part of this type's extract prompt
│       │   └── thread_summary.md.erb # custom prompt
│       └── heater_status/
│           └── resolve.md.erb        # how two HeaterStatus facts are compared
├── config/
│   ├── application.rb                # storage, indexes, pinned models, and search
│   └── environments/
│       ├── development.rb
│       └── production.rb
└── evals/leases_and_repairs.jsonl
```

Each class lives in a file matching its name. Factorial loads classes by name without `require` statements.

Each pipeline step is a hook on `Document` or `Fact`:

| Class | Hooks | Purpose |
| --- | --- | --- |
| `Document` | `classify`, `segment`, and `extract` | Check whether a document matches this type, split the document into passages, and extract candidate facts. |
| `Fact` | `classify`, `judge`, `repair`, and `resolve` | Check whether a candidate matches this type, check candidate quality, reword text, and check whether the candidate repeats, replaces, or contradicts a stored fact. |

Every hook supports three levels of customization:

1. **Use the default.** The base class provides a working implementation.
2. **Add a prompt.** A file at `app/prompts/<class_name>/<hook>.md.erb` replaces the built-in prompt for that class.
3. **Override the method.** Implement the step in Ruby, and call `super` to keep the default behavior around your code.

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

A class's `definition` is prompt text passed to models during classification and extraction. `slot` declares typed
fields on a fact. Settings such as `resolve_neighbors` accept a static value (`resolve_neighbors 20`) or a method.

Base classes hold shared defaults that subclasses inherit:

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factorial::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end
```

### Classification

By default, `classify` uses a fast choice model that returns a probability for each option in one pass without
generating text. To classify a document, Factorial sends one request whose options are the project's document classes
and their definitions. To classify a candidate fact, Factorial sends one request with the fact classes that the
document extracts. Adding classes adds options to that request without adding model calls.

```ruby
# app/documents/plumber_invoice.rb
class PlumberInvoice < ApplicationDocument
  definition "An invoice from a plumber for work done on a unit."
  extracts HeaterStatus
  classify_threshold 0.8            # the default threshold comes from calibration

  # Send the letterhead at the top and the totals at the bottom to the classifier.
  def classify_view = head(400) + tail(400)
end
```

Override `classify` to replace the model call with Ruby code, such as a header rule.

### Default judges

Every candidate fact passes a default chain of judges before being stored. A project gets this chain without
writing any code, and a custom judge appends to the chain without replacing the defaults. The chain runs in
order and rejects the candidate at the first failure, so the cheap judge runs first.

| Judge | Check |
| --- | --- |
| `nli` | A small, cheap entailment model. Runs first and checks that the cited passage entails the sentence. |
| `jev_floors` | Six yes-or-no questions in one choice-model call; all six probabilities must pass their floors. |

Each `jev_floors` answer is a probability, each question has its own floor, and all six questions must pass:

- `grounded`: The cited passages support the sentence.
- `attribution`: Who stated the claim, and whether the claim was certain or negated, match the source.
- `self_contained`: The sentence names its subject, with no unresolved pronouns.
- `atomic`: The sentence states one claim.
- `useful`: The fact is worth keeping.
- `distinct`: No stored fact already states the claim.

Floors come from calibration on labeled data; Factorial does not use a fixed 0.5 cutoff. A candidate that
narrowly fails gets one repair (a rewording) and is judged again.

A project can change one floor or add a judge without replacing the default chain:

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factorial::Fact
  judges :nli, :jev_floors      # the default chain, written out
  floor :useful, 0.8            # one floor raised
end

# app/facts/heater_status.rb
class HeaterStatus < ApplicationFact
  judges FirstHandJudge         # runs after the inherited chain
end
```

`factorial eval --vary judge=none,nli,jev_floors` compares judge chains on the same documents.

### Model calls

Hooks call models through four methods. Factorial logs, prices, budgets, and replays these calls, and includes each
prompt in the step's fingerprint.

| Method | Returns | Model kind |
| --- | --- | --- |
| `choose(prompt, options)` | A probability for each option | Choice model |
| `decide(prompt)` | A probability that the answer is yes | Choice model |
| `score(prompt, rubric)` | A rubric level | Choice model |
| `generate(prompt)` | Text | Generative model |

Models are configured in `config/application.rb` and pinned to exact versions. Secrets come from environment variables.

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

Eval runs can swap a hook's strategy without editing project files. `factorial eval --vary classify=choice,llm,rules`
runs the documents once per setting and compares quality, cost, and latency.

## Sources and judges

A source class specifies an adapter and the document type that the source yields. A judge class implements `judge` to
accept or reject a candidate fact.

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

Add a custom judge to a fact class with `judges FirstHandJudge`. Custom judges run after inherited judges. A judge
chain runs in order and stops at the first rejection, so list inexpensive judges first.

## Prompts

Prompts are ERB templates composed of named parts. Every model-backed hook has a built-in template. Files in
`app/prompts/` replace a full template or one named part: `app/prompts/extract.md.erb` replaces the extract prompt for
every document type, and `app/prompts/tenant_email/_guidance.md.erb` replaces the `guidance` part for `TenantEmail`.

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

## Code hooks

Fact classes can run Ruby logic without calling a model. A class can validate candidates, define when a newer fact
supersedes an older one, and run callbacks on fact events.

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
return structured values: `HeaterStatus.current(unit: "Unit 4B").status` returns the active status, and
`HeaterStatus.history(unit: "Unit 4B")` returns all versions with their source quotes.

## Usage

- **CLI project.** Manage a RAG corpus in a project directory, tune retrieval units, and evaluate prompt, extractor,
  and judge choices with `factorial ingest`, `factorial search`, and `factorial eval`.
- **Agent memory over MCP.** Connect `imap`, `folder`, `jsonl`, and `mcp` sources for mail, calls, notes, and chats,
  then expose fact search and writes to an agent over `factorial mcp` or the CLI.
- **Library or HTTP service.** Run `factorial serve` as an HTTP sidecar, or `require "factorial"` inside an existing
  service and pass classes directly to `Factorial.new`:

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

## Design

- **Fact retrieval.** Search returns short, self-contained sentences within a token budget. On dialogue, fact retrieval
  beat chunk retrieval at about one-seventh of the read tokens ([docs/prior-art.md](../../../prior-art.md)).
- **Passage citations.** The extractor cites numbered passages, and Factorial attaches the exact quote, speaker, and
  timestamp in code.
- **Event log.** Writes append events (`added`, `superseded`, `contradicted`, `retracted`, and `restored`) to a log.
  Current state and search indexes (`sqlite_fts`, `pgvectorscale`, and `turbopuffer`) are views rebuilt from that log.
- **Evaluations.** Defaults across `classify`, `segment`, `extract`, `judge`, `repair`, `resolve`, and `tag` come from
  eval results. `factorial eval` scores quality, cost, and latency on labeled data.
- **Extension points.** Storage (local folders and S3-compatible buckets), sources (`folder`, `jsonl`, `imap`, and
  `mcp`), models, and judges share small base classes that projects subclass.

## Trade-offs

Class macros (`definition`, `slot`, `extracts`, and `judges`) keep type declarations short. `ApplicationDocument` and
`ApplicationFact` put project defaults in one place. Callbacks, blocks, and `super` let classes wrap default steps with
custom code. Loading classes by file name removes `require` statements.

Costs of this design: Factorial requires a Ruby runtime, so Python NLP and model libraries cannot run in process. Ruby
lacks docstrings and typed attributes, so Factorial provides `definition` and `slot` macros. ERB lacks template
inheritance, so prompt overrides target named parts. Configuration is Ruby code evaluated at load time, so external
tools must load the project to read its settings.

## Further reading

Start with [docs/mental-model.md](../../../mental-model.md), and then read [docs/README.md](../../../README.md).
[docs/config.md](../../../config.md) and [docs/plugins.md](../../../plugins.md) still describe the older single-YAML
design and will be updated.
