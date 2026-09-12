"""Shared helpers for the war-room update scripts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

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


def publication_time(value: str) -> datetime | None:
    """Parse a source timestamp; never replace an unknown date with today's date."""
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            stamp = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
    return stamp if stamp.tzinfo is not None else None


def is_recent(value: str, hours: int = 24, now: datetime | None = None) -> bool:
    stamp = publication_time(value)
    return stamp is not None and timedelta(0) <= (now or now_ist()) - stamp <= timedelta(hours=hours)


def public_error(exc: Exception) -> dict:
    """Public-safe health reason, without response bodies, credentials or URLs."""
    message = str(exc).lower()
    if "credit balance" in message and "too low" in message:
        return {"code": "provider_credits_exhausted", "message": "Anthropic API credits are exhausted; paid research is unavailable."}
    if "anthropic_api_key not set" in message:
        return {"code": "provider_key_missing", "message": "The Anthropic API key is missing; paid research is unavailable."}
    if getattr(exc, "status_code", None) in {401, 403}:
        return {"code": "provider_auth_failed", "message": "The research provider rejected its credentials. Check the Actions secret."}
    return {"code": "refresh_failed", "message": "Refresh failed (%s). See the linked workflow logs." % type(exc).__name__}
