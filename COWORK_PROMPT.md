# HVM War Room — Content Refresh via Claude Cowork

The dashboard's **prices + action cards** refresh automatically and for free
(GitHub Action → `scripts/analyze_daily.py`, rule-based TA, no LLM).

The two **content feeds** — *Leader Signals* and *YouTube Intel* — are generated
by **Claude** (Cowork / Claude Code), not the paid Anthropic API. Re-run the
prompt below any time you want them refreshed. Claude writes two JSON files and
pushes; GitHub Pages redeploys and the dashboard picks them up on next load.

> The old paid-API workflows (`news-daily`, `themes-biweekly`, `framework-daily`)
> are disabled — they needed funded `ANTHROPIC_API_KEY` credits. This Cowork flow
> replaces them at zero marginal cost.

---

## How the data reaches the UI

- `data/voices.json` → prepended to the `VOICES` array → **Leader Signals** tab (`buildLeaders`)
- `data/youtube.json` → prepended to the `YTVIDEOS` array → **YouTube Intel** tab (`buildYT`)

Both are loaded by the bootstrap at the bottom of `index.html`, which merges them
into the live arrays and re-renders. **Match these schemas exactly** or cards
render blank.

### `data/voices.json`
```json
{
  "updated_at": "ISO-8601",
  "source": "claude-cowork",
  "items": [
    {
      "name": "Jensen Huang",
      "role": "CEO",
      "org": "Nvidia",
      "cat": "CEO",                         // CEO | Analyst | Investor
      "date": "YYYY-MM-DD",
      "themes": ["#NVDA", "#AI"],
      "quotes": [{ "t": "Direct quote.", "k": true }],
      "src": "https://real-source-url"
    }
  ]
}
```

### `data/youtube.json`
```json
{
  "updated_at": "ISO-8601",
  "source": "claude-cowork",
  "items": [
    {
      "ch": "Channel/publisher",
      "c": "#4a9eff",                        // accent hex
      "theme": "AI Compute",                 // AI Compute|Energy|Defense|Agentic AI|Healthcare|Robotics|Critical Minerals|Sovereign AI
      "title": "Video title",
      "date": "YYYY-MM-DD",
      "views": "Views or source label",
      "tags": ["#NVDA", "#AI"],
      "verd": "SHORT UPPERCASE VERDICT",
      "vc": "var(--green)",                  // var(--green|red|gold|blue|purple|teal|orange)
      "body": "2-3 sentence thesis with numbers.",
      "url": "https://real-source-url"
    }
  ]
}
```

> Note: the **AI Themes** tab is an evergreen market-size projection view driven
> by the inline `THEMES` const in `index.html` — it is not a daily-news feed and
> does not need refreshing. `data/themes.json` is kept for reference only.

---

## Re-run prompt (paste into Claude Cowork / Claude Code)

```
Refresh my HVM War Room content feeds in harshvm59/war-room.

1. Web-search for the last ~10 days of:
   A) 8-10 AI-investing videos/segments (Tom Nash, CNBC Fast Money, Bloomberg,
      Yahoo Finance, Motley Fool, ARK Invest, Meet Kevin, Benzinga, etc.) covering
      NVDA TSLA TSM META GOOGL AMZN PLTR MSFT AMD CRWD MU VRT AVGO ASML CEG ANET BE.
   B) 6-8 fresh quotes from Jensen Huang, Sam Altman, Dan Ives, Satya Nadella,
      Lisa Su, Hock Tan, Chamath, Cathie Wood, Marc Andreessen, Alex Karp, Jim Cramer.

2. Write data/youtube.json and data/voices.json using the EXACT schemas in
   COWORK_PROMPT.md (envelope: {updated_at, source:"claude-cowork", items:[...]}).
   Every item must have a real working URL found via search.

3. Commit + push to main. GitHub Pages auto-deploys.
```

### Or run the saved workflow
A multi-agent version (`war-room-content-refresh`) fans out the research across
parallel agents and returns schema-validated JSON for both files. Re-invoke it,
write the two files, and push — the automated equivalent of the prompt above.
