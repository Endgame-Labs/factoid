# factoid-legal

Legal due diligence on [Factoid](https://github.com/Endgame-Labs/factoid): contracts, amendments, and counsel emails in; facts with legal traits,
linked to companies, agreements, and people, out. It is the first app built on Factoid, and it drives what the
framework needs.

## Layout

```text
legal/
├── settings.py    # models: Jev for decisions, GLM 5.3 Flash for extraction, Qwen3 for embeddings
├── documents.py   # Contract, CounselEmail, and ContractRegister (the data room's CSV)
├── entities.py    # Company, Agreement, and Person
└── facts.py       # legal traits, SourceFact, and CounselFact
evals/
├── cuad.py        # CUAD test split: clause traits and contract dates
├── amendments.py  # real CUAD contract chains: supersession, as-of search, and time
└── diligence.py   # the README's Orion and Vega deal, end to end
sample_docs/       # the made-up Orion and Vega deal
```

## Running it

```sh
uv sync
factoid doctor
factoid ingest sample_docs                # classify, extract, judge, link, and resolve
factoid search "Vega liability cap" --as-of 2027-02-01T00:00:00Z
factoid eval diligence
factoid eval cuad --limit 10              # CUAD downloads to data/ on first use
factoid eval amendments
factoid eval cuad --limit 10 --vary "fact_evals=default,none"
```

Runs replay model calls from `.factoid/calls.db`, so a re-run of the same pipeline costs nothing. Scorecards are in
`runs/`.

## Data

CUAD, the Contract Understanding Atticus Dataset, is CC BY 4.0: https://www.atticusprojectai.org/cuad. The scorers in
`evals/` are our own. The documents in `sample_docs/` are made up.

## Results (2026-11-15)

Jev for decisions, GLM 5.3 Flash for extraction, Qwen3 embeddings, and the Qwen3 reranker. Floors, thresholds, and
prompts were tuned while looking at CUAD contracts 1 to 20 and the NETGEAR, Federated, and BioAmber chains. CUAD
contracts 21 to 40 were held out and scored after tuning; contracts 41 to 60 were first scored after the last change
to floors and prompts. The NEON Systems chain was held out at first, then looked at to diagnose its misses, so it is
no longer a clean held-out set.

| Suite | Tuning set | Held out (21 to 40) | Fresh (41 to 60) |
| --- | --- | --- | --- |
| CUAD clause detection (F1, mean AUPR) | 0.82, 0.97 | 0.84, 0.97 | 0.81, 0.95 |
| CUAD gold clauses quoted by a kept fact | 0.97 | 0.92 | 0.97 |
| CUAD gold clauses quoted by a fact with the right trait | 0.83 | 0.82 | 0.83 |
| CUAD dates: agreement, effective, expiration | 16/18, 12/14, 8/9 | 16/18, 10/12, 5/5 | 17/18, 7/7, 2/2 |

| Amendment chains | Tuning (NETGEAR, Federated, BioAmber) | NEON (looked at) | Fresh (Glu, ScanSource, PC Quote) |
| --- | --- | --- | --- |
| Supersessions found | 2/2 | 1/2 | 2/4 |
| Untouched clauses kept | 4/4 | 1/1 | 2/2 |
| As-of search | 3/3 | 2/2 | 3/4 |
| Dated windows | 2/2 | none labeled | 2/2 |
| False changes to base facts | 3.1% | 5.1% | 2.5% |

The sample deal (diligence suite) passes 15 of 15, including the data room's contract register, a CSV read as a
structured document.

| SEC chains (Tyson, Furniture Brands, Life Sciences Research) | Result, scored once |
| --- | --- |
| Supersessions found | 4/4 |
| Untouched clauses kept | 2/2 |
| As-of search | 6/6 |
| Dated windows | 0/1 |
| False changes to base facts | 1.4% |

The SEC chains are credit agreements from public EDGAR exhibits (the MIT-licensed SEC_Exhibit_10 dataset), labeled
from the text in commit cfd823f before any run, and kept out of every tuning step.

The fresh chains were labeled from the contract text before any run (commit "Fresh amendment suite") and scored
once. They are the honest measure for amendments. Their misses: a base clause never kept as a fact (ScanSource's
inventory claim window), a section deleted and replaced with fully redacted text (PC Quote), and one as-of question.

Two choices made while looking at NEON were tested on the fresh chains and turned off: retiring the facts of a section
an amendment rewrites in its entirety (no gain, and more false changes) and a lower "useful" floor (no effect). See
SPEC section 17 in the framework.

## Against plain RAG (2026-11-16)

The as-of questions in every chain ("When does the Cisco and ScanSource distributor agreement end?" on a date) are
answered twice by the same reader (GLM 5.3 Flash) with the same prompt and budget, and graded by the same judge (Kimi
K3.1 Pro): once from Factoid's facts (`search_facts` with `as_of`), and once from plain RAG. The plain RAG baseline
is hybrid search (BM25 and embeddings) over 2,000-character windows of the documents signed by that date, each shown
with its signing date. The code is `evals/qa.py`; it runs with every amendment suite.

There are 36 questions. The first 17 were written with the chains; 19 more (commit e38c201) were labeled from the
text before any run, including five paraphrases that avoid the contract's own words.

| Questions answered with the terms in force | Facts, 2k tokens | Facts, 8k tokens | Chunks, 2k tokens | Chunks, 8k tokens |
| --- | --- | --- | --- | --- |
| Held out: fresh, NEON, and SEC chains (28) | 25 | 26 | 16 | 26 |
| Tuning and dev chains (8) | 8 | 8 | 4 | 7 |
| All (36) | 33 | 34 | 20 | 33 |
| Answered with the outdated terms | 1 | 1 | 4 | 2 |

Facts win at the small budget, where chunks have room for about four windows and often miss the clause. At 8k tokens
chunks catch up, 33 against 34, and still give outdated terms more often. The 17 first questions overstated the 8k gap
(16 against 15). These numbers are after two search changes of 2026-11-16 (a wider rerank pool, and full validity for a
replaced fact until it was replaced; see SPEC section 17).

The two outdated fact answers:

- A fact that names its document only by a short name: "the Borrowers have no right to prepay the Term Loan ... on or
  prior to July 31, 2008" under "the Financing Agreement as amended" never says Life Sciences Research, so a
  paraphrased question finds the base clause it replaced instead (SPEC decision 71).
- A reader mistake: asked about NEON's payment terms in June 1997, the reader answered with the 1999 amendment's 60
  days, though the fact it read says it is in force from 1999.

Other misses: a detail dropped in extraction (Glu's notice fact leaves out "Attention: Paul Zuzelo", and the fact
naming the Fox party says only "Fox"), and judge noise on terse answers.

The judge sees 800 characters around each labeled clause. At 300 it could not see that NEON's payment terms step from
120 to 90 days in the next sentence, and graded right answers wrong.

After the fixes of 2026-11-16 (linking, claim indexing, and repair context; see SPEC section 17), the fresh chains
find 3 of 4 supersessions (was 2 of 4), and a new dev chain of term extensions (`extensions_dev`, Navistar) finds 4
of 4.

## After the fact eval tuning (2026-11-17)

On 2026-11-17, framework fact evals and prompts changed (SPEC decisions 73 to 76). They were tuned on news transcripts
(the iscrag app), and this app was re-run to check that contracts did not get worse. Nothing here changed. Fact evals
and repair now see the 1,200 characters before each quote. The self-contained question is strict about pronouns, unclear
descriptions, and relative dates. Facts below target get one repair and keep their wording if it does not help. The
extract prompt asks the extractor to resolve references and relative dates.

During tuning, an extract prompt line against repeating the document's date stopped facts like "The Sponsorship
Agreement is dated July 16, 2012." CUAD agreement dates fell to 13 of 18. Rewording it brought them back to 16 of 18.

| Suite | Before (2026-11-16) | After (2026-11-17) |
| --- | --- | --- |
| Sample deal checks | 15/15 | 15/15 |
| CUAD 1 to 20: clause detection (F1, mean AUPR) | 0.80, 0.97 | 0.80, 0.96 |
| CUAD 1 to 20: gold clauses quoted by a kept fact | 0.97 | 0.96 |
| CUAD 1 to 20: gold clauses quoted by a fact with the right trait | 0.83 | 0.84 |
| CUAD 1 to 20: dates (agreement, effective, expiration) | 16/18, 12/14, 8/9 | 16/18, 13/14, 8/9 |
| Amendment supersessions found (all chains) | 15/16 | 12/16 |
| Amendment as-of search (all chains) | 35/36 | 32/36 |
| False changes to base facts (tuning, NEON, fresh, SEC) | 3.3%, 6.8%, 3.4%, 1.4% | 2.1%, 5.9%, 3.5%, 1.2% |

Amendment numbers move by one or two between runs of the same code. Treat a difference of one as noise. This run missed
two supersessions that passed in the run before it: the ScanSource term extension (both facts were kept, and resolve did
not connect them) and a Tyson leverage ratio replaced by a schedule of ratios (SPEC decision 69).

| Questions answered with the terms in force (36) | Facts, 2k tokens | Facts, 8k tokens | Chunks, 2k tokens | Chunks, 8k tokens |
| --- | --- | --- | --- | --- |
| Before (2026-11-16) | 33 | 34 | 20 | 33 |
| After (2026-11-17) | 34 | 33 | 20 | 35 |
| Answered with the outdated terms, after | 0 | 2 | 4 | 0 |

The two outdated fact answers at 8k are reader mistakes. With more facts in view, the reader picked a later amendment's
terms for an earlier date (Glu's Fox party in 2005 and ScanSource's returns in 2008).

After tuning, CUAD 1 to 20 (20 contracts) produced 4,200 facts and 450 entities. It took 19 minutes, 17,715 model calls,
and 29.8 million tokens.

## Facts and entities

Counts and samples come from `factoid stats --examples 3` on two eval runs.

The sample deal (`factoid eval diligence`) has 4 documents: 2 `Contract`, 1 `CounselEmail`, and 1 `ContractRegister`.
This run has 11 entities and 22 facts, with 21 current and 1 superseded (the old liability cap).

| Entities | Count | Most facts |
| --- | --- | --- |
| Company | 5 | Vega Components Corp. (20), Orion Robotics, Inc. (15) |
| Agreement | 3 | Supply Agreement between Orion and Vega (18), Amendment 2 to the Supply Agreement between Orion and Vega (2) |
| Person | 2 | Dana Whitfield (6), Sam Ortiz (1) |
| Untyped | 1 | State of Delaware (1) |

- `SourceFact`: "Under the Supply Agreement between Orion and Vega, as amended by Amendment 2, from January 1, 2027, Vega Components Corp.'s total liability to Orion Robotics, Inc. under the Supply Agreement will not exceed $2,000,000."
- `SourceFact`, from a text cell of the contract register: "Vega Components Corp. has asked to reprice servo motors from April 1, 2027 under the Supply Agreement between Orion and Vega."
- `CounselFact`: "Dana Whitfield stated that Hallbrook Law's view is that Vega's consent is a closing risk for the Acme deal, because the Vega supply agreement covers most of Orion's motors."

The run on CUAD contracts 1 to 20 (`factoid eval cuad --limit 20`) covers 20 contracts, 3,884 facts, and 480 entities.
Of the facts, 3,859 are current, 23 are contradicted, 4 are corrected, and 2 are superseded.

| Entities | Count | Most facts |
| --- | --- | --- |
| Untyped | 211 | Guidelines for Administration of Service Receivables ECP-UTE-G-008 (134), Roundup Products (91), Steering Committee (51) |
| Company | 137 | Monsanto Company (584), Soupman, Inc. (439), Qualigen, Inc. (436) |
| Agreement | 72 | Supply Agreement (383), Distribution and Development Agreement (352), Transportation Contract No. VIT-005-2012 (295) |
| Person | 60 | Kathy Ireland (119), Brett Ogle (41), Brett Shockley (6) |

- "Under the Endorsement Agreement, the license granted by Kathy Ireland, Inc. to Diplomat extends worldwide."
- "Under the Web Site Hosting Agreement between Centrack International and i-on interactive, the Customer must pay the recurring monthly fees by the 5th day of each month beginning April 1, 1999."
- "Under the Joint Venture Agreement, Pivotal Self Service Tech, Inc. must provision any additional Products deemed by the Joint Venturers to be salable through the channels established by CCGI."

Agreements with only a short name, such as "Supply Agreement" (383 facts), are the known limit in SPEC decision 71.
Facts from different contracts can share these agreements.

Cost on CUAD: about 700 model calls and 1M tokens per contract, 60 to 95 seconds per contract at the median.
