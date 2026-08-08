#!/usr/bin/env python3
"""Daily themes refresh with source-linked RSS fallback when paid research is unavailable."""
from __future__ import annotations
import json, re, sys
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
import requests
from anthropic import Anthropic
from _common import envelope, now_ist, require_key, write_json

MODEL="claude-haiku-4-5-20251001"
THEMES=["AI Compute & Semiconductors","Energy & Nuclear Power","Defense & National Security","Agentic AI & Enterprise SaaS","Healthcare AI & GLP-1","Physical AI & Humanoid Robotics","Critical Minerals & Copper","Sovereign AI Infrastructure"]
PROMPT="""Today is {date}. Use web_search to refresh these investment themes: {themes}. Return a JSON array where each item has theme, rating HOT|WARM|COLD, rc, summary, news:[{{title,date,url}}], and tickers. Every statement needs a source URL; never make up a data point."""

def call_claude_with_search():
    client=Anthropic(api_key=require_key())
    msg=client.messages.create(model=MODEL,max_tokens=8000,tools=[{"type":"web_search_20250305","name":"web_search","max_uses":10}],messages=[{"role":"user","content":PROMPT.format(date=now_ist().strftime('%Y-%m-%d'),themes='; '.join(THEMES))}])
    raw='\n'.join(b.text for b in msg.content if getattr(b,'type','')=='text').strip()
    a,b=raw.find('['),raw.rfind(']')
    if a<0 or b<0: raise ValueError('No JSON array returned')
    data=json.loads(raw[a:b+1])
    if not isinstance(data,list) or not data: raise ValueError('Invalid themes response')
    return data

def rss(query, limit=2):
    r=requests.get('https://news.google.com/rss/search?q='+quote_plus(query)+'&hl=en-US&gl=US&ceid=US:en',timeout=15,headers={'User-Agent':'HVM-WarRoom/1.0'}); r.raise_for_status()
    root=ET.fromstring(r.content); out=[]
    for x in root.findall('.//item')[:limit]: out.append({'title':(x.findtext('title') or 'Market update').strip(),'date':now_ist().strftime('%Y-%m-%d'),'url':(x.findtext('link') or '').strip()})
    return out

def fallback_themes():
    queries={
      'AI Compute & Semiconductors':'Nvidia AMD TSM semiconductor AI stocks',
      'Energy & Nuclear Power':'nuclear energy data center power CEG stocks',
      'Defense & National Security':'defense technology AI stocks national security',
      'Agentic AI & Enterprise SaaS':'enterprise AI software Palantir agentic AI stocks',
      'Healthcare AI & GLP-1':'GLP-1 healthcare AI stocks Eli Lilly Novo Nordisk',
      'Physical AI & Humanoid Robotics':'humanoid robotics Tesla physical AI stocks',
      'Critical Minerals & Copper':'copper critical minerals AI data center stocks',
      'Sovereign AI Infrastructure':'sovereign AI infrastructure government data center stocks',
    }
    out=[]
    for theme in THEMES:
        articles=rss(queries[theme])
        headline=articles[0]['title'] if articles else 'No fresh RSS headline returned'
        out.append({'theme':theme,'rating':'WARM','rc':'var(--gold)','summary':'Daily automated RSS scan on %s. Latest source-linked signal: %s' % (now_ist().strftime('%Y-%m-%d'),headline),'news':articles,'tickers':[]})
    return out

def main():
    print('[update_themes]',now_ist().isoformat())
    try: themes=call_claude_with_search(); source='claude+web_search'
    except Exception as exc:
        print('[update_themes] paid research unavailable; using RSS fallback:',exc,file=sys.stderr)
        themes=fallback_themes(); source='google-news-rss-fallback'
    write_json('themes.json',envelope(themes,source=source)); print('[update_themes] themes=%d' % len(themes)); return 0
if __name__=='__main__': sys.exit(main())
