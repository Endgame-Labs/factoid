# factoid-legal

Legal due diligence on [Factoid](../factoid): contracts, amendments, and counsel emails in; facts with legal traits,
linked to companies, agreements, and people, out. It is the first app built on Factoid, and it drives what the
framework needs.

## Layout

```text
legal/
├── settings.py    # models: Jev for decisions, GLM 5.3 Flash for extraction, Qwen3 for embeddings
├── documents.py   # Contract and CounselEmail
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

First full run of all three suites, with Jev, GLM 5.3 Flash, Qwen3 embeddings, and the Qwen3 reranker.

| Suite | Result |
| --- | --- |
| diligence (sample deal) | 12 of 12 checks pass |
| CUAD, first 20 test contracts | clause recall 0.97, precision 0.69, F1 0.81, mean AUPR 0.95 |
| | gold clauses quoted by a kept fact (coverage) 0.92; quoted by a fact with the right trait 0.78 |
| | dates in the right year: agreement date 0.83, effective date 0.79, expiration date 0.44 |
| amendments (3 real chains) | supersessions found 2 of 2; untouched clauses kept 3 of 4; false changes 4.9% |
| | as-of search 1 of 3; dated windows 1 of 2 |

Cost on CUAD: about 630 model calls and 1.1M tokens per contract, 84 seconds per contract at the median. Most calls
are decisions (Jev).

Known gaps: precision of clause detection (more facts means more false traits), expiration dates, false
contradictions between facts of one contract, and as-of ranking after more than one amendment.
