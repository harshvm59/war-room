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

Settings → Pages → Source → `main` branch → `/ (root)`

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
| Seven-question framework | 22:30 UTC daily | Funded Anthropic API; previous output is retained and labelled stale when blocked |
| Broker holdings | 09:00, 19:00, 21:00 and 23:00 IST on the owner's Mac | Mac available, authenticated INDMoney connection and network |

GitHub schedules are best effort and can run late. Prices do not change merely because a weekend refresh ran. Broker holdings are a separate local sync; public cloud jobs do not access broker credentials.

`data/refresh-status-{feed}.json` records the last attempt, last successful packet timestamp, dependency failure and workflow link. Failed updates preserve prior source timestamps. RSS items retain their actual publication dates and must pass the freshness filter. An empty verified feed replaces old items instead of keeping historical headlines under a current date.

### Refresh regression checks

```sh
python -m unittest discover -s scripts -p 'test_refresh*.py'
node --test scripts/test_refresh*.mjs
node scripts/test_cohort_planner.mjs
```

## 🔑 API Keys

| Service        | Purpose                                         | Required?                  |
| -------------- | ----------------------------------------------- | -------------------------- |
| Yahoo Finance  | Prices + history for TA (server-side, no key)   | **No key — FREE**          |
| GitHub Actions | Runs the pipeline + commits data                | **FREE**                   |
| Telegram Bot   | Optional digest push                            | Optional                   |
| Anthropic      | Written framework and optional research enrichment | Funded key required for framework |

The core dashboard (prices + action cards) needs **no API keys at all.**

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
