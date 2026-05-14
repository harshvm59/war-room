# HVM Investment OS — Millionaire Dashboard

> **$100K → $1,000,000** · AI-Powered Investment Intelligence Platform

[![GitHub Pages](https://img.shields.io/badge/Live-GitHub%20Pages-gold)](https://harshvm59.github.io/war-room)
[![Portfolio](https://img.shields.io/badge/Portfolio-$96.5K-green)](https://harshvm59.github.io/war-room)
[![Return](https://img.shields.io/badge/Return-%2B68.24%25-brightgreen)](https://harshvm59.github.io/war-room)
[![Daily Update](https://github.com/harshvm59/war-room/actions/workflows/daily-update.yml/badge.svg)](https://github.com/harshvm59/war-room/actions/workflows/daily-update.yml)

## 🚀 Live Features

- **Real-time stock prices** — Yahoo Finance API, auto-refreshes every 60 seconds
- **17 live positions** — DCA module + 5 legend investor analysis per stock
- **AI Daily Brief** — Claude API generates fresh investment brief on page open
- **30+ Leader Signals** — Jensen Huang, Sam Altman, Dan Ives, Chamath + 30 more
- **YouTube Intel** — 30+ videos across 8 AI investment themes, daily scrapes
- **AI Themes P0-P3** — Interactive charts, daily news, filter by priority
- **Deploy Capital** — Real-time actionable recommendations per stock
- **Conviction Picks** — Top 10 ranked by 100%+ probability

## 🌐 Hosting on GitHub Pages

Live at: `https://harshvm59.github.io/war-room`

Settings → Pages → Source → `main` branch → `/ (root)`

## 🔄 Daily Auto-Update via GitHub Actions

A GitHub Action runs daily at **09:00 IST** (03:30 UTC) and:

1. Calls the Anthropic API for fresh action recommendations
2. Patches `index.html` (replaces the `TODAY_ACTIONS_MAY5` array + live date stamp)
3. Commits and pushes the change back to `main`
4. GitHub Pages auto-deploys

See `.github/workflows/daily-update.yml` and `scripts/daily_update.py`.

### One-time setup

1. Settings → Secrets and variables → Actions → New repository secret
2. Name: `ANTHROPIC_API_KEY` · Value: your key from [console.anthropic.com](https://console.anthropic.com)
3. Optional: trigger a manual run from the **Actions** tab → "Daily War Room Update" → "Run workflow"

## 🔑 API Keys Needed

| Service        | Purpose                            | Cost         |
| -------------- | ---------------------------------- | ------------ |
| Anthropic      | Daily update + in-page AI features | Pay per use  |
| Yahoo Finance  | Live stock prices                  | **FREE**     |
| Finnhub        | Backup prices + news               | Free tier    |
| GitHub Actions | Daily auto-update                  | **FREE**     |

## 📊 Stack

- **Frontend**: Pure HTML/CSS/JS — zero dependencies, zero build step
- **APIs**: Anthropic Claude, Yahoo Finance v7, allorigins CORS proxy
- **Hosting**: GitHub Pages (free, global CDN)
- **Automation**: GitHub Actions (daily 09:00 IST)
- **Database**: localStorage (client-side, no server needed)

## 🛣️ Roadmap to Productize

### Phase 1 — Personal Dashboard (NOW ✅)

- [x] Live stock prices
- [x] Daily AI brief
- [x] Portfolio tracking
- [x] Leader signals
- [x] Daily auto-update via GitHub Actions

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
