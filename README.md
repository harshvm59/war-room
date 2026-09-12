# HVM Investment OS — Millionaire Dashboard

> **$100K → $1,000,000** · AI-themed Investment Intelligence Platform

[![GitHub Pages](https://img.shields.io/badge/Live-GitHub%20Pages-gold)](https://harshvm59.github.io/war-room)
[![Portfolio](https://img.shields.io/badge/Portfolio-$106K-green)](https://harshvm59.github.io/war-room)
[![Return](https://img.shields.io/badge/Return-%2B82%25-brightgreen)](https://harshvm59.github.io/war-room)
[![Daily TA](https://github.com/harshvm59/war-room/actions/workflows/analyze-daily.yml/badge.svg)](https://github.com/harshvm59/war-room/actions/workflows/analyze-daily.yml)

## 🚀 Live Features

- **Live stock prices** — fetched server-side from Yahoo and committed to `data/prices.json`; the page reads that (no API key in the browser, no blocked cross-origin calls). Refreshes every ~30 min during market hours.
- **17 live positions** — DCA module + 5 legend-investor analyses per stock
- **Daily action cards** — generated server-side from technical analysis (RSI / MACD / SMA) by a deterministic rule engine. **No LLM, no API key, no per-view cost.**
- **30+ Leader Signals** — Jensen Huang, Sam Altman, Dan Ives, Chamath + more
- **AI Themes P0–P3** — interactive charts, filter by priority
- **Deploy Capital** — actionable recommendations per stock
- **Conviction Picks** — ranked by conviction

## 🌐 Hosting on GitHub Pages

Live at: `https://harshvm59.github.io/war-room`

Settings → Pages → Source → **GitHub Actions**. `deploy-pages.yml` publishes the public site from the latest `main` checkout after refresh workflows complete and after site pushes.

## 🔄 Auto-Update via GitHub Actions

`analyze-daily.yml` runs every ~30 min during US market hours (plus an after-close run) and:

1. Pulls 6 months of daily OHLCV per ticker from Yahoo's v8 chart endpoint (free, no key — works from GitHub runners even though it blocks browsers)
2. Computes RSI / MACD / SMA20-50-200 / returns / volume ratios
3. Generates action cards with a **deterministic rule engine** (`scripts/analyze_daily.py` → `generate_actions`) — no external API
4. Writes `data/actions.json` + `data/prices.json` and commits to `main`; GitHub Pages auto-deploys
5. Optionally pushes a plain-text Telegram digest (if `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` secrets are set)

Trigger manually: **Actions** tab → "Daily TA Analysis" → "Run workflow", or
`gh workflow run analyze-daily.yml`.

### Published data refresh

The dashboard checks all published feeds every 60 seconds and when the tab returns to the foreground. **Refresh dashboard**, **Refresh Now**, and **Refresh Brief** reload published data and report the source timestamp separately from the time the browser checked it. Loading a file does not regenerate server research.

To regenerate public feeds now, open [Refresh all dashboard feeds](https://github.com/harshvm59/war-room/actions/workflows/refresh-all.yml), sign in to GitHub, and choose **Run workflow** on `main`. This run refreshes prices, actions, news, themes, framework and agent packets without sending a Telegram message. It publishes individual source status even if another source fails.

| Source | Server schedule | Dependency |
| --- | --- | --- |
| Prices and technical signals | Every 30 minutes, 14:00–20:30 UTC weekdays; 21:30 UTC after-close run | Yahoo public market data |
| News, leader signals, YouTube/source links | 03:30 UTC daily; 13:35 and 17:35 UTC weekdays | Public RSS fallback continues when paid research is unavailable |
| Themes | 03:45 UTC daily; 13:45 and 17:45 UTC weekdays | Public RSS and deterministic cohort calculations |
| Agent workboard | Hourly at :15 UTC | Published research packets and source checks |
| Seven-question framework | 22:30 UTC daily | OpenAI API; one paid attempt per IST day, previous output retained when blocked |
| Broker holdings | 09:00, 19:00, 21:00 and 23:00 IST on the owner's Mac | Mac available, authenticated INDMoney connection and network |

All cloud feed writers share one concurrency group, preventing manual refreshes from racing scheduled writers. GitHub may coalesce queued runs. `deploy-pages.yml` also listens for their completion (including partial failures), checks out the newest `main`, and deploys the public site files. This is required because a normal `GITHUB_TOKEN` push does not trigger a Pages build.

GitHub schedules are best effort and can run late. Prices do not change merely because a weekend refresh ran. Broker holdings are a separate local sync; public cloud jobs do not access broker credentials.

`data/refresh-status-{feed}.json` records the last attempt, last successful packet timestamp, dependency failure and workflow link. Failed updates preserve prior source timestamps. RSS items retain their actual publication dates and must pass the freshness filter. An empty verified feed replaces old items instead of keeping historical headlines under a current date.

### Refresh regression checks

```sh
python -m unittest discover -s scripts -p 'test_*.py'
node --test scripts/test_refresh*.mjs
node scripts/test_cohort_planner.mjs
```

## 🔑 API Keys

| Service        | Purpose                                         | Required?                  |
| -------------- | ----------------------------------------------- | -------------------------- |
| Yahoo Finance  | Prices + history for TA (server-side, no key)   | **No key — FREE**          |
| GitHub Actions | Runs the pipeline + commits data                | **FREE**                   |
| Telegram Bot   | Optional digest push                            | Optional                   |
| OpenAI API     | Daily source-linked research and written framework | Separate API billing; OPENAI_API_KEY secret |

The core dashboard (prices + action cards) needs **no AI API keys at all.**

### Switch to OpenAI with a $10 monthly budget

1. Create a dedicated **HVM Dashboard** project in [OpenAI Platform](https://platform.openai.com/).
2. Add $10 of API credit in [Billing](https://platform.openai.com/settings/organization/billing/overview). Keep automatic recharge off if you want to approve each top-up yourself. ChatGPT subscription billing is separate from API usage.
3. In the project's **Limits → Spend → Edit spend limit**, set **$8** and enable **Enforce a hard limit**. A spend alert alone does not stop requests. OpenAI notes enforcement can lag slightly; the $2 buffer leaves room. See [spend controls](https://developers.openai.com/api/docs/guides/spend-limits).
4. Create a project API key at [API keys](https://platform.openai.com/api-keys), with permission to create Responses. Add it in [this repo's Actions secrets](https://github.com/harshvm59/war-room/settings/secrets/actions) as **OPENAI_API_KEY**. Never put it in HTML, JavaScript, a commit or chat.
5. Run [Refresh all dashboard feeds](https://github.com/harshvm59/war-room/actions/workflows/refresh-all.yml). Confirm an OpenAI source timestamp and successful usage entry in `.github/ai-usage.json`. After the first successful OpenAI run, the unused **ANTHROPIC_API_KEY** repository secret can be deleted. This repository no longer calls Anthropic; cancelling or changing billing for other Anthropic applications is separate.

The model is **gpt-5.6-luna**, using the Responses API with live web search. Prices checked September 12, 2026: $0.20 per million input tokens, $1.20 per million output tokens, plus $0.01 per search and search-content tokens. [Current pricing](https://developers.openai.com/api/docs/pricing).

The same guard covers scheduled, manual and concurrent runs. Before each paid call, a durable GitHub ledger atomically reserves that feed's slot for the IST calendar day. At most one paid attempt each for news, themes and framework is permitted daily. An uncertain timeout or failed call consumes the slot; the application never automatically retries a paid request. News/themes allow up to four searches each and framework up to six. Output limits are 6,000 / 6,000 / 14,000 tokens. Browser refreshes incur no AI charge.

For 31 days, the search allowance is at most 434 calls ($4.34). Maximum generated tokens at those limits cost about $0.97; input/search-context tokens are additional. A normal month is **estimated around $6–8**, not yet measured for this integration. The app stops new paid calls when its recorded/reserved estimate would exceed $8. This is an application estimate, not a substitute for the provider's hard spend limit; it excludes taxes, other projects and future price changes.

Free RSS, prices, leader monitoring and deterministic cohort calculations retain their existing schedules. Later same-day refreshes use those free sources and clearly report the paid-research daily limit. Missing keys, exhausted credit or an unavailable budget ledger cannot freeze free feeds. Framework failures keep the previous dated assessment. Framework figures are AI summaries with links and reporting periods; they are not independently reconciled financial data. Missing evidence is shown as REVIEW/CAUTION. Switching providers does not validate the separate technical trading rules or allocation engine.

Do not delete or reset `.github/ai-usage.json`: it stores reservation and usage metadata across runner restarts. It contains no API keys, prompts or model text. Only the paid-call guard writes it during operation, using GitHub's commit-SHA conflict checks. A missing/corrupt ledger blocks paid calls until repaired.

## 📊 Stack

- **Frontend**: Pure HTML/CSS/JS — zero dependencies, zero build step
- **Data**: Yahoo Finance v8 chart (server-side), committed JSON in `data/`
- **Hosting**: GitHub Pages (free, global CDN)
- **Automation**: GitHub Actions (every ~30 min, market hours)
- **Storage**: static JSON files + browser `localStorage` (no server)

## 🛣️ Roadmap to Productize

### Phase 1 — Personal Dashboard (NOW ✅)

- [x] Live (server-side) stock prices
- [x] Daily rule-based action cards (no LLM dependency)
- [x] Portfolio tracking
- [x] Leader signals
- [x] Auto-update via GitHub Actions

### Phase 2 — Multi-User SaaS (Month 2-3)

- [ ] Supabase auth (email login)
- [ ] User portfolios stored in DB
- [ ] Stripe payments ($29/month)
- [ ] Custom portfolio input UI

### Phase 3 — Scale (Month 4-6)

- [ ] Mobile app (React Native)
- [ ] Email digest delivery
- [ ] Discord bot
- [ ] API for developers

## ⚡ Not Financial Advice

All data is for educational purposes. Do your own research.
