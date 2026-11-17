# Input: Documents

A Document is one thing that was said or written. Everything Factoid knows comes from Documents, so this shape is
small, strict, and easy to produce from anything.

## The shape

```json
{
  "id": "email:CAF8x2@mail.gmail.com",
  "revision": "r2",
  "type": "email",
  "title": "Re: Acme renewal",
  "at": "2026-11-03T16:42:00-08:00",
  "text": "From: Dana Ruiz <dana@acme.com>\nTo: Kyle <kyle@example.com>\n\nWe'll renew at $115K if legal signs off by Friday.\n\n> On Nov 2, Kyle wrote: ...",
  "people": [
    {"name": "Dana Ruiz", "email": "dana@acme.com", "side": "theirs"},
    {"name": "Kyle Wild", "email": "kyle@example.com", "side": "ours"}
  ],
  "url": "https://mail.google.com/mail/u/0/#inbox/18c2...",
  "meta": {"thread_id": "18c2...", "labels": ["renewals"]}
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Stable across revisions. Convention: `<type>:<source id>`. |
| `revision` | no | Anything that changes when the content changes. Omitted: a hash of `text`. |
| `type` | no | `call`, `email`, `chat`, `doc`, `record`, or your own. Omitted: the `classify` stage decides. |
| `title` | no | Shown with citations. |
| `at` | yes | When it was said or written, with an offset. Facts inherit dates from this; Factoid never invents one. |
| `text` | yes | The content. Plain text or Markdown. Transcripts use `Speaker Name: words` lines. |
| `people` | no | Who took part. Used to name speakers in full and to attribute facts. Never inferred by a model. |
| `url` | no | A link back to the original. |
| `meta` | no | Anything else. Kept, shown to `classify`, never extracted from blindly. |

A document can be removed (`doc.deleted`): its facts lose that document's quotes, and a fact left with no quotes is
retracted. A new revision replaces the facts of the old revision through `resolve`, so unchanged facts keep their ids.

## Getting documents in

| Way | Example |
| --- | --- |
| Files | `factoid ingest notes/*.md calls/*.vtt mail/*.eml`. File types map to documents by convention. |
| JSON Lines | `factoid ingest docs.jsonl`, one Document per line. The universal adapter. |
| HTTP | `POST /v1/documents` with a Document or an array of them. |
| A source | Declared in `factoid.yml`, pulled by `factoid sync` or the daemon. See below. |

## Sources

A source answers two questions: *what changed since then?* and *give me this one*. That's the whole interface, and it is
what makes sources pluggable.

```yaml
sources:
  - name: mail
    use: imap                  # built in
    host: imap.gmail.com
  - name: calls
    use: folder
    path: ~/calls
    type: call                 # every document from here is a call
  - name: crm
    use: mcp                   # any MCP server with list and get tools
    command: ["salesforce-mcp"]
  - name: notion
    use: ./plugins/notion.py   # any program that speaks the plugin protocol
```

| Method | Input | Output |
| --- | --- | --- |
| `list` | `{"since": "<cursor or null>"}` | `{"ids": ["..."], "cursor": "..."}` |
| `get` | `{"id": "..."}` | a Document |

Built in at first: `folder`, `jsonl`, `imap`, and `mcp`. Everything else starts as a plugin; see [plugins.md](plugins.md).

## Document types

The type picks the segmenter and tells the extractor what it is reading. The built-in types:

| Type | Passages are | Notes |
| --- | --- | --- |
| `call` | speaker turns, adjacent turns by one speaker joined | speaker comes from the transcript, never a model |
| `email` | paragraphs of the newest message | quoted replies and signatures are context, not citable |
| `chat` | messages | author is the speaker |
| `doc` | paragraphs and list items | author is the speaker when known |
| `record` | fields | becomes slot facts directly; no model extracts them |

When `type` is missing, `classify` decides. Which classifier is good enough, and at what cost, is an eval question:
the `doctype` metric in [evals.md](evals.md) measures it.
