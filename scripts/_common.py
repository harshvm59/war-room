"""Shared helpers for the war-room update scripts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
ET = timezone(timedelta(hours=-4))  # EDT; close enough for headers

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")

TICKERS = [
    "NVDA", "TSLA", "TSM", "META", "GOOGL", "AMZN", "PLTR", "MSFT",
    "AMD", "CRWD", "MU", "VRT", "AVGO", "ASML", "CEG", "ANET", "BE",
]

URGENCY_COLORS = {
    "critical": "#e05252",
    "high":     "#c9a84c",
    "medium":   "#4a9eff",
    "low":      "#2dd4bf",
}


def now_ist() -> datetime:
    return datetime.now(IST)


def write_json(filename: str, payload: dict | list) -> str:
    """Write JSON to data/<filename>. Returns absolute path."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def envelope(items, source: str) -> dict:
    """Wrap a list of items in a standard envelope with a timestamp."""
    return {
        "updated_at": now_ist().isoformat(),
        "source": source,
        "items": items,
    }


def require_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it as a repo secret "
            "(Settings → Secrets and variables → Actions)."
        )
    return key
