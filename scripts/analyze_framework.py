#!/usr/bin/env python3
"""Source-linked seven-question quality summaries for each portfolio holding.

A bounded OpenAI web-search request gathers cited company disclosures and reporting
periods. Missing evidence remains CAUTION / REVIEW, never a memory-derived score.
Financial figures remain explicitly unreconciled; this job does not execute trades.
"""

from __future__ import annotations

import json, os, sys
from urllib.parse import urlparse
from datetime import datetime, timezone
import requests
from _research import research_json
from _common import DATA_DIR, envelope, now_ist, write_json

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
            "quote_as_of": datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc).isoformat() if meta.get("regularMarketTime") else None,
            "52w_high": max(highs) if highs else None,
            "52w_low": min(lows) if lows else None,
            "return_1y_pct": round((closes[-1]/closes[0]-1)*100, 1) if len(closes) >= 2 else None,
        }
    except Exception as e:
        print(f"[WARN] price {sym}: {e}", file=sys.stderr); return {}


QUESTION_KEYS = ("growing", "moat", "management", "margins", "cash", "risk", "timing")
QUALITY_WARNING = "AI summary with linked sources; financial figures are not independently reconciled."

SYS_PROMPT = (
    "You summarize linked primary equity disclosures using web search. Prefer company investor-relations "
    "releases and regulatory filings. Use only figures supported by an opened source and name their reporting "
    "periods; never supply financial facts from training memory. Treat supplied portfolio thesis notes as "
    "unverified user assumptions, not evidence. Missing evidence must be explicit and must not become a buy "
    "or sell conclusion. Do not invent quotes, URLs, reporting periods or publication dates."
)

PROMPT = """Research time: {date}.
Evaluate every supplied ticker exactly once using the seven questions below. Return a JSON array only.
Search for current company disclosures and recent primary evidence. A complete array is required even where
evidence is missing: emit unknown questions with CAUTION and an overall REVIEW for those rows.

Each row must have ticker, company, overall (BUY|HOLD|AVOID|REVIEW), overall_color, score (0-7), summary,
sources:[{{url,title,published,reporting_period}}], and questions with exactly these keys:
growing, moat, management, margins, cash, risk, timing.
Each question must be {{"verdict":"PASS|CAUTION|FAIL", "note":"one short factual explanation or explicit unknown",
"evidence_status":"supported|unknown", "source_urls":[], "reporting_period":"period or null"}}.
Every supported question needs at least one source_urls entry matching its row's sources and a reporting_period.
Use actual direct article/filing URLs, never search-result URLs. The source's reporting_period must identify
its fiscal quarter/year or dated as-of period. published is the actual source publication date/timestamp;
use null when unavailable. Never substitute the research date for an unknown publication date.
A source link alone does not reconcile figures; describe this as a source-linked AI summary.

Topics: growing=revenue trajectory; moat=competitive durability; management=capital allocation;
margins=gross/operating margin trend; cash=FCF/OCF and balance sheet; risk=material downside;
timing=current valuation/catalysts using dated evidence.
Scoring: count supported PASS answers. If any answer lacks evidence, overall MUST be REVIEW regardless of score.
Only when all seven questions have linked support: 6-7 PASS -> BUY, 4-5 -> HOLD, 0-3 -> AVOID.
Colors: BUY=#3ddc84, HOLD=#c9a84c, AVOID=#e05252, REVIEW=#c9a84c.
Do not fabricate missing values or direct quotes. No trade is authorized by this output.

INPUT (dated market context and unverified portfolio thesis assumptions):
{blob}
"""


def valid_source_url(value) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and parsed.hostname not in {"localhost", "127.0.0.1"}


def validate_framework(data, expected_tickers: list[str]) -> list[dict]:
    """Reject malformed/partial responses and make unsupported conclusions REVIEW."""
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("Invalid framework response: expected an array of ticker rows")
    got = [row.get("ticker") for row in data]
    if len(got) != len(expected_tickers) or any(not isinstance(ticker, str) for ticker in got) or set(got) != set(expected_tickers) or len(set(got)) != len(got):
        raise ValueError("Framework ticker coverage does not match the portfolio")
    validated = []
    for row in data:
        if not isinstance(row.get("company"), str) or not row["company"].strip() or not isinstance(row.get("summary"), str):
            raise ValueError("Invalid framework company or summary")
        questions, sources = row.get("questions"), row.get("sources")
        if not isinstance(questions, dict) or set(questions) != set(QUESTION_KEYS) or not isinstance(sources, list):
            raise ValueError("Invalid framework questions or sources schema")
        source_by_url = {}
        for source in sources:
            if not isinstance(source, dict) or not valid_source_url(source.get("url")) or not isinstance(source.get("title"), str) or not source["title"].strip():
                raise ValueError("Invalid framework source link or title")
            source_by_url[source["url"]] = source
        normalized = {}
        unknown = False
        for key in QUESTION_KEYS:
            q = questions[key]
            if not isinstance(q, dict) or q.get("verdict") not in {"PASS", "CAUTION", "FAIL"} or not isinstance(q.get("note"), str) or not q["note"].strip():
                raise ValueError("Invalid framework question verdict or note")
            refs = q.get("source_urls", [])
            if not isinstance(refs, list) or any(not isinstance(url, str) or not valid_source_url(url) or url not in source_by_url for url in refs):
                raise ValueError("Framework question references an invalid or unlisted source")
            period = q.get("reporting_period")
            supported = (
                q.get("evidence_status") == "supported" and bool(refs)
                and isinstance(period, str) and bool(period.strip())
                and all(isinstance(source_by_url[url].get("reporting_period"), str) and source_by_url[url]["reporting_period"].strip() for url in refs)
            )
            clean = dict(q)
            if not supported:
                unknown = True
                clean.update(verdict="CAUTION", evidence_status="unknown")
                clean["note"] = "Evidence unavailable or insufficient for this question; review required."
            normalized[key] = clean
        score = sum(q["verdict"] == "PASS" for q in normalized.values())
        overall = "REVIEW" if unknown else "BUY" if score >= 6 else "HOLD" if score >= 4 else "AVOID"
        summary = "Evidence is incomplete; review the linked disclosures before any investment decision." if unknown else row["summary"]
        validated.append({**row, "questions": normalized, "score": score, "overall": overall, "summary": summary,
                          "overall_color": {"BUY":"#3ddc84", "HOLD":"#c9a84c", "AVOID":"#e05252", "REVIEW":"#c9a84c"}[overall]})
    return validated


def call_research(blob):
    holdings = json.loads(blob)
    data = research_json("framework", PROMPT.format(date=now_ist().isoformat(), blob=blob), system=SYS_PROMPT)
    return validate_framework(data, [row["ticker"] for row in holdings])


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
            "return_1y_pct": price.get("return_1y_pct"),
            "quote_as_of": price.get("quote_as_of"),
        })
        print(f"[framework] {sym} ${price.get('current_price')}")
    if not enriched: print("[FATAL] no data"); return 1
    framework = call_research(json.dumps(enriched, indent=2))
    print(f"[framework] got {len(framework)} evaluations")
    out = envelope(framework, source="openai+web_search+yahoo-chart+tom-7q")
    out["fundamentals_verified"] = False
    out["refresh_warning"] = {
        "code": "fundamentals_unverified",
        "message": QUALITY_WARNING,
    }
    write_json("framework.json", out)
    print(f"[DONE] wrote framework.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
