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

Jev for decisions, GLM 5.3 Flash for extraction, Qwen3 embeddings, and the Qwen3 reranker. Floors, thresholds, and
prompts were tuned while looking at CUAD contracts 1 to 20 and the NETGEAR, Federated, and BioAmber chains. CUAD
contracts 21 to 40 and the NEON Systems chain were held out: scored once, after tuning, with nothing changed for them.

| Suite | Tuning set | Held out |
| --- | --- | --- |
| CUAD clause detection (F1, mean AUPR) | 0.82, 0.97 | 0.85, 0.96 |
| CUAD gold clauses quoted by a kept fact | 0.95 | 0.93 |
| CUAD gold clauses quoted by a fact with the right trait | 0.82 | 0.84 |
| CUAD dates in the right year: agreement, effective, expiration | 16/18, 12/14, 8/9 | 16/18, 10/12, 5/5 |
| Amendments: supersessions found | 2/2 | 1/2 |
| Amendments: untouched clauses kept | 4/4 | 0/1 |
| Amendments: as-of search | 3/3 | 2/2 |
| Amendments: false changes to base facts | 3.4% | 6.0% |
| Sample deal (diligence) | 12/12 | |

The one tuning-set expiration miss is a term defined by reference to another agreement (the Sales Dealer
Agreement). On the held-out chain, the missed supersession is a payment clause the amendment restructured (120 days
after invoice became royalty advances with 60 days after invoice for the excess), and the untouched clause is a
boilerplate representation that was never kept as a fact.

Cost on CUAD: about 700 model calls and 1M tokens per contract, 60 to 85 seconds per contract at the median.

Open: clause-detection precision (0.70 and 0.75), restructured clauses in amendments, and the size of the amendment
suites (5 chains in all), which is too small to measure supersession precisely.
