#!/usr/bin/env python3
"""analyze_daily.py — TA + fundamentals → rule-based action cards + live prices.

No external LLM. Everything is computed deterministically from price history
(Yahoo v8 chart, free, no key) plus the portfolio file. Writes:
  - data/actions.json  (action cards for the dashboard)
  - data/prices.json   (live-ish prices the frontend reads instead of Yahoo)
and optionally pushes a plain-text Telegram digest.
"""

from __future__ import annotations
import json, os, sys
import requests
from _common import DATA_DIR, URGENCY_COLORS, envelope, now_ist, write_json

PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=6mo&interval=1d&includePrePost=false"
HDR = {"User-Agent": "Mozilla/5.0 (war-room-bot)"}

CORE = {"NVDA", "TSM"}  # never trim/sell the core compute holdings


def load_portfolio():
    with open(PORTFOLIO_PATH) as f: doc = json.load(f)
    return {h["ticker"]: h for h in doc.get("holdings", [])}


def fetch_ohlcv(s):
    try:
        r = requests.get(YAHOO_CHART.format(s=s), headers=HDR, timeout=15); r.raise_for_status()
        res = r.json()["chart"]["result"][0]; ind = res["indicators"]["quote"][0]
        return {"open": ind["open"], "high": ind["high"], "low": ind["low"], "close": ind["close"], "volume": ind["volume"]}
    except Exception as e:
        print(f"[WARN] OHLCV {s}: {e}", file=sys.stderr); return None


def _dn(xs): return [x for x in xs if x is not None]
def sma(v, w):
    x = _dn(v[-w:]); return sum(x)/len(x) if len(x)==w else None
def ema(v, w):
    if not v: return []
    k = 2/(w+1); out = [None]*len(v); sv = _dn(v[:w])
    if len(sv) < w: return out
    out[w-1] = sum(sv)/w
    for i in range(w, len(v)):
        val = v[i]
        if val is None: out[i] = out[i-1]; continue
        p = out[i-1]; out[i] = val*k + (p if p is not None else val)*(1-k)
    return out
def rsi(v, w=14):
    c = _dn(v)
    if len(c) < w+1: return None
    g, l = [], []
    for i in range(1, len(c)):
        d = c[i]-c[i-1]; g.append(max(d,0)); l.append(max(-d,0))
    ag = sum(g[:w])/w; al = sum(l[:w])/w
    for i in range(w, len(g)):
        ag = (ag*(w-1)+g[i])/w; al = (al*(w-1)+l[i])/w
    if al == 0: return 100.0
    return round(100 - (100/(1 + ag/al)), 2)
def macd(v):
    e12 = ema(v, 12); e26 = ema(v, 26)
    line = [(a-b) if a is not None and b is not None else None for a,b in zip(e12, e26)]
    sig = ema(line, 9)
    hist = (line[-1] or 0) - (sig[-1] or 0) if line and sig and line[-1] is not None and sig[-1] is not None else None
    return {"macd": round(line[-1], 3) if line and line[-1] is not None else None,
            "signal": round(sig[-1], 3) if sig and sig[-1] is not None else None,
            "histogram": round(hist, 3) if hist is not None else None}


def analyze_ticker(sym, h):
    o = fetch_ohlcv(sym)
    if not o: return None
    cl, hi, lo, vo = o["close"], o["high"], o["low"], o["volume"]
    cln = _dn(cl)
    last = cln[-1] if cln else None
    if last is None: return None
    prev_close = cln[-2] if len(cln) >= 2 else last
    s20 = sma(cl, 20); s50 = sma(cl, 50); s200 = sma(cl, 200)
    r = rsi(cl, 14); m = macd(cl)
    va = sma(vo, 20); cv = _dn(vo)[-1] if _dn(vo) else None
    vr = round(cv/va, 2) if cv and va else None
    def pct(sp):
        if len(cln) <= sp: return None
        return round((cln[-1]/cln[-1-sp]-1)*100, 2)
    units = h["units"]; ac = h["avg_cost"]
    cv2 = round(units*last, 2); inv = round(units*ac, 2)
    pnl = round((last/ac-1)*100, 2) if ac else None
    return {
        "ticker": sym, "name": h["name"], "theme": h["theme"], "priority": h["priority"],
        "monthly_dca": h.get("monthly_dca", 0),
        "holding": {"units": units, "avg_cost": ac, "current_price": last, "prev_close": round(prev_close, 2),
                    "invested": inv, "current_value": cv2, "pnl_pct": pnl},
        "ta": {"rsi14": r, "macd": m["macd"], "macd_signal": m["signal"], "macd_hist": m["histogram"],
               "sma20": round(s20,2) if s20 else None, "sma50": round(s50,2) if s50 else None, "sma200": round(s200,2) if s200 else None,
               "vs_sma50_pct": round((last/s50-1)*100, 2) if s50 else None,
               "vs_sma200_pct": round((last/s200-1)*100, 2) if s200 else None,
               "vol_ratio_20d": vr, "ret_1d": pct(1), "ret_5d": pct(5), "ret_20d": pct(20)},
        "thesis_note": h.get("thesis", "")[:160],
    }


def _decide(sym, weight, ta, pnl, pri):
    """Pure rule engine — returns (action, urgency)."""
    rsi_v = ta.get("rsi14")
    vs50 = ta.get("vs_sma50_pct") or 0
    hist = ta.get("macd_hist")
    overbought = rsi_v is not None and rsi_v > 70 and vs50 > 10
    oversold = rsi_v is not None and rsi_v < 35
    uptrend = hist is not None and hist > 0 and vs50 > 0
    downtrend = vs50 < -5

    if sym == "TSLA":
        return ("TRIM", "high") if ((pnl or 0) > 30 or weight > 8) else ("HOLD", "medium")
    if weight > 15 and sym not in CORE:
        return ("TRIM", "high")                 # over-concentrated, lock gains
    if overbought:
        return ("WATCH", "medium")              # extended — don't chase
    if oversold and pri in ("P0", "P1"):
        return ("ADD", "critical")              # quality on sale
    if pri == "P0":
        return ("ADD", "critical")              # priority underweight gap
    if uptrend and pri == "P1":
        return ("ADD", "high")                  # healthy trend, keep building
    if sym in CORE:
        return ("HOLD", "low")                  # never trim the core
    if downtrend and pri in ("P0", "P1"):
        return ("ADD", "medium")                # buy the dip on quality
    return ("HOLD", "medium")


def generate_actions(per, total_value):
    """Deterministic action cards from TA + position — same schema the UI expects."""
    out = []
    for p in per:
        sym = p["ticker"]; ta = p["ta"]; hold = p["holding"]
        last = hold["current_price"]; ac = hold["avg_cost"]; pnl = hold["pnl_pct"] or 0
        pri = p["priority"]; dca = p.get("monthly_dca", 0)
        weight = (hold["current_value"] / total_value * 100) if total_value else 0
        action, urgency = _decide(sym, weight, ta, pnl, pri)

        rsi_v = ta.get("rsi14"); hist = ta.get("macd_hist"); vs50 = ta.get("vs_sma50_pct")
        s50 = ta.get("sma50"); s20 = ta.get("sma20")
        # entry / stop / target derived from trend levels
        anchor = s50 or s20 or last
        entry = f"${anchor*0.97:.0f}–${anchor*1.02:.0f}"
        stop = f"${min(anchor, last)*0.92:.0f}"
        target = f"${last*1.20:.0f} (3 mo)"
        price = f"${last:.2f}, {'+' if pnl>=0 else ''}{pnl:.1f}% from ${ac:.2f}"
        sizing = (f"${dca}/mo DCA · {weight:.1f}% of portfolio" if dca
                  else f"{weight:.1f}% of portfolio · no active DCA")

        rsi_tag = ("overbought" if rsi_v and rsi_v > 70 else
                   "oversold" if rsi_v and rsi_v < 35 else "neutral")
        signal = (
            f"RSI {rsi_v if rsi_v is not None else 'n/a'} ({rsi_tag}), "
            f"MACD histogram {'+' if (hist or 0)>=0 else ''}{hist if hist is not None else 'n/a'}, "
            f"price {'+' if (vs50 or 0)>=0 else ''}{vs50 if vs50 is not None else 'n/a'}% vs SMA50. "
            f"Position {'+' if pnl>=0 else ''}{pnl:.1f}% at {weight:.1f}% weight ({pri}). "
            f"{p.get('thesis_note','')}"
        ).strip()

        if action == "ADD":
            action_text = f"Accumulate near {entry}; stop {stop}"
        elif action == "TRIM":
            action_text = f"Trim into strength near ${last:.0f}; redeploy to P0 names"
        elif action == "WATCH":
            action_text = f"Extended — wait for pullback to {entry}, do not chase"
        else:
            action_text = "Hold; review on next signal"

        out.append({
            "ticker": sym, "action": action, "urgency": urgency,
            "color": URGENCY_COLORS[urgency], "price": price, "signal": signal,
            "entry": entry, "stop": stop, "target": target, "sizing": sizing,
            "action_text": action_text,
            "_rank": {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(urgency, 9),
        })
    out.sort(key=lambda a: a["_rank"])
    for a in out: a.pop("_rank", None)
    return out


def build_prices(per):
    """prices.json — exact shape the frontend's LIVE_PRICES expects."""
    prices = {}
    for p in per:
        h = p["holding"]; last = h["current_price"]; prev = h["prev_close"]
        prices[p["ticker"]] = {
            "price": round(last, 2),
            "prevClose": prev,
            "change": round(last - prev, 2),
            "changePct": p["ta"].get("ret_1d"),
            "volume": p["ta"].get("vol_ratio_20d"),
            "marketCap": None,
        }
    return prices


def notify_telegram(actions, snap):
    """Plain text push. Top 5 critical+high every run."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not cid:
        print("[notify] secrets missing — skipping push"); return
    items = [a for a in actions if a.get("urgency") in ("critical", "high")][:5] or actions[:5]
    ts = now_ist().strftime("%a %b %-d %H:%M IST")
    v = snap.get("total_value", 0); p = snap.get("pnl_pct", 0)
    lines = [f"🚨 War Room - {ts}", f"Portfolio: ${v:,.0f} ({p:+.1f}%)", "", f"🔥 Top {len(items)} actionables:"]
    em = {"ADD":"🟢","TRIM":"🔴","WATCH":"🟡","HOLD":"⚪"}
    for a in items:
        e = em.get(a.get("action","").upper(), "•")
        lines += ["", f"{e} {a['ticker']} - {a['action']} ({a['urgency']})"]
        if a.get("price"): lines.append(f"   {a['price']}")
        if a.get("entry"): lines.append(f"   Entry: {a['entry']} | Stop: {a.get('stop','-')} | Target: {a.get('target','-')}")
        if a.get("sizing"): lines.append(f"   Size: {a['sizing']}")
        if a.get("action_text"): lines.append(f"   {a['action_text']}")
    lines += ["", "📊 https://harshvm59.github.io/war-room"]
    text = "\n".join(lines)
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": cid, "text": text, "disable_web_page_preview": True}, timeout=15)
        r.raise_for_status()
        print(f"[notify] pushed {len(items)} actionables ({len(text)} chars)")
    except Exception as e:
        print(f"[notify] push failed: {e}", file=sys.stderr)


def main():
    print(f"[analyze_daily] {now_ist().isoformat()}")
    portfolio = load_portfolio()
    print(f"[analyze_daily] {len(portfolio)} holdings")
    per = []
    for sym, h in portfolio.items():
        x = analyze_ticker(sym, h)
        if x: per.append(x); print(f"[analyze_daily] {sym} ${x['holding']['current_price']:.2f} RSI={x['ta']['rsi14']}")
        else: print(f"[analyze_daily] {sym}: skipped (no data)")
    if not per:
        print("[FATAL] no price data for any ticker", file=sys.stderr); return 1

    inv = round(sum(p["holding"]["invested"] for p in per), 2)
    val = round(sum(p["holding"]["current_value"] for p in per), 2)
    snap = {"total_invested": inv, "total_value": val, "pnl_pct": round((val/inv-1)*100, 2) if inv else 0}

    actions = generate_actions(per, val)
    print(f"[analyze_daily] generated {len(actions)} actions (rule-based)")
    out = envelope(actions, source="yahoo+local-ta+rules")
    out["portfolio_snapshot"] = snap
    write_json("actions.json", out)

    prices_doc = envelope([], source="yahoo")
    prices_doc.pop("items", None)
    prices_doc["prices"] = build_prices(per)
    write_json("prices.json", prices_doc)
    # Full daily technical snapshot consumed by the frontend. Unlike the old
    # inline TA constants this contains fresh RSI, MACD, moving averages and
    # rule-based entry/stop/target data for every ticker.
    write_json("analysis.json", envelope(per, source="yahoo+local-ta+rules"))
    print(f"[analyze_daily] wrote prices and analysis for {len(prices_doc['prices'])} tickers")

    notify_telegram(actions, snap)
    print(f"[DONE] ${val:,.0f} ({snap['pnl_pct']:+.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
