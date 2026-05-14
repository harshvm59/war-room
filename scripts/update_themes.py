#!/usr/bin/env python3
"""
Themes refresh — runs every 2 days at 09:00 IST.

Uses Anthropic's `web_search` tool to gather the latest data points for each of
the 8 macro investment themes the dashboard tracks. Writes a single
`data/themes.json` consumed by the dashboard.
"""

from __future__ import annotations

import json
import re
import sys

from anthropic import Anthropic

from _common import envelope, now_ist, require_key, write_json

MODEL = "claude-sonnet-4-5-20250929"

THEMES = [
    "AI Compute & Semiconductors",
    "Energy & Nuclear Power",
    "Defense & National Security",
    "Agentic AI & Enterprise SaaS",
    "Healthcare AI & GLP-1",
    "Physical AI & Humanoid Robotics",
    "Critical Minerals & Copper",
    "Sovereign AI Infrastructure",
]


PROMPT = """Today is {date}. Use web_search to refresh the 8 investment themes
the HVM Investment OS tracks. For each theme, find 1–2 fresh data points or
news items from the past 7 days and assign a heat rating.

OUTPUT a single JSON array, one object per theme, in this exact order:
{themes}

Each object shape:
{{
  "theme": "AI Compute & Semiconductors",
  "rating": "HOT|WARM|COLD",
  "rc": "var(--red)|var(--gold)|var(--blue)",   // red=hot, gold=warm, blue=cold
  "summary": "2-3 sentence current state of the theme, with hard numbers and dated data.",
  "news": [
    {{ "title": "Headline", "date": "YYYY-MM-DD", "url": "https://..." }}
  ],
  "tickers": ["NVDA", "MU", "TSM"]
}}

Rules:
- Each item MUST include at least one real news URL from web_search.
- Skip anything older than 7 days.
- Return ONLY the JSON array, nothing else.
"""


def call_claude_with_search() -> list[dict]:
    client = Anthropic(api_key=require_key())

    msg = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 10,
            }
        ],
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(
                    date=now_ist().strftime("%Y-%m-%d"),
                    themes="\n".join(f"  - {t}" for t in THEMES),
                ),
            }
        ],
    )
    text_blocks = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    raw = "\n".join(text_blocks).strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    s, e = raw.find("["), raw.rfind("]")
    if s == -1 or e == -1:
        raise ValueError(f"No JSON array in response:\n{raw[:600]}")
    data = json.loads(raw[s : e + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("Parsed response is not a non-empty list.")
    return data


def main() -> int:
    print(f"[update_themes] {now_ist().isoformat()}")
    themes = call_claude_with_search()
    print(f"[update_themes] got {len(themes)} themes")
    write_json("themes.json", envelope(themes, source="claude+web_search"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
