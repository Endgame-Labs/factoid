# Fact traits: research

Two rounds of review of the fact traits draft (`SPEC.md`, "Fact traits"), run on 2026-11-14 by Carbon (Gemini 4 Carbon
medium, through `agy`) and Astra (`gpt-6-astra`, through Codex). Each round gave both reviewers the same brief, and they
did not see each other's answers.

- Round 1: each reviewer brainstormed its own corpus types and stress-tested the CRM-shaped draft on the six that broke
  it hardest. Prompt: `round1-prompt.txt`. Answers: `round1-carbon.md`, `round1-astra.md`.
- Round 2: a revised draft, built from round 1, tested on corpora from Claude's list that each reviewer had not covered.
  Prompts: `round2-prompt-carbon.txt`, `round2-prompt-astra.txt`. Answers: `round2-carbon.md`, `round2-astra.md`.

Corpora covered across both rounds: clinical notes, contracts and statutes, policies and handbooks, incident logs and
telemetry, release notes and specs, engineering chat, scientific papers, journalism and depositions, news, oral
histories and archives, fiction and game lore, an agent's memory of one user, support tickets, and financial filings.

## What both reviewers agreed on

1. **Never anchor a fact about the past to when it was said.** "Lincoln practiced law in Springfield", read from a 2024
   book, is not valid until 2027. Time comes from the text: when something was observed, when a state started and
   ended, when an event happened, and the target date of a plan or forecast. Publication time is kept separately.
2. **Kind classifies what the fact is about, not its tense.** A past residence is still a state, with a closed interval.
   A closed interval needs no persistence guess.
3. **"Fixed" is narrow:** invariant attributes and closed-period values. A dated reading of something that moves ("cash
   was $1.18B as of September 30") is an observation of a state, and should fade as time passes.
4. **Persistence is counted from the latest observation of an ongoing state**, needs a range shorter than hours and an
   open-ended longest range, and is updated by repeated observations. "Never mentioned again" is censored data, not proof
   that the state held.
5. **Stance was too broad.** A stated preference ("I prefer quiet restaurants") is direct, not evaluative. Rounded
   numbers, policy discretion ("generally"), and attribution are not uncertainty. A real conditional instruction ("if the
   culture is positive, start amoxicillin") is a rule, not a hypothetical.
6. **Plans need deadlines, not persistence.** When a plan's target date passes with no confirmation, it is overdue or
   unverified, not false.
7. **Both would merge `decision` into `event`.** A decision is something that happened. What it sets up (an obligation, a
   new state, a rule) should be extracted as its own fact. Kyle asked for `decision` as a kind, so this needs his call.
8. **Scope (version, jurisdiction, edition, environment) is entities, and comparison needs overlapping scope**, not just
   matching entities.

## Where they differed

- **Endings and corrections.** Carbon proposes a new trait, `transition`: none, ends ("the hotfix resolved the 502s"),
  or corrects ("restated Q1 revenue was $380M"). Astra would handle corrections, retractions, cancellations, and
  amendments as linked evidence outside the traits.
- **Plans versus forecasts.** Astra splits them: a plan is someone's intended action, and a forecast is an expected
  outcome ("the central bank is expected to cut rates"). Carbon kept them together.
- **Persistence on rules.** Carbon would estimate persistence for rules, so an old expense limit fades. Astra would use
  supersede and review dates instead.
- **Proposition structure.** Astra wants subject, relation, and object roles extracted for comparison. That conflicts
  with Factoid's decision against typed slots on facts.
- **Fiction.** Carbon notes that story time is an order of chapters, not a calendar, and proposes ordinal positions.

## Risks both named

- Entity names leak what the model already knows about famous entities. Mask them while scoring, by type (`[COMPANY]`,
  `[TICKET]`), so the kind of thing stays visible.
- A distribution over ranges is not a survival curve. Interpolation within a range and the tail need to be specified.
- Calibrate against observed transitions, with censoring, and audit a sample by hand.
