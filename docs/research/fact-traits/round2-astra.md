**1. An AI agent’s memory of one user 🧠**

All examples below are invented. `A` = asserted_at, `F/T` = valid_from/valid_to, `?` = unsupported or unknown. Persistence examples describe plausible model outputs, not ground truth; production should retain the full distribution.

- **“I prefer quiet restaurants.”** Said 2026-03-01.
  - **Kind:** state. **Stance:** evaluative. **Time:** A=2026-03-01; F/T=?. **Persistence:** a year / several years.
  - **Problem:** “Evaluative” must not discount a first-person preference. The preference can be reliably reported even though the restaurant’s quietness is subjective. A later preference for lively birthday dinners need not supersede it: occasion matters.
- **“I lived in Boston from 2018 through 2020.”** Said 2026-03-01.
  - **Kind:** state, but also qualifies as fixed under “cannot change once true.” **Stance:** direct. **Time:** A=2026-03-01; F=2018; T=2020, both at year precision. **Persistence:** the draft asks, although the interval is already closed.
  - **Problem:** historical anchoring makes virtually every past state immutable history. Kind needs to classify the underlying predicate, independently of whether its interval is complete. Known endpoints should bypass persistence estimation.
- **“I’m moving to Berlin in September.”** Said 2026-03-01.
  - **Kind:** plan. **Stance:** direct. **Time:** A=2026-03-01; September 2026 is supported, but there is no unambiguous field for its role. **Persistence:** not asked.
  - **Problem:** September is the intended move time, not when the intention starts being valid. A cancellation tomorrow makes this obsolete as an active plan while preserving it as historical intent.

**2. Clinical notes**

- **“The patient denies chest pain today.”** Note dated 2026-04-02.
  - **Kind:** state. **Stance:** uncertain under the attribution rule; arguably direct as a report of denial. **Time:** A=2026-04-02; F/T=the reported day, with finer boundaries unknown. **Persistence:** hours / a day.
  - **Problem:** the observed fact is a denial; absence of pain is its reported content. Those are different propositions. “Reports chest pain” tomorrow is a change; a nurse documenting pain that same day is not automatically a contradiction.
- **“The patient has had type 1 diabetes since 2011.”** Note dated 2026-04-02.
  - **Kind:** state. **Stance:** direct. **Time:** A=2026-04-02; F=2011; T=?. **Persistence:** several years.
  - **Problem:** the model needs a remaining-duration estimate from the observation date. Applying “several years” from 2011 could make a currently reaffirmed diagnosis look stale immediately. Long-lasting states also exceed the finite bucket vocabulary.
- **“If the culture is positive, start amoxicillin.”** Instruction dated 2026-04-02.
  - **Kind:** rule. **Stance:** hypothetical under a literal reading of the draft. **Time:** A=2026-04-02; F/T=?. **Persistence:** not asked.
  - **Problem:** this is an actual conditional instruction, not a hypothetical instruction. Its condition belongs in the proposition. The instruction can later be withdrawn, but rule facts currently receive no freshness handling.

**3. News articles**

- **“The minister resigned on May 6.”** Published 2026-05-07.
  - **Kind:** event; fixed also fits the draft. **Stance:** direct. **Time:** A=2026-05-07; F/T=2026-05-06 at day precision. **Persistence:** not asked.
  - **Problem:** a correction saying the resignation never occurred challenges truth, not persistence. Historically durable claims still need correction and retraction handling.
- **“An anonymous official says the ceasefire is holding.”** Published 2026-05-07.
  - **Kind:** state for the ceasefire, event for the official’s statement. **Stance:** uncertain for the embedded claim, direct for the report of speech. **Time:** A=2026-05-07; F/T=? unless the reporting time is supplied. **Persistence:** hours / a day for the ceasefire.
  - **Problem:** the system must preserve which proposition it scores. Republishing this sentence a week later must not create a fresh observation of the ceasefire.
- **“The central bank is expected to cut rates in June.”** Published 2026-05-07.
  - **Kind:** plan. **Stance:** uncertain. **Time:** A=2026-05-07; June 2026 is a forecast target, not an established validity interval. **Persistence:** not asked.
  - **Problem:** an outside forecast is not the bank’s intention. Treating it as a plan can fabricate institutional commitment, particularly when the forecaster is unnamed.

**4. Customer support tickets**

- **“The customer cannot log in.”** Agent note dated 2026-06-10.
  - **Kind:** state. **Stance:** direct as written, uncertain if explicitly attributed to the customer. **Time:** A=2026-06-10; F/T=?. **Persistence:** hours / a day.
  - **Problem:** wording changes stance despite identical evidence. Later troubleshooting might reveal that login works but authorization fails; that is a correction to the diagnosis, not necessarily a state transition.
- **“The customer chose annual billing on June 10.”** Recorded 2026-06-10.
  - **Kind:** decision. **Stance:** direct. **Time:** A=2026-06-10; F/T=2026-06-10 at day precision. **Persistence:** not asked.
  - **Problem:** choosing annual billing does not establish that annual billing was activated. Historical decisions must not answer queries about the current subscription state.
- **“The refund will arrive within five business days.”** Agent promise dated 2026-06-10.
  - **Kind:** plan. **Stance:** direct. **Time:** A=2026-06-10; a relative delivery deadline is supported; F/T cannot cleanly represent it. **Persistence:** not asked.
  - **Problem:** a promise, an estimate, and a completed refund require different follow-up. Calculating the deadline also requires the applicable business calendar. Passing it means overdue or unverified, not disproved.

**5. Financial filings and earnings calls**

- **“Revenue for the quarter ended March 31 was $42 million.”** Filing dated 2026-05-01.
  - **Kind:** fixed as a completed measurement; state is also plausible as a time-bounded number. **Stance:** direct. **Time:** A=2026-05-01; T=2026-03-31; F=? unless the fiscal period is defined. **Persistence:** not asked if fixed.
  - **Problem:** restatements revise the reported value without changing the historical quarter. Comparison needs metric, units, consolidation scope, accounting basis, and reporting revision—not merely matching company entities.
- **“We expect full-year revenue of $180–190 million.”** Earnings call dated 2026-05-01.
  - **Kind:** plan. **Stance:** uncertain. **Time:** A=2026-05-01; target=the identified fiscal year; F/T are ambiguous. **Persistence:** not asked.
  - **Problem:** later guidance replaces a forecast, not realized revenue. Guidance has an active lifespan distinct from its forecast horizon. “Approximate” also should not conflate a numerical range with weak evidence.
- **“The credit agreement requires net leverage below 4.0× at each quarter-end.”** Filing dated 2026-05-01.
  - **Kind:** rule. **Stance:** direct. **Time:** A=2026-05-01; F/T=? without agreement dates. **Persistence:** not asked.
  - **Problem:** amendments, waivers, and termination change applicability. Exact scope matching can prevent comparison between an original agreement and its amendment precisely when comparison is necessary.

**6. Engineering team chat**

- **“The API is down in production right now.”** Posted 2026-07-08 at 14:03 UTC.
  - **Kind:** state. **Stance:** direct. **Time:** A=2026-07-08T14:03Z; state observed at that instant; onset and end unknown. **Persistence:** hours.
  - **Problem:** “right now” supplies an observation time, not valid_from as onset. Minutes may matter operationally, yet the shortest bucket is hours. Recovery followed by another outage is a new episode.
- **“We decided to disable retries.”** Posted 2026-07-08 at 14:05 UTC.
  - **Kind:** decision. **Stance:** direct. **Time:** A=2026-07-08T14:05Z; decision time unspecified. **Persistence:** not asked.
  - **Problem:** it does not establish that retries are disabled. Thread context may identify the service and environment, but attaching every mentioned entity does not express which entity fills which role.
- **“If retries were disabled, this request would have succeeded.”** Posted 2026-07-08 at 14:07 UTC.
  - **Kind:** rule is the nearest option, but incorrectly implies a regularity. **Stance:** hypothetical. **Time:** A=2026-07-08T14:07Z; target=request time, if recoverable. **Persistence:** not asked.
  - **Problem:** this is a counterfactual outcome for one request. Kind should describe the embedded event, while stance records its counterfactual status. It must not become evidence that the request succeeded.

**Changes I would make**

1. **Make kind independent of tense and modality; merge decision into event.** A historical residence remains a state; a decision is an event whose domain importance can be labeled. Reserve fixed for invariant attributes and fixed historical values, with explicit tie-breaking examples. Motivation: memory, support, finance, and chat.

2. **Separate forecast from plan within kind.** Plan means an agent’s intended or committed action; forecast means an expected outcome. Keep conditions and commitment wording in structured extraction. Motivation: news, earnings guidance, and support promises. This adds an option, not another question.

3. **Remove attribution and approximation from the definition of uncertain.** Attribution belongs in provenance; numerical precision belongs with the value. Reserve hypothetical for assumed or counterfactual propositions, not actual conditional rules. Allow stance options to overlap using independent probabilities from the same pass. Motivation: clinical reports, anonymous news sources, preferences, and conditional instructions.

4. **Add temporal roles, not a temporal trait.** Distinguish observation time, state onset/end, event time, and plan/forecast target time; preserve precision and unresolved relative expressions. Keep source publication time separate from the original assertion time. Motivation: every corpus.

5. **Estimate persistence from the latest supported observation of an ongoing state.** Define it as time until the *current episode* ends, conditional on what is known. Skip closed intervals; allow a dated observation even when publication date is missing. Add a sub-hour range and an open-ended longest range. Treat unknown as abstention, not duration. Motivation: chronic diagnoses, outages, and preferences.

6. **Do not equate a bucket distribution with a survival curve.** Specify within-bucket interpolation and an explicit tail model. Repeated observations should update the estimate; an end discovered between observations is interval-censored. No further mention supplies no evidence beyond the last confirmed observation. Calibrate against observed transitions, with uncertainty. Motivation: clinical records, tickets, and sparse personal memories.

7. **Handle revisions and comparability outside traits.** Extract subject–relation–object roles, polarity, conditions, and scope relationships; record corrections, retractions, cancellations, and amendments as linked evidence. Compare overlapping applicability, not just identical scope entities. Use deadlines and review policies for plans, forecasts, and rules; state persistence alone cannot cover their freshness. Motivation: all six corpora.

**No new always-on trait is needed.** The largest gaps are proposition structure, temporal roles, and evidence updates. A persistence score estimates continuity conditional on a state having held; it does not establish initial truth or resolve a contradiction.