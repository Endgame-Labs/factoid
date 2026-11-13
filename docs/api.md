# HTTP API and MCP

`factorial serve` answers on one address. All bodies are JSON. Errors are `{"error": "...", "hint": "..."}` with `400`,
`401`, `404`, `409`, or `429`.

## HTTP

| Method | Path | Body or query | Result |
| --- | --- | --- | --- |
| `POST` | `/v1/documents` | a Document, or an array | `202` with `{"accepted": n, "events_from": seq}` |
| `GET` | `/v1/documents/:id` | | the Document with its current facts |
| `DELETE` | `/v1/documents/:id` | | `202`; its facts lose their quotes from it |
| `GET` | `/v1/search` | `q`, `status`, `subject`, `since`, `until`, `budget`, `limit` | `{"facts": [...], "left_out": n}` |
| `GET` | `/v1/facts/:id` | `history=true` | a Fact, optionally with its events |
| `POST` | `/v1/facts` | `{"text": "...", "subject": "..."}` | `201` with the Fact; you are its source |
| `POST` | `/v1/facts/:id/retract` | `{"reason": "..."}` | `200` with the event |
| `POST` | `/v1/events/:seq/restore` | `{"reason": "..."}` | `200` with the event |
| `GET` | `/v1/events` | `since` (a seq), `wait` (seconds, for long polling) | events in order |
| `GET` | `/v1/status` | | counts, staleness, queue, and spend |
| `GET` | `/healthz` | | `ok` |

`/v1/events` is how other systems follow Factorial: a wiki rebuilding a page when its facts change, or a CRM sync
reacting to a superseded price.

`search` fits its answer to `budget` tokens (default from config) and says how many matches it left out, so a model
reader never gets more than it asked for.

Auth: a bearer key per client, read-only or read-write, stored hashed. Local and loopback use needs no key.

## MCP

The same server speaks MCP at `/mcp`, and `factorial mcp` speaks it over stdio. Its tools:

| Tool | Does |
| --- | --- |
| `search` | the search above, with the result rendered as cited Markdown plus the structured facts |
| `read` | facts or documents by id, with quotes and history |
| `tell` | add a fact in your own words |
| `retract` | take one back, with a reason |

Answers carry fact ids, so an agent can cite them and a person can check them.
