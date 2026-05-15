#!/usr/bin/env python3
"""analyze_daily.py - TA + fundamentals + plain-text Telegram every run."""

from __future__ import annotations
import json, os, re, sys
import requests
from anthropic import Anthropic
from _common import DATA_DIR, URGENCY_COLORS, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=6mo&interval=1d&includePrePost=false"
HDR = {"User-Agent": "Mozilla/5.0 (war-room-bot)"}


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
    last = _dn(cl)[-1] if _dn(cl) else None
    if last is None: return None
    s20 = sma(cl, 20); s50 = sma(cl, 50); s200 = sma(cl, 200)
    r = rsi(cl, 14); m = macd(cl)
    va = sma(vo, 20); cv = _dn(vo)[-1] if _dn(vo) else None
    vr = round(cv/va, 2) if cv and va else None
    cln = _dn(cl)
    def pct(sp):
        if len(cln) <= sp: return None
        return round((cln[-1]/cln[-1-sp]-1)*100, 2)
    units = h["units"]; ac = h["avg_cost"]
    cv2 = round(units*last, 2); inv = round(units*ac, 2)
    pnl = round((last/ac-1)*100, 2) if ac else None
    return {
        "ticker": sym, "name": h["name"], "theme": h["theme"], "priority": h["priority"],
        "holding": {"units": units, "avg_cost": ac, "current_price": last, "invested": inv, "current_value": cv2, "pnl_pct": pnl},
        "ta": {"rsi14": r, "macd": m["macd"], "macd_signal": m["signal"], "macd_hist": m["histogram"],
               "sma20": round(s20,2) if s20 else None, "sma50": round(s50,2) if s50 else None, "sma200": round(s200,2) if s200 else None,
               "vs_sma50_pct": round((last/s50-1)*100, 2) if s50 else None,
               "vs_sma200_pct": round((last/s200-1)*100, 2) if s200 else None,
               "vol_ratio_20d": vr, "ret_1d": pct(1), "ret_5d": pct(5), "ret_20d": pct(20)},
        "thesis_note": h.get("thesis", "")[:200],
    }


SYS = "You are an institutional equities analyst. Cite specific TA values + thesis in every signal. Plain text only - no HTML chars (less-than, greater-than, ampersand, asterisk, underscore, backtick)."

PROMPT = """Date: {date}. For EACH ticker output one JSON object. Final: single JSON ARRAY sorted by urgency. No markdown.

Schema:
{{
  "ticker": "NVDA",
  "action": "ADD" | "HOLD" | "TRIM" | "WATCH",
  "urgency": "critical" | "high" | "medium" | "low",
  "color": "#hex",
  "price": "$199.97, +131% from $86.44",
  "signal": "4-5 sentences citing 2+ TA values (RSI/MACD/SMA distance) + reasoning. Plain text only.",
  "entry": "$185-192",
  "stop": "$178",
  "target": "$240 (3 mo)",
  "sizing": "$500 monthly DCA, already 12% of portfolio",
  "action_text": "Tight imperative max 70 chars"
}}

Hex: critical=#e05252, high=#c9a84c, medium=#4a9eff, low=#2dd4bf.

RULES: ADD/critical needs positive TA AND fundamental green light. RSI>70 + price >10% above SMA50: WATCH only. TSLA: lean TRIM. Never SELL NVDA/TSM core. Position >15%: bias HOLD/TRIM. Earnings within 7 days: HOLD/WATCH.

INPUT:
{blob}
"""


def call_claude(blob):
    c = Anthropic(api_key=require_key())
    msg = c.messages.create(model=MODEL, max_tokens=6000, system=SYS,
        messages=[{"role": "user", "content": PROMPT.format(date=now_ist().strftime("%a %b %-d, %Y %H:%M IST"), blob=blob)}])
    raw = (msg.content[0].text if msg.content else "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1: raise ValueError(f"No JSON array:\n{raw[:500]}")
    data = json.loads(raw[s:e+1])
    if not isinstance(data, list) or not data: raise ValueError("empty")
    for it in data:
        u = str(it.get("urgency", "medium")).lower()
        it["urgency"] = u if u in URGENCY_COLORS else "medium"
        it["color"] = URGENCY_COLORS[it["urgency"]]
        for k in ("ticker","action","price","signal","action_text"): it.setdefault(k, "")
        for k in ("entry","stop","target","sizing"): it.setdefault(k, None)
    return data


def notify_telegram(actions, snap):
    """Plain text push. Top 5 critical+high every run."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not cid:
        print("[notify] secrets missing"); return
    items = [a for a in actions if a.get("urgency") in ("critical", "high")][:5]
    if not items:
        items = actions[:5]  # fallback: top 5 overall
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
        else: print(f"[analyze_daily] {sym}: skipped")
    if not per: print("[FATAL] no data"); return 1
    actions = call_claude(json.dumps(per, indent=2))
    print(f"[analyze_daily] got {len(actions)} actions")
    inv = round(sum(p["holding"]["invested"] for p in per), 2)
    val = round(sum(p["holding"]["current_value"] for p in per), 2)
    snap = {"total_invested": inv, "total_value": val, "pnl_pct": round((val/inv-1)*100, 2) if inv else 0}
    out = envelope(actions, source="claude-haiku+yahoo+local-ta")
    out["portfolio_snapshot"] = snap
    write_json("actions.json", out)
    notify_telegram(actions, snap)
    print(f"[DONE] ${val:,.0f} ({snap['pnl_pct']:+.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
