# Example: cedar_clinic

`cedar_clinic` tracks patient medication doses, blood types, and smoking status across clinic visits and lab reports.

## Fifteen minutes

Install Factoid on Ruby 3.4+, create the project, ingest sample chart files, and query the extracted facts.

```sh
gem install factoid
factoid new cedar_clinic
cd cedar_clinic
factoid ingest ./sample_charts
factoid search "patient_402 lisinopril"
factoid read fact_01j9x8k2m
factoid eval --vary judge=none,nli,jev_floors
```

## Layout

```text
cedar_clinic/
├── Gemfile
├── app/
│   ├── documents/
│   │   ├── application_document.rb
│   │   ├── intake_form.rb
│   │   ├── doctor_note.rb
│   │   └── lab_report.rb
│   ├── facts/
│   │   ├── application_fact.rb
│   │   ├── medication_dose.rb
│   │   ├── blood_type.rb
│   │   └── smoking_status.rb
│   ├── judges/
│   │   └── active_order_judge.rb
│   ├── sources/
│   │   └── lab_feed.rb
│   └── prompts/
│       ├── doctor_note/
│       │   ├── _guidance.md.erb
│       │   └── visit_summary.md.erb
│       └── active_order_judge/
│           └── active_order.md.erb
├── config/
│   ├── application.rb
│   └── environments/
│       ├── development.rb
│       └── production.rb
└── evals/visits_and_labs.jsonl
```

## Documents

Each document class defines what the classifier looks for and which facts the extractor pulls from passages.

```ruby
# app/documents/intake_form.rb
class IntakeForm < ApplicationDocument
  definition "A check-in questionnaire completed by a patient before an appointment."
  extracts BloodType, SmokingStatus
end

# app/documents/doctor_note.rb
class DoctorNote < ApplicationDocument
  definition "A clinician's visit note recording assessment, smoking history, and prescriptions."
  extracts MedicationDose, SmokingStatus

  def extract(passages)
    visit_summary = generate("visit_summary", passages:)
    super(passages, visit_summary:)
  end
end

# app/documents/lab_report.rb
class LabReport < ApplicationDocument
  definition "A diagnostic report from an in-house or reference laboratory."
  extracts BloodType
  classify_threshold 0.85

  def classify_view = head(300) + tail(300)
end
```

## Facts

Shared defaults live on `ApplicationFact`. Fact classes declare typed slots, extra judges, and plain code hooks.

```ruby
# app/facts/application_fact.rb
class ApplicationFact < Factoid::Fact
  judges :nli, :jev_floors
  resolve :hash, :slot, :vector_judge
end

# app/facts/medication_dose.rb
class MedicationDose < ApplicationFact
  definition "A patient's prescribed daily dose for one medication, in milligrams."
  slot :patient, Entity
  slot :medication, String
  slot :mg, Integer
  judges ActiveOrderJudge

  def supersedes?(prior) = patient == prior.patient && medication == prior.medication && stated_at > prior.stated_at
end

# app/facts/blood_type.rb
class BloodType < ApplicationFact
  definition "A patient's ABO and Rh blood type."
  slot :patient, Entity
  slot :blood_type, enum: %w[A+ A- B+ B- AB+ AB- O+ O-]
end

# app/facts/smoking_status.rb
class SmokingStatus < ApplicationFact
  definition "Whether a patient has never smoked, formerly smoked, or currently smokes."
  slot :patient, Entity
  slot :smoking_status, enum: %w[never former current]
  after_contradict :flag_chart

  private

  def flag_chart(other) = ChartReviewQueue.push(self, other)
end
```

## Sources and judges

A source links a feed to a document class. `ActiveOrderJudge` rejects discontinued or tentative medication doses.

```ruby
# app/sources/lab_feed.rb
class LabFeed < Factoid::Source
  adapter :folder, path: "./incoming/labs"
  yields LabReport
end

# app/judges/active_order_judge.rb
class ActiveOrderJudge < Factoid::Judge
  def judge(candidate)
    decide("active_order", candidate:) > 0.75 ? accept : reject("dose is discontinued or hypothetical")
  end
end
```

## Prompts

ERB templates in `app/prompts/` define custom prompts and override named parts of built-in hooks.

```erb
<%# app/prompts/doctor_note/visit_summary.md.erb %>
Summarize the visit reason and active treatment plan in two sentences:
<% passages.each do |passage| %>
[<%= passage.n %>] <%= passage.speaker %>: <%= passage.text %>
<% end %>

<%# app/prompts/doctor_note/_guidance.md.erb %>
Visit context: <%= visit_summary %>
Skip family history, drug allergies, and past medication trials.
Normalize split daily regimens to a single daily milligram key, such as lisinopril_daily_mg.

<%# app/prompts/active_order_judge/active_order.md.erb %>
Candidate: <%= candidate %>
Does the clinician prescribe or confirm this daily dose as part of the patient's active regimen?
```

## Settings

```ruby
# config/application.rb
class CedarClinic < Factoid::Application
  store :s3, bucket: "cedar-clinic-facts", key: ENV.fetch("S3_KEY")
  index :sqlite_fts, path: "./var/index.db"

  model :choice,   "typesafe/jev-1.13.0"
  model :generate, "fireworks/glm-5p3-flash"
  model :embed,    "openai/text-embedding-3-small"

  search retrieve: :hybrid_rrf, budget_tokens: 1200
end
```

## What happens as documents arrive

Four documents for `patient_402` arrive across two visits:

1. **2026-03-03 `IntakeForm` (speaker: `patient_402`).** The patient checks blood type `O-` and `former` tobacco use.
   Factoid adds `BloodType` `("patient_402", "O-")` and `SmokingStatus` `("patient_402", "former")`.
2. **2026-03-03 `DoctorNote` (speaker: `dr_chen`).** Dr. Chen starts lisinopril 10 mg daily and notes daily smoking.
   Factoid adds `MedicationDose` `("patient_402", "lisinopril_daily_mg", 10)`. The `"current"` smoking fact
   conflicts with the same-day `"former"` intake fact, so Factoid marks both `contradicted` and calls `flag_chart`.
3. **2026-03-05 `LabReport` (speaker: `cedar_lab`).** The lab reports blood group `O-`. Resolution matches the stored
   `BloodType` `("patient_402", "O-")` slot, merges the duplicate, and attaches the lab quote, speaker, and date.
4. **2026-06-18 `DoctorNote` (speaker: `dr_chen`).** Dr. Chen raises lisinopril to 20 mg daily. `supersedes?` retires
   the 10 mg dose and makes `("patient_402", "lisinopril_daily_mg", 20)` current while keeping both quotes in history.

The design is described in [the Ruby README](../README.md).
