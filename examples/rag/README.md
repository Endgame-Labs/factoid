# RAG: a docs assistant for Python's standard library

A retrieval-augmented generation (RAG) app built on Factoid. It answers questions like "Can I use distutils on
Python 3.12?" from Python's "What's New" pages, and cites its sources. `rag.py` is the whole pipeline in one file:
retrieve, pack the sources into a budget, and answer from them. It can retrieve Factoid's facts, plain chunks of the
pages, or both, and the eval scores all three on the same questions.

Docs change between releases: the 3.10 page says distutils is deprecated, and the 3.12 page says it is removed.
Factoid resolves the two facts when the 3.12 page is ingested, so a search as of 3.12 finds the removal, and a search
as of 3.11 finds the deprecation. Each fact is one short sentence, so many of them fit in a small budget.

| File | What it is |
| --- | --- |
| `fetch.py` | Downloads the "What's New" pages for 3.9 to 3.14 into `data/` and keeps New Modules, Deprecated, and Removed |
| `rag.py` | The pipeline and a command line: `facts`, `chunks`, and `both` retrievers, `pack`, and `answer` |
| `app/` | `ReleaseNotes` (one page per release, dated by its release), `ChangeFact` with traits `added`, `deprecated`, `removed`, and `replacement`, and `StdlibApi` and `Pep` entities |
| `evals/qa.py` | 45 questions, each with the answer for its version and an outdated answer, checked against the pages |

The pages are the Python documentation (PSF license). They are downloaded, not committed.

## Run it

From this folder, with keys for TypeSafe and Fireworks (`uv run factoid keys set`):

```sh
uv sync
uv run python fetch.py                     # six pages into data/, about 140,000 characters
for v in 3.9 3.10 3.11 3.12 3.13 3.14; do uv run factoid ingest data/whatsnew-$v.md; done   # oldest first
uv run python rag.py "Is the distutils package available?" --python 3.12
uv run python rag.py "Is the distutils package available?" --python 3.11
uv run python rag.py "Is the distutils package available?" --python 3.12 --retriever chunks
uv run factoid eval qa                     # all three retrievers on the 45 questions
```

Ingest the pages oldest first, so each one is resolved against what came before it. All six cost about 30 cents at
list prices.

## The pipeline

```text
question, Python version
  -> retrieve   facts:  search_facts(question, as_of=release date, valid_at=release date)
                chunks: hybrid search over 2,000-character windows of the pages released by then
                both:   facts, then windows
  -> pack       the best sources that fit the budget (8,000 characters, about 2,000 tokens, by default)
  -> answer     one call to the project's `generate` model: JSON with the answer and the numbers of the sources it used
```

To use it in your own app, keep `pack` and `answer` and swap the retriever. The facts retriever is three lines.

## Results

`factoid eval qa` asks each question with each retriever at about 500, 2,000, and 8,000 tokens of sources. A judge
(Kimi K3.1 Pro) decides whether each answer gives the answer for that version, the outdated one, or neither. 30
questions ask about the release that made a change. 15 more ask about Python 3.14 for changes made in earlier
releases, whose answer is on an older page.

The run on 2026-11-24, with the default settings (Jev 1.14, GLM 5.3 Flash, and Qwen3 embeddings):

| Retriever | Budget | Right | Outdated | Right on 3.14 | Tokens read |
| --- | --- | --- | --- | --- | --- |
| facts | 500 | 45 of 45 | 0 | 15 of 15 | 473 |
| facts | 2,000 | 45 of 45 | 0 | 15 of 15 | 1,439 |
| chunks | 500 | 37 of 45 | 0 | 13 of 15 | 832 |
| chunks | 2,000 | 44 of 45 | 0 | 14 of 15 | 1,853 |
| chunks | 8,000 | 45 of 45 | 0 | 15 of 15 | 7,711 |
| both | 500 | 45 of 45 | 0 | 15 of 15 | 473 |
| both | 2,000 | 45 of 45 | 0 | 15 of 15 | 1,903 |

Facts answer every question from about 470 tokens. Chunks need about 7,700 for the same score, 16 times as much.
Below that, chunks miss the window that holds the answer, and the reader says "The sources do not say", as it should.
At 500 tokens, a window of about 500 tokens sometimes does not fit, so chunks read up to 832. At 8,000 tokens, facts
reads the same 1,439 tokens as at 2,000, because the 40 facts considered all fit, and both reads 7,700; each scores 45
of 45.

No retriever gave an outdated answer. Each source is labelled with its release, and the reader is told the version,
so it does not mistake a 3.10 deprecation for the state in 3.12. Stale answers may still be a risk with sources that do
not say when they were written. This eval does not test that.

The whole run (ingesting the six pages, 405 answers, and 405 judgments) cost $0.81 at list prices. Rerunning it
replays saved calls and costs nothing.
