#!/usr/bin/env python3
"""
analyze_framework.py — Tom's 7-Question quality filter per holding.

Runs once daily post-market-close. Uses Claude's training knowledge for
fundamentals (since Yahoo quoteSummary 401s from GitHub IPs). Yahoo `chart`
endpoint works fine for current price + 52w range.

Output: data/framework.json with PASS/CAUTION/FAIL per question + overall
BUY/HOLD/AVOID verdict per stock.
"""

from __future__ import annotations

import json, os, re, sys
import requests
from anthropic import Anthropic
from _common import DATA_DIR, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=1y&interval=1d&includePrePost=false"
HDR = {"User-Agent": "Mozilla/5.0 (war-room-bot)"}


def load_portfolio():
    with open(PORTFOLIO_PATH) as f: doc = json.load(f)
    return doc.get("holdings", [])


def fetch_price_info(sym):
    try:
        r = requests.get(YAHOO_CHART.format(s=sym), headers=HDR, timeout=15); r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        meta = res.get("meta", {})
        ind = res["indicators"]["quote"][0]
        closes = [c for c in ind["close"] if c is not None]
        highs = [h for h in ind["high"] if h is not None]
        lows = [l for l in ind["low"] if l is not None]
        return {
            "current_price": closes[-1] if closes else None,
            "52w_high": max(highs) if highs else None,
            "52w_low": min(lows) if lows else None,
            "ytd_pct": round((closes[-1]/closes[0]-1)*100, 1) if len(closes) >= 2 else None,
        }
    except Exception as e:
        print(f"[WARN] price {sym}: {e}", file=sys.stderr); return {}


SYS_PROMPT = ("You are an institutional buy-side equity analyst running Tom's 7-Question Quality Filter. Use your training knowledge of fundamentals (revenue trend, margins, FCF, management quality, moat, sector dynamics) for each ticker. Be specific and data-driven; cite numbers from training data + provided current price/52w range. Concise: one sentence per question.")


PROMPT = """Date: {date}.

Evaluate each ticker against Tom's 7-Question Framework. For fundamentals you don't have live data on, use your training knowledge (cite period if relevant). Output as JSON array, no markdown.

Schema per ticker:
{{
  "ticker": "NVDA",
  "company": "Nvidia",
  "overall": "BUY" | "HOLD" | "AVOID",
  "overall_color": "#3ddc84" | "#c9a84c" | "#e05252",
  "score": 5,
  "questions": {{
    "growing":    {{"verdict": "PASS|CAUTION|FAIL", "note": "Revenue +X% YoY, 3y trajectory ..."}},
    "moat":       {{"verdict": "PASS|CAUTION|FAIL", "note": "Type of moat, specific ..."}},
    "management": {{"verdict": "PASS|CAUTION|FAIL", "note": "CEO track record, capital allocation ..."}},
    "margins":    {{"verdict": "PASS|CAUTION|FAIL", "note": "Gross/op margin, trend ..."}},
    "cash":       {{"verdict": "PASS|CAUTION|FAIL", "note": "FCF, OCF quality, balance sheet ..."}},
    "risk":       {{"verdict": "PASS|CAUTION|FAIL", "note": "3 specific risks (regulatory/comp/macro/debt) ..."}},
    "timing":     {{"verdict": "PASS|CAUTION|FAIL", "note": "Price vs 52w, sector momentum, catalysts ..."}}
  }},
  "summary": "1-sentence overall thesis."
}}

Rules:
- BUY: 6 or 7 PASS
- HOLD: 4-5 PASS
- AVOID: 0-3 PASS
- overall_color: BUY=#3ddc84, HOLD=#c9a84c, AVOID=#e05252

INPUT (current prices + thesis from user):
{blob}
"""


def call_claude(blob):
    c = Anthropic(api_key=require_key())
    msg = c.messages.create(model=MODEL, max_tokens=16000, system=SYS_PROMPT,
        messages=[{"role": "user", "content": PROMPT.format(date=now_ist().strftime("%a %b %-d, %Y"), blob=blob)}])
    raw = (msg.content[0].text if msg.content else "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1: raise ValueError(f"No JSON array:\n{raw[:500]}")
    return json.loads(raw[s:e+1])


def main():
    print(f"[framework] {now_ist().isoformat()}")
    holdings = load_portfolio()
    print(f"[framework] {len(holdings)} holdings")
    enriched = []
    for h in holdings:
        sym = h["ticker"]
        price = fetch_price_info(sym)
        enriched.append({
            "ticker": sym, "name": h["name"], "theme": h["theme"], "priority": h["priority"],
            "units": h["units"], "avg_cost": h["avg_cost"],
            "thesis_note": h.get("thesis", "")[:300],
            "current_price": price.get("current_price"),
            "52w_high": price.get("52w_high"),
            "52w_low": price.get("52w_low"),
            "ytd_pct": price.get("ytd_pct"),
        })
        print(f"[framework] {sym} ${price.get('current_price')}")
    if not enriched: print("[FATAL] no data"); return 1
    framework = call_claude(json.dumps(enriched, indent=2))
    print(f"[framework] got {len(framework)} evaluations")
    out = envelope(framework, source="claude-haiku+yahoo-chart+tom-7q")
    write_json("framework.json", out)
    print(f"[DONE] wrote framework.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
