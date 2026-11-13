# Command line

One program, `factorial`. It is the CLI, the daemon, the HTTP API, and the MCP server. Every command reads
`factorial.yml` from the current directory or its parents, and `--json` makes any command print JSON.

## Everyday

```sh
factorial new <dir>                    # scaffold a project
factorial ingest <path|file.jsonl|->   # documents in; prints facts added, superseded, disputed, and rejected
factorial sync [source]                # pull new and changed documents from sources
factorial search "<words>" [--status current,disputed] [--subject Acme] [--since 30d] [--budget 2000]
factorial read <fact id|doc id>        # a fact with quotes and history, or a document with its facts
factorial history <fact id>            # every event that touched it
factorial tell "<sentence>"            # add a fact yourself; you are the source
factorial retract <fact id> --reason "<why>"
factorial restore <event seq>          # undo any event
factorial serve                        # HTTP API, MCP, and the daemon that syncs and rebuilds
```

## Inspecting the pipeline

```sh
factorial explain <doc id>             # each stage's output for one document: type, passages, candidates, verdicts
factorial try <file> [--set judge=nli] # run the pipeline on one document without writing anything
factorial rejected [--stage judge] [--reason grounded]
factorial prompts list | copy <name> | diff <name>
factorial pipeline                     # the effective config, with fingerprints
```

`explain` and `try` are the most important commands for building intuition: they show exactly what each stage saw and
decided.

## Evals

```sh
factorial eval [suite...]                       # run the current pipeline; print a scorecard
factorial eval --vary judge=none,nli,jev-floors # one run per value, same documents, then compare
factorial eval --set extract.window_bytes=10000 # one-off change
factorial eval compare <run> <run> [...]        # side by side, with significance and per-item diffs
factorial eval show <run> --misses              # the items a run got wrong, to read by eye
factorial eval label <suite>                    # label rejected and accepted candidates in the terminal
```

See [evals.md](evals.md).

## Keeping current

```sh
factorial status                        # documents, facts by status, stale facts, queue, spend today
factorial rebuild --estimate            # what re-deriving stale facts would cost
factorial rebuild [--stage judge]       # re-derive; replays archived model calls where it can
factorial reindex [index]               # rebuild a search index from the log
factorial compact                       # snapshot the log; required for hard deletes
```

Every command ends with one line that says it is done, done with warnings, or failed, and the one thing to do next.
