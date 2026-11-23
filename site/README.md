# Landing page

The landing page at https://endgame-labs.github.io/factoid/ is one static file (`index.html`, with its CSS and
JavaScript inline) with no build step, no backend, and no analytics. This folder is its source. GitHub Pages hosts it.

The design is one of four drafts Neon (agy) made, in Endgame's brand colors. The words are the first version's, which
Netlify's agent wrote.

## Updating the page

1. Edit the files in `site/`. Open `site/index.html` in a browser to check your changes, or serve the folder with
   `python3 -m http.server -d site`. Check it at phone width too.
2. Commit and push to `main`. The `landing page` workflow (`.github/workflows/pages.yml`) publishes `site/` on every
   push to `main` that changes it, in about a minute. Watch it with `gh run watch`.

To publish again without a change, run `gh workflow run pages.yml`.

## Rollback

Revert the commit and push. The workflow publishes the reverted page.

## Netlify

The page was on Netlify at https://factoid-landing-page.netlify.app (site ID `89962c6b-dacb-4aa9-b877-048cdf6a2bc8`)
until 2026-11-23, when the account's free credits ran out and Netlify blocked new deploys. The Netlify site was deleted
the same day.

## Page content

The page states facts about Factoid. Keep them in step with the README:

- The version: each `data-version` span holds the latest release as a fallback, and the page replaces it with
  PyPI's latest version when it loads. Update the fallback when you release.
- The Python version (3.13+) and the license (MIT).
- The install command: `uv tool install factoid`.
- The news transcripts result: 0.92 for facts at 512 tokens, 0.87 for chunks at 2,048, and even at 8,192. If
  `examples/mediasum` publishes new numbers, update the page.
- The seven fact statuses: `current`, `superseded`, `ended`, `corrected`, `contradicted`, `replaced`, and `retracted`.
- The two papers.

Follow the repo's writing rules: plain words, short sentences, the Oxford comma, and plain headings. Do not add numbers,
customers, logos, or quotes that the repo does not support.

The "Fork me on GitHub" ribbon sits in a 150 px clipping box (120 px at viewport widths under 480 px). If you change its
text or font size, check that the full text shows at both widths.

## Approval

Ask Kyle before you add a custom domain or analytics.
