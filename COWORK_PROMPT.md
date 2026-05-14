# HVM War Room — Daily Update (Legacy Cowork Prompt)

> **Note**: This file is kept for reference only. The actual automation now runs as a
> GitHub Action — see `.github/workflows/daily-update.yml`. You no longer need to paste
> this prompt into Cowork; the workflow handles it automatically every day.

If you ever want to run a one-off manual update outside the workflow, you can still
paste the prompt below into Cowork.

---

## MANUAL PROMPT

```
Today is [TODAY'S DATE]. Update my HVM Investment OS dashboard on GitHub.

GITHUB CONFIG:
- Repo: harshvm59/war-room
- File: index.html
- Token: Read from ~/war_room_config.txt

STEP 1 — Read current index.html from GitHub API:
GET https://api.github.com/repos/harshvm59/war-room/contents/index.html
Header: Authorization: token [YOUR_TOKEN]

STEP 2 — Search the web for today's AI investment signals:

A) TOP 10 YOUTUBE VIDEOS (last 24h):
Search YouTube for AI investment videos from: Tom Nash, CNBC Fast Money,
Bloomberg Markets, Yahoo Finance, Motley Fool, ARK Invest, Andrei Jikh,
Patrick Boyle, Meet Kevin, Joseph Hogue CFA, Schwab Network, Benzinga.
For each: channel, title, date, key stocks, 2-line thesis.

B) LEADER SIGNALS (new in last 24h):
Check for new quotes/signals from: Jensen Huang, Sam Altman, Dan Ives (Wedbush),
Satya Nadella, Lisa Su, Hock Tan, Chamath, Cathie Wood, Marc Andreessen.

C) PORTFOLIO NEWS:
Check earnings, upgrades, downgrades for:
NVDA, TSLA, TSM, META, GOOGL, AMZN, PLTR, MSFT, AMD, CRWD, MU, VRT, AVGO, ASML, CEG, ANET, BE

D) THEME RATINGS:
Rate each HOT/WARM/COLD: AI Compute | Energy/Nuclear | Defense | Agentic AI | GLP-1 | Robotics

STEP 3 — Update the file:
In the downloaded index.html:
1. Add 5 new entries to YTVIDEOS array at the top with today's videos
2. Add 3 new entries to VOICES array with today's leader signals
3. Update TODAY_ACTIONS_MAY5 with today's specific action recommendations

STEP 4 — Push back to GitHub:
PUT https://api.github.com/repos/harshvm59/war-room/contents/index.html
Body: {"message": "Daily update [TODAY DATE]", "content": [base64 of updated file], "sha": [sha from step 1]}
Authorization: token [YOUR_TOKEN]

STEP 5 — Email nitrharsh@gmail.com:
Subject: "⚡ HVM War Room Updated — [TODAY DATE]"
List the 5 new videos and 3 new signals added today.
Include link: https://harshvm59.github.io/war-room
```

## PREFERRED PATH (GitHub Action)

The GitHub Action at `.github/workflows/daily-update.yml` automates the same flow:

1. Set the `ANTHROPIC_API_KEY` secret in your repo
2. The workflow runs every day at 09:00 IST
3. To trigger manually: Actions tab → "Daily War Room Update" → "Run workflow"
