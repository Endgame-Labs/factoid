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

## Results on the development sample (2026-11-16)

The same reader (GLM 5.3 Flash) answers each question twice, and the same judge (Kimi K3.1 Pro) grades both answers.
One answer comes from Factoid's facts. The other comes from Factoid's chunks of the same transcripts (4,000
characters with 400 characters of overlap, like the paper's fixed chunks). The paper's reader and judge are retired,
so its numbers are a reference, not a head-to-head.

| Read budget | Facts | Chunks | Only facts right | Only chunks right | McNemar p |
| --- | --- | --- | --- | --- | --- |
| 512 tokens | 0.885 | 0.57 | 73 | 10 | < 0.001 |
| 2,048 tokens | 0.915 | 0.86 | 26 | 15 | 0.12 |
| 8,192 tokens | 0.92 | 0.94 | 11 | 15 | 0.56 |

By question type at 2,048 tokens, facts lead on pronoun coreference (1.0 against 0.775), direct control (0.95 against
0.85), and attribution (0.875 against 0.8). Facts are close on decontextualization (0.95 against 0.925). They trail
on opinion, belief, and judgment (0.8 against 0.95).

The run took 15 minutes and used 30,019 model calls (17,596 replayed from an earlier run's cache) and 21.0 million
tokens. These are tuning numbers. The held-out 500 has not been run with the current framework.

## Facts and entities

The run above (`factoid stats --examples 3`) produced 5,653 facts (5,586 current, 59 contradicted, 5 superseded, 2
corrected, and 1 ended) and 1,612 entities across 100 transcripts. The app declares no entity classes, so every
entity is untyped. The entities with the most facts are Donald Trump (648), the United States (178), and Theresa May
(138).

- "Miles O'Brien said that "Brokeback Mountain" was the inside favorite to win best picture at the Academy Awards but
  was derailed by "Crash," a story of race relations in Los Angeles."
- "Lou Dobbs said there may finally be a move to force China's hand to end its currency manipulation, which American
  companies say makes it impossible for them to compete fairly."
- "In the 911 call, the operator asked Melinda Duckett whether she did not know what she dressed Trenton in before he
  went to bed, and Melinda Duckett said he might have had his shoes off and his shirt off, no shoes."

The fact evals reject 5,546 facts, almost as many as they keep. Most rejections fall on the grounded (2,324),
self-contained (2,034), and useful (1,682) floors. Some rejected facts look sound. For example, the evals rejected
this fact as not grounded: "Carl Rochelle said that the jackscrew is what investigators are looking at very carefully
as they try to determine the cause of the crash of the Alaska Airlines plane." The floors were set on contracts.
Transcripts may need their own.
