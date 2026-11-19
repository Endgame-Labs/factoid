# iscrag

This is the held-out benchmark from "RAG Deserves an Index" ([arXiv 2608.20845](https://arxiv.org/abs/2608.20845)),
rerun with Factoid in place of the original ISC pipeline. It uses 500 MediaSum transcripts and 499 questions, keeping
the paper's answer prompt, judge prompt, source rendering, and token budgets. The `dev` suite is the paper's
100-transcript development sample (200 questions), used for tuning. The `heldout` suite is the held-out 500.

## Running it

```sh
uv sync
factoid eval dev        # 100 transcripts, 200 questions, read at 512, 2,048, and 8,192 tokens
factoid eval heldout    # 500 transcripts, 499 questions, read at seven budgets from 256 to 16,384 tokens
```

The data goes in `data/` and stays out of git. MediaSum (`data/mediasum/test.json`) is research-use only and must not
be redistributed. The questions (`data/dev/` and `data/heldout-500-questions.jsonl`) come from the ISC-RAG study
database.

## Results on the development sample (2026-11-17)

The same reader (GLM 5.3 Flash) answers each question twice, and the same judge (Kimi K3.1 Pro) grades both answers.
One answer comes from Factoid's facts. The other comes from Factoid's chunks of the same transcripts (4,000
characters with 400 characters of overlap, like the paper's fixed chunks). The paper's reader and judge are retired,
so its numbers are a reference, not a head-to-head.

| Read budget | Facts | Chunks | Only facts right | Only chunks right | McNemar p |
| --- | --- | --- | --- | --- | --- |
| 512 tokens | 0.925 | 0.57 | 76 | 5 | < 0.001 |
| 2,048 tokens | 0.965 | 0.87 | 26 | 7 | 0.001 |
| 8,192 tokens | 0.955 | 0.945 | 11 | 9 | 0.82 |

By question type at 2,048 tokens, facts score 0.95 against 0.775 on pronoun coreference, 0.975 against 0.85 on direct
control, 0.975 against 0.825 on attribution, 0.95 against 0.95 on decontextualization, and 0.975 against 0.95 on
opinion, belief, and judgment (up from 0.8 before tuning).

This run is after tuning the fact evals and prompts on the first 30 transcripts of this sample (see the framework's
SPEC, decisions 73 to 76). The other 70 were not looked at while tuning. Before tuning (2026-11-16), facts scored
0.885, 0.915, and 0.92 at the same budgets. Chunks scored the same both times, within one question. Three things
changed. The fact evals and repair now see the transcript text just before each quote. The self-contained question is
strict about pronouns, unclear descriptions ("the case"), and relative dates, and a fact below its target now gets one
repair (previously it was dropped). The app also gives the extractor a roster that maps short speaker tags ("VAUSE")
to full names.

The run took 16 minutes and used 35,644 model calls (16,538 replayed from cache) and 34.8 million tokens, up from 21.0
million tokens before tuning. A run with nothing replayed uses about 40 million. The repairs account for most of the increase. These are still development numbers; the
held-out 500 has not been run.

## Tuning and unseen transcripts (2026-11-19)

The development numbers above pool two groups: the first 30 transcripts, used to tune the fact evals and prompts, and
the other 70, which were not looked at. The rerun on 0.1.6 scores them separately.

| Read budget | Facts, 30 tuning | Facts, 70 unseen | Chunks, 30 tuning | Chunks, 70 unseen |
| --- | --- | --- | --- | --- |
| 512 tokens | 0.90 | 0.93 | 0.55 | 0.58 |
| 2,048 tokens | 0.95 | 0.95 | 0.88 | 0.86 |
| 8,192 tokens | 0.95 | 0.96 | 0.95 | 0.94 |

The unseen transcripts score as well as the tuning set, so the tuning did not fit itself to the 30. Across all 200
questions, facts score 0.92, 0.95, and 0.955; chunks score 0.57, 0.87, and 0.945. Neither arm uses a reranker here. The
held-out 500 has not been run yet. The scorecard is in `scorecards/`. It leaves out the rejected fact samples, which
quote MediaSum.

## Facts and entities

The run above (`factoid stats --examples 3`) produced 6,676 facts (6,611 current, 56 contradicted, 6 superseded, 2
corrected, and 1 ended) and 1,603 entities across 100 transcripts. The app declares no entity classes, so every entity
is untyped. The entities with the most facts are Donald Trump (820), Theresa May (150), and Carol Costello (147).

- "Melinda Duckett, the mother of missing two-year-old Trenton Duckett, said that she and others had already gone out
  and distributed the flyers about him."
- "Lou Dobbs said that the injection of administration partisanship into public policy, in this case the Justice
  Department, is reason for all of us to be concerned, whether Republican, Democrat, or whatever."
- "Jerrold Kessel reported that the drugs distributed in Deir Istiya were mostly samples or donations the doctors had
  personally managed to collect."

Of the 6,676 kept facts, 3,383 are repairs. For example, "Tom Boeder, an antitrust attorney, said the case makes it
difficult not only for Microsoft but for Microsoft's competitors to settle down and know where they're going." became
"Antitrust attorney Tom Boeder said the Microsoft antitrust case makes it difficult not only for Microsoft but for
Microsoft's competitors to settle down and know where they are going."

The fact evals rejected 226 facts: useful 149 (such as "Ana Cabrera thanked Professor Alan Dershowitz and Ambassador
Norm Eisen for joining her."), grounded 75, atomic 22, attribution 20, and self-contained 3. One more cited no
passage. The earlier README
reported 5,546 rejections. That count was wrong: with documents ingested in parallel, each document's result also
counted other documents' rejections. The bug is fixed.

An independent model (Kimi K3.1 Pro) read 450 random kept facts and flagged those with a reference a reader cannot
resolve: 14% now, down from 25% before tuning. Facts that name a speaker by surname only fell from 13% to 6.3%. About
a third of the flagged facts are as specific as the transcript allows ("Anna", "an unidentified man"), and about a
third are references a better repair could resolve ("the targeted regions", "his last report").
Examples still flagged include "Darrel Whitten said he found it hard to believe that the Hashimoto faction would just
lay quiet during all of this." and "Ban Ki-Moon said he was doing this in close coordination with the government of the
United States and other European states."
