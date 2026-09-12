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
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree as ET

import requests
from _research import research_json

from _common import DATA_DIR, envelope, now_ist, write_json, publication_time, is_recent, public_error


YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d&includePrePost=false"
HEADERS = {"User-Agent": "Mozilla/5.0 (HVM-WarRoom/3.0)"}
QUERY_STOPWORDS = {
    "AI", "AND", "THE", "FOR", "STOCK", "STOCKS", "THEME", "INVESTING",
    "TECHNOLOGY", "COMPANY", "COMPANIES", "MARKET", "US", "DATA", "CENTER",
}
LOW_SIGNAL_ARTICLE_TERMS = (
    "STOCK PRICE, NEWS, QUOTE & HISTORY", "HISTORICAL DATA", "COMPANY PROFILE",
    "MESSAGE BOARD", "NET WORTH", "WEDDING", "DIVORCE", "MANSION",
)


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

PROMPT = """Research time: {date}. Use web search to refresh these investment themes: {themes}.
Return a JSON array with theme, rating HOT|ACTIVE|QUIET, rc, summary,
news:[{{title,date,published,url,source}}], and tickers (US-listed stock symbols directly relevant to the theme).
Only include articles published in the last 24 hours. Every article must carry its actual source publication
timestamp in published (ISO 8601 with timezone), its source date, and the direct article URL, not a search-results page.
Never substitute the research date for a missing source date. Exclude undated or stale articles; use QUIET,
empty news and an explicit no-fresh-evidence summary when no qualifying article exists.
Every factual statement and discovered ticker must be supported by a linked article. Do not use training-memory
financial figures or fabricate quotes. This is source-linked research, not an order instruction. Return JSON only."""

def read_json(name: str) -> dict:
    try:
        return json.loads((Path(DATA_DIR) / name).read_text())
    except Exception:
        return {}


def call_research() -> list[dict]:
    data = research_json("themes", PROMPT.format(date=now_ist().isoformat(), themes="; ".join(THEMES)))
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError("Invalid themes response")
    for item in data:
        clean = []
        for article in item.get("news", []) if isinstance(item.get("news"), list) else []:
            if not isinstance(article, dict):
                continue
            parsed = urlparse(str(article.get("url", "")))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or not is_recent(article.get("published")):
                continue
            article = dict(article)
            article["date"] = publication_time(article["published"]).astimezone(now_ist().tzinfo).strftime("%Y-%m-%d")
            clean.append(article)
        item["news"] = clean
        if not clean:
            item["rating"] = "QUIET"
            item["summary"] = "No qualifying source-linked article in the rolling 24-hour window; the configured cohort remains under monitoring."
            item["tickers"] = []
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
    for item in root.findall(".//item"):
        published = (item.findtext("pubDate") or "").strip()
        if not is_recent(published):
            continue
        source = item.find("source")
        out.append({
            "title": (item.findtext("title") or "Market update").strip(),
            "date": publication_time(published).astimezone(now_ist().tzinfo).strftime("%Y-%m-%d"),
            "url": (item.findtext("link") or "").strip(),
            "source": source.text.strip() if source is not None and source.text else "Google News",
            "published": published,
        })
        if len(out) >= limit:
            break
    return out


def article_relevance_score(article: dict, cfg: dict) -> int:
    """Score explicit theme/ticker matches so name-adjacent noise is discarded."""
    title = str(article.get("title", "")).upper()
    if any(term in title for term in LOW_SIGNAL_ARTICLE_TERMS):
        return -10
    score = 0
    for spec in cfg["universe"]:
        ticker = spec["ticker"]
        if re.search(r"(?<![A-Z0-9])" + re.escape(ticker) + r"(?![A-Z0-9])", title):
            score += 5
        if len(spec["name"]) > 3 and spec["name"].upper() in title:
            score += 4
    keywords = {
        word for word in re.findall(r"[A-Z0-9-]+", cfg["query"].upper())
        if len(word) >= 4 and word not in QUERY_STOPWORDS
    }
    score += min(6, sum(2 for word in keywords if word in title))
    return score


def relevant_articles(articles: list[dict], cfg: dict, limit: int = 3) -> list[dict]:
    ranked = []
    for article in articles:
        if not isinstance(article, dict) or not str(article.get("url", "")).startswith("http"):
            continue
        score = article_relevance_score(article, cfg)
        if score < 2:
            continue
        clean = dict(article)
        clean["relevance_score"] = score
        ranked.append(clean)
    ranked.sort(key=lambda row: row["relevance_score"], reverse=True)
    return ranked[:limit]


def fallback_themes() -> list[dict]:
    out = []
    failures = 0
    for theme, cfg in THEME_CONFIG.items():
        try:
            articles = relevant_articles(rss(cfg["query"] + " when:1d", 8), cfg)
        except Exception as exc:
            failures += 1
            print(f"[update_themes] RSS unavailable for {theme}: {exc}", file=sys.stderr)
            articles = []
        headline = articles[0]["title"] if articles else "No fresh RSS headline returned"
        summary = (
            "Daily automated RSS scan on %s. Latest source-linked signal: %s"
            % (now_ist().strftime("%Y-%m-%d"), headline)
            if articles
            else "No qualifying source-linked article in the rolling 24-hour window; the configured cohort remains under monitoring."
        )
        out.append({
            "theme": theme,
            "rating": "ACTIVE" if articles else "QUIET",
            "rc": "var(--gold)" if articles else "var(--blue)",
            "summary": summary,
            "news": articles,
            "tickers": [],
        })
    if failures == len(THEME_CONFIG):
        raise RuntimeError("All theme RSS feeds failed; retaining the previous research packet")
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
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [x for x in closes if x is not None]
        # chartPreviousClose is the beginning of the requested 5-day range,
        # not yesterday's close. Use the adjacent daily closes for 1D change.
        previous = closes[-2] if len(closes) > 1 else meta.get("previousClose")
        if price is None:
            price = closes[-1] if closes else None
        change = ((price / previous - 1) * 100) if price and previous else None
        return ticker, {
            "price": round(float(price), 2) if price is not None else None,
            "change_pct": round(float(change), 2) if change is not None else None,
            "as_of": datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc).isoformat() if meta.get("regularMarketTime") else None,
            "retrieved_at": now_ist().isoformat(),
            "status": "fetched" if price is not None else "missing",
        }
    except Exception as exc:
        print(f"[update_themes] quote unavailable for {ticker}: {exc}", file=sys.stderr)
        return ticker, {"price": None, "change_pct": None, "as_of": None, "status": "missing"}


def load_known_prices() -> dict[str, dict]:
    raw = read_json("prices.json").get("prices", {})
    return {
        ticker: {
            "price": quote.get("price"),
            "change_pct": quote.get("changePct"),
            "as_of": quote.get("as_of"),
            "retrieved_at": quote.get("retrieved_at"),
            "status": "retained",
        }
        for ticker, quote in raw.items()
    }


def quote_universe(tickers: set[str], known: dict[str, dict]) -> dict[str, dict]:
    # A theme refresh must request every quote, including held names. Existing
    # prices are only a dated fallback when the current request fails.
    missing = sorted(tickers)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_quote, ticker) for ticker in missing]
        for future in as_completed(futures):
            ticker, quote = future.result()
            if quote.get("price") is not None or not known.get(ticker, {}).get("price"):
                known[ticker] = quote
            else:
                known[ticker]["status"] = "retained"
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


def fresh_daily_moves(rows: list[dict]) -> list[float]:
    """Retained or undated quotes cannot contribute to a fresh momentum score."""
    return [
        float(row["change_pct"]) for row in rows
        if row.get("change_pct") is not None
        and row.get("price_status") == "fetched"
        and is_recent(row.get("price_as_of"))
    ]


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
        incoming_articles = live.get("news") if isinstance(live.get("news"), list) else []
        articles = relevant_articles(incoming_articles, cfg)
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
                "price_as_of": quotes.get(ticker, {}).get("as_of"),
                "price_retrieved_at": quotes.get(ticker, {}).get("retrieved_at"),
                "price_status": quotes.get(ticker, {}).get("status", "missing"),
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

        source_hits = sum(int(row.get("source_hits", 0)) for row in rows)
        daily_moves = fresh_daily_moves(rows)
        average_move = sum(daily_moves) / len(daily_moves) if daily_moves else 0.0
        raw_signal_score = min(5.0, len(articles) * 1.5) + min(3.0, source_hits * 0.75) + max(-1.0, min(2.0, average_move * 0.5))
        signal_score = round(max(0.0, min(10.0, raw_signal_score)), 1)
        if not articles:
            rating = "QUIET"
        elif signal_score >= 6.0:
            rating = "HOT"
        else:
            rating = "ACTIVE"
        rc = {"HOT": "var(--green)", "ACTIVE": "var(--gold)", "QUIET": "var(--blue)"}[rating]
        momentum_basis = ("%+.2f%% average 1D move from %d current quotes" % (average_move, len(daily_moves))) if daily_moves else "1D momentum unavailable; no current dated quotes"
        signal_basis = "%d fresh sources · %d direct cohort mentions · %s" % (
            len(articles), source_hits, momentum_basis
        )
        base_summary = live.get("summary") or "Daily research packet refreshed from the configured evidence feed."
        summary = "%s Signal score %.1f/10 (%s). This is research activity, not an automatic trade order." % (
            base_summary, signal_score, signal_basis
        )

        normalized.append({
            "theme": theme,
            "dashboard_name": cfg["dashboard_name"],
            "priority": cfg["priority"],
            "target_pct": cfg["target_pct"],
            "rating": rating,
            "rc": rc,
            "signal_score": signal_score,
            "signal_basis": signal_basis,
            "rating_method": "fresh-source breadth + direct cohort mentions + 1D cohort momentum",
            "summary": summary,
            "news": articles,
            "tickers": rows,
            "candidate_count": sum(1 for row in rows if not row["owned"]),
            "owned_count": sum(1 for row in rows if row["owned"]),
            "research_mode": "AI + sources" if source == "openai+web_search" else "RSS + deterministic cohort",
            "cohort_updated_at": now_ist().isoformat(),
        })
    return normalized


def main() -> int:
    print("[update_themes]", now_ist().isoformat())
    provider_error = None
    try:
        raw = call_research()
        source = "openai+web_search"
    except Exception as exc:
        provider_error = public_error(exc)
        print("[update_themes] paid research unavailable; using RSS fallback:", exc, file=sys.stderr)
        raw = fallback_themes()
        source = "google-news-rss+deterministic-cohorts"
    themes = normalize_themes(raw, source)
    document = envelope(themes, source=source)
    document["fresh_window_hours"] = 24
    document["rating_method"] = "fresh-source breadth + direct cohort mentions + 1D cohort momentum"
    document["provider_error"] = provider_error
    write_json("themes.json", document)
    print("[update_themes] themes=%d tickers=%d" % (
        len(themes), sum(len(item["tickers"]) for item in themes)
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
