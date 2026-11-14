### 1. Corpus Brainstorm & Top 6 Stressors

**Candidate corpora:** clinical/EHR notes, legal contracts & statutes, software incident logs & runbooks, scientific papers, investigative journalism/depositions, historical/biographical archives, intelligence/OSINT cables, financial SEC filings, manufacturing QA logs, real-estate title records, tabletop/fiction lore bibles, government policy/rulemaking dockets.

**The 6 that stress the draft traits hardest:**
1. **Clinical / EHR Notes:** Mixes minute-by-minute vitals, episode-bound treatments, and lifelong allergies; states end via interventions, not clocks.
2. **Legal Contracts & Statutes:** Statements are normative rules and conditional obligations whose effective windows differ from when the document was written.
3. **Software Incident Logs & Runbooks:** Truth is scoped to versions, environments, and sub-hour timescales rather than calendar months.
4. **Scientific Literature:** Claims assert timeless mechanisms yet get overturned by new evidence—falsification, not temporal state change.
5. **Investigative Journalism / Depositions:** Sources lie, hedge, and retrodict past states; disagreement is evidentiary conflict, not supersession.
6. **Historical / Biographical Archives:** Written decades after the events described, breaking `valid_until = when_stated + range`.

---

### 2. Stress-Testing the Draft Traits

**1. Clinical / EHR Notes**
- *"Patient's potassium is 6.2 mEq/L."* → `current state`, `a day`, `observed`. **Fails:** Dangerous hyperkalemia changes in *hours*, not days; `a day` is the shortest bucket, ranking lethal stale labs as fresh.
- *"Patient has a severe penicillin allergy."* → `stable`, `permanent`, `observed`. **Misleads:** If a later allergy challenge disproves it, `permanent` + `stable` flags an unresolved contradiction forever instead of a diagnostic correction.
- *"Patient is on IV heparin drip."* → `current state` or `plan`, `a week`, `observed`. **Fails:** Expiry is event-driven (discharge or surgery), not calendar-driven.

**2. Legal Contracts & Statutes**
- *"Tenant shall pay $4,000 on the 1st of each month from Jan 2027 to Dec 2028."* (signed Nov 2026) → `decision`/`plan`, `several years`. **Fails:** `when_stated + median` marks it valid *now* (Nov 2026) before the lease even starts, and guesses duration instead of using explicit bounds.
- *"Either party may terminate upon 30 days' written notice for material breach."* → `stable`, `several years`. **Fails:** Conditional/normative rule, not an empirical state or event.
- *"The 2024 Privacy Act repeals Section 12 retroactive to Jan 1, 2023."* → `event` or `decision`, `permanent`. **Misleads:** Event stays true as history, but Factoid has no signal that prior Section 12 facts are retroactively invalidated for past-date queries.

**3. Software Incident Logs & Runbooks**
- *"Checkout p99 latency spiked to 14s."* → `current state`, `a day`. **Fails:** `a day` keeps a 12-minute outage "currently true" for 24 hours.
- *"Auth-service retries failed RPCs 3 times in v2.4."* → `stable`, `a year`. **Misleads:** Expiry is tied to deploying `v2.5`, not wall-clock time; two environments running `v2.4` and `v2.5` simultaneously look like a contradiction unless entity-scoped.
- *"Root cause was an unindexed foreign key on `orders`."* → `event`/`observed` (or `opinion`?). **Misleads:** Postmortem conclusions are fallible inferences about past events; revised root causes aren't state changes.

**4. Scientific Literature**
- *"Compound ZX-9 inhibits kinase mTORC1 in vitro (p = 0.03)."* → `stable`, `permanent`, `observed`. **Fails:** Empirical measurements are permanent, but generalized mechanistic claims get refuted. Treating refutation like an eternal contradiction without distinguishing scope ("in HeLa cells" vs universal) pollutes search.
- *"Dark matter may consist of ultralight axions."* → `stable`, `permanent`, `hedged=yes`. **Misleads:** Not an `opinion`, nor `observed`—it is a testable hypothesis.
- *"Global mean CO2 reached 422 ppm."* → `current state` or `event`, `a year`. **Misleads:** True permanently as a dated measurement, false next year as a current reading; Kind blurs the two.

**5. Investigative Journalism / Depositions**
- *"Witness A testified that CFO Vance shredded ledgers on Oct 4."* → `event`, `permanent`, `observed`. **Fails:** What is observed is *that Witness A said it*, not that Vance did it. Two witnesses disagreeing on an `event` creates a genuine conflict that should *never* expire, yet attribution reliability is invisible.
- *"In 2019, Vance controlled shell company RedOak."* (deposition in 2026) → `slow-changing`, `several years`. **Fails:** `2026 + several years` says Vance controls RedOak until ~2029!
- *"Vance appeared panicked during the audit."* → `event` or `current state`, `opinion`. **Misleads:** Demeanor is half-observation, half-judgment, anchored to a past moment.

**6. Historical / Biographical Archives**
- *"Lincoln practiced law in Springfield."* (2024 book) → `slow-changing`, `several years`. **Fails catastrophically:** Anchoring validity to `when_stated` (2024) makes Lincoln a practicing Springfield lawyer until ~2027.
- *"Census records list Ada's birth year as 1842."* (vs parish record: 1841) → `stable`, `permanent`. **Works for contradiction, fails on decay:** Draft wants contradictions to "go stale when facts expire," which never happens here—requiring source/epistemic resolution instead.
- *"The regiment intended to cross the river at dawn."* → `plan`, `a day`. **Fails:** `when_stated` + 1 day marks an 1863 plan active in 2024.

---

### 3. Cross-Corpus Gaps & Where Each Belongs

1. **Statement time vs. reference time (`when_stated` bug):** Past-tense states in history, depositions, and medical histories get projected into the future. → **New option on Kind (`past_state`)** so Factoid skips `when_stated + lifespan`. (Extracting exact historical dates requires text/span extraction, not a fixed-choice trait.)
2. **Immutable facts vs. durable mutable states:** Draft `stable` conflates things that *cannot* change (birth date, founding year) with things that change *rarely* (HQ city, diagnosis). Clashes on the first are always contradictions; clashes on the second across years are supersedes. → **Split options on Kind (`immutable` vs `state` + long `lifespan`), and drop `slow-changing`** (which duplicates `lifespan`).
3. **Normative / conditional rules:** Leases, statutes, runbooks, clinical protocols. → **New option on Kind (`rule`)**.
4. **Sub-day volatility & non-clock (trigger-bound) expiry:** Vitals, outages, feature flags, hospital stays. → **New options on Validity (`hours` at the low end; `indefinite` for non-clock/immutable facts)**. Version, encounter, or jurisdiction scoping is **better left to entities and labels** (e.g., linking facts to entity `v2.4` or `Admission-88`).
5. **Hypotheses, hearsay, and reported claims:** `opinion vs observed` + `hedged` costs 2 questions yet misses attributed/unverified claims and scientific hypotheses. → **Merge into one `epistemic` choice trait**.
6. **Domain workflow status (e.g., repealed, retracted, HIPAA-sensitive, deal stage):** → **Better left to project labels**; universal rubrics can't know domain revocation rules.

---

### 4. Proposed General Trait Set

3 default traits (one pass, 3 probability distributions per fact; down from 4 in draft) + 1 optional trait:

1. **`kind` (choice — DEFAULT ON)** — *Separates supersession logic from contradiction logic and prevents projecting past states forward.*
   - `immutable`: Fixed once true; cannot change over time (completed events, birth/founding dates, dated measurements).
   - `state`: Mutable property, status, role, or metric presented as current when stated.
   - `past_state`: Mutable state explicitly described as holding in the past relative to statement time.
   - `prospective`: Plan, forecast, intention, or scheduled future occurrence.
   - `rule`: Normative obligation, policy, definition, or conditional invariant.

2. **`lifespan` (ordered ranges — DEFAULT ON)** — *Drives search freshness, re-check queues, and supersede windows across sub-hour to multi-year scales.*
   - `hours`: Expected to change within <24 hours (vitals, live incident metrics).
   - `days`: Lasts ~1–7 days (sprint blockers, acute symptoms, short weather/travel).
   - `weeks`: Lasts ~1–4 weeks (deal stages, inpatient regimens, active negotiations).
   - `months`: Lasts ~1–6 months (quarterly plans, contractor assignments, Macro/KPI trends).
   - `years`: Lasts ~0.5–3 years (job titles, leases, software major versions).
   - `decades`: Lasts 3+ years but remains mutable (headquarters, chronic conditions, statutes).
   - `indefinite`: Does not decay by wall-clock time (`immutable` facts, `past_state`, universal claims).

3. **`epistemic` (choice — DEFAULT ON)** — *Prevents hypotheses, hearsay, and subjective takes from triggering false contradictions against hard records.*
   - `direct`: Stated as an unhedged observation, primary record, or enacted rule/decision.
   - `uncertain`: Hedged ("likely", "approx."), hypothesized, forecast, or attributed to an unverified third party ("witness claims").
   - `evaluative`: Subjective judgment, sentiment, or qualitative interpretation ("codebase is fragile").

4. **`generality` (choice — OPTIONAL)** — *Useful in scientific, technical, and legal corpora to separate class-level laws from entity-instance states.*
   - `instance`: Describes specific concrete entities or episodes ("Node-3 ran out of memory").
   - `general`: Asserts a class-level regularity, physical mechanism, or universal principle ("Redis uses single-threaded execution").

---

### 5. Risks of Model-Guessed Validity & How to Keep It Honest

- **Entity memorization & hindsight leakage:** The model knows *Northwind* isn't real, *Lehman Brothers* collapsed in 2008, and *Steve Jobs* left Apple in 1985—so its validity probabilities cheat on famous entities and miscalibrate on private ones. **Fix:** Mask or replace linked entity names with typed placeholders (`[ORG_1]`, `[PERSON_1]`) during trait scoring.
- **Hard cutoff fallacy (`valid_until = t + median`):** Treating a broad probability distribution over log-spaced buckets as a deterministic expiration cliff drops a 51%-likely-true fact off a cliff at day 31. **Fix:** Compute expected survival probability $P(\text{still valid at } \Delta t) = \sum_b p_b S_b(\Delta t)$ from the full option distribution for ranking and filtering, rather than storing one brittle `valid_until` date.
- **Right-censoring & observation bias in calibration:** You only observe a fact dying when a new document bothers to mention the entity again; quiet entities look immortal, and noisy entities look volatile. **Fix:** Calibrate per `(kind, label)` using survival analysis (Kaplan–Meier / interval-censored likelihood) where "last seen unchanged" is right-censored, and "superseded between $t_1$ and $t_2$" is interval-censored—never treat silence as persistence.
- **Missing document timestamps:** If `when_stated` defaults to ingestion time on undated archives, every `lifespan` projection is garbage. **Fix:** Require an explicit document/quote timestamp to materialize calendar validity; when absent, leave `valid_until = null` and use `lifespan` only as a relative volatility weight.
