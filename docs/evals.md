# Evals: how algorithms get chosen

Factoid does not ask you to guess whether NLI beats a JEV judge, or whether 10 KB windows lose facts. It measures.
This doc is the contract for that measurement.

## Three nouns

- A **suite** is documents plus gold: what a careful reader says about them.
- A **run** is one pipeline over one suite. It produces a scorecard, and it keeps every event and every model call.
- A **comparison** is several runs over the same suite, with the differences tested for significance and listed item by item.

## A suite

```text
evals/acme-calls/
  suite.yml
  corpus/            # Documents, as files or documents.jsonl
  candidates.jsonl   # labeled candidate facts: keep, reject, or borderline, with a reason
  pairs.jsonl        # labeled fact pairs: duplicate, supersedes, contradicts, or unrelated
  doctypes.jsonl     # document id and its true type
  questions.jsonl    # questions with reference answers and the documents that hold the evidence
```

Every gold file is optional. A suite with only `questions.jsonl` still scores the whole pipeline end to end, and a suite
with only `candidates.jsonl` scores extraction and judging. Suites can be imported from public benchmarks
(`factoid eval import mediasumqa`, `enronqa`, `isc-rag`) and from your own data.

```jsonl
{"doc": "call:991", "text": "BetterUp's enablement team onboards in batches with a set curriculum.", "label": "keep"}
{"doc": "call:991", "text": "The call was titled Q3 review.", "label": "reject", "reason": "metadata"}
```

```jsonl
{"q": "What renewal price did Acme agree to?", "a": "$115K, conditional on legal sign-off", "evidence": ["email:CAF8x2"]}
```

## What a run measures

Each stage is scored on its own, so a comparison shows *where* a pipeline wins.

| Layer | Metric | Needs |
| --- | --- | --- |
| classify | accuracy and confusion matrix of document types; calibration | `doctypes.jsonl` |
| extract | recall of `keep` facts (a candidate matches when a judge says it states the same claim); facts per 10 KB; quote validity (always 100% by construction, checked anyway) | `candidates.jsonl` |
| judge | precision and recall of acceptance against labels; per-criterion calibration (ECE); the threshold that would maximize F1 | `candidates.jsonl` |
| resolve | precision and recall of duplicate, supersede, and contradict decisions | `pairs.jsonl` |
| retrieve | recall@k and MRR of the gold evidence, at the token budget | `questions.jsonl` |
| answer | accuracy of a fixed reader model answering from the retrieved facts at the budget, scored by string metrics and by a judge, reported separately | `questions.jsonl` |
| cost | dollars and tokens per document and per question, by stage | always |
| latency | p50 and p95 per document and per query, by stage | always |

The **reader** used by `answer` is part of the suite, not the pipeline, so pipelines are compared on equal terms.

## A scorecard

```text
run r_7d2  acme-calls  pipeline p_3fa9  2026-11-13 18:04
                          value      vs r_6c1   (p, Holm)
extract  keep recall      0.91       +0.04      0.03
judge    precision        0.96       −0.01      0.61
judge    recall           0.89       +0.07      0.004
resolve  dup F1           0.84       new
answer   accuracy @2k     0.852      +0.031     0.02
cost     $/doc            0.0021     +18%
latency  p95/doc          41s        +6s
```

## Replay: why runs are cheap

Every model call is archived, keyed by its exact request. A run that changes only the judge gets the extraction from the
archive at no cost, and a run that changes only the index re-derives nothing at all. `--vary` builds the runs of a matrix
and runs only the stages that differ. A run with `--offline` refuses any call that is not in the archive, so a
comparison can be reproduced exactly.

## Labeling

Gold is the scarce part, so Factoid helps make it:

- `factoid eval label` shows candidates one at a time, with the quote and its context. You press `k`, `r`, or `b`.
- It shows the items where runs **disagree** first, because those labels move the comparison most.
- Rejected candidates are in the log, so labels can come from real traffic, not only from suites.

## Adopting a result

A default changes only with a checked-in comparison that shows the new choice is better on the shipped suites, or no
worse at lower cost. `factoid defaults --why` lists each default with the run that chose it. Your own project can
follow the same rule with `factoid eval adopt <run>`, which writes the winning settings into `factoid.yml` with a
comment citing the run.
