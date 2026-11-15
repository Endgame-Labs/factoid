*Research cutoff: November 15, 2026. Product capabilities and performance figures below are vendor-reported unless stated otherwise. “Inferred” marks my interpretation or proposed Factoid design. All example fact sentences are fictional.*

## 1. Architecture, models, evaluation, and products

### Models and retrieval

| Component | What public sources establish |
|---|---|
| **Multiple model providers** | Harvey uses OpenAI, Anthropic, and Google DeepMind models, choosing among them for quality, latency, regional availability, and resilience. Its March 2026 explanation names GPT-5.2, Claude Opus/Sonnet 4.6, and Gemini 3 Flash as examples—not a permanent routing map. [Multi-model architecture](https://www.harvey.ai/blog/why-harvey-is-multi-model-by-design) |
| **Earlier custom model** | OpenAI’s case study describes a custom case-law model developed with Harvey using approximately 10 billion tokens of additional legal data. Lawyers at ten large firms preferred its answers to GPT-4’s 97% of the time; this measures preference, not factual accuracy. [OpenAI case study](https://openai.com/index/harvey/) |
| **Newer post-training** | An August 2026 research preview describes **Harvey Tenet**, built from Kimi K3 with Fireworks using reinforcement learning and LoRA. Training combines synthetic, public legal, and expert data. Treat this as a disclosed research model, not evidence that every Harvey feature runs on Tenet. [Tenet research preview](https://www.harvey.ai/blog/post-training-update-harvey-tenet) |
| **Specialized extraction models** | Harvey and Applied Compute describe post-training a GLM-5.2-based review-table model. The disclosed production harness retrieves context for each cell, then makes a model call over one or more documents. Separate experiments investigate iterative, agentic retrieval. [Review-table model research](https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute) |
| **Retrieval infrastructure** | A February 2025 engineering post identifies LanceDB Enterprise as the principal production vector database and PostgreSQL/pgvector for smaller public-data projects. A November 2026 post describes turbopuffer for **client-matter search**; that does not establish replacement of the document-retrieval stack. [RAG infrastructure](https://www.harvey.ai/blog/enterprise-grade-rag-systems), [Matter search](https://www.harvey.ai/blog/building-ethical-wall-enforcement-into-harvey) |
| **Legal retrieval** | Harvey evaluates retrieval separately from generation. Its legal datasets emphasize defined terms and cross-references in contracts, email metadata and threads, and jurisdiction and authority in legal research. Exact current chunking, embedding models, and ranking formulas remain undisclosed in these sources. [Retrieval evaluation](https://www.harvey.ai/blog/biglaw-bench-retrieval) |
| **Graph context** | **Harvey Graph** combines a per-Space context graph with a U.S. case-law knowledge graph. Agents can follow citations and case-treatment relationships. The October announcement places law-evolution tracking and firm-defined legal ontologies on the roadmap. [Harvey Graph](https://www.harvey.ai/blog/improving-agent-accuracy-with-harvey-graph) |
| **Licensed legal research** | Ask LexisNexis supplies answers through LexisNexis’s own tuned models and infrastructure, grounded in primary law and Shepard’s relationships. This is a partner research service inside Harvey, not merely documents copied into a generic vector store. [Alliance architecture](https://www.harvey.ai/blog/lexisnexis-harvey-strategic-alliance) |

### Products and document flow

| Product | Inputs → outputs |
|---|---|
| **Assistant / Threads** | Prompts, uploaded documents, and selected knowledge → analysis, summaries, drafts, and follow-up answers. Library resources supply reusable prompts, playbooks, templates, and workflows. [Product documentation](https://help.harvey.ai/articles/getting-started-with-harvey) |
| **Vault** | Document collections → search, bulk analysis, cited reports, and review tables. The current product page advertises storage of 100,000 files per vault; storage capacity should not be confused with a particular workflow’s processing limit. [Vault](https://www.harvey.ai/platform/vault) |
| **Review tables** | Questions become columns; documents or document groups become rows. Cells contain extracted or interpreted answers. Types include dates, currency, verbatim text, free response, and classification. [Typed extraction](https://www.harvey.ai/blog/introducing-the-next-version-of-vault), [Email-review example](https://www.harvey.ai/blog/harvey-in-practice-build-a-case-chronology-from-emails) |
| **Workflows / Agents** | Matter inputs plus reusable instructions and organizational standards → multi-step analysis and deliverables. Newer agents can modify review tables, group related documents, import metadata, assign reviewers, and turn tables into memos within one conversation. [Agent actions](https://www.harvey.ai/blog/review-table-agent-actions) |
| **Knowledge** | Public legal sources, licensed databases, SEC filings, web information, and institutional knowledge → grounded research. Listed partners include LexisNexis, Wolters Kluwer, FromCounsel, SCC Online, and others. [Knowledge](https://www.harvey.ai/platform/knowledge) |
| **Spaces and Memory** | Matter documents, people, permissions, history, and instructions provide shared context. User memory retains preferences and corrections and can be inspected, edited, or disabled. [Harvey II](https://www.harvey.ai/blog/introducing-harvey-ii) |
| **Contract Intelligence** | Incoming contracts, playbooks, precedents, and negotiation history → reviews, redlines, issue tracking, and portfolio insights. The November 12 version-history update points customers to early access. [Contract Intelligence](https://www.harvey.ai/platform/contract-intelligence), [Version-history update](https://www.harvey.ai/blog/close-contracts-faster-with-every-version-in-one-place) |
| **Horizon Scanning and Intake** | Horizon Scanning connects regulatory developments to relevant follow-up work. Intake captures and routes business requests; its November announcement describes early access. [Horizon Scanning](https://www.harvey.ai/platform/horizon-scanning), [FORUM announcements](https://www.harvey.ai/blog/forum-chicago-product-announcements) |
| **Facts & Chronologies / fact graph** | Announced November 5: extracts facts, links them to exact source lines, connects people, events, and issues, flags inconsistencies, and identifies outdated work product. Developed with design partners, including Slaughter and May; the announcement describes forthcoming early access. **This is the closest public overlap with Factoid.** [Fact-graph announcement](https://www.harvey.ai/blog/fact-graph-for-litigation-disputes-internal-investigations) |

The documented ingestion paths include uploads and DMS synchronization from iManage, SharePoint, and Google Drive. Processing includes OCR; visual questions can trigger page rendering and a vision model after text search identifies candidate pages. Results feed tables, conversations, and document deliverables. [Release notes](https://help.harvey.ai/release-notes), [OCR release](https://help.harvey.ai/release-notes/page/12), [Image-understanding architecture](https://www.harvey.ai/blog/building-image-understanding-for-legal-documents)

### Evaluation

- **BigLaw Bench:** realistic legal assignments with task-specific rubrics. It separates answer quality from sourcing quality and penalizes hallucinations and other failures. [BigLaw Bench](https://www.harvey.ai/blog/introducing-biglaw-bench)
- **Retrieval benchmark:** relevant evidence recovered within a fixed token budget, rather than answer quality alone. [Retrieval evaluation](https://www.harvey.ai/blog/biglaw-bench-retrieval)
- **Arena:** lawyer comparisons of paired outputs, with preference explanations and Elo scores. Preference and correctness are different signals. [Arena](https://www.harvey.ai/blog/introducing-biglaw-bench-arena)
- **Legal Agent Benchmark, or LAB:** more than 1,200 tasks across 24 practice areas, with over 75,000 expert-written criteria. Its strict “all-pass” measure requires every criterion to pass. [LAB](https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark)
- **Important limit:** initial May 2026 LAB results had tested frontier models completing fewer than 10% of tasks under that all-pass standard. This is a dated benchmark result, not Harvey’s current production failure rate. [Initial results](https://www.harvey.ai/blog/legal-agent-benchmark-initial-results)

## 2. Domain: users, tasks, and documents

Harvey serves law firms, in-house legal departments, and adjacent professional-services teams. Named customers include A&O Shearman, Dentons, Bridgewater, KKR, Deutsche Telekom, and PwC UK. [Customers](https://www.harvey.ai/customers)

| Work | Recurring documents and tasks |
|---|---|
| **M&A diligence** | Material customer and supplier contracts, merger agreements, stock purchase agreements, cap tables, board minutes, IP records, employment arrangements, and leases. Extract transfer restrictions, change-of-control terms, ownership issues, and closing risks. [Diligence](https://www.harvey.ai/blog/data-room-due-diligence) |
| **Commercial contracting** | MSAs, NDAs, order forms, SOWs, redlines, negotiation emails, and playbooks. Review risk allocation, propose edits, compare accepted terms, and track obligations. [Contract Intelligence](https://www.harvey.ai/platform/contract-intelligence), [Contracting benchmark](https://www.harvey.ai/blog/legal-agent-benchmark-in-house-contracting) |
| **Litigation and investigations** | Emails, pleadings, exhibits, correspondence, business records, and interview material. Build chronologies, identify witnesses, connect evidence to issues, and draft disclosures and arguments. [Email chronology](https://www.harvey.ai/blog/harvey-in-practice-build-a-case-chronology-from-emails), [Initial-disclosure workflow](https://www.harvey.ai/blog/rule-26-initial-disclosures) |
| **Regulatory and compliance** | Laws, guidance, notices, policies, evidence files, and remediation commitments. Monitor changes, assess applicability, reconstruct events, and prepare responses. [Horizon Scanning](https://www.harvey.ai/platform/horizon-scanning), [Regulatory responses](https://www.harvey.ai/blog/notice-of-violation-response) |
| **Employment and real estate** | Employment agreements, offer letters, restrictive covenants, severance provisions, leases, estoppel certificates, rent rolls, and title materials. Draft, compare, extract terms, and reconcile inconsistencies. [Employment](https://www.harvey.ai/blog/employment-contract-drafting), [Real estate](https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams) |

**Which dominate?** Public material does not provide a document-volume breakdown. **Inferred:** contracts dominate transactional extraction, emails dominate many discovery workflows, and cases/statutes dominate research. Harvey’s retrieval taxonomy supports that distinction, but not percentages. [Retrieval document families](https://www.harvey.ai/blog/biglaw-bench-retrieval)

A concrete customer example: Bridgewater reports using Harvey for bespoke trading agreements and vendor-contract reviews; Adecco describes contract review, policy drafting, cross-border research, and litigation strategy. These are customer/vendor accounts, not controlled productivity studies. [Customer examples](https://www.harvey.ai/blog/how-legal-teams-are-driving-real-results-with-ai)

## 3. How Harvey treats facts and extracted information

| Question | Documented behavior—and what remains unclear |
|---|---|
| **Structured facts or fields?** | Yes. Review tables provide configurable typed extraction; they can also produce interpretations rather than literal fields. The newer fact graph explicitly describes persistent, connected facts. Neither source publishes a Factoid-like requirement that every fact be one self-contained sentence. [Tables](https://www.harvey.ai/blog/introducing-the-next-version-of-vault), [Fact graph](https://www.harvey.ai/blog/fact-graph-for-litigation-disputes-internal-investigations) |
| **Source passages?** | Review tables moved from whole-cell citations and fuzzy matching to sentence-level citations referencing document indices. Answers and explanatory reasoning are separate. Verbatim columns preserve source wording. [Citation engineering](https://www.harvey.ai/blog/rebuilding-harveys-review-algorithm), [Verbatim extraction](https://www.harvey.ai/blog/introducing-the-next-version-of-vault) |
| **Missing information?** | The revised table system explains unsuccessful searches rather than returning only a dash. Specialized model training includes abstention examples. Public sources do not establish a platform-wide distinction among absent, unknown, inapplicable, and unprocessed. [Review algorithm](https://www.harvey.ai/blog/rebuilding-harveys-review-algorithm), [Training](https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute) |
| **Conflicting evidence?** | Harvey describes comparing rent rolls against leases and flagging conflicting accounts for attorney review. The fact graph promises inconsistency flags. I found no public conflict-resolution schema, precedence algorithm, or guarantee that contradictory assertions remain separately addressable. [Reconciliation](https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams), [Conflicting accounts](https://www.harvey.ai/blog/rule-26-initial-disclosures), [Fact graph](https://www.harvey.ai/blog/fact-graph-for-litigation-disputes-internal-investigations) |
| **Dates and effective periods?** | Typed dates, chronology sorting, renewals, and notice periods are documented. I found no published general model separating event time, effective time, observation time, and ingestion time. [Chronologies](https://www.harvey.ai/blog/harvey-in-practice-build-a-case-chronology-from-emails), [Contract dates](https://www.harvey.ai/platform/contract-intelligence) |
| **Jurisdiction and legal authority?** | Retrieval explicitly considers controlling jurisdiction and recency. LexisNexis provides Shepard’s-backed research; Harvey also describes its own case-law graph. A publicly specified “law applicable on date X” engine is not established by these materials. [Retrieval](https://www.harvey.ai/blog/biglaw-bench-retrieval), [LexisNexis](https://www.harvey.ai/blog/lexisnexis-harvey-strategic-alliance), [Graph](https://www.harvey.ai/blog/improving-agent-accuracy-with-harvey-graph) |
| **Document versions?** | The November Contract Intelligence update matches new drafts to existing contracts, retains prior rounds and related agreements, and considers previously accepted positions. That is stronger than isolated redline comparison; it does not disclose clause-level legal supersession rules. [Version history](https://www.harvey.ai/blog/close-contracts-faster-with-every-version-in-one-place) |
| **Privilege and confidentiality?** | Tables can classify material as attorney-client, work product, or not privileged and route it for review. Separately, ethical walls govern access to documents and derived conversations. Restrictions persist after an attachment is removed because earlier answers may contain its information. [Privilege review](https://www.harvey.ai/blog/review-table-agent-actions), [Wall enforcement](https://www.harvey.ai/blog/building-ethical-wall-enforcement-into-harvey) |
| **Training and retention?** | Harvey says customer content is not used for underlying-model training, requires model-provider zero retention, and offers configurable platform retention. Its security FAQ permits an exclusively customer-specific model when explicitly requested. Provider zero retention does **not** mean Vault stores nothing. [Security](https://www.harvey.ai/security) |

**Hallucination control needs careful reading.** Harvey’s October 2024 study reported 0.2% of response sentences containing hallucinations on a selected benchmark subset. Its definition excludes reasoning and comprehension errors; the result is neither a current universal rate nor 99.8% task accuracy. Its evaluation pipeline decomposes answers into claims, checks them against sources, and uses human review. [Hallucination methodology](https://www.harvey.ai/blog/biglaw-bench-hallucinations)

## 4. Traits for a legal Factoid project

### Proposed trait catalog

**All definitions below are inferred Factoid designs, not Harvey’s internal taxonomy.** “Harvey” identifies the source of the underlying task; “legal practice” identifies broader practice inspiration. Examples describe hypothetical documents or evidence, not legal advice.

**B** = Boolean classification is useful by itself.  
**V** = Boolean classification plus typed values or entity links.  
**R** = requires comparison, relationships, calculations, or external context.

#### M&A diligence

| Trait | One-line docstring | Example fact | Implementation; origin |
|---|---|---|---|
| `ChangeOfControl` | `"""Concerns a consequence triggered by a change in ownership or control."""` | Orion’s license terminates if a competitor acquires Orion. | **V:** trigger and consequence. Harvey: [Diligence](https://www.harvey.ai/blog/data-room-due-diligence). |
| `TransferRestriction` | `"""Restricts assignment, delegation, or transfer of an agreement or right."""` | Orion may not assign the supply agreement without Vega’s consent. | **V:** restricted act and exceptions. Harvey: [Diligence](https://www.harvey.ai/blog/data-room-due-diligence). |
| `ConsentRequired` | `"""Requires an identified person’s approval before a specified action."""` | Vega must approve the proposed assignment before closing. | **V:** approver, action, and timing. Harvey: [LAB diligence task](https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark). |
| `ClosingCondition` | `"""Makes completion of a transaction conditional on a requirement."""` | The acquisition may close only after the lender releases its security. | **V:** condition and satisfaction evidence. Legal practice; [Deal workflow](https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams). |
| `OwnershipEncumbrance` | `"""Concerns ownership or a third-party claim over an asset."""` | North Bank holds security over Orion’s patent portfolio. | **V:** asset, owner, and claimant. Harvey: [Diligence workstreams](https://www.harvey.ai/blog/data-room-due-diligence). |
| `Exclusivity` | `"""Limits a party’s ability to deal with alternative counterparties."""` | Orion must buy all regional packaging from Vega. | **V:** scope and duration. Harvey: [Diligence](https://www.harvey.ai/blog/data-room-due-diligence). |

#### Contract review and negotiation

| Trait | One-line docstring | Example fact | Implementation; origin |
|---|---|---|---|
| `PaymentTerm` | `"""Specifies a payment amount, calculation, trigger, or timing."""` | Orion must pay Vega $80,000 within 30 days after acceptance. | **V:** money and trigger. Legal practice; [Contract review](https://www.harvey.ai/blog/contract-review-process). |
| `LiabilityLimit` | `"""Limits or excludes liability for a specified category of loss."""` | Vega’s ordinary liability is capped at fees paid in the preceding year. | **V:** formula and carve-outs. Harvey: [Contracting benchmark](https://www.harvey.ai/blog/legal-agent-benchmark-in-house-contracting). |
| `Indemnity` | `"""Allocates responsibility for specified claims, losses, or defense costs."""` | Vega must defend Orion against third-party patent claims. | **V:** parties, claim scope, and exceptions. Harvey: [Contracting benchmark](https://www.harvey.ai/blog/legal-agent-benchmark-in-house-contracting). |
| `TerminationRight` | `"""Grants or limits a right to end an agreement."""` | Orion may terminate after an uncured material breach. | **V:** trigger, notice, and cure. Harvey: [Contract review](https://www.harvey.ai/blog/contract-review-process). |
| `AutoRenewal` | `"""Extends an agreement automatically unless a stated condition prevents renewal."""` | The services agreement renews yearly unless Orion gives 60 days’ notice. | **V/R:** renewal and notice calculation. Harvey: [Contract review](https://www.harvey.ai/blog/contract-review-process). |
| `ConfidentialityDuty` | `"""Requires protection or restricted use of specified information."""` | Vega must restrict access to Orion’s technical drawings. | **V:** information and permitted recipients. Legal practice; [Contract Intelligence](https://www.harvey.ai/platform/contract-intelligence). |
| `GoverningLaw` | `"""Identifies the law selected to govern an agreement or issue."""` | The supply agreement selects New York law. | **V:** jurisdiction entity. Legal practice; [CUAD](https://www.atticusprojectai.org/cuad/). |
| `PlaybookDeviation` | `"""States a departure from an identified approved negotiating position."""` | Counsel concluded that the uncapped indemnity exceeds Orion’s approved position. | **R:** versioned playbook and reviewer perspective. Harvey: [Contracting benchmark](https://www.harvey.ai/blog/legal-agent-benchmark-in-house-contracting). |

#### Litigation and discovery

| Trait | One-line docstring | Example fact | Implementation; origin |
|---|---|---|---|
| `IssueRelevant` | `"""Bears on an identified claim, defense, or investigation question."""` | Vega’s inspection log records the defect before shipment. | **R:** link to a defined issue. Harvey: [Discovery](https://www.harvey.ai/blog/legal-discovery-process). |
| `Admission` | `"""Records a person or party expressly acknowledging a proposition."""` | Vega admitted in its answer that delivery occurred on May 4. | **V:** speaker and admitted proposition. Legal practice; [Pleadings workflow](https://www.harvey.ai/blog/rule-26-initial-disclosures). |
| `Denial` | `"""Records a person or party expressly rejecting a proposition."""` | Vega denied receiving Orion’s termination notice. | **V:** speaker and denied proposition. Legal practice; [Pleadings workflow](https://www.harvey.ai/blog/rule-26-initial-disclosures). |
| `ContradictoryEvidence` | `"""Expressly identifies incompatible accounts of the same material proposition."""` | The receipt records May 4 delivery, while Vega’s answer states May 6. | **R:** two assertions and both sources. Harvey: [Conflict review](https://www.harvey.ai/blog/rule-26-initial-disclosures). |
| `WitnessKnowledge` | `"""Connects a person to information they may have observed or received."""` | Mira received the defect report before approving shipment. | **V:** person, information, and time. Inferred from [Fact graph](https://www.harvey.ai/blog/fact-graph-for-litigation-disputes-internal-investigations). |
| `Damages` | `"""Concerns a claimed loss, remedy amount, or damages calculation."""` | Orion’s ledger records $240,000 in replacement purchases. | **V/R:** amount, category, and calculation basis. Harvey: [Disclosures](https://www.harvey.ai/blog/rule-26-initial-disclosures). |
| `PreservationDuty` | `"""Requires retention of evidence or suspension of routine deletion."""` | Orion’s legal hold requires Mira to retain project messages. | **V:** custodians, scope, and release condition. Legal practice; [Discovery](https://www.harvey.ai/blog/legal-discovery-process). |

#### Regulatory and compliance

| Trait | One-line docstring | Example fact | Implementation; origin |
|---|---|---|---|
| `RegulatoryObligation` | `"""Requires an action under an identified regulatory authority."""` | Rule R requires licensed operators to retain inspection records. | **V:** authority, actor, and applicability. Inferred from [Horizon Scanning](https://www.harvey.ai/platform/horizon-scanning). |
| `ReportingDuty` | `"""Requires notification, disclosure, or filing with a specified recipient."""` | Rule R requires incident notice to the regulator within 72 hours. | **V/R:** recipient, trigger, and clock. Legal practice; [Regulatory workflow](https://www.harvey.ai/blog/notice-of-violation-response). |
| `Prohibition` | `"""Forbids a specified action within a defined scope."""` | Rule R prohibits exporting the listed material without a permit. | **V:** action and scope. Legal practice; [Knowledge](https://www.harvey.ai/platform/knowledge). |
| `Exemption` | `"""Creates an exception to an identified requirement or prohibition."""` | Rule R exempts operators with fewer than ten covered devices. | **V/R:** parent rule and qualifying conditions. Legal practice; [Knowledge](https://www.harvey.ai/platform/knowledge). |
| `EnforcementExposure` | `"""Concerns an alleged violation, sanction, or enforcement consequence."""` | The regulator’s notice alleges that Orion missed three inspections. | **V:** allegation, authority, and exposure. Harvey: [Regulatory response](https://www.harvey.ai/blog/notice-of-violation-response). |
| `RemediationCommitment` | `"""Commits an actor to correcting an identified deficiency."""` | Orion committed to replacing the inspection system by September 30. | **V:** owner, action, and due date. Harvey: [Regulatory response](https://www.harvey.ai/blog/notice-of-violation-response). |

#### Employment, investigations, and real estate

| Trait | One-line docstring | Example fact | Implementation; origin |
|---|---|---|---|
| `Compensation` | `"""Concerns salary, incentive pay, equity, or another employment benefit."""` | Mira’s agreement provides a $20,000 signing bonus. | **V:** amount and conditions. Harvey: [Employment](https://www.harvey.ai/blog/employment-contract-drafting). |
| `Severance` | `"""Provides compensation or benefits upon an employment separation."""` | Mira receives six months’ salary if terminated without cause. | **V/R:** trigger and formula. Harvey: [Employment](https://www.harvey.ai/blog/employment-contract-drafting). |
| `RestrictiveCovenant` | `"""Restricts post-employment competition, solicitation, or related conduct."""` | Mira’s agreement bars customer solicitation for twelve months after departure. | **V:** activity, territory, and duration. Harvey: [Employment](https://www.harvey.ai/blog/employment-contract-drafting). |
| `WorkplaceComplaint` | `"""Records a reported workplace grievance or allegation of misconduct."""` | Mira reported to HR that her manager altered her time records. | **B**, with speaker attribution retained. Legal practice; inferred from [Investigation workflow](https://www.harvey.ai/blog/notice-of-violation-response). |
| `RenewalOption` | `"""Grants a party an option to extend a lease or agreement."""` | Orion may extend the warehouse lease for five years. | **V/R:** option holder, exercise window, and conditions. Harvey: [Real estate](https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams). |
| `RentAdjustment` | `"""Changes rent according to a date, index, formula, or event."""` | Warehouse rent increases by 3% each January. | **V/R:** recurrence and formula. Legal practice; [Rent-roll reconciliation](https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams). |

#### Shared temporal traits

| Trait | One-line docstring | Example fact | Implementation; origin |
|---|---|---|---|
| `Deadline` | `"""Specifies the latest permitted time for an action."""` | Orion must deliver its objection within ten business days after receipt. | **V/R:** trigger, calendar, timezone, and exceptions. Harvey: [Contract review](https://www.harvey.ai/blog/contract-review-process). |
| `EffectivePeriod` | `"""Specifies when a provision or status begins or ends."""` | Amendment 2 changes the fee cap from January 1, 2027. | **V:** interval and affected provision. Legal practice; inferred from [Version handling](https://www.harvey.ai/blog/improving-agent-accuracy-with-harvey-graph). |
| `Survival` | `"""Keeps an obligation or right operative after another relationship ends."""` | The NDA’s confidentiality duty continues for three years after termination. | **V/R:** surviving provision and end condition. Harvey: [Contract review](https://www.harvey.ai/blog/contract-review-process). |

### What needs code, entities, or fact classes?

These are **inferred design recommendations**, motivated by Harvey’s typed tables, related-document grouping, and privilege controls. [Typed extraction](https://www.harvey.ai/blog/introducing-the-next-version-of-vault), [Grouping](https://www.harvey.ai/blog/review-table-agent-actions), [Privilege distinctions](https://www.harvey.ai/blog/rules-of-privilege-still-apply-when-lawyers-use-ai)

- **Keep traits Boolean; attach values separately.** `Deadline=True` should point to a date expression and calculation, not conceal them inside the label. Preserve the original wording alongside normalized dates, currencies, durations, percentages, and formulas.
- **Code should validate and calculate.** Use it for business-day arithmetic, renewal windows, monetary calculations, exact-quote verification, entity resolution, and document-version relationships. Legal applicability still needs evidence and review.
- **Cross-fact judgments need another pass.** A small model examining one sentence cannot discover contradictions elsewhere. Build `contradicts`, `supports`, `amends`, and `supersedes` relationships first; a trait can then make those findings filterable.
- **Use entities for identities.** Parties, people, courts, regulators, statutes, cases, contracts, clauses, assets, and jurisdictions belong in the entity layer. `GoverningLaw` is the relationship’s topic; “New York” is its value.
- **Use fact classes for evidence character.** A compact starting set is `SourceAssertion`, `OperativeInstrument`, and `LegalAssessment`. “Mira reported retaliation” belongs to the first; “the court found retaliation” has a different evidentiary basis.
- **Privilege is an independent protection dimension.** Prefer separate attorney-client/work-product designations, reviewer decisions, and access policy. A single privileged/not-privileged fact class loses overlapping protections and unknown status. A `PrivilegedLegalAssessment` class can be convenient, but must not be the security boundary.
- **Do not infer absence from a false trait.** “This fact is not about indemnity” says nothing about whether the contract contains indemnity. Missing-clause findings need a documented search scope and coverage record.

### Corpora that stress kinds and expiration

**Inferred:** legal facts need historical validity and supersession, not deletion when their present applicability ends. Harvey itself highlights changing law, contract versions, and evolving matter records, but does not publish an expiration system matching Factoid’s kinds. [Legal context](https://www.harvey.ai/blog/enterprise-grade-rag-systems), [Versions](https://www.harvey.ai/blog/close-contracts-faster-with-every-version-in-one-place)

| Stress corpus | Pressure on Factoid’s kinds |
|---|---|
| **Statutes, regulations, amendments, and transition provisions** | An enacted requirement with a future effective date is a **rule**, not a forecast. Track publication, enactment, applicability, repeal, and transitional populations separately. |
| **Executed contracts, amendments, side letters, and waivers** | An amendment can replace one **rule** while leaving others intact. A waiver may be temporary or transaction-specific. Document-level expiration is too coarse. |
| **Negotiation drafts and emails** | A proposed clause is a **plan** or negotiating position, not an operative rule. Acceptance is a **decision**; execution is an **event**; the resulting obligation is a **rule**. |
| **Court dockets and appellate histories** | A ruling is a historical **decision** even after reversal. Its present precedential force is a separate **state** or applicability relationship. |
| **Discovery, testimony, and corrected statements** | A witness’s statement is an **event**; what the witness alleges is a separately attributed proposition. Contradictory evidence should not erase either account. |
| **Leases and recurring obligations** | A renewal clause is a **rule**; the exercised option is an **event**; the current term is a **state**. Calculate each notice window independently. |
| **Employment and ownership histories** | Employment, directorship, and ownership are interval-bound **states**. Departure changes current status without invalidating past status. |
| **Deal forecasts and remediation plans** | “Management expects closing in June” is a **forecast**. “The board approved closing” is a **decision**. “Closing occurred” is an **event**. Passing June does not establish what happened. |
| **Allegedly permanent facts** | Reserve **fixed** for carefully scoped invariants, such as an immutable source identifier. A business fact is not fixed merely because its sentence lacks a date. |

The motivating document families appear in Harvey’s [contracting benchmark](https://www.harvey.ai/blog/legal-agent-benchmark-in-house-contracting), [employment analysis](https://www.harvey.ai/blog/employment-contract-drafting), [real-estate workflows](https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams), and [case-law graph](https://www.harvey.ai/blog/improving-agent-accuracy-with-harvey-graph).

**Inferred implementation:** retain `valid_from`, `valid_to`, `observed_at`, `recorded_at`, source version, and supersession links. Keep review freshness separate from truth validity. Split compound assertions when necessary so each fact still has exactly one kind.

## 5. What Factoid should learn from Harvey

### Worth copying

1. **Make verification the central interaction.** Put the sentence, exact quote, source location, and reviewer decision together. Harvey’s citation redesign directly addresses the cost of checking individual assertions. **Inferred:** immutable source snapshots and offset validation would strengthen Factoid’s version of this. [Citation engineering](https://www.harvey.ai/blog/rebuilding-harveys-review-algorithm)

2. **Offer review tables over reusable facts.** Lawyers need familiar columns, filters, assignments, and deliverables. **Inferred:** Factoid can generate those views from facts and traits while preserving a reusable evidence record underneath. [Agentic tables](https://www.harvey.ai/blog/review-table-agent-actions)

3. **Carry evidence relationships forward.** Harvey’s new fact graph makes persistence across tasks a product feature. **Inferred:** dependency links should let Factoid flag every assessment or report affected by corrected evidence. [Fact graph](https://www.harvey.ai/blog/fact-graph-for-litigation-disputes-internal-investigations)

4. **Apply permissions to derived information.** Harvey checks access before evidence reaches models and preserves restrictions on derived conversations. **Inferred:** facts, embeddings, summaries, caches, and exports should inherit source restrictions. [Ethical-wall engineering](https://www.harvey.ai/blog/building-ethical-wall-enforcement-into-harvey)

5. **Evaluate extraction, support, and complete work separately.** Use field-level recall, citation precision, contradiction handling, and end-to-end task criteria. **Inferred:** a correct sentence with the wrong quote should fail evidence verification even if a reader finds it plausible. [BigLaw Bench](https://www.harvey.ai/blog/introducing-biglaw-bench), [LAB](https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark)

### Publicly documented limits and lessons

- **Retrieval can omit necessary evidence.** Harvey’s single-turn review harness cannot fetch more information after receiving incomplete initial context. **Inferred:** allow targeted follow-up retrieval and expose coverage gaps. [Review-model research](https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute)
- **Text extraction loses evidence.** Harvey added on-demand vision because charts, signatures, handwriting, and layout can carry meaning missing from OCR. **Inferred:** Factoid needs visual evidence anchors or an explicit unsupported-content state. [Image understanding](https://www.harvey.ai/blog/building-image-understanding-for-legal-documents)
- **More citations can become citation spam.** Harvey explicitly penalizes irrelevant and invalid citations during training. **Inferred:** validate whether each quote supports the whole fact, including qualifiers and exceptions. [Citation reward design](https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute)
- **High average scores can hide incomplete work.** LAB’s initial results expose the gap between satisfying many criteria and completing an assignment. **Inferred:** test missing critical facts and exceptions, not only average trait accuracy. [LAB results](https://www.harvey.ai/blog/legal-agent-benchmark-initial-results)
- **Human review remains part of the operating model.** Gabe Pereyra describes Harvey’s role through the partner–associate analogy: work is checked before reaching clients. [Founder interview](https://www.adr.org/podcasts/ai-and-the-future-of-law/harvey-s-gabe-pereyra-on-the-future-of-legal-ai/)

**Inferred priority for Factoid:** build exact evidence anchoring, attributed assertions, temporal applicability, and derived-data permissions before expanding the trait catalog. Harvey’s public material validates demand for connected facts; it leaves the detailed semantics of those facts largely unspecified.

## Sources

Every source cited above is listed below. Research announcements, product descriptions, customer accounts, and benchmark results have been distinguished in the text.

1. Multi-model architecture  
https://www.harvey.ai/blog/why-harvey-is-multi-model-by-design

2. OpenAI’s Harvey case study  
https://openai.com/index/harvey/

3. Harvey Tenet research preview  
https://www.harvey.ai/blog/post-training-update-harvey-tenet

4. Specialized review-table models  
https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute

5. RAG infrastructure  
https://www.harvey.ai/blog/enterprise-grade-rag-systems

6. Ethical-wall enforcement  
https://www.harvey.ai/blog/building-ethical-wall-enforcement-into-harvey

7. Retrieval evaluation  
https://www.harvey.ai/blog/biglaw-bench-retrieval

8. Harvey Graph  
https://www.harvey.ai/blog/improving-agent-accuracy-with-harvey-graph

9. LexisNexis alliance  
https://www.harvey.ai/blog/lexisnexis-harvey-strategic-alliance

10. Product documentation  
https://help.harvey.ai/articles/getting-started-with-harvey

11. Vault  
https://www.harvey.ai/platform/vault

12. Typed review tables  
https://www.harvey.ai/blog/introducing-the-next-version-of-vault

13. Email chronologies  
https://www.harvey.ai/blog/harvey-in-practice-build-a-case-chronology-from-emails

14. Review-table agent actions  
https://www.harvey.ai/blog/review-table-agent-actions

15. Knowledge  
https://www.harvey.ai/platform/knowledge

16. Harvey II  
https://www.harvey.ai/blog/introducing-harvey-ii

17. Contract Intelligence  
https://www.harvey.ai/platform/contract-intelligence

18. Contract version history  
https://www.harvey.ai/blog/close-contracts-faster-with-every-version-in-one-place

19. Horizon Scanning  
https://www.harvey.ai/platform/horizon-scanning

20. FORUM product announcements  
https://www.harvey.ai/blog/forum-chicago-product-announcements

21. Fact-graph announcement  
https://www.harvey.ai/blog/fact-graph-for-litigation-disputes-internal-investigations

22. Current release notes  
https://help.harvey.ai/release-notes

23. Historical release notes, including OCR and review verification  
https://help.harvey.ai/release-notes/page/12

24. Image-understanding architecture  
https://www.harvey.ai/blog/building-image-understanding-for-legal-documents

25. BigLaw Bench  
https://www.harvey.ai/blog/introducing-biglaw-bench

26. BigLaw Bench: Arena  
https://www.harvey.ai/blog/introducing-biglaw-bench-arena

27. Legal Agent Benchmark  
https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark

28. Initial LAB results  
https://www.harvey.ai/blog/legal-agent-benchmark-initial-results

29. Customers  
https://www.harvey.ai/customers

30. M&A diligence  
https://www.harvey.ai/blog/data-room-due-diligence

31. Contracting benchmark  
https://www.harvey.ai/blog/legal-agent-benchmark-in-house-contracting

32. Initial-disclosure workflow  
https://www.harvey.ai/blog/rule-26-initial-disclosures

33. Regulatory response workflow  
https://www.harvey.ai/blog/notice-of-violation-response

34. Employment contracts  
https://www.harvey.ai/blog/employment-contract-drafting

35. Real-estate workflows  
https://www.harvey.ai/blog/harvey-in-practice-real-estate-teams

36. In-house customer examples  
https://www.harvey.ai/blog/how-legal-teams-are-driving-real-results-with-ai

37. Review-algorithm and citation redesign  
https://www.harvey.ai/blog/rebuilding-harveys-review-algorithm

38. Security and customer-data policies  
https://www.harvey.ai/security

39. Hallucination methodology  
https://www.harvey.ai/blog/biglaw-bench-hallucinations

40. Contract-review practice  
https://www.harvey.ai/blog/contract-review-process

41. CUAD, The Atticus Project  
https://www.atticusprojectai.org/cuad/

42. Discovery workflow  
https://www.harvey.ai/blog/legal-discovery-process

43. Privilege and work product  
https://www.harvey.ai/blog/rules-of-privilege-still-apply-when-lawyers-use-ai

44. Gabe Pereyra interview, American Arbitration Association  
https://www.adr.org/podcasts/ai-and-the-future-of-law/harvey-s-gabe-pereyra-on-the-future-of-legal-ai/