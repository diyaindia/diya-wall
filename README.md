# Diya Wall

A GitHub Pages site that collects Light a Diya share links from X, Reddit and people who add their own, and lets visitors light them one tap at a time.

- `index.html`: the page. It remembers on each phone which links that visitor has already opened.
- `scrape.py`: collects links into `links.json`.
- `.github/workflows/scrape.yml`: runs the scraper every 15 minutes and whenever someone adds a link, then commits `links.json`.
- `.github/ISSUE_TEMPLATE/diya.yml`: the "Add your link" form.

## Setup

1. Push this folder to a public GitHub repo.
2. Go to **Settings → Pages** and deploy from the `main` branch, root folder.
3. Create an issue label named `diya-link`.
4. Optional keys, under **Settings → Secrets and variables → Actions**:
   - `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`: create a free "script" app at reddit.com/prefs/apps.
   - `X_BEARER_TOKEN`: needs an X API plan that includes recent search.

Sources without keys are skipped. Added links work without any keys.
