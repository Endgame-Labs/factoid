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
| CUAD clause detection (F1, mean AUPR) | 0.81, 0.97 | 0.83, 0.96 | 0.81, 0.95 |
| CUAD gold clauses quoted by a kept fact | 0.97 | 0.93 | 0.93 |
| CUAD dates: agreement, effective, expiration | 17/18, 13/14, 8/9 | 15/18, 9/12, 5/5 | 17/18, 7/7, 1/2 |

| Amendment chains | NETGEAR, Federated, BioAmber | NEON Systems |
| --- | --- | --- |
| Supersessions found | 2/2 | 2/2 |
| Untouched clauses kept | 4/4 | 0/1 |
| As-of search | 3/3 | 2/2 |
| Dated windows | 2/2 | none labeled |

The sample deal (diligence suite) passes 12 of 12.

NEON's restructured payment clause (Sections 3.1 and 3.2 "amended to read in their entirety") is now retired by the
amendment's new Section 3.2, through the framework's replaced-sections step. Its one failing check is recall, not a
false change: the authority representation ("all requisite power and authority ... and duly executed") is extracted
as one compound sentence, and the repair does not split it, so it is rejected as not atomic. The four other Licensee
representations next to it are kept and current. Most of NEON's 8% "false changes" are real changes to Sections 2.x,
3.x, 14.1, 13.1, and 15.2 that the gold labels do not list.

Cost on CUAD: about 700 model calls and 1M tokens per contract, 60 to 95 seconds per contract at the median.
