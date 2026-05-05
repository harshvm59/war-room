# HVM Investment OS — Millionaire Dashboard

> **$100K → $1,000,000** · AI-Powered Investment Intelligence Platform

[![GitHub Pages](https://img.shields.io/badge/Live-GitHub%20Pages-gold)](https://YOUR_USERNAME.github.io/war-room)
[![Portfolio](https://img.shields.io/badge/Portfolio-$96.5K-green)](https://YOUR_USERNAME.github.io/war-room)
[![Return](https://img.shields.io/badge/Return-%2B68.24%25-brightgreen)](https://YOUR_USERNAME.github.io/war-room)

## 🚀 Live Features

- **Real-time stock prices** — Yahoo Finance API, auto-refreshes every 60 seconds
- **17 live positions** — DCA module + 5 legend investor analysis per stock
- **AI Daily Brief** — Claude API generates fresh investment brief on page open
- **30+ Leader Signals** — Jensen Huang, Sam Altman, Dan Ives, Chamath + 30 more
- **YouTube Intel** — 30+ videos across 8 AI investment themes, daily scrapes
- **AI Themes P0-P3** — Interactive charts, daily news, filter by priority
- **Deploy Capital** — Real-time actionable recommendations per stock
- **Conviction Picks** — Top 10 ranked by 100%+ probability

## 🌐 Hosting on GitHub Pages (5 min setup)

1. Fork this repo or create new repo named `war-room`
2. Upload `index.html` to the repo root
3. Go to **Settings → Pages → Source → main branch → / (root)**
4. Your URL: `https://YOUR_USERNAME.github.io/war-room`

## 🔄 Daily Auto-Update via Cowork

Your Cowork routine updates this file daily at 9AM:
```
Repo: YOUR_USERNAME/war-room  
File: index.html
Token: [stored in ~/war_room_config.txt]
```

See `COWORK_PROMPT.md` for the exact routine prompt.

## 🔑 API Keys Needed

| Service | Purpose | Cost |
|---------|---------|------|
| Anthropic | Daily brief + AI analysis | Pay per use |
| Yahoo Finance | Live stock prices | **FREE** |
| Finnhub | Backup prices + news | Free tier |
| GitHub API | Daily auto-update | **FREE** |

## 📊 Stack

- **Frontend**: Pure HTML/CSS/JS — zero dependencies, zero build step
- **APIs**: Anthropic Claude, Yahoo Finance v7, allorigins CORS proxy  
- **Hosting**: GitHub Pages (free, global CDN)
- **Automation**: Claude Cowork routine (daily 9AM)
- **Database**: localStorage (client-side, no server needed)

## 🛣️ Roadmap to Productize

### Phase 1 — Personal Dashboard (NOW ✅)
- [x] Live stock prices
- [x] Daily AI brief
- [x] Portfolio tracking
- [x] Leader signals

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
