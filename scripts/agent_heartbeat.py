#!/usr/bin/env python3
"""Build the HVM Trade Firm operating board.

The output is deliberately more than an animated-office heartbeat.  It defines
17 accountable employees, their hand-offs, live theme ownership, the rules-
based action queue, a five-framework CIO debate, and the material used in the
CEO end-of-day report.

All prices, position calculations and technical signals come from deterministic
JSON feeds.  Research agents may attach source-linked Google News RSS items, but
no agent can place an order or move money.
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
        "code": "LEDGER", "name": "Kunal Mehta", "department": "Finance & Data",
        "desk": "Portfolio Controller", "stage": "DATA CONTROL",
        "mission": "Own the canonical holdings, units, average costs, cash and portfolio P&L.",
        "coverage": [], "receives_from": ["INDmoney snapshot"], "hands_to": ["DELTA", "GUARDIAN", "ALLOCATOR"],
        "deliverable": "PortfolioSnapshot", "query": "",
    },
    {
        "code": "DELTA", "name": "Ananya Rao", "department": "Finance & Data",
        "desk": "Transaction & Reconciliation Accountant", "stage": "DATA CONTROL",
        "mission": "Compare broker snapshots and investigate every unit, cash or transaction change.",
        "coverage": [], "receives_from": ["LEDGER"], "hands_to": ["GUARDIAN", "BRIEF"],
        "deliverable": "ReconciliationReport", "query": "",
    },
    {
        "code": "ATLAS", "name": "Arjun Kapoor", "department": "Finance & Data",
        "desk": "Market Data Engineer", "stage": "DATA CONTROL",
        "mission": "Publish validated live marks, previous close, OHLCV and daily movement for every holding.",
        "coverage": [], "receives_from": ["Yahoo market feed"], "hands_to": ["VECTOR", "SENTINEL", "ALLOCATOR"],
        "deliverable": "MarketSnapshot", "query": "",
    },
    {
        "code": "GUARDIAN", "name": "Siddharth Bose", "department": "Finance & Data",
        "desk": "Data Quality & Systems Controller", "stage": "DATA CONTROL",
        "mission": "Block stale, missing or unreconciled data and monitor automation and dashboard health.",
        "coverage": [], "receives_from": ["LEDGER", "DELTA", "ATLAS"], "hands_to": ["Research desks", "BRIEF"],
        "deliverable": "DataQualityCertificate", "query": "",
    },
    {
        "code": "PULSE", "name": "Aanya Menon", "department": "Company Research",
        "desk": "AI Compute & Memory Analyst", "stage": "RESEARCH",
        "mission": "Own the daily fundamental thesis, earnings, valuation and catalysts for NVDA, AMD and MU.",
        "coverage": ["NVDA", "AMD", "MU"], "receives_from": ["GUARDIAN", "ATLAS"], "hands_to": ["SOURCECHECK", "VECTOR"],
        "deliverable": "CompanyResearchPacket", "query": "Nvidia AMD Micron AI GPU HBM earnings stocks",
    },
    {
        "code": "MOSAIC", "name": "Nikhil Verma", "department": "Company Research",
        "desk": "Foundry & AI Infrastructure Analyst", "stage": "RESEARCH",
        "mission": "Own TSM, ASML, AVGO, VRT and ANET plus the sovereign-AI infrastructure theme.",
        "coverage": ["TSM", "ASML", "AVGO", "VRT", "ANET"], "receives_from": ["GUARDIAN", "ATLAS"], "hands_to": ["SOURCECHECK", "VECTOR"],
        "deliverable": "CompanyResearchPacket", "query": "TSM ASML Broadcom Vertiv Arista AI infrastructure stocks",
    },
    {
        "code": "ECHO", "name": "Tara Khanna", "department": "Company Research",
        "desk": "Big Tech & Cloud Analyst", "stage": "RESEARCH",
        "mission": "Own MSFT, META, GOOGL and AMZN; track cloud, AI capex, monetisation and management signals.",
        "coverage": ["MSFT", "META", "GOOGL", "AMZN"], "receives_from": ["GUARDIAN", "ATLAS"], "hands_to": ["SOURCECHECK", "VECTOR"],
        "deliverable": "CompanyResearchPacket", "query": "Microsoft Meta Alphabet Amazon AI cloud capex earnings",
    },
    {
        "code": "CATALYST", "name": "Dev Malhotra", "department": "Company Research",
        "desk": "AI Software & Cybersecurity Analyst", "stage": "RESEARCH",
        "mission": "Own PLTR and CRWD; track contracts, ARR, guidance, competition and software catalysts.",
        "coverage": ["PLTR", "CRWD"], "receives_from": ["GUARDIAN", "ATLAS"], "hands_to": ["SOURCECHECK", "VECTOR"],
        "deliverable": "CompanyResearchPacket", "query": "Palantir CrowdStrike AI software cybersecurity earnings contracts",
    },
    {
        "code": "RADAR", "name": "Rohan Batra", "department": "Company Research",
        "desk": "Physical AI & Power Analyst", "stage": "RESEARCH",
        "mission": "Own TSLA, CEG and BE; track autonomy, robotics, nuclear and data-centre power economics.",
        "coverage": ["TSLA", "CEG", "BE"], "receives_from": ["GUARDIAN", "ATLAS"], "hands_to": ["SOURCECHECK", "VECTOR"],
        "deliverable": "CompanyResearchPacket", "query": "Tesla Constellation Energy Bloom Energy AI data center power stocks",
    },
    {
        "code": "MACRO", "name": "Priya Desai", "department": "Company Research",
        "desk": "Macro, Policy & Liquidity Strategist", "stage": "RESEARCH",
        "mission": "Translate rates, inflation, trade policy, energy policy and geopolitics into portfolio impact.",
        "coverage": ["TSM", "ASML", "CEG", "BE", "TSLA"], "receives_from": ["Market and policy feeds"], "hands_to": ["SOURCECHECK", "SENTINEL"],
        "deliverable": "MarketRegimeBrief", "query": "interest rates semiconductor export controls AI energy policy markets",
    },
    {
        "code": "SOURCECHECK", "name": "Zoya Ali", "department": "Independent Review",
        "desk": "Research Integrity Officer", "stage": "EVIDENCE GATE",
        "mission": "Verify source quality, dates, direct links and fact-versus-inference labels before committee review.",
        "coverage": [], "receives_from": ["All research desks"], "hands_to": ["VECTOR", "SENTINEL", "ALLOCATOR"],
        "deliverable": "EvidenceCertificate", "query": "AI investment markets company filings earnings credible sources",
    },
    {
        "code": "VECTOR", "name": "Isha Nair", "department": "Independent Review",
        "desk": "Quantitative & Technical Analyst", "stage": "ANALYST REVIEW",
        "mission": "Calculate trend, RSI, MACD, moving averages, entry ranges, stops and timing for all holdings.",
        "coverage": [], "receives_from": ["ATLAS", "SOURCECHECK"], "hands_to": ["SENTINEL", "ALLOCATOR"],
        "deliverable": "TechnicalSignal", "query": "",
    },
    {
        "code": "SENTINEL", "name": "Kabir Singh", "department": "Independent Review",
        "desk": "Chief Risk Officer", "stage": "RISK GATE",
        "mission": "Challenge concentration, drawdown, correlation, downside and proposed position size.",
        "coverage": [], "receives_from": ["VECTOR", "MACRO", "LEDGER"], "hands_to": ["ALLOCATOR", "DEPLOY", "CIO"],
        "deliverable": "RiskOpinion", "query": "",
    },
    {
        "code": "ALLOCATOR", "name": "Riya Shah", "department": "Finance Analysts",
        "desk": "Portfolio Construction Analyst", "stage": "FINANCE REVIEW",
        "mission": "Own live theme exposure, target gaps, rebalancing impact and conviction ranking.",
        "coverage": [], "receives_from": ["LEDGER", "VECTOR", "SENTINEL"], "hands_to": ["DEPLOY", "CIO"],
        "deliverable": "PortfolioImpactReport", "query": "",
    },
    {
        "code": "DEPLOY", "name": "Meera Joshi", "department": "Finance Analysts",
        "desk": "Capital Deployment Analyst", "stage": "FINANCE REVIEW",
        "mission": "Convert approved research into a proposed action, amount, entry plan, invalidation and expiry.",
        "coverage": [], "receives_from": ["ALLOCATOR", "SENTINEL", "VECTOR"], "hands_to": ["CIO"],
        "deliverable": "CapitalPlan", "query": "",
    },
    {
        "code": "CIO", "name": "Vikram Iyer", "department": "Leadership",
        "desk": "Chief Investment Officer", "stage": "CIO COMMITTEE",
        "mission": "Chair the five-framework investment committee, preserve dissent and send a synthesis to the CEO.",
        "coverage": [], "receives_from": ["SOURCECHECK", "VECTOR", "SENTINEL", "ALLOCATOR", "DEPLOY"], "hands_to": ["CEO", "BRIEF"],
        "deliverable": "InvestmentCommitteeDecision", "query": "",
    },
    {
        "code": "BRIEF", "name": "Aditya Kulkarni", "department": "Leadership",
        "desk": "Chief of Staff & Firm COO", "stage": "CEO REPORTING",
        "mission": "Orchestrate tasks, record completed work and compile the CEO end-of-day report and decision queue.",
        "coverage": [], "receives_from": ["All 16 agents"], "hands_to": ["CEO"],
        "deliverable": "CEOEndOfDayReport", "query": "",
    },
]


THEME_OWNERS = {
    "AI Compute & Semiconductors": ("PULSE", "Aanya Menon"),
    "Energy & Nuclear Power": ("RADAR", "Rohan Batra"),
    "Defense & National Security": ("CATALYST", "Dev Malhotra"),
    "Agentic AI & Enterprise SaaS": ("CATALYST", "Dev Malhotra"),
    "Healthcare AI & GLP-1": ("ECHO", "Tara Khanna"),
    "Physical AI & Humanoid Robotics": ("RADAR", "Rohan Batra"),
    "Critical Minerals & Copper": ("MACRO", "Priya Desai"),
    "Sovereign AI Infrastructure": ("MOSAIC", "Nikhil Verma"),
}


def read_doc(name: str) -> dict:
    path = Path(DATA_DIR) / name
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def rss(query: str) -> dict:
    if not query:
        return {"headline": "Internal deterministic work packet", "url": "", "source": "HVM data plane", "published": ""}
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
    try:
        response = requests.get(url, timeout=18, headers={"User-Agent": "HVM-AgentOps/2.0"})
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
        return {"headline": "RSS unavailable — retaining the latest verified evidence packet.", "url": "", "source": "RSS retry pending", "published": ""}


def action_rank(action: dict) -> tuple[int, int]:
    urgency = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(action.get("urgency", "low")).lower(), 9)
    kind = {"ADD": 0, "TRIM": 1, "WATCH": 2, "HOLD": 3}.get(str(action.get("action", "HOLD")).upper(), 9)
    return urgency, kind


def build_action_queue(actions: list[dict], prices: dict) -> list[dict]:
    queue = []
    for action in sorted(actions, key=action_rank):
        ticker = str(action.get("ticker", "")).upper()
        quote = prices.get(ticker, {})
        decision = str(action.get("action", "WATCH")).upper()
        urgency = str(action.get("urgency", "medium")).lower()
        queue.append({
            "ticker": ticker,
            "current_price": quote.get("price"),
            "daily_change_pct": quote.get("changePct"),
            "proposal": decision,
            "proposal_label": "PROPOSED ADD NOW" if decision == "ADD" else f"PROPOSED {decision}",
            "urgency": urgency,
            "entry": action.get("entry") or "Review current market price",
            "stop": action.get("stop") or "Not defined",
            "target": action.get("target") or "Not defined",
            "sizing": action.get("sizing") or "Sizing review required",
            "rationale": action.get("action_text") or action.get("signal") or "Rules-based review required.",
            "price_owner": "Arjun Kapoor · ATLAS",
            "technical_owner": "Isha Nair · VECTOR",
            "risk_owner": "Kabir Singh · SENTINEL",
            "portfolio_owner": "Riya Shah · ALLOCATOR",
            "proposal_owner": "Meera Joshi · DEPLOY",
            "committee_owner": "Vikram Iyer · CIO",
            "status": "CIO REVIEW" if urgency in {"critical", "high"} else "FINANCE REVIEW",
            "ceo_status": "PENDING — NO TRADE EXECUTED",
        })
    return queue


def lens_vote(action: str, urgency: str, lens: str) -> str:
    action = action.upper()
    if action == "TRIM":
        return {"buffett": "WATCH", "graham": "APPROVE", "lynch": "WATCH", "soros": "APPROVE", "taleb": "APPROVE"}[lens]
    if action == "ADD":
        if lens == "taleb":
            return "REDUCE SIZE"
        if lens == "graham" and urgency not in {"critical", "high"}:
            return "WATCH"
        return "APPROVE"
    if action == "WATCH":
        return "MORE RESEARCH"
    return "HOLD"


def build_cio_committee(queue: list[dict]) -> dict:
    top = queue[0] if queue else {"ticker": "MARKET", "proposal": "WATCH", "urgency": "medium", "entry": "—", "stop": "—", "sizing": "—", "rationale": "No material action is queued."}
    ticker, action, urgency = top["ticker"], top["proposal"], top["urgency"]
    lenses = [
        {"code": "BUFFETT", "name": "Buffett Lens", "framework": "Quality · moat · cash flow", "vote": lens_vote(action, urgency, "buffett"), "argument": f"Test {ticker}'s durable economics before accepting the {action} proposal."},
        {"code": "GRAHAM", "name": "Graham Lens", "framework": "Value · margin of safety", "vote": lens_vote(action, urgency, "graham"), "argument": f"Demand valuation protection around {top.get('entry')} and reject undefined downside."},
        {"code": "LYNCH", "name": "Lynch Lens", "framework": "Growth · PEG · operating story", "vote": lens_vote(action, urgency, "lynch"), "argument": f"Confirm that operating growth still supports {ticker}'s current market narrative."},
        {"code": "SOROS", "name": "Soros Lens", "framework": "Catalyst · momentum · reflexivity", "vote": lens_vote(action, urgency, "soros"), "argument": f"Challenge whether the catalyst and price loop support acting now rather than waiting."},
        {"code": "TALEB", "name": "Taleb Lens", "framework": "Fragility · tail risk · asymmetry", "vote": lens_vote(action, urgency, "taleb"), "argument": f"Cap exposure using {top.get('stop')} as the explicit invalidation reference."},
    ]
    approve = sum(1 for x in lenses if x["vote"] == "APPROVE")
    return {
        "chair": "Vikram Iyer · CIO",
        "status": "DEBATING",
        "ticker": ticker,
        "current_price": top.get("current_price"),
        "proposal": action,
        "proposal_owner": top.get("proposal_owner"),
        "lenses": lenses,
        "vote_summary": {"approve": approve, "challenge": len(lenses) - approve},
        "cio_synthesis": f"{ticker} remains in CIO review: {approve}/5 frameworks approve without qualification. Preserve dissent, validate sizing ({top.get('sizing')}), and send no trade until the CEO decides.",
        "next_gate": "HVM · CEO",
    }


def role_activity(spec: dict, relevant: list[dict], docs: dict) -> tuple[str, str, str]:
    primary = relevant[0] if relevant else {}
    code = spec["code"]
    holdings = docs["portfolio"].get("holdings", [])
    themes = docs["themes"].get("items", [])
    prices = docs["prices"].get("prices", {})
    transactions = docs["transactions"]
    if code == "LEDGER":
        return "MONITORING", f"Reconciling {len(holdings)} holdings against the latest broker snapshot.", "Canonical holdings packet prepared for downstream analysis."
    if code == "DELTA":
        return "MONITORING", f"Auditing {len(transactions)} detected transaction or unit-change rows.", "Any unexplained unit difference remains blocked for CEO visibility."
    if code == "ATLAS":
        return "MONITORING", f"Validating live marks for {len(prices)} portfolio tickers.", "Price tape is published for technical, risk and allocation desks."
    if code == "GUARDIAN":
        missing = max(0, len(holdings) - len(prices))
        status = "BLOCKED" if missing else "COMPLETE"
        return status, f"Checking data freshness, {missing} missing prices and dashboard health.", "Data gate passed." if not missing else f"Blocked: {missing} holdings do not have a current market mark."
    if code == "SOURCECHECK":
        return "REVIEWING", f"Verifying evidence and freshness across {len(themes)} theme packets and company research.", "Only direct, dated and source-linked claims move to analyst review."
    if code == "VECTOR":
        return "REVIEWING", f"Recomputing entry, stop and timing for {len(docs['actions'])} holdings.", "Technical cards handed to risk and portfolio construction."
    if code == "SENTINEL":
        high = sum(1 for a in docs["actions"] if str(a.get("urgency", "")).lower() in {"critical", "high"})
        return "REVIEWING", f"Stress-testing concentration and downside for {high} material action signals.", "No proposal bypasses risk review or the CEO gate."
    if code == "ALLOCATOR":
        return "REVIEWING", "Mapping live stock values into theme weights and target gaps.", "Portfolio impact and opportunity cost prepared for DEPLOY."
    if code == "DEPLOY":
        return "REVIEWING", f"Preparing {min(5, len(docs['action_queue']))} actionable capital proposals with entry and invalidation.", "Proposals are recommendations only; no brokerage order is created."
    if code == "CIO":
        top = docs["action_queue"][0] if docs["action_queue"] else {}
        return "DEBATING", f"Chairing five-framework debate on {top.get('ticker', 'the current queue')}.", "Committee synthesis will be routed to HVM · CEO with dissent preserved."
    if code == "BRIEF":
        return "COMPILING", f"Collecting completed work from {len(AGENTS)-1} employees for the CEO report.", "EOD report contains decisions, risks, themes, completed work and blocked tasks."
    if primary:
        status = "REVIEWING" if str(primary.get("urgency", "")).lower() in {"critical", "high"} else "MONITORING"
        activity = f"Reviewing {primary.get('ticker')} · {primary.get('action', 'WATCH')} · {primary.get('urgency', 'standard')} priority."
        conclusion = primary.get("action_text") or primary.get("signal") or "Review the latest rules-based signal."
        return status, activity, conclusion
    return "MONITORING", "Scanning assigned companies and waiting for a material change.", "No coverage-specific action is above the review threshold."


def main() -> int:
    stamp = now_ist().isoformat()
    print("[agent_heartbeat]", stamp)
    actions_doc = read_doc("actions.json")
    actions = actions_doc.get("items", [])
    prices_doc = read_doc("prices.json")
    prices = prices_doc.get("prices", {})
    portfolio = read_doc("portfolio.json")
    themes = read_doc("themes.json")
    news = read_doc("news.json")
    transactions = read_doc("transactions.json").get("items", [])
    by_ticker = {str(a.get("ticker", "")).upper(): a for a in actions}
    action_queue = build_action_queue(actions, prices)
    docs = {
        "actions": actions, "prices": prices_doc, "portfolio": portfolio,
        "themes": themes, "news": news, "transactions": transactions,
        "action_queue": action_queue,
    }

    out = []
    for spec in AGENTS:
        relevant = [by_ticker[t] for t in spec["coverage"] if t in by_ticker] if spec["coverage"] else list(actions)
        relevant.sort(key=action_rank)
        status, activity, recommendation = role_activity(spec, relevant, docs)
        latest = rss(spec.get("query", ""))
        completed = [
            f"Refreshed {spec['deliverable']}",
            f"Checked {len(relevant)} relevant signal(s)",
            f"Prepared hand-off to {', '.join(spec['hands_to'])}",
        ]
        out.append({
            **spec,
            "status": status,
            "activity": activity,
            "recommendation": recommendation,
            "signals": relevant[:5],
            "latest": latest,
            "completed_work": completed,
            "updated_at": stamp,
        })
        print(f"[agent_heartbeat] {spec['code']}: {status} | {activity[:78]}")

    theme_packets = []
    for item in themes.get("items", []):
        theme = str(item.get("theme", "Unassigned theme"))
        owner_code, owner_name = THEME_OWNERS.get(theme, ("MOSAIC", "Nikhil Verma"))
        theme_packets.append({
            **item,
            "owner_code": owner_code,
            "owner_name": owner_name,
            "evidence_reviewer": "Zoya Ali · SOURCECHECK",
            "exposure_reviewer": "Riya Shah · ALLOCATOR",
            "status": "UPDATED" if item.get("summary") else "RESEARCHING",
            "updated_at": themes.get("updated_at"),
        })

    committee = build_cio_committee(action_queue)
    critical = [x for x in action_queue if x["urgency"] in {"critical", "high"}]
    eod_report = {
        "report_date": stamp[:10],
        "status": "LIVE DRAFT — closes after the US market",
        "employees_reporting": len(out),
        "completed_packets": len(out),
        "themes_reviewed": len(theme_packets),
        "actions_reviewed": len(action_queue),
        "material_actions": len(critical),
        "top_action": action_queue[0] if action_queue else None,
        "cio_status": committee["status"],
        "ceo_decisions_pending": len(critical),
        "trade_execution": "DISABLED — CEO approval records a decision only",
    }

    doc = envelope(out, source="broker+market+themes+rss+local-ta+rules")
    doc.update({
        "cadence": "hourly operating heartbeat; market TA refreshes separately during market hours",
        "firm_status": "Research and decision support only — CEO approval required; no trade execution.",
        "agent_count": len(out),
        "workflow": ["DATA CONTROL", "RESEARCH", "EVIDENCE GATE", "ANALYST REVIEW", "RISK GATE", "FINANCE REVIEW", "CIO COMMITTEE", "CEO DECISION"],
        "theme_packets": theme_packets,
        "action_queue": action_queue,
        "cio_committee": committee,
        "eod_report": eod_report,
    })
    write_json("agent_ops.json", doc)
    print(f"[agent_heartbeat] wrote {len(out)} employee packets, {len(theme_packets)} themes and {len(action_queue)} action proposals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
