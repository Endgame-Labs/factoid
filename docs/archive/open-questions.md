# Open questions

Decisions not made yet. Algorithm choices are not listed here: those are settled by [evals](evals.md), not by debate.

## Architecture

1. **Implementation language.** Python with uv (research stack, NLP, easy evals; `uv tool install` hides interpreter
   versions), Ruby (the nicest DSLs, a weak NLP ecosystem), or Go (a single static binary; clumsier evals). The docs are
   written to be language-neutral, so this can wait until the interfaces settle.
2. **One log or one per project?** One `factoid.yml` is one log today. Do we need several tenants in one server (an Org
   per customer), or is that one process per tenant, hop-rip style?
3. **Log format in a bucket.** Newline-delimited JSON segments, compacted to Parquet like incisive? What is a segment's
   size, and how do concurrent writers order appends (single writer per project, as with hop-rip)?
4. **Entities.** Subjects are names today, and linking them to your own entities (accounts, people) is a plugin. Is a
   minimal entity registry core?
5. **Slots.** Who defines the fields (`renewal_price`, `title`, `stage`): a per-project schema in `factoid.yml`, or
   free fields proposed by the extractor and normalized later?

## Product

6. **Articles.** OpenEndgame and endgame-wiki build cited pages from facts. Is that a separate project that follows
   `/v1/events`, or a Factoid feature?
7. **Answers.** Should `factoid ask` (answer a question from facts, cited) be a first-class command, or only an eval
   reader?
8. **Privacy and hard delete.** Compaction can drop a document's text and quotes. Is that enough for a deletion request?

## Evals

9. **The first suites.** Candidates: OpenEndgame's 272 labeled candidates, ISC-RAG, MediaSumQA, EnronQA, and
   SalesTranscriptQA. Which ship in the repo, and which are imported?
10. **Matching extracted facts to gold facts.** Recall of `keep` facts needs a "states the same claim" judge, which is
    itself a model that must be calibrated. Against what?
11. **An agent reader.** The ISC agent-layer result says facts may not win when an agent uses tools. Which agent harness
    do suites use?
