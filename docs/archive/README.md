# Archive

These docs describe Factoid before 2026-11: a single `factoid.yml` config, judge stages, typed fact slots, a "disputed"
status, eval folders with `suite.yml`, and an event log that was the record of truth.

The code now uses Python classes (`Document`, `Fact`, `FactTrait`, and `Entity`), fact evals, current state in SQLite
with the event log kept for audit, and eval suites written as Python classes.

They are kept for the reasoning behind decisions. Files: `mental-model.md`, `documents.md`, `facts.md`, `config.md`,
`plugins.md`, `evals.md`, `api.md`, `open-questions.md`, and `potential/`. For the current design, read
[`../../README.md`](../../README.md) and [`../../SPEC.md`](../../SPEC.md).
