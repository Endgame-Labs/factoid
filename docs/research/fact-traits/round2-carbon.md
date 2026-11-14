## 1. AI Agent's Long-Term Memory of One User

1. **"Maya prefers concise Python snippets without type hints."** *(chat, 2026-03-10)*
   - Draft: `kind=state` (or `rule`), `stance=evaluative`, `asserted_at=2026-03-10`, `valid_from/to=None`, `persistence=a year`–`several years` (skipped if `rule`).
2. **"Maya has a final-round interview at Stripe on April 9, 2026."** *(chat, 2026-04-02)*
   - Draft: `kind=plan`, `stance=direct`, `asserted_at=2026-04-02`, `valid_from=2026-04-09`, `valid_to=2026-04-09`, `persistence=N/A`.
3. **"Maya goes to physical therapy every Tuesday morning."** *(chat, 2026-04-14)*
   - Draft: `kind=state` (straddles `rule`/`event`), `stance=direct`, `asserted_at=2026-04-14`, `valid_from/to=None`, `persistence=a month`–`a quarter`.

**Where it fails:**
- **Preferences vs. appraisals and standing instructions:** `evaluative` lumps ground-truth user directives with subjective appraisals (`"Stripe's UI is ugly"`). Worse, if classified as `rule`, `Persistence` is skipped—so stale prompt preferences never decay and clash as contradictions instead of supersedes when tastes shift.
- **Zombie `plan`s:** Once `2026-04-09` passes with no follow-up chat, `plan` has no persistence distribution and no post-`valid_to` decay rule, leaving unconfirmed past plans at full rank.
- **Recurring routines:** Flat `[valid_from, valid_to]` intervals on `state` lose periodicity (`"every Tuesday"`), misleading date-filtered availability checks.

## 2. Customer Support Tickets

1. **"Acme Corp users get HTTP 502 on CSV export in WebApp v4.2."** *(Ticket #881, customer email, 2026-05-01T09:12Z)*
   - Draft: `kind=state`, `stance=uncertain` (unverified reporter), `asserted_at=2026-05-01T09:12Z`, `valid_from/to=None`, `persistence=hours`–`a day`, scope=`WebApp v4.2`.
2. **"Rebuilding Acme's search index did not stop the 502 errors."** *(agent note, 2026-05-01T10:05Z)*
   - Draft: `kind=event`, `stance=direct`, `asserted_at=2026-05-01T10:05Z`, `valid_from/to=2026-05-01T10:05Z`, `persistence=N/A`.
3. **"Support agreed to credit Acme $500 on the June 2026 invoice."** *(agent reply, 2026-05-01T14:30Z)*
   - Draft: `kind=decision` (collides with `plan`), `stance=direct`, `asserted_at=2026-05-01T14:30Z`, `valid_from=2026-06-01`, `valid_to=2026-06-30`, `persistence=N/A`.

**Where it fails:**
- **Entity masking blinds `Persistence`:** When `Enterprise Plan`, `Ticket #881`, and `HTTP 502` are entities, masking reduces both `"Acme is on Enterprise Plan"` and `"Acme sees HTTP 502 on Ticket #881"` to `"[ENTITY] is on/sees [ENTITY]"`, hiding whether the state lasts hours or years.
- **Cross-kind ticket closure:** Symptoms enter as `state` (`"gets 502"`), while fixes enter as `event` (`"Hotfix 4.2.1 resolved Acme's 502s"`). Differing kinds prevent the fix from superseding or closing the open symptom.
- **`decision` hides pending obligations:** Typing the `$500` credit as `decision` ("stays true as history") misses that it is also an unfulfilled `plan` due for June re-checking.

## 3. Internal Policies and Employee Handbooks

1. **"US employees may expense up to $75 per day for travel meals."** *(Handbook, 2024-01-15)*
   - Draft: `kind=rule`, `stance=direct`, `asserted_at=2024-01-15`, `valid_from/to=None`, `persistence=N/A`, scope=`US`.
2. **"Managers should generally approve remote work up to two days per week."** *(Handbook, 2024-01-15)*
   - Draft: `kind=rule`, `stance=uncertain` (`"generally"`) or `evaluative` (`"should"`), `asserted_at=2024-01-15`, `valid_from/to=None`, `persistence=N/A`.
3. **"Paid parental leave increases to 16 weeks starting January 1, 2027."** *(HR memo, 2026-10-01)*
   - Draft: `kind=rule` (or `plan`), `stance=direct`, `asserted_at=2026-10-01`, `valid_from=2027-01-01`, `valid_to=None`, `persistence=N/A`.

**Where it fails:**
- **Mutable `rule`s never decay or supersede:** Handbooks never state `valid_to`. Because `rule` skips `Persistence` and supersede applies only when "the state changed", a 2021 `$50` cap and a 2024 `$75` cap stay tied in rank and flag a contradiction instead of a policy update.
- **Granted discretion misread as epistemic `uncertain`:** `"Generally"` and `"up to"` express manager discretion inside an enacted `direct` rule, not doubt about whether the rule exists.
- **Undated wiki pages:** Living handbook pages often lack in-text dates; skipping persistence on undated docs leaves retired HR policies unpenalized forever.

## 4. Fiction and Game Lore

1. **"Vaelen carries the Shattered Blade."** *(*Ashfall* Ch. 3, published 2022-09-01)*
   - Draft: `kind=state`, `stance=direct`, `asserted_at=2022-09-01`, `valid_from/to=None`, `persistence=a month`–`a year` (or skipped if undated), scope=`Ashfall`.
2. **"Tavernkeepers whisper that silver ash cures the Blight."** *(*Codex v1.0*, 2023-02-10)*
   - Draft: `kind=rule`, `stance=uncertain`, `asserted_at=2023-02-10`, `valid_from/to=None`, `persistence=N/A`, scope=`Codex v1.0`.
3. **"Emperor Malakor survived the Siege of Oakhaven in secret."** *(*Expansion v2.0*, 2025-06-01; *v1.0* stated he died there)*
   - Draft: `kind=event`, `stance=direct`, `asserted_at=2025-06-01`, `valid_from/to=None`, `persistence=N/A`, scope=`Oakhaven`.

**Where it fails:**
- **Publication dates corrupt story time:** Counting survival from `asserted_at=2022-09-01` decays Vaelen's inventory over real-world years; omitting dates triggers the undated-doc rule so Chapter 3 states never decay by Chapter 24. Fiction needs ordinal narrative position, not calendar dates.
- **Retcons and reveals collide with `event` permanence:** Since `event` stays true as history, *v2.0*'s survival reveal contradicts *v1.0*'s death unless installment scope or narrative override exists.
- **Diegetic rumor vs. source doubt:** `uncertain` merges canonically false in-world superstition (deliberate lore) with out-of-universe editorial uncertainty.

## 5. Financial Filings and Earnings Calls

1. **"Cash and cash equivalents were $1.18B as of September 30, 2026."** *(Q3 10-Q, filed 2026-11-04)*
   - Draft: `kind=fixed` ("dated measurement") or `state`, `stance=direct`, `asserted_at=2026-11-04`, `valid_from/to=2026-09-30`, `persistence=N/A` if `fixed`.
2. **"Management expects FY2027 revenue of approximately $1.9B to $2.0B."** *(Q3 call, 2026-11-04)*
   - Draft: `kind=plan`, `stance=uncertain` (`"expects"`, `"approximately"`), `asserted_at=2026-11-04`, `valid_from=2027-01-01`, `valid_to=2027-12-31`, `persistence=N/A`.
3. **"Restated Q1 2025 revenue was $380M, down from the previously reported $402M."** *(10-K/A, filed 2026-08-12)*
   - Draft: `kind=fixed`, `stance=direct`, `asserted_at=2026-08-12`, `valid_from=2025-01-01`, `valid_to=2025-03-31`, `persistence=N/A`.

**Where it fails:**
- **Point-in-time balance trap:** `"$1.18B as of Sept 30"` fits `fixed` ("dated measurement"), holding stale cash at 1.0 rank forever on liquidity queries; if typed `state` with `valid_to=2026-09-30`, it expires Oct 1 instead of decaying across Q4.
- **Guidance updates and rounded numbers:** Revised Q4 guidance for FY27 (`$1.7B–$1.8B`) shares `valid_from/to` with Q3's `plan`, flagging a contradiction rather than a forecast supersede; `"approximately"` demotes formal guidance to `uncertain`.
- **Restatements break `fixed`:** Two `fixed` Q1 2025 revenue figures (`$402M` vs. `$380M`) cannot resolve as a state change, leaving an audited restatement as an active contradiction.

## Recommended Changes to the Draft

1. **Merge `decision` into `event` (merged option in `Kind` — Support, Memory, Filings):** Making a choice (`"agreed to a $500 credit"`) is a historical `event`; extract the resulting obligation or regime separately as a `plan`, `state`, or `rule`. Removes classification overlap and keeps pending promises re-checkable.
2. **Run `Persistence` on `rule` and `plan`, and add `permanent` (widened trigger + new option in `Persistence` — Handbooks, Memory, Filings):** Enacted policies, user prompt directives, and open-ended plans mutate and should decay and supersede older `asserted_at` facts, while mechanistic invariants (`"if retries are off..."`) take `permanent`. Decay unconfirmed `plan`s once `valid_to` passes.
3. **Restrict `fixed` to immutable attributes and closed-period totals (revised option boundary in `Kind` — Filings, Support):** Keep `"Q3 revenue was $412M"` as `fixed`, but route point-in-time readings of mutable quantities (`"Cash was $1.18B as of Sept 30"`) to `state` (`valid_from=2026-09-30`, `valid_to=None`) so survival probability decays them smoothly.
4. **Narrow `evaluative` and `uncertain` (revised options in `Stance` — Memory, Handbooks, Filings, Lore):** Limit `evaluative` to subjective appraisals (`"UI is clunky"`), keeping stated preferences (`"Maya prefers no type hints"`) `direct`. Limit `uncertain` to genuine epistemic doubt or unverified attribution (customer reports, diegetic rumors), excluding numerical rounding (`"~$1.9B"`), policy discretion (`"generally"`), and forecast verbs already captured by `Kind=plan`.
5. **Add a 3-option trait: `Transition` = `none` | `ends` | `corrects` (new trait — all 5 corpora):** One compact question readable from surface phrasing: `ends` (`"resolved 502s"`, `"rescinded policy"`, `"finished PT"`) lets an `event` terminate a matching `state`, `plan`, or `rule` across kinds; `corrects` (`"restated Q1 revenue"`, `"survived in secret"`) overrides a prior `fixed` or `event` claim instead of flagging a contradiction. *(Silent restatements/retcons still require edition scope.)*
6. **Use type-preserving masks and ordinal `sequence` time (mechanics in #3 & #4 — Support, Lore, Handbooks):** Mask entities by class (`[COMPANY]`, `[TICKET]`, `[PLAN_TIER]`) during `Persistence` scoring so outages and subscription tiers stay distinct; support `(stream, ordinal)` positions alongside ISO dates so undated chapters decay in narrative order rather than wall-clock time.
