# How to apply this automation to your `war-room` repo

Estimated time: **15 minutes**. After this, the dashboard updates itself
on three independent cadences and you never have to paste a Cowork prompt again.

---

## 1. Clone the repo locally (if you haven't already)

In GitHub Desktop:
- File → Clone repository → `harshvm59/war-room` → choose a folder
  (e.g. `~/Documents/war-room`)

Or in Terminal:
```bash
git clone https://github.com/harshvm59/war-room.git ~/Documents/war-room
```

## 2. Copy these files into the repo

Everything in this `war-room-automation/` folder maps 1:1 to where it should
live in the repo. From your terminal:

```bash
cd ~/Documents/war-room

# Overwrite docs with fixed versions (placeholder usernames replaced)
cp ~/Documents/war-room-automation/README.md .
cp ~/Documents/war-room-automation/COWORK_PROMPT.md .

# Copy automation
cp -r ~/Documents/war-room-automation/.github .
cp -r ~/Documents/war-room-automation/scripts .
cp -r ~/Documents/war-room-automation/data .
```

## 3. Patch `index.html` (one-time, ~30 seconds)

Open `index.html` in any editor. Scroll to the very bottom and find the
closing `</body>` tag. Right before that line, paste the entire contents of
`patches/index-bootstrap.html`.

That's the only HTML change. The bootstrap will:
- fetch the freshly-committed JSON files on every page load
- override the inline arrays with live data
- silently fall back to the hardcoded arrays if a fetch fails
- poll `data/actions.json` every 60 seconds for intraday updates

## 4. Fix two stale strings in `index.html` (optional but recommended)

These are small one-liner search-and-replaces:

| Line | Find                                         | Replace with                                |
|------|----------------------------------------------|---------------------------------------------|
| 11   | `https://har-mourya.github.io/war-room`      | `https://harshvm59.github.io/war-room`      |
| 2071 | `Live · May 4, 2026`                         | (the daily script will overwrite this)      |

## 5. Add the Anthropic API key as a repo secret

1. Go to https://github.com/harshvm59/war-room/settings/secrets/actions
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your key from https://console.anthropic.com/settings/keys
5. Save

GitHub Actions will inject this into every script run. The key never appears
in commits or logs.

## 6. Commit & push

In GitHub Desktop:
- You'll see ~15 changed/new files
- Summary: `Wire up full automation — JSON data files + 3 workflows`
- Commit to `main` → Push

Or in Terminal:
```bash
git add .
git commit -m "Wire up full automation"
git push
```

## 7. Sanity-check the first run

After pushing:

1. Go to **Actions** tab on GitHub
2. You'll see three workflows enabled:
   - **Actions Refresh (15-min intraday)** — only runs during US market hours (Mon–Fri, 13:30–20:00 UTC)
   - **Daily News + YouTube Scrape** — runs 03:30 UTC daily
   - **Themes Refresh (every 2 days)** — runs 03:30 UTC on odd-numbered days
3. To test immediately, pick any one and click **Run workflow** → branch `main`.
4. Wait ~1 min, then check the **commits** view of your repo. You should see
   a new commit by `war-room-bot` updating one of the `data/*.json` files.
5. Hard-refresh your live dashboard at https://harshvm59.github.io/war-room —
   the "Synced …" timestamp at the top (added by the bootstrap) should update.

## 8. (Optional) Wire up the in-page Claude features

Your existing `index.html` makes five fetches to `api.anthropic.com` directly
from the browser, but none of them include an `x-api-key` header — so the
"Daily AI Brief" and similar in-page features have never actually worked.

**Recommended**: leave them disabled. The new server-side automation gives you
fresher data without exposing your API key on a public webpage.

If you really want to re-enable them, add a Settings modal that takes the user's
own key, stores it in `localStorage`, and injects it into the fetch headers. I
can build that next — just ask.

---

## What runs and when

| Workflow                  | Cadence                                 | What it touches                              |
|---------------------------|-----------------------------------------|----------------------------------------------|
| `actions-15min.yml`       | Every 15 min, Mon–Fri 13:30–20:00 UTC   | `data/actions.json`                          |
| `news-daily.yml`          | Daily, 03:30 UTC (= 09:00 IST)          | `data/news.json`, `youtube.json`, `voices.json` |
| `themes-biweekly.yml`     | Odd-numbered days, 03:30 UTC            | `data/themes.json`                           |

## Cost estimate

| Item                    | Volume                                | Estimate              |
|-------------------------|---------------------------------------|-----------------------|
| Sonnet 4.5 input/output | ~28 calls/day intraday + 1.5 daily    | ~$25/month            |
| Anthropic web_search    | ~1 daily + 0.5 biweekly = ~45/month   | ~$5/month             |
| GitHub Actions minutes  | ~30 min/day                           | **free** (public repo)|
| GitHub Pages bandwidth  | ~3 KB/refresh                         | **free**              |

**Total: ~$25–35 / month.** Drop the 15-min cadence to 30-min if you want
to halve it; edit the cron in `actions-15min.yml`.

## Troubleshooting

- **A workflow shows red ❌** — click into it, expand the failing step. Most
  common failure is rate limits or a malformed Claude response; the script
  will exit non-zero and nothing gets committed (dashboard stays as-is).
- **`data/actions.json` looks stale on the live page** — hard-refresh
  (Cmd+Shift+R). GitHub Pages caches aggressively; the bootstrap uses
  `?t=Date.now()` to bypass it on fetch, but the HTML itself is cached.
- **GitHub Actions cron is delayed** — known limitation. The 15-min
  workflow may sometimes fire 20–30 min late during GitHub peak load. Not
  fixable without moving off GitHub Actions.
- **You hit Anthropic rate limits** — the 15-min workflow uses ~1 req/min
  during market hours. If you're on free tier, upgrade to Build tier ($5
  minimum top-up gets you 5 RPM, plenty).

## Rolling back

Every change is in git. If you want to disable an automation, either:
- Delete the workflow file and push, or
- In the Actions tab, click the workflow → "..." → Disable workflow.

The `data/*.json` files will go stale but the dashboard keeps working off
its hardcoded fallback arrays. Nothing breaks.
