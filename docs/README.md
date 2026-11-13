# Factoid docs

These docs are the spec. They describe what Factoid does from the outside: its inputs, its outputs, its config, and
how it is measured. They do not depend on the implementation language.

| Doc | What it covers |
| --- | --- |
| [mental-model.md](mental-model.md) | The nouns, the pipeline, and how history works. Read this first. |
| [documents.md](documents.md) | **Input:** the Document, and how sources produce Documents. |
| [facts.md](facts.md) | **Output:** the Fact, its quotes and slot, its statuses, and the event log. |
| [config.md](config.md) | `factoid.yml`: the project layout, models, stages, and strategies. |
| [cli.md](cli.md) | Every command. |
| [api.md](api.md) | The HTTP API and the MCP tools. |
| [evals.md](evals.md) | Suites, runs, comparisons, and metrics: how algorithms get chosen. |
| [plugins.md](plugins.md) | Writing a strategy, source, store, or index in any language. |
| [prior-art.md](prior-art.md) | What we learned from OpenEndgame, endgame-wiki, cerebro, and the ISC papers. |
| [open-questions.md](open-questions.md) | Decisions not made yet. |

Writing conventions: plain words, short sentences, the Oxford comma, and an example for every shape.
