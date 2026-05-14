#!/usr/bin/env python3
"""
analyze_framework.py — runs Tom's 7-Question quality framework per holding.

Runs once per day post-market-close. For each of the 17 holdings, asks Claude
to score Pass/Fail/Caution on:

  1. GROWING — revenue trajectory 3-5y
  2. MOAT — defensive position, switching costs
  3. MANAGEMENT — capital allocation, insider activity, delivery
  4. MARGINS — gross + operating trend
  5. CASH — operating cash flow real or accounting?
  6. RISK — 3 specific downside scenarios
  7. TIMING — entry price right now

Output: data/framework.json — read by dashboard My Portfolio section.

All 17 evaluated in ONE Claude call to minimize cost (~$0.06/day = $1.3/mo).
"""

from __future__ import annotations

import json, os, re, sys
import requests
from anthropic import Anthropic
from _common import DATA_DIR, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
YAHOO_QS = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{s}?modules=summaryDetail,defaultKeyStatistics,calendarEvents,financialData,assetProfile,incomeStatementHistory,cashflowStatementHistory"
HDR = {"User-Agent": "Mozilla/5.0 (war-room-bot)"}


def load_portfolio():
    with open(PORTFOLIO_PATH) as f: doc = json.load(f)
    return doc.get("holdings", [])


def fetch_fundamentals(sym):
    try:
        r = requests.get(YAHOO_QS.format(s=sym), headers=HDR, timeout=15)
        r.raise_for_status()
        d = r.json()["quoteSummary"]["result"][0]
        sd = d.get("summaryDetail", {}) or {}
        ks = d.get("defaultKeyStatistics", {}) or {}
        fd = d.get("financialData", {}) or {}
        ap = d.get("assetProfile", {}) or {}
        ih = (d.get("incomeStatementHistory", {}) or {}).get("incomeStatementHistory", []) or []
        ch = (d.get("cashflowStatementHistory", {}) or {}).get("cashflowStatements", []) or []
        raw = lambda o, k: (o.get(k, {}) or {}).get("raw") if isinstance(o.get(k), dict) else o.get(k)

        # Revenue trend (last 3 years if available)
        rev_trend = []
        for s in ih[:3]:
            tr = raw(s, "totalRevenue")
            if tr is not None: rev_trend.append(tr)
        # Operating cash flow trend
        ocf_trend = []
        for s in ch[:3]:
            ocf = raw(s, "totalCashFromOperatingActivities")
            if ocf is not None: ocf_trend.append(ocf)
        # Gross/operating margins
        gm_trend = []
        for s in ih[:3]:
            rev = raw(s, "totalRevenue"); gp = raw(s, "grossProfit")
            if rev and gp: gm_trend.append(round(gp/rev*100, 1))
        return {
            "sector": ap.get("sector"),
            "industry": ap.get("industry"),
            "employees": ap.get("fullTimeEmployees"),
            "pe_forward": raw(sd, "forwardPE"),
            "eps_fwd": raw(ks, "forwardEps"),
            "peg": raw(ks, "pegRatio"),
            "profit_margin": raw(fd, "profitMargins"),
            "operating_margin": raw(fd, "operatingMargins"),
            "gross_margin": raw(fd, "grossMargins"),
            "rev_growth_yoy": raw(fd, "revenueGrowth"),
            "earn_growth_yoy": raw(fd, "earningsGrowth"),
            "debt_to_equity": raw(fd, "debtToEquity"),
            "current_ratio": raw(fd, "currentRatio"),
            "return_on_equity": raw(fd, "returnOnEquity"),
            "return_on_assets": raw(fd, "returnOnAssets"),
            "free_cashflow": raw(fd, "freeCashflow"),
            "operating_cashflow": raw(fd, "operatingCashflow"),
            "total_cash": raw(fd, "totalCash"),
            "total_debt": raw(fd, "totalDebt"),
            "market_cap": raw(sd, "marketCap"),
            "rec_key": fd.get("recommendationKey"),
            "target_mean": raw(fd, "targetMeanPrice"),
            "52w_high": raw(sd, "fiftyTwoWeekHigh"),
            "52w_low": raw(sd, "fiftyTwoWeekLow"),
            "revenue_3y": rev_trend,
            "operating_cashflow_3y": ocf_trend,
            "gross_margin_3y": gm_trend,
            "current_price": raw(sd, "regularMarketPrice") or raw(fd, "currentPrice"),
        }
    except Exception as e:
        print(f"[WARN] fund {sym}: {e}", file=sys.stderr); return {}


SYS_PROMPT = ("You are an institutional buy-side equity analyst running Tom's 7-Question Quality Filter Framework. For each ticker, evaluate the business across 7 dimensions and assign one of: PASS (strong yes), CAUTION (mixed), FAIL (no). Be data-driven: cite specific numbers from the input. Don't make up data — if a metric is null, say so. Concise: one sentence per question.")


PROMPT = """Date: {date}.

Evaluate each ticker against Tom's 7-Question Framework. Output a JSON array, one object per ticker. No markdown.

Schema:
{{
  "ticker": "NVDA",
  "company": "Nvidia",
  "overall": "BUY" | "HOLD" | "AVOID",
  "overall_color": "#3ddc84 (BUY)| #c9a84c (HOLD) | #e05252 (AVOID)",
  "score": 5,                       // number of PASS out of 7
  "questions": {{
    "growing":    {{"verdict": "PASS|CAUTION|FAIL", "note": "Revenue +X% YoY, 3y trajectory ..."}},
    "moat":       {{"verdict": "PASS|CAUTION|FAIL", "note": "Specific moat type ..."}},
    "management": {{"verdict": "PASS|CAUTION|FAIL", "note": "CEO track record, capital allocation ..."}},
    "margins":    {{"verdict": "PASS|CAUTION|FAIL", "note": "Gross margin X%, trend ..."}},
    "cash":       {{"verdict": "PASS|CAUTION|FAIL", "note": "FCF $X, OCF $X, trend ..."}},
    "risk":       {{"verdict": "PASS|CAUTION|FAIL", "note": "3 specific risks ..."}},
    "timing":     {{"verdict": "PASS|CAUTION|FAIL", "note": "Price vs 52w, analyst target ..."}}
  }},
  "summary": "1-sentence overall thesis in user's voice."
}}

Decision rules:
- Overall BUY: score >= 6/7 (at least 6 PASS).
- Overall HOLD: score 4-5/7.
- Overall AVOID: score <= 3/7.
- Tom's golden rule: "One NO = move on." But for the dashboard, give HOLD/AVOID rather than blanket move-on.

INPUT (each ticker has fundamentals + thesis from user):
{blob}
"""


def call_claude(blob):
    c = Anthropic(api_key=require_key())
    msg = c.messages.create(model=MODEL, max_tokens=8000, system=SYS_PROMPT,
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
        fund = fetch_fundamentals(sym)
        enriched.append({
            "ticker": sym, "name": h["name"], "theme": h["theme"], "priority": h["priority"],
            "units": h["units"], "avg_cost": h["avg_cost"],
            "thesis_note": h.get("thesis", "")[:300],
            "fundamentals": fund
        })
        print(f"[framework] {sym} fwdPE={fund.get('pe_forward')} margin={fund.get('profit_margin')}")
    if not enriched: print("[FATAL] no data"); return 1
    framework = call_claude(json.dumps(enriched, indent=2))
    print(f"[framework] got {len(framework)} evaluations")
    out = envelope(framework, source="claude-haiku+yahoo+tom-7q")
    write_json("framework.json", out)
    print(f"[DONE] wrote framework.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
