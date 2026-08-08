#!/usr/bin/env python3
"""Refresh HVM investment themes and their investable stock cohorts.

The previous fallback kept theme headlines fresh but emitted ``tickers: []``.
That made the theme cards look live while their stock lists stayed frozen in
``index.html``.  This job now always publishes a complete, source-linked cohort:

* held names are reconciled from ``data/portfolio.json``;
* current portfolio actions come from ``data/actions.json``;
* prices come from ``data/prices.json`` and Yahoo's public chart endpoint;
* non-held candidates have an explicit NEW BUY or WATCH research status;
* paid AI research can add candidates, but a deterministic universe guarantees
  that the page remains useful when model credits are unavailable.

The output is research and portfolio-planning data only.  It never places an
order or moves money.
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests
from anthropic import Anthropic

from _common import DATA_DIR, envelope, now_ist, require_key, write_json


MODEL = "claude-haiku-4-5-20251001"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d&includePrePost=false"
HEADERS = {"User-Agent": "Mozilla/5.0 (HVM-WarRoom/3.0)"}


def stock(ticker: str, name: str, reason: str, default_action: str = "WATCH") -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "reason": reason,
        "default_action": default_action,
    }


# Target weights deliberately sum to 100%.  A ticker may appear in more than
# one research theme, but ``primary`` identifies the cohort used by the capital
# allocator so that the same holding is not double-counted.
THEME_CONFIG = {
    "AI Compute & Semiconductors": {
        "dashboard_name": "AI COMPUTE & SEMICONDUCTORS",
        "priority": "P1", "target_pct": 28,
        "query": "Nvidia AMD TSM Micron Broadcom ASML AI semiconductor stocks",
        "universe": [
            stock("NVDA", "Nvidia", "GPU compute and CUDA platform leader", "HOLD"),
            stock("TSM", "Taiwan Semiconductor", "Leading-edge foundry and CoWoS bottleneck", "HOLD"),
            stock("AMD", "Advanced Micro Devices", "Second-source accelerator and server CPU exposure", "WATCH"),
            stock("MU", "Micron", "HBM and memory-cycle exposure", "ADD"),
            stock("AVGO", "Broadcom", "Custom AI accelerators and networking", "ADD"),
            stock("ASML", "ASML", "EUV lithography monopoly", "ADD"),
            stock("MRVL", "Marvell", "Custom silicon and optical interconnect challenger", "WATCH"),
            stock("ARM", "Arm Holdings", "CPU architecture leverage across edge and data centre", "WATCH"),
        ],
    },
    "Energy & Nuclear Power": {
        "dashboard_name": "ENERGY & NUCLEAR POWER",
        "priority": "P0", "target_pct": 16,
        "query": "nuclear power grid data center energy CEG ETN VST GEV stocks",
        "universe": [
            stock("CEG", "Constellation Energy", "Nuclear fleet and hyperscaler power contracts", "ADD"),
            stock("ETN", "Eaton", "Grid equipment and electrical backlog", "NEW BUY"),
            stock("VST", "Vistra", "Nuclear and ERCOT power exposure", "NEW BUY"),
            stock("GEV", "GE Vernova", "Grid, turbine and electrification build-out", "WATCH"),
            stock("CCJ", "Cameco", "Uranium supply and nuclear fuel cycle", "WATCH"),
            stock("VRT", "Vertiv", "Data-centre cooling and power distribution", "ADD"),
            stock("BE", "Bloom Energy", "On-site fuel-cell power; speculative execution risk", "WATCH"),
        ],
    },
    "Defense & National Security": {
        "dashboard_name": "DEFENSE & NATIONAL SECURITY",
        "priority": "P0", "target_pct": 13,
        "query": "defense technology AI national security LMT RTX NOC LHX KTOS stocks",
        "universe": [
            stock("LMT", "Lockheed Martin", "Scaled prime contractor with multi-year backlog", "NEW BUY"),
            stock("RTX", "RTX", "Missiles, sensors and aerospace systems", "NEW BUY"),
            stock("NOC", "Northrop Grumman", "Space, stealth and strategic systems", "WATCH"),
            stock("LHX", "L3Harris", "Communications, sensors and electronic warfare", "WATCH"),
            stock("KTOS", "Kratos Defense", "Autonomous systems and lower-cost defense platforms", "WATCH"),
            stock("PLTR", "Palantir", "Defense software and operational AI", "HOLD"),
        ],
    },
    "Agentic AI & Enterprise SaaS": {
        "dashboard_name": "AGENTIC AI & ENTERPRISE SaaS",
        "priority": "P1", "target_pct": 10,
        "query": "enterprise agentic AI Palantir Microsoft ServiceNow Salesforce stocks",
        "universe": [
            stock("PLTR", "Palantir", "Operational AI platform and deployment velocity", "HOLD"),
            stock("MSFT", "Microsoft", "Copilot distribution and Azure AI platform", "ADD"),
            stock("GOOGL", "Alphabet", "Gemini distribution and cloud AI", "HOLD"),
            stock("AMZN", "Amazon", "AWS Bedrock and custom AI infrastructure", "HOLD"),
            stock("META", "Meta Platforms", "AI advertising and open-model optionality", "HOLD"),
            stock("NOW", "ServiceNow", "Enterprise workflow agent monetisation", "NEW BUY"),
            stock("CRM", "Salesforce", "Agentforce distribution into CRM workflows", "WATCH"),
            stock("PANW", "Palo Alto Networks", "AI-led enterprise security platform", "WATCH"),
        ],
    },
    "Healthcare AI & GLP-1": {
        "dashboard_name": "HEALTHCARE AI & GLP-1",
        "priority": "P2", "target_pct": 8,
        "query": "GLP-1 healthcare AI Eli Lilly Novo Nordisk Intuitive Surgical stocks",
        "universe": [
            stock("LLY", "Eli Lilly", "GLP-1 category leader and pipeline depth", "NEW BUY"),
            stock("NVO", "Novo Nordisk", "GLP-1 scale with valuation-reset potential", "WATCH"),
            stock("ISRG", "Intuitive Surgical", "Robotic surgery platform and recurring instruments", "WATCH"),
            stock("HIMS", "Hims & Hers", "Digital health distribution with regulatory risk", "WATCH"),
            stock("VKTX", "Viking Therapeutics", "Clinical-stage metabolic optionality", "WATCH"),
        ],
    },
    "Physical AI & Humanoid Robotics": {
        "dashboard_name": "PHYSICAL AI & HUMANOID ROBOTICS",
        "priority": "P2", "target_pct": 5,
        "query": "physical AI humanoid robotics Tesla Teradyne Symbotic stocks",
        "universe": [
            stock("TSLA", "Tesla", "Autonomy and humanoid optionality with valuation risk", "TRIM"),
            stock("TER", "Teradyne", "Industrial robotics and semiconductor test exposure", "NEW BUY"),
            stock("SYM", "Symbotic", "Warehouse automation with customer concentration", "WATCH"),
            stock("ROK", "Rockwell Automation", "Factory automation installed base", "WATCH"),
            stock("MBLY", "Mobileye", "ADAS and autonomous-driving stack", "WATCH"),
        ],
    },
    "Critical Minerals & Copper": {
        "dashboard_name": "CRITICAL MINERALS & COPPER",
        "priority": "P3", "target_pct": 3,
        "query": "copper critical minerals AI grid FCX SCCO MP ALB stocks",
        "universe": [
            stock("FCX", "Freeport-McMoRan", "Large, liquid copper producer with operating leverage", "NEW BUY"),
            stock("SCCO", "Southern Copper", "Low-cost copper production and reserves", "WATCH"),
            stock("MP", "MP Materials", "US rare-earth supply-chain exposure", "WATCH"),
            stock("ALB", "Albemarle", "Lithium-cycle recovery exposure", "WATCH"),
            stock("COPX", "Global X Copper Miners ETF", "Diversified copper-miner basket", "WATCH"),
        ],
    },
    "Sovereign AI Infrastructure": {
        "dashboard_name": "SOVEREIGN AI INFRASTRUCTURE",
        "priority": "P2", "target_pct": 17,
        "query": "sovereign AI infrastructure Dell Supermicro Oracle Arista Vertiv stocks",
        "universe": [
            stock("ANET", "Arista Networks", "High-speed networking for AI clusters", "ADD"),
            stock("VRT", "Vertiv", "Power and thermal infrastructure for AI facilities", "ADD"),
            stock("DELL", "Dell Technologies", "Enterprise and sovereign AI server integration", "NEW BUY"),
            stock("SMCI", "Super Micro Computer", "AI server density with governance risk", "WATCH"),
            stock("ORCL", "Oracle", "Cloud capacity and sovereign-region footprint", "WATCH"),
            stock("CRWD", "CrowdStrike", "Cloud workload security and sovereign environments", "WATCH"),
            stock("IBM", "IBM", "Government-grade hybrid cloud and Red Hat", "WATCH"),
        ],
    },
}
THEMES = list(THEME_CONFIG)

PROMPT = """Today is {date}. Use web_search to refresh these investment themes: {themes}.
Return a JSON array where each item has theme, rating HOT|WARM|COLD, rc,
summary, news:[{{title,date,url}}], and tickers. Tickers must be US-listed stock
symbols that are directly relevant to the theme. Every statement needs a source
URL; never invent a data point. This is research, not an order instruction."""


def read_json(name: str) -> dict:
    try:
        return json.loads((Path(DATA_DIR) / name).read_text())
    except Exception:
        return {}


def call_claude_with_search() -> list[dict]:
    client = Anthropic(api_key=require_key())
    msg = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": PROMPT.format(
            date=now_ist().strftime("%Y-%m-%d"), themes="; ".join(THEMES)
        )}],
    )
    raw = "\n".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("No JSON array returned")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("Invalid themes response")
    return data


def rss(query: str, limit: int = 3) -> list[dict]:
    response = requests.get(
        "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en",
        timeout=15,
        headers=HEADERS,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    out = []
    for item in root.findall(".//item")[:limit]:
        out.append({
            "title": (item.findtext("title") or "Market update").strip(),
            "date": now_ist().strftime("%Y-%m-%d"),
            "url": (item.findtext("link") or "").strip(),
        })
    return out


def fallback_themes() -> list[dict]:
    previous = {
        str(item.get("theme", "")): item
        for item in read_json("themes.json").get("items", [])
        if isinstance(item, dict)
    }
    out = []
    for theme, cfg in THEME_CONFIG.items():
        prior = previous.get(theme, {})
        try:
            articles = rss(cfg["query"])
        except Exception as exc:
            print(f"[update_themes] RSS unavailable for {theme}: {exc}", file=sys.stderr)
            articles = prior.get("news", []) if isinstance(prior.get("news"), list) else []
        headline = articles[0]["title"] if articles else "No fresh RSS headline returned"
        summary = (
            "Daily automated RSS scan on %s. Latest source-linked signal: %s"
            % (now_ist().strftime("%Y-%m-%d"), headline)
            if articles
            else prior.get("summary") or "No fresh RSS headline returned; retaining the configured cohort."
        )
        out.append({
            "theme": theme,
            "rating": prior.get("rating", "WARM"),
            "rc": prior.get("rc", "var(--gold)"),
            "summary": summary,
            "news": articles,
            "tickers": [],
        })
    return out


def clean_ticker(value) -> str:
    if isinstance(value, dict):
        value = value.get("ticker") or value.get("symbol") or value.get("s") or ""
    value = re.sub(r"[^A-Za-z.-]", "", str(value or "")).upper()
    return value if 1 <= len(value) <= 6 else ""


def fetch_quote(ticker: str) -> tuple[str, dict]:
    try:
        response = requests.get(YAHOO_CHART.format(ticker=ticker), headers=HEADERS, timeout=12)
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes = [x for x in closes if x is not None]
            price = closes[-1] if closes else None
        change = ((price / previous - 1) * 100) if price and previous else None
        return ticker, {
            "price": round(float(price), 2) if price is not None else None,
            "change_pct": round(float(change), 2) if change is not None else None,
        }
    except Exception as exc:
        print(f"[update_themes] quote unavailable for {ticker}: {exc}", file=sys.stderr)
        return ticker, {"price": None, "change_pct": None}


def load_known_prices() -> dict[str, dict]:
    raw = read_json("prices.json").get("prices", {})
    return {
        ticker: {
            "price": quote.get("price"),
            "change_pct": quote.get("changePct"),
        }
        for ticker, quote in raw.items()
    }


def quote_universe(tickers: set[str], known: dict[str, dict]) -> dict[str, dict]:
    missing = sorted(t for t in tickers if not known.get(t, {}).get("price"))
    if not missing:
        return known
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_quote, ticker) for ticker in missing]
        for future in as_completed(futures):
            ticker, quote = future.result()
            known[ticker] = quote
    return known


def normalize_action(value: str) -> str:
    value = str(value or "").upper()
    if "TRIM" in value or "SELL" in value:
        return "TRIM"
    if "ADD" in value or "BUY" in value or "URGENT" in value:
        return "ADD"
    if "HOLD" in value:
        return "HOLD"
    return "WATCH"


def normalize_themes(raw_items: list[dict], source: str) -> list[dict]:
    portfolio = read_json("portfolio.json").get("holdings", [])
    held = {str(row.get("ticker", "")).upper(): row for row in portfolio}
    actions = {
        str(row.get("ticker", "")).upper(): row
        for row in read_json("actions.json").get("items", [])
    }
    raw_by_name = {str(item.get("theme", "")): item for item in raw_items if isinstance(item, dict)}

    all_tickers = {row["ticker"] for cfg in THEME_CONFIG.values() for row in cfg["universe"]}
    for item in raw_items:
        for value in item.get("tickers", []) if isinstance(item, dict) else []:
            ticker = clean_ticker(value)
            if ticker:
                all_tickers.add(ticker)
    quotes = quote_universe(all_tickers, load_known_prices())

    normalized = []
    for theme, cfg in THEME_CONFIG.items():
        live = raw_by_name.get(theme, {})
        articles = live.get("news") if isinstance(live.get("news"), list) else []
        title_blob = " ".join(str(x.get("title", "")) for x in articles).upper()
        discovered = []
        for value in live.get("tickers", []) if isinstance(live.get("tickers"), list) else []:
            ticker = clean_ticker(value)
            if ticker and ticker not in {x["ticker"] for x in cfg["universe"]}:
                discovered.append(stock(ticker, ticker, "Discovered by today's source-linked theme scan", "WATCH"))

        rows = []
        for spec in cfg["universe"] + discovered:
            ticker = spec["ticker"]
            current_action = normalize_action(actions.get(ticker, {}).get("action")) if ticker in actions else ""
            is_owned = ticker in held
            status = current_action if current_action else ("OWN" if is_owned else spec["default_action"])
            if status == "WATCH" and is_owned:
                status = "OWN"
            mention_score = title_blob.count(ticker) + title_blob.count(spec["name"].upper())
            priority_score = {"ADD": 60, "NEW BUY": 50, "OWN": 40, "HOLD": 35, "WATCH": 20, "TRIM": 0}.get(status, 10)
            rows.append({
                "ticker": ticker,
                "name": spec["name"],
                "status": status,
                "owned": is_owned,
                "priority": cfg["priority"],
                "price": quotes.get(ticker, {}).get("price"),
                "change_pct": quotes.get(ticker, {}).get("change_pct"),
                "units": held.get(ticker, {}).get("units", 0),
                "current_value": round(
                    float(held.get(ticker, {}).get("units", 0) or 0)
                    * float(quotes.get(ticker, {}).get("price", 0) or 0), 2
                ),
                "source_hits": mention_score,
                "reason": spec["reason"],
                "score": priority_score + mention_score * 5,
            })
        rows.sort(key=lambda row: (-row["score"], -int(row["owned"]), row["ticker"]))
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
            row.pop("score", None)

        normalized.append({
            "theme": theme,
            "dashboard_name": cfg["dashboard_name"],
            "priority": cfg["priority"],
            "target_pct": cfg["target_pct"],
            "rating": live.get("rating", "WARM"),
            "rc": live.get("rc", "var(--gold)"),
            "summary": live.get("summary") or "Daily research packet refreshed from the configured evidence feed.",
            "news": articles,
            "tickers": rows,
            "candidate_count": sum(1 for row in rows if not row["owned"]),
            "owned_count": sum(1 for row in rows if row["owned"]),
            "research_mode": "AI + sources" if source == "claude+web_search" else "RSS + deterministic cohort",
            "cohort_updated_at": now_ist().isoformat(),
        })
    return normalized


def main() -> int:
    print("[update_themes]", now_ist().isoformat())
    try:
        raw = call_claude_with_search()
        source = "claude+web_search"
    except Exception as exc:
        print("[update_themes] paid research unavailable; using RSS fallback:", exc, file=sys.stderr)
        raw = fallback_themes()
        source = "google-news-rss+deterministic-cohorts"
    themes = normalize_themes(raw, source)
    write_json("themes.json", envelope(themes, source=source))
    print("[update_themes] themes=%d tickers=%d" % (
        len(themes), sum(len(item["tickers"]) for item in themes)
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
