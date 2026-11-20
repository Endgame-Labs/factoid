# Landing page

The landing page at https://factoid-landing-page.netlify.app is a static page (`index.html`, `styles.css`, and
`script.js`) with no build step, no backend, and no analytics. This folder is its source. Netlify hosts it.

Netlify's agent (Agent Runner, with Gemini) wrote the first version from a prompt. The ribbon was fixed by hand. Edit
the page here, commit your changes, and deploy them with the CLI.

## Site details

| | |
| --- | --- |
| Site name | `factoid-landing-page` |
| Site ID | `89962c6b-dacb-4aa9-b877-048cdf6a2bc8` |
| URL | https://factoid-landing-page.netlify.app |
| Dashboard | https://app.netlify.com/projects/factoid-landing-page |
| Owner | Kyle's Netlify team. Ask Kyle for access. |
| Password or SSO | Off. Every deploy, including drafts, is public to anyone with its URL. |

The CLI's `--site` flag takes the site ID, not the site name.

## Setup

```sh
npm install -g netlify-cli
netlify login
netlify status          # shows the account you are logged in as
```

## Updating the page

1. Edit the files in `site/`. Open `site/index.html` in a browser to check your changes, or serve the folder with
   `python3 -m http.server -d site`.
2. Deploy a draft. Each draft gets its own URL and does not change the live site:

   ```sh
   netlify deploy --no-build --dir site --site 89962c6b-dacb-4aa9-b877-048cdf6a2bc8 --message "what changed"
   ```

3. Open the draft URL printed by the command. Check it at phone width too.
4. Publish the change. Deploy again with `--prod`:

   ```sh
   netlify deploy --no-build --prod --dir site --site 89962c6b-dacb-4aa9-b877-048cdf6a2bc8 --message "what changed"
   ```

   Or publish the exact draft you checked:

   ```sh
   netlify api restoreSiteDeploy --data '{"site_id": "89962c6b-dacb-4aa9-b877-048cdf6a2bc8", "deploy_id": "<draft deploy id>"}'
   ```

5. Commit the changes in `site/` and push so the repo matches the live site.

CLI deploys are not tied to git. The live site serves whichever deploy ran last, so always deploy from a clean checkout
of `main`.

## Rollback

Netlify keeps every deploy. To roll back, list recent deploys and publish an older one:

```sh
netlify api listSiteDeploys --data '{"site_id": "89962c6b-dacb-4aa9-b877-048cdf6a2bc8", "per_page": 10}' \
  | python3 -c 'import json, sys; [print(d["id"], d["created_at"], d["context"], d.get("title")) for d in json.load(sys.stdin)]'
netlify api restoreSiteDeploy --data '{"site_id": "89962c6b-dacb-4aa9-b877-048cdf6a2bc8", "deploy_id": "<deploy id>"}'
```

To see which deploy is live:

```sh
netlify api getSite --data '{"site_id": "89962c6b-dacb-4aa9-b877-048cdf6a2bc8"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["published_deploy"]["id"])'
```

You can also roll back in the dashboard: open Deploys, pick a deploy, and click "Publish deploy".

## Page content

The page states facts about Factoid. Keep them in step with the README:

- The version line (0.1.x), the Python version (3.13+), and the license (MIT).
- The install command: `uv tool install factoid`.
- The news transcripts result: 0.92 for facts at 512 tokens, 0.87 for chunks at 2,048, and even at 8,192. If
  `examples/iscrag` publishes new numbers, update the page.
- The seven fact statuses: `current`, `superseded`, `ended`, `corrected`, `contradicted`, `replaced`, and `retracted`.
- The two papers.

Follow the repo's writing rules: plain words, short sentences, the Oxford comma, and plain headings. Do not add numbers,
customers, logos, or quotes that the repo does not support.

The "Fork me on GitHub" ribbon sits in a 150 px clipping box (120 px at viewport widths under 480 px). If you change its
text or font size, check that the full text shows at both widths.

## Approval

Ask Kyle before you add a custom domain, connect the site to a git repo, or delete the site. Also ask before turning on
forms, analytics, or functions.
