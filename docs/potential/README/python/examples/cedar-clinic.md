# Example: cedar_clinic

`cedar_clinic` is a Factorial project for a primary care clinic that tracks patient facts across visits and labs.

## Fifteen minutes

Install Factorial with `uv` on Python 3.13+, open the project, ingest sample charts, search facts, and run evals.

```sh
uv tool install factorial
cd cedar_clinic
factorial ingest ./sample_docs
factorial search "patient_402 lisinopril"
factorial read fact_01j9z4m8p
factorial eval
factorial eval --vary judge=none,nli,clinical_floors
```

## Layout

```text
cedar_clinic/
├── pyproject.toml
├── cedar_clinic/
│   ├── settings.py    # storage, indexes, pinned models, and search
│   ├── sources.py     # visit chart folder and nightly lab JSONL feed
│   ├── documents.py   # IntakeForm, DoctorNote, and LabReport
│   ├── facts.py       # MedicationDose, BloodType, and SmokingStatus
│   └── judges.py      # ClinicalFloors
├── prompts/
│   ├── doctor_note/
│   │   ├── extract.md.j2       # extraction rules for signed visit notes
│   │   └── med_changes.md.j2   # summarizes medication changes in a visit
│   └── clinical_floors/
│       └── judge.md.j2         # rubric prompt for clinical evidence
└── evals/visits_and_labs.jsonl
```

## Documents

`IntakeForm` uses the built-in defaults. `DoctorNote` summarizes medication orders before running extraction, and
`LabReport` trims reference tables during classification so the choice model sees the header and final results.

```python
# documents.py
from factorial import Document
from cedar_clinic.facts import BloodType, MedicationDose, SmokingStatus

class IntakeForm(Document):
    """A check-in questionnaire completed and signed by a patient before an office visit."""
    facts = [MedicationDose, BloodType, SmokingStatus]

class DoctorNote(Document):
    """A clinician's signed office visit note covering history, exam, assessment, and plan."""
    facts = [MedicationDose, SmokingStatus]

    def extract(self, passages):
        med_summary = self.generate("med_changes.md.j2", passages=passages)
        return super().extract(passages, med_summary=med_summary)

class LabReport(Document):
    """A clinical laboratory report containing specimen details and completed test results."""
    facts = [BloodType]
    classify_threshold = 0.85

    def classify_view(self) -> str:
        return self.head(350) + self.tail(350)
```

## Facts

Typed attributes define each slot. Two plain code hooks enforce domain rules: `MedicationDose.validate` bounds
milligram doses, and `SmokingStatus.supersedes` prevents a `"never"` claim from replacing a prior smoking history.

```python
# facts.py
from typing import Literal
from factorial import Entity, Fact

class MedicationDose(Fact):
    """A patient's prescribed daily dose of a medication, measured in milligrams."""
    patient: Entity
    medication: str
    daily_mg: int

    def validate(self) -> bool:
        return 0 < self.daily_mg <= 1000

class BloodType(Fact):
    """A patient's ABO and Rh blood group."""
    patient: Entity
    blood_type: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

class SmokingStatus(Fact):
    """Whether a patient currently smokes, smoked in the past, or has never smoked."""
    patient: Entity
    smoking_status: Literal["never", "former", "current"]

    def supersedes(self, older: "SmokingStatus") -> bool:
        if older.smoking_status in ("former", "current") and self.smoking_status == "never":
            return False
        return super().supersedes(older)
```

## Sources and judges

Records arrive from a visit chart folder and a nightly lab feed. `ClinicalFloors` uses the choice model to score
whether each candidate fact is backed by a direct order, lab result, or patient report.

```python
# sources.py
from factorial.sources import FolderSource, JsonlSource

class VisitCharts(FolderSource):
    """Scanned intake questionnaires and signed clinician notes from office visits."""
    path = "./var/inbox/visits"

class LabFeed(JsonlSource):
    """Nightly JSONL export of finalized reports from the reference laboratory."""
    path = "./var/inbox/labs.jsonl"
```

```python
# judges.py
from factorial import Judge

class ClinicalFloors(Judge):
    """Filters out clinical claims that come from family history, questions, or rule-out notes."""

    def judge(self, fact) -> bool:
        level = self.score("judge.md.j2", rubric=["unsupported", "hedged", "documented"], fact=fact)
        return level == "documented"
```

## Prompts

Templates in `prompts/<class_name>/` override built-in hook prompts with `{% extends %}` or define helper prompts.

```jinja
{# prompts/doctor_note/med_changes.md.j2 #}
List medications started, adjusted, or stopped in this {{ document.at }} visit note, citing passage numbers.
Ignore family history and declined treatments.
{% for passage in passages %}
[{{ passage.n }}] {{ passage.speaker }}: {{ passage.text }}
{% endfor %}
```

```jinja
{# prompts/doctor_note/extract.md.j2 #}
{% extends "factorial/extract.md.j2" %}
{% block guidance %}
Medication summary for this visit: {{ med_summary }}
Record active daily doses in milligrams. Skip discontinued drugs and as-needed doses.
{% endblock %}
```

```jinja
{# prompts/clinical_floors/judge.md.j2 #}
Score whether the quote supports this clinical fact.
Fact: {{ fact }}
Quote ({{ fact.speaker }}, {{ fact.at }}): {{ fact.quote }}
Return "documented" for a direct order, lab result, or patient report, "hedged" for a rule-out note, and
"unsupported" for family history or unconfirmed remarks.
```

## Settings

```python
# settings.py
import os
from factorial import Model, Search, Settings
from factorial.indexes import SqliteFts
from factorial.stores import S3Store

class ClinicSettings(Settings):
    store = S3Store(bucket="cedar-clinic-facts", key=os.environ["S3_KEY"])
    index = SqliteFts(path="./var/index.db")
    models = {
        "choice": Model("typesafe/jev-1.13.0"),
        "generate": Model("fireworks/glm-5p3-flash"),
        "embed": Model("openai/text-embedding-3-small"),
    }
    search = Search(retrieve="hybrid-rrf", budget_tokens=1500)
```

## What happens as documents arrive

Four records for `patient_402` arrive over three months:

1. **2026-01-12, `LabReport` (`speaker="metro_lab"`):** Reports `"ABO/Rh: O negative."` `LabReport.classify_view`
   sends the header and result lines to the choice model, which scores above `0.85`. Factorial logs `added` for
   `BloodType(patient="patient_402", blood_type="O-")`.
2. **2026-01-15, `DoctorNote` (`speaker="dr_patel"`):** Notes `"Start lisinopril 10 mg daily. Former smoker, quit in
   2018."` `DoctorNote.extract` summarizes the new order, `MedicationDose.validate` accepts `10`, and `ClinicalFloors`
   marks both `"documented"`. Factorial logs `added` for `MedicationDose("patient_402", "lisinopril", 10)` and
   `SmokingStatus("patient_402", "former")`.
3. **2026-04-09, `IntakeForm` (`speaker="patient_402"`):** On check-in, the patient writes blood type `"O-"` and
   checks `"Never smoked."` `resolve` merges the `"O-"` `BloodType` as a duplicate, attaching the patient's quote,
   speaker, and date to the lab fact. `SmokingStatus.supersedes` returns `False` when `"never"` meets `"former"`, so
   `resolve` flags `contradicted` and keeps both quotes, speakers, and timestamps visible.
4. **2026-04-09, `DoctorNote` (`speaker="dr_patel"`):** That afternoon's note states `"BP elevated; increase
   lisinopril to 20 mg daily."` `resolve` retires the January dose as `superseded` and logs `added` for
   `MedicationDose("patient_402", "lisinopril", 20)`. Calling
   `MedicationDose.current(patient="patient_402", medication="lisinopril").daily_mg` now returns `20`.

The design is described in [the Python README](../README.md).
