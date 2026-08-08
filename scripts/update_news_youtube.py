#!/usr/bin/env python3
"""Daily investment research feed with an Anthropic-web-search primary and RSS fallback.

The fallback deliberately writes only source-linked headlines and labels leader items
as signals rather than inventing quotes. It keeps the dashboard fresh when the paid
research provider is unavailable.
"""
from __future__ import annotations
import json, re, sys
from datetime import datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
import requests
from anthropic import Anthropic
from _common import TICKERS, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"
CHANNELS = ["Tom Nash", "CNBC Fast Money", "Bloomberg Markets", "Yahoo Finance", "Motley Fool", "ARK Invest", "Benzinga"]
LEADERS = ["Jensen Huang", "Sam Altman", "Dan Ives", "Satya Nadella", "Lisa Su", "Chamath Palihapitiya"]

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
    roles={"Jensen Huang":("CEO","Nvidia"),"Sam Altman":("CEO","OpenAI"),"Dan Ives":("Analyst","Wedbush"),"Satya Nadella":("CEO","Microsoft"),"Lisa Su":("CEO","AMD"),"Chamath Palihapitiya":("Investor","Social Capital")}
    voices=[]
    for name in LEADERS:
        found=rss('"%s" AI investment' % name, 1)
        if not found: continue
        item=found[0]; role,org=roles[name]
        voices.append({"name":name,"role":role,"org":org,"cat":"Analyst" if role=="Analyst" else "CEO" if role=="CEO" else "Investor","date":date_label(item),"themes":["#AI","#"+ticker_from_title(item["title"])],"quotes":[{"t":"Headline signal (not a direct quote): "+item["title"],"k":True}],"src":item["url"]})
    return {"youtube":youtube,"voices":voices,"news":news}

def main() -> int:
    print("[update_news_youtube]", now_ist().isoformat())
    try:
        bundle=call_claude_with_search(); source="claude+web_search"
    except Exception as exc:
        print("[update_news_youtube] paid research unavailable; using RSS fallback:", exc, file=sys.stderr)
        bundle=fallback_bundle(); source="google-news-rss-fallback"
    for key in ("youtube","voices","news"):
        if not isinstance(bundle.get(key), list): bundle[key]=[]
    write_json("youtube.json", envelope(bundle["youtube"], source=source))
    write_json("voices.json", envelope(bundle["voices"], source=source))
    write_json("news.json", envelope(bundle["news"], source=source))
    print("[update_news_youtube] yt=%d voices=%d news=%d" % (len(bundle["youtube"]),len(bundle["voices"]),len(bundle["news"])))
    return 0
if __name__ == "__main__": sys.exit(main())
