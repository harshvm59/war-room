#!/usr/bin/env python3
"""
analyze_daily.py — TRADING signals with TA + fundamentals + diff-based push.

Runs every 30 min during US market hours + post-close.

Pipeline:
  1. Fetch 6mo OHLCV + fundamentals (P/E, EPS, earnings date, 52w) per ticker.
  2. Compute TA in Python: RSI(14), MACD(12,26,9), SMA-20/50/200, ATR, volume.
  3. Read portfolio.json for holdings + cost basis.
  4. Send TA + FUND + portfolio to Claude Haiku 4.5.
  5. Always write data/actions.json (dashboard fresh).
  6. DIFF against prev run. Telegram push ONLY when:
       - action upgraded to ADD, OR
       - urgency escalated to critical, OR
       - price just entered entry zone.
"""

from __future__ import annotations

import json, os, re, sys
import requests
from anthropic import Anthropic
from _common import DATA_DIR, URGENCY_COLORS, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
ACTIONS_PATH = os.path.join(DATA_DIR, "actions.json")
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=6mo&interval=1d&includePrePost=false"
YAHOO_QS = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{s}?modules=summaryDetail,defaultKeyStatistics,calendarEvents,financialData"
HDR = {"User-Agent": "Mozilla/5.0 (war-room-bot)"}


def load_portfolio():
    with open(PORTFOLIO_PATH) as f: doc = json.load(f)
    return {h["ticker"]: h for h in doc.get("holdings", [])}

def load_prev_actions():
    if not os.path.exists(ACTIONS_PATH): return None
    try:
        with open(ACTIONS_PATH) as f: return json.load(f).get("items") or None
    except Exception: return None

def fetch_ohlcv(s):
    try:
        r = requests.get(YAHOO_CHART.format(s=s), headers=HDR, timeout=15); r.raise_for_status()
        res = r.json()["chart"]["result"][0]; ind = res["indicators"]["quote"][0]
        return {"open": ind["open"], "high": ind["high"], "low": ind["low"], "close": ind["close"], "volume": ind["volume"]}
    except Exception as e:
        print(f"[WARN] OHLCV {s}: {e}", file=sys.stderr); return None

def fetch_fund(s):
    try:
        r = requests.get(YAHOO_QS.format(s=s), headers=HDR, timeout=12); r.raise_for_status()
        d = r.json()["quoteSummary"]["result"][0]
        sd = d.get("summaryDetail", {}) or {}; ks = d.get("defaultKeyStatistics", {}) or {}
        ce = d.get("calendarEvents", {}) or {}; fd = d.get("financialData", {}) or {}
        raw = lambda o, k: (o.get(k, {}) or {}).get("raw") if isinstance(o.get(k), dict) else o.get(k)
        edate = None
        el = (ce.get("earnings", {}) or {}).get("earningsDate") or []
        if el and isinstance(el[0], dict) and el[0].get("raw"):
            from datetime import datetime
            edate = datetime.utcfromtimestamp(el[0]["raw"]).strftime("%Y-%m-%d")
        return {
            "pe_trailing": raw(sd, "trailingPE"), "pe_forward": raw(sd, "forwardPE"),
            "eps_ttm": raw(ks, "trailingEps"), "eps_fwd": raw(ks, "forwardEps"),
            "peg": raw(ks, "pegRatio"), "div_yield": raw(sd, "dividendYield"),
            "52w_high": raw(sd, "fiftyTwoWeekHigh"), "52w_low": raw(sd, "fiftyTwoWeekLow"),
            "market_cap": raw(sd, "marketCap"), "beta": raw(sd, "beta") or raw(ks, "beta"),
            "earnings_date": edate, "rec_mean": raw(fd, "recommendationMean"),
            "target_mean": raw(fd, "targetMeanPrice"), "target_high": raw(fd, "targetHighPrice"),
            "rev_growth_yoy": raw(fd, "revenueGrowth"), "earn_growth_yoy": raw(fd, "earningsGrowth"),
            "profit_margin": raw(fd, "profitMargins"),
        }
    except Exception as e:
        print(f"[WARN] fund {s}: {e}", file=sys.stderr); return {}

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
    h2 = line[-3] - sig[-3] if len(line) >= 3 and len(sig) >= 3 and line[-3] is not None and sig[-3] is not None else None
    bull_cross = hist is not None and hist > 0 and (h2 is None or h2 < 0)
    return {"macd": round(line[-1], 3) if line and line[-1] is not None else None,
            "signal": round(sig[-1], 3) if sig and sig[-1] is not None else None,
            "histogram": round(hist, 3) if hist is not None else None,
            "bull_cross_recent": bull_cross}
def atr(h, l, c, w=14):
    n = min(len(h), len(l), len(c))
    if n < w+1: return None
    tr = []
    for i in range(1, n):
        hi, lo, pc = h[i], l[i], c[i-1]
        if hi is None or lo is None or pc is None: continue
        tr.append(max(hi-lo, abs(hi-pc), abs(lo-pc)))
    if len(tr) < w: return None
    return round(sum(tr[-w:])/w, 2)

def analyze_ticker(sym, h):
    o = fetch_ohlcv(sym)
    if not o: return None
    cl, hi, lo, vo = o["close"], o["high"], o["low"], o["volume"]
    last = _dn(cl)[-1] if _dn(cl) else None
    if last is None: return None
    s20 = sma(cl, 20); s50 = sma(cl, 50); s200 = sma(cl, 200)
    r = rsi(cl, 14); m = macd(cl); a = atr(hi, lo, cl, 14)
    va = sma(vo, 20); cv = _dn(vo)[-1] if _dn(vo) else None
    vr = round(cv/va, 2) if cv and va else None
    cln = _dn(cl)
    def pct(sp):
        if len(cln) <= sp: return None
        return round((cln[-1]/cln[-1-sp]-1)*100, 2)
    units = h["units"]; ac = h["avg_cost"]
    cv2 = round(units*last, 2); inv = round(units*ac, 2)
    pnl = round((last/ac-1)*100, 2) if ac else None
    fund = fetch_fund(sym)
    return {
        "ticker": sym, "name": h["name"], "theme": h["theme"], "priority": h["priority"],
        "holding": {"units": units, "avg_cost": ac, "current_price": last, "invested": inv, "current_value": cv2, "pnl_pct": pnl},
        "ta": {"rsi14": r, "macd": m["macd"], "macd_signal": m["signal"], "macd_hist": m["histogram"], "macd_bull_cross": m["bull_cross_recent"],
               "sma20": round(s20,2) if s20 else None, "sma50": round(s50,2) if s50 else None, "sma200": round(s200,2) if s200 else None,
               "atr14": a, "vs_sma50_pct": round((last/s50-1)*100, 2) if s50 else None,
               "vs_sma200_pct": round((last/s200-1)*100, 2) if s200 else None,
               "range_60d_high": round(max(_dn(hi[-60:])),2) if _dn(hi[-60:]) else None,
               "range_60d_low": round(min(_dn(lo[-60:])),2) if _dn(lo[-60:]) else None,
               "vol_ratio_20d": vr, "ret_1d": pct(1), "ret_5d": pct(5), "ret_20d": pct(20)},
        "fundamentals": fund,
        "monthly_dca_target": h.get("monthly_dca", 0),
        "thesis_note": h.get("thesis", "")[:200],
    }

SYS = "You are an institutional-grade equities analyst writing daily-grade decisions for the HVM Investment OS. You have user's real holdings + cost basis, TA (RSI/MACD/SMA/volume), fundamentals (P/E, EPS, earnings, analyst targets, growth), and a thesis. Be rigorous: cite specific TA values AND fundamental data in every signal. No generic filler. Specific dollar entry/stop/target required."

PROMPT = """Date: {date} (US market session).

For EACH ticker, output ONE JSON object. Final output: single JSON ARRAY sorted by urgency (critical first). No markdown.

Schema:
{{
  "ticker": "NVDA",
  "action": "ADD" | "HOLD" | "TRIM" | "WATCH",
  "urgency": "critical" | "high" | "medium" | "low",
  "color": "#hex",
  "price": "$199.97 · +131% from $86.44",
  "signal": "4-5 sentences. MUST cite: 2+ TA values (RSI/MACD/SMA distance) AND 2+ fundamentals (P/E, EPS growth, earnings date, analyst target). Then explain why ACTION makes sense given cost basis + position size.",
  "entry": "$185-192",
  "stop": "$178",
  "target": "$240 (3 mo)",
  "sizing": "$500 monthly DCA · already 12% of portfolio",
  "action_text": "Tight imperative (max 70 chars)"
}}

Hex: critical=#e05252, high=#c9a84c, medium=#4a9eff, low=#2dd4bf.

RULES:
- ADD/critical needs BOTH: positive TA trigger (RSI<55, or MACD bull cross, or near SMA50 support) AND fundamental green light (forward P/E reasonable, EPS growth positive, analyst target > current).
- RSI > 70 AND price > 10% above SMA50: WATCH only, do NOT ADD even on P0.
- macd_bull_cross=true AND price > SMA50: strong ADD trigger.
- TSLA: lean TRIM on rallies. Never SELL NVDA/TSM core.
- Position > 15% of portfolio: bias HOLD/TRIM.
- Earnings within 7 days: HOLD or WATCH (binary risk).
- P0 + RSI<50 + forward P/E reasonable: ADD HARD critical.

ANALYSIS INPUT:
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
    if not isinstance(data, list) or not data: raise ValueError("empty list")
    for it in data:
        u = str(it.get("urgency", "medium")).lower()
        it["urgency"] = u if u in URGENCY_COLORS else "medium"
        it["color"] = URGENCY_COLORS[it["urgency"]]
        for k in ("ticker","action","price","signal","action_text"): it.setdefault(k, "")
        for k in ("entry","stop","target","sizing"): it.setdefault(k, None)
    return data

URG = {"low":0,"medium":1,"high":2,"critical":3}
def _pp(s):
    if not s: return None
    m = re.search(r"\$(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None
def _pz(s):
    if not s: return None
    m = re.search(r"\$?(\d+(?:\.\d+)?)[\s]*[-–][\s]*\$?(\d+(?:\.\d+)?)", s)
    if not m: return None
    return float(m.group(1)), float(m.group(2))

def diff_for_signals(new_items, prev_items):
    if not prev_items:
        return [{**a, "_reason": "Initial signal — critical ADD"} for a in new_items
                if a.get("action")=="ADD" and a.get("urgency")=="critical"]
    pm = {a["ticker"]: a for a in prev_items}
    out = []
    for n in new_items:
        p = pm.get(n["ticker"], {})
        if n.get("action")=="ADD" and p.get("action")!="ADD":
            out.append({**n, "_reason": f"Action upgraded: {p.get('action','-')} → ADD"}); continue
        if URG.get(n.get("urgency"),-1) > URG.get(p.get("urgency"),-1) and n.get("urgency")=="critical":
            out.append({**n, "_reason": f"Urgency escalated to CRITICAL (was {p.get('urgency','-')})"}); continue
        if n.get("action")=="ADD" and n.get("entry"):
            z = _pz(n["entry"]); cur = _pp(n.get("price")); pcur = _pp(p.get("price"))
            if z and cur is not None:
                in_now = z[0]<=cur<=z[1]
                in_prev = pcur is not None and z[0]<=pcur<=z[1]
                if in_now and not in_prev:
                    out.append({**n, "_reason": f"Price ${cur} entered zone ${z[0]:.0f}-{z[1]:.0f}"}); continue
    return out

def notify_telegram(items, snap):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not cid: print("[notify] secrets missing"); return
    if not items: print("[notify] no fresh signals — silent"); return
    ts = now_ist().strftime("%a %b %-d %H:%M IST")
    v = snap.get("total_value", 0); p = snap.get("pnl_pct", 0)
    lines = [f"<b>🚨 War Room — {ts}</b>", f"Portfolio: ${v:,.0f} ({p:+.1f}%)", "",
             f"<b>🔥 {len(items)} NEW signal{'s' if len(items)!=1 else ''}:</b>"]
    em = {"ADD":"🟢","TRIM":"🔴","WATCH":"🟡","HOLD":"⚪"}
    for a in items[:5]:
        e = em.get(a.get("action","").upper(), "•")
        lines += ["", f"{e} <b>{a['ticker']}</b> — {a['action']} ({a['urgency']})",
                  f"   <i>{a.get('_reason','')}</i>"]
        if a.get("price"): lines.append(f"   {a['price']}")
        if a.get("entry"): lines.append(f"   📍 Entry: {a['entry']}  |  Stop: {a.get('stop','-')}  |  Target: {a.get('target','-')}")
        if a.get("sizing"): lines.append(f"   📏 {a['sizing']}")
        if a.get("action_text"): lines.append(f"   ⚡ {a['action_text']}")
    lines += ["", "📊 https://harshvm59.github.io/war-room"]
    text = "\n".join(lines)
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
        r.raise_for_status(); print(f"[notify] pushed {len(items)} fresh signals")
    except Exception as e:
        print(f"[notify] push failed: {e}", file=sys.stderr)

def main():
    print(f"[analyze_daily] {now_ist().isoformat()}")
    portfolio = load_portfolio(); prev = load_prev_actions()
    print(f"[analyze_daily] {len(portfolio)} holdings, prev = {len(prev) if prev else 0}")
    per = []
    for sym, h in portfolio.items():
        x = analyze_ticker(sym, h)
        if x:
            per.append(x)
            print(f"[analyze_daily] {sym} ${x['holding']['current_price']:.2f} RSI={x['ta']['rsi14']} MACDh={x['ta']['macd_hist']} fwdPE={x['fundamentals'].get('pe_forward')}")
        else:
            print(f"[analyze_daily] {sym}: skipped")
    if not per: print("[FATAL] no data"); return 1
    actions = call_claude(json.dumps(per, indent=2))
    print(f"[analyze_daily] got {len(actions)} actions")
    inv = round(sum(p["holding"]["invested"] for p in per), 2)
    val = round(sum(p["holding"]["current_value"] for p in per), 2)
    snap = {"total_invested": inv, "total_value": val, "pnl_pct": round((val/inv-1)*100, 2) if inv else 0}
    out = envelope(actions, source="claude-haiku+yahoo+local-ta+fundamentals")
    out["portfolio_snapshot"] = snap
    write_json("actions.json", out)
    fresh = diff_for_signals(actions, prev)
    print(f"[analyze_daily] fresh vs prev: {len(fresh)}")
    notify_telegram(fresh, snap)
    print(f"[DONE] ${val:,.0f} ({snap['pnl_pct']:+.1f}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
