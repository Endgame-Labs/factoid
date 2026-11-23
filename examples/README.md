# Examples

Apps built on Factoid. Each folder is its own Factoid project, using the framework from this repo (`../..`).

| App | What it is |
| --- | --- |
| [`legal/`](legal/) | Legal due diligence: contracts, amendments, counsel emails, and a data room register, scored on CUAD and real amendment chains |
| [`nba/`](nba/) | The Golden State Warriors' 2022 playoffs: box scores and game logs (CSV), AP recaps, press conference transcripts, and articles |
| [`mediasum/`](mediasum/) | The ISC-RAG held-out benchmark (500 MediaSum transcripts, 499 questions), rerun with Factoid |

Facts and entities from each app's last full run (each README has the breakdown and sample facts):

| App | Run | Documents | Facts | Entities |
| --- | --- | --- | --- | --- |
| `legal` | The sample deal | 4 | 22 | 11 |
| `legal` | CUAD contracts 1 to 20 | 20 | 3,884 | 480 |
| `nba` | The 2022 playoffs | 73 | 4,194 | 311 |
| `mediasum` | The 100-transcript development sample | 100 | 6,676 | 1,603 |

Data, model-call caches, and run outputs stay out of git: see each app's `.gitignore`. MediaSum is research-use only,
and the ISC-RAG questions come from the study database, so neither is committed. The NBA app's recaps and transcripts
are copyrighted by their publishers; `fetch.py` downloads them and they are never redistributed.

```sh
cd examples/legal && uv sync && factoid eval diligence
```
