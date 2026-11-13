# Plugins

Four kinds of things can be plugged in: **strategies** (one way to do a pipeline stage), **sources**, **stores** (where
the log lives), and **indexes** (search views). Common ones are built in. Anything else is a plugin: a small program,
in any language, that Factoid starts and talks to.

## How a plugin runs

Factoid starts the program and exchanges JSON-RPC 2.0 messages with it over stdin and stdout, one JSON object per line.
The program stays running and handles many requests. This is the same pattern MCP and Terraform providers use.

```yaml
pipeline:
  judge:
    - {use: ./plugins/legal_judge.py, min: 0.8}   # settings are passed to the plugin
```

```
factoid → {"jsonrpc":"2.0","id":0,"method":"describe"}
plugin    → {"jsonrpc":"2.0","id":0,"result":{"kind":"judge","name":"legal-judge","version":"3"}}
factoid → {"jsonrpc":"2.0","id":1,"method":"judge","params":{"candidate":{...},"passages":[...],"document":{...},"settings":{"min":0.8}}}
plugin    → {"jsonrpc":"2.0","id":1,"result":{"pass":false,"scores":{"legal":0.42},"reasons":["states a guess as a decision"]}}
```

`describe` comes first. Its `version` goes into the stage's fingerprint, so changing a plugin's behavior means bumping
its version, and the facts it made become stale.

A plugin that wants to call a model asks Factoid to (`model.generate`, `model.decide`, `model.embed`), so its calls are
archived, priced, budgeted, and replayable like every other call.

## The contracts

| Kind | Methods | Input | Output |
| --- | --- | --- | --- |
| source | `list`, `get` | cursor; id | ids and a cursor; a Document |
| classify | `classify` | Document | `{"type": "...", "confidence": 0.0}` |
| segment | `segment` | Document | passages: `[{"n": 1, "text": "...", "speaker": "...", "offset": [a, b], "citable": true}]` |
| extract | `extract` | Document, passages | candidates: `[{"text": "...", "subject": "...", "slot": {...}, "cites": [3, 4]}]` |
| judge | `judge` | candidate, cited passages, Document, similar facts | `{"pass": bool, "scores": {...}, "reasons": [...]}` |
| repair | `repair` | candidate, the judge's reasons | a reworded candidate (its `cites` are kept, never changed) |
| resolve | `resolve` | new fact, neighbor facts | `[{"relation": "duplicate|supersedes|contradicts|unrelated", "other": "f_...", "score": 0.0}]` |
| store | `append`, `read` | events; a starting seq | ok; events |
| index | `upsert`, `delete`, `query` | facts; ids; a query | ok; ok; ranked fact ids with scores |

Note what extract returns: `cites` are passage numbers, never quote text. Factoid attaches quotes itself.

## Built in

| Kind | Built in |
| --- | --- |
| source | `folder`, `jsonl`, `imap`, `mcp` |
| classify | `declared`, `rules`, `systemone`, `llm` |
| segment | `auto`, `turns`, `email`, `paragraphs`, `rows` |
| extract | `passages`, `staged` |
| judge | `nli`, `jev-floors`, `llm` |
| resolve | `hash`, `slot`, `vector-judge` |
| store | local folder, S3-compatible bucket |
| index | `sqlite-fts`, `pgvectorscale`, `turbopuffer` |

## Testing a plugin

`factoid plugin check ./plugins/legal_judge.py` runs the contract tests for its kind: well-formed replies, stable output
for the same input, sensible handling of empty and huge inputs. `factoid eval --set judge=./plugins/legal_judge.py`
then tells you whether it is any good.
