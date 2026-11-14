# TODO

## Discuss: the system's dependencies

Kyle wants to talk this through before anything is decided. Bring it up with him.

**Local mode.** Postgres with pgvector and pgvectorscale, plus a local embedding model (Gemma?).

**2026-11-14:** decided for v1 (Kyle): storage is pluggable; SQLite is the system of record; search requires
turbopuffer or a turbopuffer-compatible endpoint. See `SPEC.md` section 11. Still open: a keyless local mode.

**Production mode.** Unknown.

Questions to settle:

- Can both modes use Postgres as the main system of record?
- Is there a better way that uses only files? (Settled for v1: no flat files. Current state is the truth, and the event
  log is for audit and provenance.)
- If the store is files, how do secondary lookups work, such as getting all facts for a given entity?
- Which embedding model runs locally, and which runs in production?
- What does a new user have to install before `factoid ingest` works?
- Pydantic as a dependency: use it underneath (model output, stored records, and validating class settings at
  import), and keep the classes users write as plain classes. Tested against Pydantic 2.14: a `BaseModel` subclass
  rejects plain attributes such as `chunk_size = 4000`.
