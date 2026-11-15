# factoid-apps

Apps built on [Factoid](https://github.com/Endgame-Labs/factoid). Each folder is its own Factoid project.

| App | What it is |
| --- | --- |
| [`legal/`](legal/) | Legal due diligence: contracts, amendments, and counsel emails, scored on CUAD and real amendment chains |
| [`iscrag/`](iscrag/) | The ISC-RAG held-out benchmark (500 MediaSum transcripts, 499 questions), rerun with Factoid |

Each app expects the framework checked out next to this repo, at `../factoid`. Data, model-call caches, and run outputs
stay out of git: see each app's `.gitignore`.
