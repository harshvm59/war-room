#!/usr/bin/env python3
"""
analyze_daily.py — high-conviction daily signals for the HVM portfolio.

Runs ONCE per trading day (post US market close).

  1. Pull ~6 months OHLCV from Yahoo Finance `chart` endpoint.
  2. Compute RSI/MACD/SMA/ATR/support-resistance in Python.
  3. Read data/portfolio.json for holdings + cost basis.
  4. Send TA + portfolio context to Claude Haiku 4.5.
  5. Write data/actions.json with BUY/HOLD/TRIM + entry/stop/target.
  6. PUSH top 5 critical/high actionables to Telegram bot.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import requests
from anthropic import Anthropic

from _common import (
    DATA_DIR,
    URGENCY_COLORS,
    envelope,
    now_ist,
    require_key,
    write_json,
)

MODEL = "claude-haiku-4-5-20251001"
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    "?range=6mo&interval=1d&includePrePost=false"
)


def load_portfolio():
    if not os.path.exists(PORTFOLIO_PATH):
        raise FileNotFoundError("data/portfolio.json missing.")
    with open(PORTFOLIO_PATH) as f:
        doc = json.load(f)
    return {h["ticker"]: h for h in doc.get("holdings", [])}


def fetch_ohlcv(symbol):
    try:
        r = requests.get(
            YAHOO_CHART_URL.format(sym=symbol),
            headers={"User-Agent": "Mozilla/5.0 (war-room-bot)"},
            timeout=15,
        )
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        ind = result["indicators"]["quote"][0]
        return {"timestamps": result["timestamp"], "open": ind["open"], "high": ind["high"], "low": ind["low"], "close": ind["close"], "volume": ind["volume"]}
    except Exception as exc:
        print(f"[analyze_daily] WARN OHLCV fetch failed for {symbol}: {exc}", file=sys.stderr)
        return None


def _drop_nones(xs):
    return [x for x in xs if x is not None]


def sma(values, window):
    v = _drop_nones(values[-window:])
    return sum(v) / len(v) if len(v) == window else None


def ema(values, window):
    if not values: return []
    k = 2 / (window + 1)
    out = [None] * len(values)
    sv = _drop_nones(values[:window])
    if len(sv) < window: return out
    out[window - 1] = sum(sv) / window
    for i in range(window, len(values)):
        v = values[i]
        if v is None:
            out[i] = out[i - 1]; continue
        prev = out[i - 1]
        out[i] = v * k + (prev if prev is not None else v) * (1 - k)
    return out


def rsi(values, window=14):
    closes = _drop_nones(values)
    if len(closes) < window + 1: return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:window]) / window; al = sum(losses[:window]) / window
    for i in range(window, len(gains)):
        ag = (ag * (window - 1) + gains[i]) / window
        al = (al * (window - 1) + losses[i]) / window
    if al == 0: return 100.0
    return round(100 - (100 / (1 + ag / al)), 2)


def macd(values):
    e12 = ema(values, 12); e26 = ema(values, 26)
    line = [(a - b) if (a is not None and b is not None) else None for a, b in zip(e12, e26)]
    sig = ema(line, 9)
    return {
        "macd": round(line[-1], 4) if line and line[-1] is not None else None,
        "signal": round(sig[-1], 4) if sig and sig[-1] is not None else None,
        "histogram": round((line[-1] or 0) - (sig[-1] or 0), 4) if line and sig and line[-1] is not None and sig[-1] is not None else None,
    }


def atr(highs, lows, closes, window=14):
    n = min(len(highs), len(lows), len(closes))
    if n < window + 1: return None
    trs = []
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        if h is None or l is None or pc is None: continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < window: return None
    return round(sum(trs[-window:]) / window, 2)


def near_levels(highs, lows, lookback=60):
    h = _drop_nones(highs[-lookback:]); l = _drop_nones(lows[-lookback:])
    return {"recent_high": round(max(h), 2) if h else None, "recent_low": round(min(l), 2) if l else None}


def analyze_ticker(symbol, holding):
    ohlcv = fetch_ohlcv(symbol)
    if not ohlcv: return None
    closes = ohlcv["close"]; highs = ohlcv["high"]; lows = ohlcv["low"]; vols = ohlcv["volume"]
    last = _drop_nones(closes)[-1] if _drop_nones(closes) else None
    if last is None: return None
    rh = max(_drop_nones(highs)) if highs else None
    rl = min(_drop_nones(lows)) if lows else None
    lvl = near_levels(highs, lows, 60)
    s20 = sma(closes, 20); s50 = sma(closes, 50); s200 = sma(closes, 200)
    r = rsi(closes, 14); m = macd(closes); a = atr(highs, lows, closes, 14)
    va = sma(vols, 20); cv = _drop_nones(vols)[-1] if _drop_nones(vols) else None
    vr = round(cv / va, 2) if cv and va else None
    cl = _drop_nones(closes)
    def pct(sp):
        if len(cl) <= sp: return None
        return round((cl[-1] / cl[-1 - sp] - 1) * 100, 2)
    units = holding["units"]; ac = holding["avg_cost"]
    cv2 = round(units * last, 2); inv = round(units * ac, 2)
    pnl = round((last / ac - 1) * 100, 2) if ac else None
    return {
        "ticker": symbol, "name": holding["name"], "theme": holding["theme"], "priority": holding["priority"],
        "holding": {"units": units, "avg_cost": ac, "current_price": last, "invested": inv, "current_value": cv2, "pnl_pct": pnl},
        "ta": {
            "rsi14": r, "macd": m["macd"], "macd_signal": m["signal"], "macd_hist": m["histogram"],
            "sma20": round(s20, 2) if s20 else None, "sma50": round(s50, 2) if s50 else None, "sma200": round(s200, 2) if s200 else None,
            "atr14": a,
            "vs_sma50_pct": round((last / s50 - 1) * 100, 2) if s50 else None,
            "vs_sma200_pct": round((last / s200 - 1) * 100, 2) if s200 else None,
            "range_60d_high": lvl["recent_high"], "range_60d_low": lvl["recent_low"],
            "range_6m_high": round(rh, 2) if rh else None, "range_6m_low": round(rl, 2) if rl else None,
            "vol_ratio_20d": vr, "ret_1d": pct(1), "ret_5d": pct(5), "ret_20d": pct(20),
        },
        "monthly_dca_target": holding.get("monthly_dca", 0),
        "thesis_note": holding.get("thesis", "")[:200],
    }


SYSTEM_PROMPT = ("You are a sharp, no-bullshit equities analyst writing one daily decision per holding for the HVM Investment OS dashboard. You have the user's actual holdings + cost basis and pre-computed technical indicators. Be specific: give actual entry/stop/target levels in dollars, cite the exact TA reading that justifies the call, and never produce vague filler.")


PROMPT_TEMPLATE = """Date: {date} (post US market close).

For EACH ticker in order, output ONE JSON object with the schema below. Output as a single JSON ARRAY. No markdown, no commentary.

Schema:
{{
  "ticker": "NVDA",
  "action": "ADD" | "HOLD" | "TRIM" | "WATCH",
  "urgency": "critical" | "high" | "medium" | "low",
  "color": "#hex",
  "price": "$199.97 · +131% from $86.44",
  "signal": "3-4 sentences citing 2+ specific TA values (e.g. 'RSI 38 oversold, MACD bullish cross 2 days ago, 4% above 50-DMA $192'). Cite specific dollar levels.",
  "entry": "$185-192",
  "stop": "$178",
  "target": "$240 (3 mo)",
  "sizing": "$500 monthly DCA · already 25% of portfolio",
  "action_text": "Tight imperative (max 70 chars)"
}}

Color by urgency: critical→#e05252, high→#c9a84c, medium→#4a9eff, low→#2dd4bf.

Heuristics:
- P0 priority + RSI <50: lean ADD HARD (critical urgency).
- TSLA bias TRIM on bounces. Never sell NVDA/TSM core.
- If RSI > 70 AND price > 10% above SMA50: WATCH for pullback, do NOT add.
- If MACD just crossed above signal + price above SMA50: strong ADD trigger.
- If position size > 15% of total portfolio: bias TRIM/HOLD even if bullish.

Sort: critical first. ONLY the JSON array.

ANALYSIS INPUT:
{ticker_blob}
"""


def call_claude(blob):
    client = Anthropic(api_key=require_key())
    msg = client.messages.create(
        model=MODEL, max_tokens=5000, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(date=now_ist().strftime("%A, %B %-d, %Y"), ticker_blob=blob)}],
    )
    raw = (msg.content[0].text if msg.content else "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1:
        raise ValueError(f"No JSON array in response:\n{raw[:500]}")
    data = json.loads(raw[s : e + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("Parsed response is not a non-empty list.")
    for item in data:
        u = str(item.get("urgency", "medium")).lower()
        item["urgency"] = u if u in URGENCY_COLORS else "medium"
        item["color"] = URGENCY_COLORS[item["urgency"]]
        for k in ("ticker", "action", "price", "signal", "action_text"):
            item.setdefault(k, "")
        for k in ("entry", "stop", "target", "sizing"):
            item.setdefault(k, None)
    return data


def notify_telegram(actions, snapshot):
    """Send top critical+high actionables to Telegram. Silent if env vars missing."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notify] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping push")
        return

    urgent = [a for a in actions if a.get("urgency") in ("critical", "high")][:5]
    if not urgent:
        print("[notify] no critical/high actionables today — skipping push")
        return

    date_str = now_ist().strftime("%a %b %-d")
    val = snapshot.get("total_value", 0)
    pnl = snapshot.get("pnl_pct", 0)

    lines = [
        f"<b>📊 War Room — {date_str}</b>",
        f"Portfolio: ${val:,.0f} ({pnl:+.1f}%)",
        "",
        f"<b>🔥 Top {len(urgent)} actionables:</b>",
    ]
    emoji_map = {"ADD": "🟢", "TRIM": "🔴", "WATCH": "🟡", "HOLD": "⚪"}
    for a in urgent:
        em = emoji_map.get(a.get("action", "").upper(), "•")
        lines.append("")
        lines.append(f"{em} <b>{a['ticker']}</b> — {a['action']} ({a['urgency']})")
        if a.get("price"):    lines.append(f"   {a['price']}")
        entry = a.get("entry"); stop = a.get("stop"); tgt = a.get("target")
        if entry: lines.append(f"   📍 Entry: {entry}  |  Stop: {stop or '-'}  |  Target: {tgt or '-'}")
        if a.get("sizing"):   lines.append(f"   📏 {a['sizing']}")
        if a.get("action_text"): lines.append(f"   <i>{a['action_text']}</i>")

    lines.append("")
    lines.append("📊 https://harshvm59.github.io/war-room")

    text = "\n".join(lines)
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        r.raise_for_status()
        print(f"[notify] telegram push sent ({len(text)} chars, {len(urgent)} items)")
    except Exception as exc:
        print(f"[notify] telegram push failed: {exc}", file=sys.stderr)


def main():
    print(f"[analyze_daily] {now_ist().isoformat()}")
    portfolio = load_portfolio()
    print(f"[analyze_daily] {len(portfolio)} holdings loaded")
    per = []
    for sym, h in portfolio.items():
        a = analyze_ticker(sym, h)
        if a:
            per.append(a)
            print(f"[analyze_daily] {sym}: ${a['holding']['current_price']:.2f} RSI={a['ta']['rsi14']} MACDh={a['ta']['macd_hist']} vs50DMA={a['ta']['vs_sma50_pct']}%")
        else:
            print(f"[analyze_daily] {sym}: skipped")
    if not per:
        print("[analyze_daily] FATAL: no usable data")
        return 1
    blob = json.dumps(per, indent=2)
    actions = call_claude(blob)
    print(f"[analyze_daily] got {len(actions)} action items")
    out = envelope(actions, source="claude-haiku+yahoo+local-ta")
    inv = round(sum(p["holding"]["invested"] for p in per), 2)
    val = round(sum(p["holding"]["current_value"] for p in per), 2)
    out["portfolio_snapshot"] = {"total_invested": inv, "total_value": val, "pnl_pct": round((val / inv - 1) * 100, 2) if inv else 0}
    write_json("actions.json", out)
    print(f"[analyze_daily] wrote data/actions.json — portfolio ${val:,.0f} ({out['portfolio_snapshot']['pnl_pct']:+.1f}%)")
    notify_telegram(actions, out["portfolio_snapshot"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
