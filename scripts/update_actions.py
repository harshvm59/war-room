#!/usr/bin/env python3
"""
Intra-day actions refresh — runs every 15 minutes during US market hours.

Steps:
  1. Pull live last-trade prices from Yahoo Finance (no API key needed).
  2. Ask Claude for one fresh action recommendation per ticker, using the
     live prices as today's context.
  3. Write the array to `data/actions.json` so the dashboard's bootstrap
     fetch can pick it up.

The workflow only commits if the file actually changed.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import requests
from anthropic import Anthropic

from _common import (
    TICKERS,
    URGENCY_COLORS,
    envelope,
    now_ist,
    require_key,
    write_json,
)

MODEL = "claude-sonnet-4-5-20250929"

YAHOO_QUOTE_URL = (
    "https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}"
)


def fetch_live_prices() -> dict[str, dict[str, Any]]:
    """Return {ticker: {price, change_pct, day_high, day_low}} or {} on failure."""
    try:
        r = requests.get(
            YAHOO_QUOTE_URL.format(syms=",".join(TICKERS)),
            headers={"User-Agent": "Mozilla/5.0 (war-room-bot)"},
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("quoteResponse", {}).get("result", [])
    except Exception as exc:
        print(f"[update_actions] WARN Yahoo fetch failed: {exc}", file=sys.stderr)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for q in results:
        sym = q.get("symbol")
        if not sym:
            continue
        out[sym] = {
            "price": q.get("regularMarketPrice"),
            "change_pct": q.get("regularMarketChangePercent"),
            "day_high": q.get("regularMarketDayHigh"),
            "day_low": q.get("regularMarketDayLow"),
        }
    return out


def build_prompt(prices: dict[str, dict[str, Any]]) -> str:
    now = now_ist()
    price_lines = []
    for t in TICKERS:
        p = prices.get(t, {})
        if p.get("price") is not None:
            price_lines.append(
                f"- {t}: ${p['price']:.2f} ({p.get('change_pct') or 0:+.2f}% today, "
                f"day range ${p.get('day_low')}–${p.get('day_high')})"
            )
        else:
            price_lines.append(f"- {t}: price unavailable")
    price_block = "\n".join(price_lines)

    return f"""Intraday refresh — generate one action recommendation per ticker for the HVM Investment OS dashboard.

Timestamp: {now.isoformat()} (IST)

LIVE PRICES RIGHT NOW (use these in your `price` field):
{price_block}

Portfolio context: long-term AI/compute thesis. P0 conviction names (lean ADD when in doubt):
MU, CEG, AVGO, MSFT. Never sell NVDA or TSM core. TSLA overweight — bias TRIM on bounces.

Output: ONLY a JSON array, exactly 17 items, in this shape:
{{
  "ticker": "NVDA",
  "action": "HOLD",
  "urgency": "critical|high|medium|low",
  "color": "#hex",
  "price": "$199.97 · +0.6% today",
  "signal": "3-4 sentence analysis using today's price action and known catalysts. Cite specific $ levels.",
  "action_text": "Tight imperative line"
}}

Order by urgency (critical first). No markdown, no commentary, just the JSON array.
"""


def call_claude(prompt: str) -> list[dict]:
    client = Anthropic(api_key=require_key())
    msg = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (msg.content[0].text if msg.content else "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1:
        raise ValueError(f"No JSON array found in response:\n{raw[:400]}")
    data = json.loads(raw[s : e + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("Parsed response is not a non-empty list.")

    for item in data:
        u = str(item.get("urgency", "medium")).lower()
        item["urgency"] = u if u in URGENCY_COLORS else "medium"
        item["color"] = URGENCY_COLORS[item["urgency"]]
        for k in ("ticker", "action", "price", "signal", "action_text"):
            item.setdefault(k, "")
    return data


def main() -> int:
    print(f"[update_actions] {now_ist().isoformat()}")
    prices = fetch_live_prices()
    if not prices:
        print("[update_actions] WARN: no live prices, prompt will be unanchored")
    actions = call_claude(build_prompt(prices))
    print(f"[update_actions] got {len(actions)} action items")
    path = write_json("actions.json", envelope(actions, source="claude+yahoo"))
    print(f"[update_actions] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
