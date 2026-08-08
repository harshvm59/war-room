#!/usr/bin/env python3
"""Build the live investment-firm agent workboard.

Each run reads the current rule-based TA/action data and scans fresh, source-linked
Google News RSS results for the desk's assigned investment theme.  It produces
``data/agent_ops.json`` for the CEO workspace.  The client never executes trades;
it only displays research, assigned coverage and review queues.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests

from _common import DATA_DIR, envelope, now_ist, write_json

AGENTS = [
    {
        "code": "PULSE", "name": "Aanya Menon", "desk": "AI Compute & Semiconductors",
        "mission": "Track the AI compute stack and surface semiconductor catalysts.",
        "coverage": ["NVDA", "AMD", "TSM", "MU", "AVGO", "ASML"],
        "query": "Nvidia AMD TSM Micron Broadcom AI semiconductor stocks",
    },
    {
        "code": "MOSAIC", "name": "Nikhil Verma", "desk": "AI Platforms & Hyperscalers",
        "mission": "Compare AI monetisation, cloud demand and capex across big tech.",
        "coverage": ["MSFT", "META", "GOOGL", "AMZN"],
        "query": "Microsoft Meta Alphabet Amazon AI cloud capex stocks",
    },
    {
        "code": "VECTOR", "name": "Isha Nair", "desk": "Technical Strategy Desk",
        "mission": "Read price, trend, RSI and momentum before any action reaches CIO.",
        "coverage": ["NVDA", "TSM", "AMD", "MU", "AVGO", "MSFT"],
        "query": "AI stocks technical analysis Nvidia AMD semiconductor market",
    },
    {
        "code": "CATALYST", "name": "Dev Malhotra", "desk": "Earnings & Catalysts",
        "mission": "Watch results, guidance, contracts and product catalysts across holdings.",
        "coverage": ["NVDA", "AMD", "PLTR", "META", "AMZN", "TSLA"],
        "query": "AI stock earnings guidance Nvidia AMD Palantir Meta Amazon Tesla",
    },
    {
        "code": "ECHO", "name": "Tara Khanna", "desk": "Leadership & Capital Signals",
        "mission": "Monitor CEO, investor and analyst statements without treating headlines as facts.",
        "coverage": ["NVDA", "MSFT", "AMD", "PLTR"],
        "query": "Jensen Huang Satya Nadella Lisa Su Alex Karp AI investment statements",
    },
    {
        "code": "ATLAS", "name": "Arjun Kapoor", "desk": "AI Infrastructure & Networking",
        "mission": "Track data-centre demand, networking and physical infrastructure bottlenecks.",
        "coverage": ["VRT", "ANET", "AVGO", "TSM"],
        "query": "Vertiv Arista data center AI infrastructure networking stocks",
    },
    {
        "code": "LEDGER", "name": "Kunal Mehta", "desk": "Portfolio & Capital Deployment",
        "mission": "Reconcile holdings, units, cash and implementation capacity before a decision.",
        "coverage": ["NVDA", "TSM", "META", "PLTR", "AVGO", "CEG"],
        "query": "portfolio management position sizing investment allocation AI stocks",
    },
    {
        "code": "SENTINEL", "name": "Kabir Singh", "desk": "Risk, Power & Nuclear",
        "mission": "Stress-test concentration and monitor power/nuclear exposure supporting AI demand.",
        "coverage": ["CEG", "BE", "VRT", "TSLA"],
        "query": "nuclear power data centers Constellation Energy Bloom Energy AI demand",
    },
    {
        "code": "MACRO", "name": "Priya Desai", "desk": "Macro, Policy & Liquidity",
        "mission": "Follow rates, energy, policy and geopolitical changes that alter portfolio risk.",
        "coverage": ["CEG", "TSM", "ASML", "BE"],
        "query": "AI data center power rates policy semiconductor geopolitics market",
    },
    {
        "code": "SOURCECHECK", "name": "Zoya Ali", "desk": "Evidence & Research Integrity",
        "mission": "Verify links, freshness and source quality before research reaches the investment committee.",
        "coverage": ["NVDA", "AMD", "PLTR", "MSFT", "CEG"],
        "query": "AI investment stocks credible market research sources",
    },
]


def read_doc(name: str) -> dict:
    path = Path(DATA_DIR) / name
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def rss(query: str) -> dict:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
    try:
        response = requests.get(url, timeout=18, headers={"User-Agent": "HVM-AgentOps/1.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        item = root.find(".//item")
        if item is None:
            raise RuntimeError("No RSS item")
        source = item.find("source")
        return {
            "headline": (item.findtext("title") or "Fresh source-linked market update").strip(),
            "url": (item.findtext("link") or "").strip(),
            "source": (source.text if source is not None else "Google News").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
        }
    except Exception as exc:
        print(f"[agent_heartbeat] RSS unavailable for {query!r}: {exc}", file=sys.stderr)
        return {"headline": "RSS source temporarily unavailable — desk is using its latest verified packet.", "url": "", "source": "RSS retry pending", "published": ""}


def main() -> int:
    print("[agent_heartbeat]", now_ist().isoformat())
    actions = read_doc("actions.json").get("items", [])
    by_ticker = {str(a.get("ticker", "")).upper(): a for a in actions}
    out = []
    for spec in AGENTS:
        relevant = [by_ticker[t] for t in spec["coverage"] if t in by_ticker]
        relevant.sort(key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(a.get("urgency", "low")).lower(), 9))
        primary = relevant[0] if relevant else {}
        latest = rss(spec["query"])
        if primary:
            activity = f"Reviewing {primary.get('ticker')} · {primary.get('action', 'WATCH')} · {primary.get('urgency', 'standard')} priority."
            recommendation = primary.get("action_text") or primary.get("signal") or "Review the latest rules-based technical signal."
        else:
            activity = "Scanning source-linked research and waiting for the next technical action update."
            recommendation = "No desk-specific action is currently ranked above the review threshold."
        out.append({
            **spec,
            "status": "WORKING",
            "activity": activity,
            "recommendation": recommendation,
            "signals": relevant[:4],
            "latest": latest,
            "updated_at": now_ist().isoformat(),
        })
        print(f"[agent_heartbeat] {spec['code']}: {latest['source']} | {latest['headline'][:70]}")

    doc = envelope(out, source="google-news-rss+local-ta+rules")
    doc.update({
        "cadence": "hourly online research heartbeat; TA refreshes separately during market hours",
        "firm_status": "Research only — CEO approval required before investment decisions.",
        "agent_count": len(out),
    })
    write_json("agent_ops.json", doc)
    print(f"[agent_heartbeat] wrote {len(out)} agent packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
