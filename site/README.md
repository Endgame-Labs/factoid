# Landing site

The landing site at https://endgame-labs.github.io/factoid/ is built from this folder. Its pages are Jinja templates
that extend one base template, so the header, nav, and footer are written once. Flask serves them while you work. The
build renders each page to one self-contained HTML file in `dist/`, with its CSS and JavaScript inline, and GitHub
Pages hosts those files. There is no backend and no analytics.

```text
site/
  app.py              Flask app, the page list, the nav, the footer links, and the build
  templates/
    base.html         <head>, header and nav, footer, and the shared scripts
    index.html        the home page
    what-is-a-fact.html
  static/
    base.css, base.js the shared styles, theme toggle, mobile nav, and PyPI version check
    home.css, home.js the home page's styles and copy button
    fact.css, fact.js the "What is a fact?" page
  data/demo.json      the "What is a fact?" page's data
  dist/               the build (ignored by git)
```

The design is one of four drafts Neon (agy) made, in Endgame's brand colors. The words are the first version's, which
Netlify's agent wrote.

## Working on it

From the repo root:

```sh
uv run --project site flask --app site/app.py run --debug   # http://127.0.0.1:5000, reloads on change
uv run --project site python site/app.py build              # writes site/dist/
```

- **A nav link or a footer link:** edit `NAV` or `FOOTER` in `app.py`. A nav link that starts with `#` goes to that
  section of the home page.
- **A new page:** add a template that extends `base.html`, and add its file name to `PAGES` and, if it belongs there,
  to `NAV`.
- **The version:** taken from the repo's `pyproject.toml` at build time. Each page also asks PyPI for the latest
  release when it loads.

Check both pages at phone width before you push.

## The "What is a fact?" page

`data/demo.json` is real output from `examples/demo`. To refresh it after a change to Factoid, ingest the demo's three
documents in order (its README says how), then run `uv run python page_data.py ../../site/data/demo.json` from
`examples/demo`.

## Publishing

Push to `main`. The `landing page` workflow (`.github/workflows/pages.yml`) builds the site and publishes `dist/` on
every push to `main` that changes `site/` or `pyproject.toml`, in about a minute. Watch it with `gh run watch`. The
`test` workflow also builds the site, so a broken template fails there first.

To publish again without a change, run `gh workflow run pages.yml`.

## Rollback

Revert the commit and push. The workflow publishes the reverted site.

## Netlify

The page was on Netlify at https://factoid-landing-page.netlify.app (site ID `89962c6b-dacb-4aa9-b877-048cdf6a2bc8`)
until 2026-11-23, when the account's free credits ran out and Netlify blocked new deploys. The Netlify site was deleted
the same day.

## Page content

The pages state facts about Factoid. Keep them in step with the README:

- The Python version (3.13+) and the license (MIT).
- The install command: `uv tool install factoid`.
- The news transcripts result: 0.92 for facts at 512 tokens, 0.87 for chunks at 2,048, and even at 8,192. If
  `examples/mediasum` publishes new numbers, update the page.
- The seven fact statuses: `current`, `superseded`, `ended`, `corrected`, `contradicted`, `replaced`, and `retracted`.
- The two papers.

Follow the repo's writing rules: plain words, short sentences, the Oxford comma, and plain headings. Do not add numbers,
customers, logos, or quotes that the repo does not support.

## Approval

Ask Kyle before you add a custom domain or analytics.
