#!/usr/bin/env python3
"""Run one feed, publish honest health, and preserve prior data on failure.

The workflow commits the health file even when this command exits nonzero.
That leaves failures visible both in Actions and in the public dashboard.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback
from pathlib import Path

from _common import DATA_DIR, now_ist, publication_time, public_error, write_json

FEEDS = {
    "prices": ("analyze_daily", ["prices.json", "actions.json", "analysis.json"]),
    "news": ("update_news_youtube", ["news.json", "youtube.json", "voices.json"]),
    "themes": ("update_themes", ["themes.json"]),
    "framework": ("analyze_framework", ["framework.json"]),
    "agents": ("agent_heartbeat", ["agent_ops.json"]),
}


def read_document(path: Path) -> dict:
    try:
        document = json.loads(path.read_text())
        return document if isinstance(document, dict) else {}
    except (OSError, ValueError):
        return {}


def last_success(documents: list[dict]) -> str | None:
    stamps = [publication_time(doc.get("updated_at")) for doc in documents]
    return min(stamps).isoformat() if stamps and all(stamps) else None


def run_feed(feed: str, execute=None) -> int:
    module_name, filenames = FEEDS[feed]
    paths = [Path(DATA_DIR) / name for name in filenames]
    previous = {path: path.read_bytes() if path.exists() else None for path in paths}
    old_documents = [read_document(path) for path in paths]
    status = {
        "feed": feed,
        "status": "failed",
        "last_attempt_at": now_ist().isoformat(),
        "last_success_at": last_success(old_documents),
        "error": None,
        "source": "; ".join(sorted({doc.get("source", "unknown") for doc in old_documents})),
        "outputs": filenames,
        "workflow_url": (
            "https://github.com/%s/actions/runs/%s" % (os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"])
            if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_RUN_ID") else None
        ),
    }
    exit_code = 0
    try:
        result = (execute or importlib.import_module(module_name).main)()
        if result not in (None, 0):
            raise RuntimeError("Feed command exited with status %s" % result)
        documents = [read_document(path) for path in paths]
        for old, doc in zip(old_documents, documents):
            if not publication_time(doc.get("updated_at")) or doc.get("updated_at") == old.get("updated_at"):
                raise ValueError("Feed did not publish a new dated snapshot")
            if not (isinstance(doc.get("items"), list) or isinstance(doc.get("prices"), dict)):
                raise ValueError("Feed published an invalid snapshot")
        status["last_success_at"] = last_success(documents)
        status["source"] = "; ".join(sorted({doc.get("source", "unknown") for doc in documents}))
        errors = [doc.get("provider_error") or doc.get("refresh_warning") for doc in documents
                  if doc.get("provider_error") or doc.get("refresh_warning")]
        status["error"] = errors[0] if errors else None
        status["status"] = "degraded" if errors else "ok"
    except (Exception, SystemExit) as exc:
        exit_code = 1
        # A feed containing several files must not publish a partially new bundle.
        for path, content in previous.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        status["error"] = public_error(exc)
        status["status"] = "blocked" if status["error"]["code"].startswith("provider_") else "failed"
        traceback.print_exc()
    write_json("refresh-status-%s.json" % feed, status)
    print("[refresh-health] %s: %s; last successful data: %s" % (feed, status["status"], status["last_success_at"]))
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", choices=FEEDS)
    parser.add_argument("--no-notify", action="store_true", help="Suppress existing optional Telegram delivery for manual refreshes")
    args = parser.parse_args()
    if args.no_notify:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
    sys.exit(run_feed(args.feed))
