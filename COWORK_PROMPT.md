# HVM War Room — Daily Update Cowork Prompt

Copy this EXACTLY into your Cowork routine. Schedule: Daily at 9:00 AM.

---

## PROMPT

```
Today is [TODAY'S DATE]. Update my HVM Investment OS dashboard on GitHub.

GITHUB CONFIG:
- Repo: YOUR_USERNAME/war-room  
- File: index.html
- Token: Read from ~/war_room_config.txt

STEP 1 — Read current index.html from GitHub API:
GET https://api.github.com/repos/YOUR_USERNAME/war-room/contents/index.html
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
PUT https://api.github.com/repos/YOUR_USERNAME/war-room/contents/index.html
Body: {"message": "Daily update [TODAY DATE]", "content": [base64 of updated file], "sha": [sha from step 1]}
Authorization: token [YOUR_TOKEN]

STEP 5 — Email nitrharsh@gmail.com:
Subject: "⚡ HVM War Room Updated — [TODAY DATE]"
List the 5 new videos and 3 new signals added today.
Include link: https://YOUR_USERNAME.github.io/war-room
```

## SETUP STEPS

1. Create ~/war_room_config.txt with your GitHub token on line 1
2. Replace YOUR_USERNAME with your actual GitHub username
3. Set Cowork to run Daily at 9:00 AM
4. Click "Select Folder" → point to your Downloads folder
5. First run: click "Run Now" to test
