#!/usr/bin/env python3
"""Daily investment research feed with an Anthropic-web-search primary and RSS fallback.

The fallback deliberately writes only source-linked headlines and labels leader items
as signals rather than inventing quotes. It keeps the dashboard fresh when the paid
research provider is unavailable.
"""
from __future__ import annotations
import json, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
import requests
from anthropic import Anthropic
from _common import TICKERS, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"
CHANNELS = ["Tom Nash", "CNBC Fast Money", "Bloomberg Markets", "Yahoo Finance", "Motley Fool", "ARK Invest", "Benzinga"]
LEADERS = [
    {"name":"Jensen Huang","role":"CEO","org":"Nvidia","cat":"CEO"},
    {"name":"Sam Altman","role":"CEO","org":"OpenAI","cat":"CEO"},
    {"name":"Dan Ives","role":"Senior Analyst","org":"Wedbush","cat":"Analyst"},
    {"name":"Satya Nadella","role":"CEO","org":"Microsoft","cat":"CEO"},
    {"name":"Lisa Su","role":"CEO","org":"AMD","cat":"CEO"},
    {"name":"Chamath Palihapitiya","role":"Investor","org":"Social Capital","cat":"Investor"},
    {"name":"Alex Karp","role":"CEO","org":"Palantir","cat":"CEO"},
    {"name":"Elon Musk","role":"CEO","org":"Tesla / xAI / SpaceX","cat":"CEO"},
    {"name":"Mark Zuckerberg","role":"CEO","org":"Meta","cat":"CEO"},
    {"name":"Sundar Pichai","role":"CEO","org":"Alphabet","cat":"CEO"},
    {"name":"Andy Jassy","role":"CEO","org":"Amazon","cat":"CEO"},
    {"name":"Hock Tan","role":"CEO","org":"Broadcom","cat":"CEO"},
    {"name":"Sanjay Mehrotra","role":"CEO","org":"Micron","cat":"CEO"},
    {"name":"C. C. Wei","role":"CEO","org":"TSMC","cat":"CEO"},
    {"name":"Lip-Bu Tan","role":"CEO","org":"Intel","cat":"CEO"},
    {"name":"Arvind Krishna","role":"CEO","org":"IBM","cat":"CEO"},
    {"name":"Larry Ellison","role":"Chairman and CTO","org":"Oracle","cat":"CEO"},
    {"name":"Cathie Wood","role":"CEO and CIO","org":"ARK Invest","cat":"Investor"},
    {"name":"Jim Cramer","role":"Host","org":"CNBC","cat":"Analyst"},
    {"name":"Gene Munster","role":"Managing Partner","org":"Deepwater Asset Management","cat":"Investor"},
    {"name":"Beth Kindig","role":"Lead Technology Analyst","org":"I/O Fund","cat":"Analyst"},
    {"name":"Stacy Rasgon","role":"Senior Analyst","org":"Bernstein","cat":"Analyst"},
    {"name":"Vivek Arya","role":"Senior Analyst","org":"Bank of America","cat":"Analyst"},
    {"name":"Hans Mosesmann","role":"Senior Analyst","org":"Rosenblatt Securities","cat":"Analyst"},
    {"name":"Pierre Ferragu","role":"Senior Analyst","org":"New Street Research","cat":"Analyst"},
    {"name":"Matt Ramsay","role":"Senior Analyst","org":"TD Cowen","cat":"Analyst"},
    {"name":"Toshiya Hari","role":"Senior Analyst","org":"Goldman Sachs","cat":"Analyst"},
    {"name":"Patrick Moorhead","role":"CEO and Chief Analyst","org":"Moor Insights and Strategy","cat":"Analyst"},
    {"name":"Dylan Patel","role":"Chief Analyst","org":"SemiAnalysis","cat":"Analyst"},
    {"name":"Morris Chang","role":"Founder","org":"TSMC","cat":"Investor"},
]

PROMPT = """Today is {date}. Use web_search to gather the past 24 hours of investment intel.
OUTPUT ONE JSON OBJECT with keys youtube, voices and news. Each item must have a real working source URL.
youtube: 5-10 recent AI-investing articles or videos with ch,c,theme,title,date,views,tags,verd,vc,body,url.
voices: 3-6 fresh CEO/analyst signals with name,role,org,cat,date,themes,quotes:[{{t,k:true}}],src.
news: 5-10 portfolio-relevant items with ticker,headline,date,summary,tag,url.
Return JSON only; never fabricate a direct quote."""

def call_claude_with_search() -> dict:
    client = Anthropic(api_key=require_key())
    msg = client.messages.create(model=MODEL, max_tokens=8000, tools=[{"type":"web_search_20250305","name":"web_search","max_uses":8}], messages=[{"role":"user","content":PROMPT.format(date=now_ist().strftime('%Y-%m-%d'))}])
    raw = "\n".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip(); raw = re.sub(r"```$", "", raw).strip()
    a,b = raw.find("{"), raw.rfind("}")
    if a < 0 or b < 0: raise ValueError("No JSON object returned")
    data = json.loads(raw[a:b+1])
    if not isinstance(data, dict): raise ValueError("Invalid research response")
    return data

def rss(query: str, limit: int = 8) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, timeout=15, headers={"User-Agent":"HVM-WarRoom/1.0"}); r.raise_for_status()
    root = ET.fromstring(r.content); out=[]
    for item in root.findall(".//item")[:limit]:
        title=(item.findtext("title") or "Market update").strip()
        link=(item.findtext("link") or "").strip()
        published=(item.findtext("pubDate") or "").strip()
        source=item.find("source")
        out.append({"title":title,"url":link,"source":(source.text if source is not None else "Google News"),"published":published})
    return out

def date_label(item: dict) -> str:
    return now_ist().strftime("%Y-%m-%d")

def ticker_from_title(title: str) -> str:
    up=title.upper()
    for t in TICKERS:
        if t in up: return t
    aliases={"NVIDIA":"NVDA","MICRON":"MU","PALANTIR":"PLTR","TESLA":"TSLA","BROADCOM":"AVGO","CROWDSTRIKE":"CRWD","VERTIV":"VRT","CONSTELLATION":"CEG","ARISTA":"ANET"}
    return next((t for n,t in aliases.items() if n in up), "AI")

def theme_for(title: str) -> str:
    u=title.upper()
    if any(x in u for x in ("NUCLEAR","POWER","ENERGY","GRID")): return "Energy"
    if any(x in u for x in ("ROBOT","TESLA","AUTONOM")): return "Robotics"
    if any(x in u for x in ("PALANTIR","AGENT","SOFTWARE")): return "Agentic AI"
    return "AI Compute"

def fallback_bundle() -> dict:
    general=rss("AI investing stocks Nvidia AMD Microsoft earnings", 12)
    if not general: raise RuntimeError("RSS fallback returned no research")
    news=[]
    for item in general[:8]:
        ticker=ticker_from_title(item["title"])
        news.append({"ticker":ticker,"headline":item["title"],"date":date_label(item),"summary":"Automated RSS market signal from %s. Open the linked source for full context before acting." % item["source"],"tag":"market","url":item["url"]})
    youtube=[]
    for item in general[:8]:
        ticker=ticker_from_title(item["title"])
        youtube.append({"ch":item["source"],"c":"#4a9eff","theme":theme_for(item["title"]),"title":item["title"],"date":date_label(item),"views":"RSS source","tags":["#"+ticker,"#AI"],"verd":"SOURCE-LINKED MARKET SIGNAL","vc":"var(--blue)","body":"Automated daily research feed. Read the linked source for the original reporting and context.","url":item["url"]})
    return {"youtube":youtube,"voices":[],"news":news}


def fetch_leader_signal(profile: dict) -> dict | None:
    """Return a source-linked headline from the last day; never invent a quote."""
    name = profile["name"]
    try:
        found = rss('"%s" (AI OR stocks OR earnings OR investment) when:1d' % name, 1)
    except Exception as exc:
        print("[leader-watch] %s: %s" % (name, exc), file=sys.stderr)
        return None
    if not found:
        return None
    item = found[0]
    return {
        **profile,
        "date": date_label(item),
        "published": item.get("published", ""),
        "source_name": item.get("source", "Google News"),
        "signal_type": "source-linked headline",
        "themes": ["#AI", "#" + ticker_from_title(item["title"])],
        "quotes": [{"t": "Headline signal (not a direct quote): " + item["title"], "k": True}],
        "src": item["url"],
    }


def fresh_leader_signals() -> list[dict]:
    order = {row["name"]: i for i, row in enumerate(LEADERS)}
    signals = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch_leader_signal, row) for row in LEADERS]
        for future in as_completed(futures):
            item = future.result()
            if item:
                signals.append(item)
    signals.sort(key=lambda row: order.get(row.get("name", ""), 999))
    return signals


def merge_voices(primary: list[dict], monitored: list[dict]) -> list[dict]:
    """Prefer paid source-linked research, then fill from the 30-person monitor."""
    out, seen = [], set()
    for row in list(primary or []) + monitored:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        src = str(row.get("src", "")).strip()
        quotes = row.get("quotes")
        if not name or not src.startswith("http") or not isinstance(quotes, list) or not quotes:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        row.setdefault("date", now_ist().strftime("%Y-%m-%d"))
        row.setdefault("themes", ["#AI"])
        row.setdefault("cat", "Research")
        row.setdefault("role", "Market signal")
        row.setdefault("org", row.get("source_name", "Daily research feed"))
        row.setdefault("signal_type", "source-linked signal")
        out.append(row)
    return out[:36]

def main() -> int:
    print("[update_news_youtube]", now_ist().isoformat())
    try:
        bundle=call_claude_with_search(); source="claude+web_search"
    except Exception as exc:
        print("[update_news_youtube] paid research unavailable; using RSS fallback:", exc, file=sys.stderr)
        bundle=fallback_bundle(); source="google-news-rss-fallback"
    for key in ("youtube","voices","news"):
        if not isinstance(bundle.get(key), list): bundle[key]=[]
    watched = fresh_leader_signals()
    bundle["voices"] = merge_voices(bundle["voices"], watched)
    write_json("youtube.json", envelope(bundle["youtube"], source=source))
    voices_doc = envelope(bundle["voices"], source=source + "+30-leader-monitor")
    voices_doc["monitored_leaders"] = len(LEADERS)
    voices_doc["fresh_window_hours"] = 24
    voices_doc["fresh_signal_count"] = len(bundle["voices"])
    write_json("voices.json", voices_doc)
    write_json("news.json", envelope(bundle["news"], source=source))
    print("[update_news_youtube] yt=%d voices=%d news=%d" % (len(bundle["youtube"]),len(bundle["voices"]),len(bundle["news"])))
    return 0
if __name__ == "__main__": sys.exit(main())
