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

Jev for decisions, GLM 5.3 Flash for extraction, Qwen3 embeddings, and the Qwen3 reranker.

| Suite | Result |
| --- | --- |
| diligence (sample deal) | 12 of 12 checks pass |
| CUAD, first 20 test contracts | clause recall 1.0, precision 0.68, F1 0.81, mean AUPR 0.97 |
| | gold clauses quoted by a kept fact (coverage) 0.96; quoted by a fact with the right trait 0.83 |
| | dates in the right year: agreement date 0.89, effective date 0.86, expiration date 0.67 |
| amendments (3 real chains) | supersessions 2 of 2; untouched clauses kept 4 of 4; as-of search 3 of 3; dated windows 2 of 2 |
| | false changes to base-agreement facts 2.5% |

Cost on CUAD: about 700 model calls and 1M tokens per contract, 62 seconds per contract at the median. Most calls
are decisions (Jev).

Open: precision of clause detection (a fact about a nearby clause can carry the trait), and expiration dates that are
defined by reference to another document.
