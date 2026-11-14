# TODO

## Discuss: the system's dependencies

Kyle wants to talk this through before anything is decided. Bring it up with him.

**Local mode.** Postgres with pgvector and pgvectorscale, plus a local embedding model (Gemma?).

**2026-11-14:** flat-file stores are off the table for now (Kyle). Postgres is the leading proposal; see `SPEC.md`
section 11.

**Production mode.** Unknown.

Questions to settle:

- Can both modes use Postgres as the main system of record?
- Is there a better way that uses only files? The README currently says the truth is an append-only event log, with
  current state and search indexes rebuilt from it.
- If the store is files, how do secondary lookups work, such as getting all facts for a given entity?
- Which embedding model runs locally, and which runs in production?
- What does a new user have to install before `factoid ingest` works?
- Pydantic as a dependency: use it underneath (model output, stored records, and validating class settings at
  import), and keep the classes users write as plain classes. Tested against Pydantic 2.14: a `BaseModel` subclass
  rejects plain attributes such as `chunk_size = 4000`.
