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

The sample deal (diligence suite) passes 12 of 12.

The fresh chains were labeled from the contract text before any run (commit "Fresh amendment suite") and scored
once. They are the honest measure for amendments. Their misses: a base clause never kept as a fact (ScanSource's
inventory claim window), a section deleted and replaced with fully redacted text (PC Quote), and one as-of question.

Two choices made while looking at NEON were tested on the fresh chains and turned off: retiring the facts of a section
an amendment rewrites in its entirety (no gain, and more false changes) and a lower "useful" floor (no effect). See
SPEC section 17 in the framework.

Cost on CUAD: about 700 model calls and 1M tokens per contract, 60 to 95 seconds per contract at the median.
