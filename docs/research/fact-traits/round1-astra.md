## 1. Corpus choices

Candidates: scientific papers, statutes, software specifications, incident reports, oral histories, archaeological catalogs, recipes, financial filings, classroom materials, fiction, weather forecasts, and maintenance manuals.

The six hardest tests:

| Corpus | Why it stresses the draft |
|---|---|
| Scientific papers and lab notebooks | Results depend on experimental conditions; observations, interpretations, and hypotheses have different standing. |
| Statutes, contracts, and policies | Requirements are not observations, and effective dates differ from publication dates. |
| Software specifications and release notes | Truth is often scoped to a version, platform, or configuration rather than elapsed time. |
| Incident reports and telemetry | Conditions can change in milliseconds, while records of those conditions remain historically true. |
| Oral histories and archival records | Sources disagree, dates are uncertain, and later discoveries revise our knowledge of an unchanged past. |
| Fiction and game lore | Truth depends on a fictional world, continuity, narrator, and sometimes a counterfactual premise. |

## 2. Examples and draft behavior

All examples below are invented. Draft assignments are plausible model outputs, not uniquely correct answers. That ambiguity is part of the problem. “Validity” means the draft’s proposed duration.

### Scientific papers and lab notebooks

| Fact | Likely draft classification | Failure or missing distinction |
|---|---|---|
| At 20°C, sample A had a resistance of 12 Ω during trial 7. | Event; permanent; observed | Permanent as a measurement record, not as the sample’s present resistance. Conditions and trial identity matter. |
| The authors hypothesize that protein P inhibits pathway Q. | Stable; several years; hedged; opinion | Hypothesis is neither ordinary opinion nor established observation. Its evidential standing can change without the proposed mechanism changing. |
| In model M, doubling input x doubles output y. | Stable; permanent; observed | A conditional relationship within a model is not an unconditional claim about the world. |

### Statutes, contracts, and policies

| Fact | Likely draft classification | Failure or missing distinction |
|---|---|---|
| Policy R requires visitors to wear badges beginning July 1. | Stable or slow-changing; year; observed | This is a requirement, not evidence that visitors wear badges. Its effective date is explicit. |
| Contract C ends on December 31 unless both parties extend it. | Plan; year; hedged | A conditional contractual boundary is not a speculative plan. “Unless” expresses a condition, not uncertainty. |
| The board adopted Policy R on June 12. | Decision or event; permanent; observed | Both kinds apply. Adoption, effectiveness, and subsequent repeal are separate events. |

### Software specifications and release notes

| Fact | Likely draft classification | Failure or missing distinction |
|---|---|---|
| Parser 2.4 rejects trailing commas in strict mode. | Stable; several years; observed | This may remain true of version 2.4 indefinitely, even after newer versions behave differently. |
| Starting in version 3.0, the cache is disabled by default. | Current state; month; observed | Version boundaries determine applicability; a month-long expiration is arbitrary. |
| If retries are disabled, the client sends each request at most once. | Stable; permanent; observed | The configuration condition must survive extraction and retrieval. It is not hedging. |

### Incident reports and telemetry

| Fact | Likely draft classification | Failure or missing distinction |
|---|---|---|
| At 14:03:02, node N’s CPU utilization was 99%. | Current state or event; day or permanent; observed | Both permitted answers are misleading for some uses. The reading is historical; its usefulness as a current estimate may last seconds. |
| Packet loss continued from 14:03 until 14:07. | Event; permanent; observed | An interval matters, not merely the statement timestamp or an expiration estimate. |
| The incident commander expected recovery within ten minutes. | Plan; day; hedged | An expectation is not necessarily a plan. The expectation remains historical even when the forecast fails. |

### Oral histories and archival records

| Fact | Likely draft classification | Failure or missing distinction |
|---|---|---|
| In her 1998 interview, Mara recalled that the bridge opened in 1947. | Event; permanent; observed or opinion | The recollection and the bridge opening are separate claims with different evidence. |
| The unsigned photograph probably depicts the east entrance. | Stable; permanent; hedged; opinion | This is an uncertain identification, not a preference. Entity resolution and evidential uncertainty are distinct. |
| A 1910 directory lists Ivo as living at 8 Pine Street. | Slow-changing; year; observed | A year after the directory or a year after ingestion? The listing is evidence about a historical residence, not a current address. |

### Fiction and game lore

| Fact | Likely draft classification | Failure or missing distinction |
|---|---|---|
| In the original trilogy, Queen Sera cannot cross running water. | Stable; permanent; observed | Fictional continuity is part of the claim’s scope. Another adaptation can disagree without contradiction. |
| Chapter 4’s narrator claims that Sera killed the king. | Event; permanent; observed | The narrator’s assertion does not establish the killing within the story. Attribution must remain explicit. |
| In the alternate ending, Sera would survive if the gate remained closed. | Plan; permanent or year; hedged | A counterfactual is neither a plan nor an uncertain prediction. It has no natural expiration date. |

## 3. Gaps across corpora

| Gap | Where it belongs | Reason |
|---|---|---|
| State versus occurrence versus general relationship | Replace the existing kind trait | These distinctions affect temporal reasoning across domains. |
| Prediction, condition, and requirement | New assertion-mode trait | They change what counts as satisfaction, failure, or contradiction. |
| Explicit uncertainty | Retain a narrowly defined yes/no trait | Wording can express uncertainty without making the claim subjective. |
| Evaluation versus description | Optional yes/no trait | Useful for some retrieval tasks; “observed” is too strong as its opposite. |
| Effective dates, observation intervals, and deadlines | Structured temporal metadata, outside traits | Exact boundaries must not be reduced to fixed options. |
| Version, jurisdiction, experimental setup, and fictional continuity | Entities and structured scope links | They determine whether two claims are comparable. Ordinary tags alone are insufficient. |
| Decision, diagnosis, hypothesis, promise, and measurement | Project labels | Their domain-specific distinctions do not justify universal questions. |
| Source reliability and evidential support | Provenance and evidence assessment, outside inherent traits | These depend on the source and supporting material, not merely sentence content. |
| Recording an assertion versus endorsing its content | Extraction and attribution structure | No single tag repairs a fact that has collapsed these two claims. |

## 4. Proposed general trait set

**Two traits on by default, two optional. Remove predicted validity from the inherent trait set.**

### A. Temporal structure — choice — **default on**

Classify the proposition as written, preserving its conditions and attribution.

| Option | Rubric |
|---|---|
| State | A condition, attribute, or relationship holds over an interval: “Dana is director.” |
| Occurrence | Something happens, changes, or is done at a time or over a bounded episode: “Dana resigned.” |
| General relation | A rule, regularity, definition, or conditional relationship is asserted: “In model M, x implies y.” |
| Unspecified | The sentence does not support a clear assignment. |

**Why:** Separates historical occurrences from conditions that may change. “Stable” and “slow-changing” become persistence estimates rather than competing kinds. Decisions are occurrences; plans typically describe an intention state or a prospective occurrence.

### B. Assertion mode — choice — **default on**

Classify the main assertion, not an embedded proposition. “Mara predicted rain” is an asserted occurrence; “Rain is expected tomorrow” is prospective.

| Option | Rubric |
|---|---|
| Asserted | Presented as obtaining or having obtained, without implying verification. |
| Prospective | Presented as intended, predicted, scheduled, or expected to obtain. |
| Conditional / hypothetical | Asserted only under a stated assumption, possibility, or counterfactual premise. |
| Normative | States what is required, permitted, or forbidden. |
| Unspecified | No dominant mode can be identified. |

**Why:** Prevents requirements, forecasts, and hypothetical outcomes from being treated as ordinary observations. For a conditional requirement, classify the main assertion as normative and preserve the condition in the fact and scope metadata. Split independently useful assertions during extraction.

### C. Explicit uncertainty — yes/no — **optional**

- **Yes:** The main assertion explicitly expresses uncertainty, approximation, or limited confidence.
- **No:** It does not; this says nothing about its actual reliability.

**Why:** Supports retrieval and cautious comparison without pretending to assess truth. “Probably” qualifies; an ordinary “if” or “unless” does not automatically qualify.

### D. Evaluative content — yes/no — **optional**

- **Yes:** The main assertion expresses a preference, value judgment, or appraisal against a subjective standard.
- **No:** It does not, including when it is an unverified descriptive claim.

**Why:** Distinguishes “the interface is delightful” from “the interface has three buttons.” Replaces the misleading opinion-versus-observed choice.

Store each trait’s probability distribution. A low maximum probability should support abstention, not force a confident category.

## 5. Persistence estimates: useful, but not validity

**Do not set `valid_until = stated_at + guessed_duration`.** That turns a model’s prior into an invented temporal boundary.

Use separate fields:

- `asserted_at`: when the source made the assertion.
- `valid_from` / `valid_to`: supported applicability boundaries, with their provenance and uncertainty.
- `observed_at` or observation interval: when a reported observation applies.
- `review_after`: an operational reminder that can be estimated.
- Optional persistence distribution: the chance that a scoped state remains unchanged after elapsed time.

If a fixed-option estimator is needed, make it an optional downstream question about eligible states: **sub-day, day, week, month, quarter, year, several years, or unknown**. Each option means “estimated time until this state changes,” not “time until this sentence becomes false.” Do not offer “permanent.”

Risks and safeguards:

- **Corpus shift:** CRM-derived persistence priors fail on telemetry and versioned specifications. Evaluate by corpus and claim type; abstain on unfamiliar cases.
- **False precision:** A range midpoint is not a calibrated survival estimate. Retain distributions and distinguish inferred estimates from source-supported boundaries.
- **Historical erasure:** Aging must not make a historical observation disappear from date-specific search.
- **False supersession:** Require matching entities, scope, and relevant time intervals before comparing claims. Later publication alone does not establish a changed state.
- **Disappearing contradictions:** Lower review priority if appropriate, but retain the disagreement and its resolution history. Expiration is not resolution.
- **Biased calibration:** “No correction found” is not proof of continued truth. Treat unobserved endings as censored, separate discovery time from change time, and audit a sample independently.

For “likely true at date D,” return the supported interval and any estimated probability separately. The framework should make the boundary between evidence and prediction visible. 🔎