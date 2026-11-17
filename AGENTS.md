# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

Factoid is a Python framework that turns documents into facts and entities. An early implementation is in
`src/factoid`, with example apps in `examples/`. The docs still settle the design before code is written: `SPEC.md`
section 17 says what is built.

## Read first

1. `README.md`: what Factoid is and how a project uses it.
2. `SPEC.md`: the decisions behind the design, and how settled each one is.
3. `TODO.md`: open discussions.
4. `AGENTS.md.local`, if it exists: the preferences of the developer you are working with (see below).

## The developer's preferences: `AGENTS.md.local`

Each developer keeps their own preferences in `AGENTS.md.local`, next to this file. It is ignored by git, so it never
leaves their machine.

- Read `AGENTS.md.local` at the start of every session, and follow it. Where it disagrees with this file on a matter of
  personal preference, it takes precedence.
- Keep it up to date. When the developer tells you how they like to work (tone, tools, review habits, things to avoid),
  write it there in the same session, so the next session does not have to be told again.
- If the file does not exist, create it the first time the developer states a preference.
- Do not put secrets in it, and do not put project decisions in it. Project decisions go in `SPEC.md`.

## Working rules

- **Keep `SPEC.md` current.** When a design decision is made or changed, update `SPEC.md` in the same change: the
  section's status (Decided, Proposed, or Open) and the decision log.
- **Do not edit the README's intro.** Everything in `README.md` above "Quickstart" is written by hand.
- **Docs before code.** Change the docs first when the design changes.
- **Files ending in `.local` are private** to a developer and ignored by git. Do not commit them, and do not copy their
  contents into tracked files.

## Style

- Plain words and short sentences. Always use the Oxford comma.
- Wrap prose at 120 columns.
- Headings are plain labels.

## Git

- Commit as the human developer. Do not add AI attribution to commits, pull requests, or issues.
- Small doc changes go straight to `main`. Open a pull request for larger ones when the developer asks.
