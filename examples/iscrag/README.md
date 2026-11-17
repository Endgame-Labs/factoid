# iscrag

This is the held-out benchmark from "RAG Deserves an Index" (arXiv 2608.20845), rerun with Factoid in place of the
original ISC pipeline. It uses 500 MediaSum transcripts and 499 questions, keeping the paper's answer prompt, judge
prompt, source rendering, and token budgets. The `dev` suite is the paper's 100-transcript development sample (200
questions), used for tuning. The `heldout` suite is the held-out 500.

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
| 512 tokens | 0.94 | 0.57 | 80 | 6 | < 0.001 |
| 2,048 tokens | 0.955 | 0.87 | 25 | 8 | 0.005 |
| 8,192 tokens | 0.965 | 0.945 | 11 | 7 | 0.48 |

By question type at 2,048 tokens, facts score 0.975 against 0.775 on pronoun coreference, 0.95 against 0.85 on direct
control, 0.975 against 0.825 on attribution, 0.95 against 0.95 on decontextualization, and 0.925 against 0.95 on
opinion, belief, and judgment (up from 0.8 before tuning).

This run is after tuning the fact evals and prompts on the first 30 transcripts of this sample (see the framework's
SPEC, decisions 73 to 76). The other 70 were not looked at while tuning. Before tuning (2026-11-16), facts scored
0.885, 0.915, and 0.92 at the same budgets. Chunks scored the same both times, within one question. Three things
changed. The fact evals and repair now see the transcript text just before each quote. The self-contained question is
strict about pronouns, unclear descriptions ("the case"), and relative dates, and a fact below its target now gets one
repair (previously it was dropped). The app also gives the extractor a roster that maps short speaker tags ("VAUSE")
to full names.

The run took 17 minutes and used 35,169 model calls (11,956 replayed from cache) and 40.2 million tokens, up from 21.0
million tokens before tuning. The repairs account for most of the increase. These are still development numbers; the
held-out 500 has not been run.

## Facts and entities

The run above (`factoid stats --examples 3`) produced 6,501 facts (6,426 current, 66 contradicted, 6 superseded, 2
ended, and 1 corrected) and 1,581 entities across 100 transcripts. The app declares no entity classes, so every entity
is untyped. The entities with the most facts are Donald Trump (803), the United States (188), and Carol Costello
(148).

- "Melinda Duckett, the late mother of missing two-year-old Trenton Duckett, said that she and others had already gone
  out and distributed the flyers."
- "Lou Dobbs said that the injection of administration partisanship into public policy at the Justice Department is
  reason for all of us to be concerned, whether Republican, Democrat, or whatever."
- "Jerrold Kessel reported that the drugs distributed in Deir Istiya were mostly samples or donations the doctors had
  personally managed to collect."

Of the 6,501 kept facts, 3,165 are repairs. For example, "Tom Boeder, an antitrust attorney, said the case makes it
difficult not only for Microsoft but for Microsoft's competitors to settle down and know where they're going." became
"Antitrust attorney Tom Boeder said the Microsoft antitrust case makes it difficult not only for Microsoft but for
Microsoft's competitors to settle down and know where they are going."

The fact evals rejected 214 facts: useful 141 (such as "Ana Cabrera thanked Professor Alan Dershowitz and Ambassador
Norm Eisen for joining her."), grounded 71, atomic 22, and attribution 22. One more cited no passage. The earlier README
reported 5,546 rejections. That count was wrong: with documents ingested in parallel, each document's result also
counted other documents' rejections. The bug is fixed.

An independent model (Kimi K3.1 Pro) read 300 random kept facts and flagged those with a reference a reader cannot
resolve: 13% now, down from 25% before tuning. Facts that name a speaker by surname only fell from 13% to 6.4%.
Examples still flagged include "Phil Mattingly said the impasse at that point seemed borderline permanent." and "Da
Silva said the United Nations serves 27 million, or possibly 24 million, Iraqis."
