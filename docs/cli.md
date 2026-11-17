# Command line

One program, `factoid`. It is the CLI, the daemon, the HTTP API, and the MCP server. Every command reads
`factoid.yml` from the current directory or its parents, and `--json` makes any command print JSON.

## Everyday

```sh
factoid new <dir>                    # scaffold a project
factoid ingest <path|file.jsonl|->   # documents in; prints facts added, superseded, disputed, and rejected
factoid sync [source]                # pull new and changed documents from sources
factoid search "<words>" [--status current,disputed] [--subject Acme] [--since 30d] [--budget 2000]
factoid read <fact id|doc id>        # a fact with quotes and history, or a document with its facts
factoid history <fact id>            # every event that touched it
factoid tell "<sentence>"            # add a fact yourself; you are the source
factoid retract <fact id> --reason "<why>"
factoid restore <event seq>          # undo any event
factoid serve                        # HTTP API, MCP, and the daemon that syncs and rebuilds
```

## Inspecting the pipeline

```sh
factoid explain <doc id>             # each stage's output for one document: type, passages, candidates, verdicts
factoid try <file> [--set judge=nli] # run the pipeline on one document without writing anything
factoid rejected [--stage judge] [--reason grounded]
factoid prompts list | copy <name> | diff <name>
factoid pipeline                     # the effective config, with fingerprints
```

`explain` and `try` are the most important commands for building intuition: they show exactly what each stage saw and
decided.

## Evals

```sh
factoid eval [suite...]                       # run the current pipeline; print a scorecard
factoid eval --vary judge=none,nli,decision-floors # one run per value, same documents, then compare
factoid eval --set extract.window_bytes=10000 # one-off change
factoid eval compare <run> <run> [...]        # side by side, with significance and per-item diffs
factoid eval show <run> --misses              # the items a run got wrong, to read by eye
factoid eval label <suite>                    # label rejected and accepted candidates in the terminal
```

See [evals.md](evals.md).

## Keeping current

```sh
factoid status                        # documents, facts by status, stale facts, queue, spend today
factoid rebuild --estimate            # what re-deriving stale facts would cost
factoid rebuild [--stage judge]       # re-derive; replays archived model calls where it can
factoid reindex [index]               # rebuild a search index from the log
factoid compact                       # snapshot the log; required for hard deletes
```

Every command ends with one line that says it is done, done with warnings, or failed, and the one thing to do next.
