# Examples

Apps built on Factoid. Each folder is its own Factoid project, using the framework from this repo (`../..`).

| App | What it is |
| --- | --- |
| [`legal/`](legal/) | Legal due diligence: contracts, amendments, and counsel emails, scored on CUAD and real amendment chains |
| [`iscrag/`](iscrag/) | The ISC-RAG held-out benchmark (500 MediaSum transcripts, 499 questions), rerun with Factoid |

Data, model-call caches, and run outputs stay out of git: see each app's `.gitignore`. MediaSum is research-use only,
and the ISC-RAG questions come from the study database, so neither is committed.

```sh
cd examples/legal && uv sync && factoid eval diligence
```
