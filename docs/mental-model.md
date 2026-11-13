# The mental model

Factorial has three parts: a **pipeline** that turns documents into facts, a **log** that remembers everything that
happened to them, and an **eval loop** that measures the pipeline. Keep these three in mind and the rest follows.

## The nouns

| Noun | One line |
| --- | --- |
| **Source** | Somewhere documents come from: a folder, a mailbox, an MCP server, a plugin. |
| **Document** | One thing that was said or written: a call, an email thread, a doc, a CRM record. Has revisions. |
| **Passage** | A numbered piece of a document (a speaker's turn, a paragraph, a row). The unit facts cite. |
| **Candidate** | A proposed fact, before it is judged. |
| **Fact** | An accepted, self-contained sentence with quotes, a speaker, and a date. Optionally a typed **slot**. |
| **Event** | One thing that happened: a document ingested, a fact added, superseded, contradicted, retracted, or restored. |
| **Stage** | A step of the pipeline (classify, segment, extract, judge, resolve, index). |
| **Strategy** | One way to do a stage (`jev-floors` and `nli` are judge strategies). Built in or a plugin. |
| **Pipeline** | The strategy chosen for every stage, plus their settings. Has a fingerprint. |
| **Suite** | A corpus plus gold labels, for evals. |
| **Run** | One pipeline over one suite, with its scores, cost, and latency. |

## The pipeline

```
 Source ──► Document ──► classify ──► segment ──► extract ──► gate ──► judge ──► resolve ──► log
                          what kind?   passages    candidates   code     models    vs. other
                                                                checks   decide    facts
```

| Stage | Question it answers | Example strategies |
| --- | --- | --- |
| `classify` | What kind of document is this? | `declared` (the source says), `rules`, `systemone`, `llm` |
| `segment` | What are its citable passages? | `auto` (by type), `turns`, `email` (drops quoted replies and signatures), `paragraphs` |
| `extract` | What facts does it state? | `passages` (the model cites passage ids; code attaches quotes), `staged` (cheap model, then a tagger) |
| `gate` | Is the candidate well formed? Always runs, never calls a model. | shape and length, cited passages exist, near-duplicate within the document, caps |
| `judge` | Is it true to the source, atomic, self-contained, and useful? A chain. | `none`, `nli`, `jev-floors`, `llm` |
| `repair` | Can a near miss be reworded once? Optional. The quote is never changed. | `none`, `reword-once` |
| `resolve` | How does it relate to facts we already have? | `hash`, `slot` (same entity and field, newer wins), `vector-judge` |
| `index` | Where can it be found? Not a stage of truth, a view. | `sqlite-fts`, `pgvectorscale`, `turbopuffer` |

`resolve` is where Factorial does what none of its predecessors did at ingest. For each new fact it asks: have we seen
this (**duplicate**: keep one, link the other as corroboration), does it replace something (**supersede**), or does it
disagree with something (**contradict**: keep both, mark both disputed). Slot facts resolve by rule: the same entity and
field, stated later, supersede. Sentence facts resolve by retrieving their nearest neighbors and asking a judge.

## The log

Facts are never edited in place. Everything is an event appended to the log:

```jsonl
{"seq":101, "type":"fact.added",       "fact":{"id":"f_a1", "text":"Acme's renewal price is $100K.", ...}}
{"seq":187, "type":"fact.added",       "fact":{"id":"f_b2", "text":"Acme's renewal price is $115K.", ...}}
{"seq":188, "type":"fact.superseded",  "id":"f_a1", "by":"f_b2", "actor":{"kind":"rule", "name":"slot"}}
{"seq":204, "type":"fact.retracted",   "id":"f_b2", "actor":{"kind":"person", "name":"kyle@example.com"}, "reason":"misheard"}
{"seq":205, "type":"fact.restored",    "id":"f_a1", "actor":{"kind":"rule", "name":"resurrect"}}
```

From the log, Factorial keeps **views**: the current state of every fact, and each search index. Views can be dropped
and rebuilt at any time, which gives us:

1. **Undo.** Every automatic change has an actor and a reason, and reversing it is another event.
2. **Time travel.** "What did we believe on October 1?" is the log replayed to October 1.
3. **Fair comparisons.** Two pipelines can be run over the same documents and their logs diffed fact by fact.

Every event says who acted: `code`, `rule`, `model`, `judge`, or `person`, with a name, a version, and the evidence.

## The eval loop

```
            ┌──────────── change one strategy ◄────────────┐
            ▼                                               │
  pipeline A, B, C ──► run each on a suite ──► scorecards ──► compare ──► adopt the winner
```

A suite holds documents plus what a careful reader would say about them: which candidate facts to keep, which pairs
are duplicates or contradictions, and questions with answers. A run scores every stage separately, so you can see
*where* a pipeline wins or loses, and what it costs. Every model call is archived and keyed by its request, so a run
that changes only the judge replays the extraction instead of paying for it again. See [evals.md](evals.md).

## Staying current

Every stage's settings and prompts hash into its **fingerprint**, and each fact records the fingerprints that made it.
Change a prompt and the facts it produced become stale; `factorial rebuild --estimate` says what re-deriving them would
cost, and the daemon re-derives them at a pace you set. Changing *only the model* of a stage does not make facts stale
(models are recorded on each fact, not fingerprinted), so switching to a cheaper model never forces a corpus rebuild
by accident. A rebuild for a model change is an explicit choice.
