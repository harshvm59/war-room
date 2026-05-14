#!/usr/bin/env python3
"""
Daily news + YouTube scrape — runs once per day at 09:00 IST.

Uses Anthropic's `web_search` tool to pull the past 24h of:
  - Top 10 YouTube investment videos (channel, title, date, key tickers, thesis)
  - Top leader signals / quotes (Jensen Huang, Sam Altman, Dan Ives, Chamath, etc)
  - Portfolio earnings/upgrades/downgrades news

Writes:
  - data/news.json   { items: [...] }
  - data/youtube.json { items: [...] }
  - data/voices.json  { items: [...] }
"""

from __future__ import annotations

import json
import re
import sys

from anthropic import Anthropic

from _common import TICKERS, envelope, now_ist, require_key, write_json

MODEL = "claude-haiku-4-5-20251001"

CHANNELS = [
    "Tom Nash", "CNBC Fast Money", "Bloomberg Markets", "Yahoo Finance",
    "Motley Fool", "ARK Invest", "Andrei Jikh", "Patrick Boyle",
    "Meet Kevin", "Joseph Hogue CFA", "Schwab Network", "Benzinga",
]

LEADERS = [
    "Jensen Huang", "Sam Altman", "Dan Ives", "Satya Nadella",
    "Lisa Su", "Hock Tan", "Chamath Palihapitiya", "Cathie Wood",
    "Marc Andreessen", "Alex Karp", "Jim Cramer",
]


PROMPT = """Today is {date}. Use web_search to gather the past 24 hours of investment intel.

OUTPUT ONE JSON OBJECT with these three keys (no markdown, no preamble):

{{
  "youtube": [
    {{
      "ch": "Channel name",
      "c": "#4a9eff",
      "theme": "AI Compute|Energy|Defense|Agentic AI|Healthcare|Robotics|Critical Minerals|Sovereign AI",
      "title": "Video title",
      "date": "{date}",
      "views": "Views or source label",
      "tags": ["#NVDA", "#AI"],
      "verd": "ONE-LINE VERDICT",
      "vc": "var(--green)|var(--red)|var(--gold)|var(--blue)",
      "body": "2-3 sentence summary of the key thesis",
      "url": "https://youtube.com/..."
    }}
  ],
  "voices": [
    {{
      "name": "Jensen Huang",
      "role": "CEO",
      "org": "Nvidia",
      "cat": "CEO|Analyst|Investor",
      "date": "{date}",
      "themes": ["#NVDA", "#AI"],
      "quotes": [{{ "t": "Direct quote", "k": true }}],
      "src": "https://source-url"
    }}
  ],
  "news": [
    {{
      "ticker": "NVDA",
      "headline": "Short headline",
      "date": "{date}",
      "summary": "1-2 sentence what & why it matters",
      "tag": "earnings|upgrade|downgrade|deal|product|macro",
      "url": "https://..."
    }}
  ]
}}

Rules:
- youtube: aim for 5–10 items, prioritize {channels}.
- voices: aim for 3–6 fresh quotes from {leaders}.
- news: aim for 5–10 portfolio-relevant items across {tickers}.
- Each item MUST have a real working URL from web_search results.
- Skip anything older than 36h.
- Return ONLY the JSON object, nothing else.
"""


def call_claude_with_search() -> dict:
    client = Anthropic(api_key=require_key())

    msg = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 8,
            }
        ],
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(
                    date=now_ist().strftime("%Y-%m-%d"),
                    channels=", ".join(CHANNELS),
                    leaders=", ".join(LEADERS),
                    tickers=", ".join(TICKERS),
                ),
            }
        ],
    )

    text_blocks = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    raw = "\n".join(text_blocks).strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"No JSON object in response:\n{raw[:600]}")
    data = json.loads(raw[s : e + 1])
    if not isinstance(data, dict):
        raise ValueError("Parsed response is not a dict.")
    return data


def main() -> int:
    print(f"[update_news_youtube] {now_ist().isoformat()}")
    bundle = call_claude_with_search()

    yt = bundle.get("youtube") or []
    voices = bundle.get("voices") or []
    news = bundle.get("news") or []

    print(f"[update_news_youtube] yt={len(yt)} voices={len(voices)} news={len(news)}")

    write_json("youtube.json", envelope(yt, source="claude+web_search"))
    write_json("voices.json", envelope(voices, source="claude+web_search"))
    write_json("news.json", envelope(news, source="claude+web_search"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
