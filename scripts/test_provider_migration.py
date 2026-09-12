"""Offline caller regressions for the OpenAI migration and free refresh path."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import _common
import analyze_framework as framework
import run_refresh
import update_news_youtube as news
import update_themes as themes


NOW = datetime(2026, 9, 12, 1, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
PUBLISHED = "2026-09-11T23:15:00+05:30"
SOURCE = "https://investor.example.test/company/quarterly-results"


class SafeProviderFailure(RuntimeError):
    """Exercise the adapter's public error contract without making an API call."""
    def __init__(self, code):
        super().__init__("private-response sk-test-secret-do-not-publish request-body")
        self.code = code
        self.message = {
            "provider_key_missing": "The OpenAI API key is missing; free feeds remain available.",
            "daily_research_limit": "Today's paid research allowance is already used; free refresh continues.",
            "budget_limit": "The monthly paid research budget is reserved; free refresh continues.",
            "budget_guard_unavailable": "The paid research budget could not be verified; free refresh continues.",
        }[code]


def framework_row(ticker="NVDA"):
    return {
        "ticker": ticker, "company": "Example Company", "overall": "BUY", "score": 7,
        "overall_color": "#3ddc84", "summary": "Assessment based on the cited filing.",
        "sources": [{"url": SOURCE, "title": "Quarterly results", "published": PUBLISHED, "reporting_period": "FY2026 Q2"}],
        "questions": {
            key: {"verdict": "PASS", "note": "Evidence is described in the cited filing.",
                  "evidence_status": "supported", "source_urls": [SOURCE], "reporting_period": "FY2026 Q2"}
            for key in framework.QUESTION_KEYS
        },
    }


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(self.temp)
        for module in (_common, run_refresh, themes):
            self.stack.enter_context(patch.object(module, "DATA_DIR", self.temp))
        for module in (_common, news, themes, framework, run_refresh):
            self.stack.enter_context(patch.object(module, "now_ist", return_value=NOW))
        self.stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network access in offline integration test")))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(redirect_stderr(io.StringIO()))

    def document(self, name):
        return json.loads((self.root / name).read_text())

    def assert_envelope(self, document):
        self.assertIsNotNone(_common.publication_time(document["updated_at"]))
        self.assertIsInstance(document["source"], str)
        self.assertIsInstance(document["items"], list)
        json.dumps(document, allow_nan=False)

    def assert_safe_failure(self, feed, names, code):
        for name in names:
            document = self.document(name)
            self.assert_envelope(document)
            self.assertEqual(document["provider_error"]["code"], code)
            for private in ("private-response", "sk-test-secret", "request-body"):
                self.assertNotIn(private, json.dumps(document))
        status = self.document("refresh-status-%s.json" % feed)
        self.assertIn(status["status"], {"degraded", "limited"})
        self.assertEqual(status["error"]["code"], code)
        self.assertIsNotNone(status["last_success_at"])
        self.assertNotIn("sk-test-secret", json.dumps(status))


class FreeFallbackIntegrationTests(OfflineTestCase):
    def test_actual_missing_openai_key_reaches_both_free_fallbacks_without_network(self):
        article = {"title": "NVIDIA AI semiconductor earnings growth", "url": SOURCE, "source": "Example Investor Relations", "published": PUBLISHED, "date": "2026-09-11"}
        with patch.dict(os.environ, {}, clear=True), patch.object(news, "rss", return_value=[article]), patch.object(news, "fresh_leader_signals", return_value=[]), patch.object(themes, "rss", return_value=[article]), patch.object(themes, "read_json", return_value={}), patch.object(themes, "quote_universe", return_value={}):
            self.assertEqual(run_refresh.run_feed("news", news.main), 0)
            self.assertEqual(run_refresh.run_feed("themes", themes.main), 0)
        self.assert_safe_failure("news", ("news.json", "youtube.json", "voices.json"), "provider_key_missing")
        self.assert_safe_failure("themes", ("themes.json",), "provider_key_missing")

    def test_news_key_daily_budget_and_guard_failures_keep_free_feeds_fresh(self):
        source = {"title": "NVIDIA AI revenue results", "url": SOURCE, "source": "Example Investor Relations", "published": PUBLISHED}
        for code in ("provider_key_missing", "daily_research_limit", "budget_limit", "budget_guard_unavailable"):
            with self.subTest(code=code):
                for path in self.root.glob("*.json"):
                    path.unlink()
                with patch.object(news, "research_json", side_effect=SafeProviderFailure(code)), patch.object(news, "rss", return_value=[source]) as rss, patch.object(news, "fresh_leader_signals", return_value=[]):
                    self.assertEqual(run_refresh.run_feed("news", news.main), 0)
                rss.assert_called_once()
                self.assert_safe_failure("news", ("news.json", "youtube.json", "voices.json"), code)
                item = self.document("news.json")["items"][0]
                self.assertEqual(item["published"], PUBLISHED)
                self.assertEqual(item["date"], "2026-09-11")
                self.assertEqual(item["url"], SOURCE)
                video = self.document("youtube.json")["items"][0]
                self.assertTrue({"ch", "title", "date", "published", "body", "url", "tags", "theme", "verd"}.issubset(video))

    def test_theme_key_daily_budget_and_guard_failures_keep_complete_free_cohorts(self):
        article = {"title": "NVIDIA AI semiconductor earnings growth", "url": SOURCE, "source": "Example Investor Relations", "published": PUBLISHED, "date": "2026-09-11"}
        for code in ("provider_key_missing", "daily_research_limit", "budget_limit", "budget_guard_unavailable"):
            with self.subTest(code=code):
                for path in self.root.glob("*.json"):
                    path.unlink()
                with patch.object(themes, "research_json", side_effect=SafeProviderFailure(code)), patch.object(themes, "rss", return_value=[article]) as rss, patch.object(themes, "read_json", return_value={}), patch.object(themes, "quote_universe", return_value={}):
                    self.assertEqual(run_refresh.run_feed("themes", themes.main), 0)
                self.assertEqual(rss.call_count, len(themes.THEME_CONFIG))
                self.assert_safe_failure("themes", ("themes.json",), code)
                rows = self.document("themes.json")["items"]
                self.assertEqual({row["theme"] for row in rows}, set(themes.THEME_CONFIG))
                self.assertTrue(all(row["tickers"] for row in rows))
                self.assertTrue(all(row["research_mode"] == "RSS + deterministic cohort" for row in rows))
                for row in rows:
                    for item in row["news"]:
                        self.assertEqual(item["published"], PUBLISHED)
                        self.assertEqual(item["date"], "2026-09-11")


class PaidSourceDateTests(OfflineTestCase):
    def bundle(self):
        shared = {"published": PUBLISHED, "date": "2099-01-01"}
        return {
            "news": [{**shared, "ticker": "NVDA", "headline": "Quarterly results", "summary": "Source-linked earnings report.", "tag": "earnings", "url": SOURCE}],
            "youtube": [{**shared, "ch": "Example", "c": "#4a9eff", "theme": "AI Compute", "title": "Results coverage", "views": "Source article", "tags": ["#NVDA"], "verd": "SOURCE-LINKED SIGNAL", "vc": "var(--blue)", "body": "Source-linked coverage.", "url": SOURCE}],
            "voices": [{**shared, "name": "Jensen Huang", "role": "CEO", "org": "Nvidia", "cat": "CEO", "themes": ["#NVDA"], "quotes": [{"t": "Source-linked summary (not a direct quote): The named executive discussed company results.", "k": True}], "src": SOURCE}],
        }

    def test_paid_news_retains_actual_prior_day_source_dates_and_discards_undated_stale_future_rows(self):
        bundle = self.bundle()
        for rows in bundle.values():
            for invalid in (None, "2026-09-08T12:00:00+05:30", "2026-09-12T05:00:00+05:30", "2026-09-12"):
                rows.append({**copy.deepcopy(rows[0]), "published": invalid})
        with patch.object(news, "research_json", return_value=bundle):
            result = news.call_research()
        for rows in result.values():
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["published"], PUBLISHED)
            self.assertEqual(rows[0]["date"], "2026-09-11")
        json.dumps(result, allow_nan=False)

    def test_paid_voice_requires_explicit_paraphrase_label(self):
        bundle = self.bundle()
        bundle["voices"][0]["quotes"][0]["t"] = "An alleged direct quote without provenance"
        with patch.object(news, "research_json", return_value=bundle):
            self.assertEqual(news.call_research()["voices"], [])

    def test_paid_news_rejects_incomplete_bundle_contract(self):
        with patch.object(news, "research_json", return_value={"news": []}):
            with self.assertRaisesRegex(ValueError, "arrays are required"):
                news.call_research()

    def test_paid_theme_dates_are_source_dates_and_no_evidence_cannot_discover_candidates(self):
        article = {"title": "Quarterly results", "url": SOURCE, "source": "Example", "published": PUBLISHED, "date": "2099-01-01"}
        raw = [
            {"theme": themes.THEMES[0], "rating": "HOT", "rc": "var(--gold)", "summary": "Recent source.", "news": [article], "tickers": ["NVDA"]},
            {"theme": themes.THEMES[1], "rating": "HOT", "rc": "var(--gold)", "summary": "Unsupported claim.", "news": [{**article, "published": None}], "tickers": ["UNVERIFIED"]},
        ]
        with patch.object(themes, "research_json", return_value=raw):
            result = themes.call_research()
        self.assertEqual(result[0]["news"][0]["date"], "2026-09-11")
        self.assertEqual(result[0]["news"][0]["published"], PUBLISHED)
        self.assertEqual(result[1]["news"], [])
        self.assertEqual(result[1]["tickers"], [])
        self.assertEqual(result[1]["rating"], "QUIET")
        self.assertIn("No qualifying source-linked article", result[1]["summary"])


class FrameworkEvidenceIntegrationTests(OfflineTestCase):
    def test_framework_rejects_missing_extra_duplicate_and_wrong_ticker_coverage(self):
        for rows in ([framework_row()], [framework_row(), framework_row()], [framework_row(), framework_row("TSLA")], [framework_row(), framework_row("AMD"), framework_row("TSLA")]):
            with self.subTest(tickers=[row["ticker"] for row in rows]):
                with self.assertRaisesRegex(ValueError, "ticker coverage"):
                    framework.validate_framework(rows, ["NVDA", "AMD"])

    def test_framework_missing_refs_question_period_or_source_period_forces_review(self):
        for missing in ("refs", "question_period", "source_period", "evidence_status"):
            with self.subTest(missing=missing):
                row = framework_row()
                if missing == "refs":
                    row["questions"]["cash"]["source_urls"] = []
                elif missing == "question_period":
                    row["questions"]["cash"]["reporting_period"] = None
                elif missing == "source_period":
                    row["sources"][0]["reporting_period"] = None
                else:
                    row["questions"]["cash"]["evidence_status"] = "unknown"
                validated = framework.validate_framework([row], ["NVDA"])[0]
                self.assertEqual(validated["overall"], "REVIEW")
                self.assertEqual(validated["overall_color"], "#c9a84c")
                self.assertEqual(validated["questions"]["cash"]["verdict"], "CAUTION")
                self.assertEqual(validated["questions"]["cash"]["evidence_status"], "unknown")
                self.assertIn("review required", validated["questions"]["cash"]["note"])
                self.assertNotIn("Evidence is described in the cited filing", validated["questions"]["cash"]["note"])
                self.assertLess(validated["score"], 7)

    def test_framework_rejects_questions_linking_unlisted_sources(self):
        row = framework_row()
        row["questions"]["cash"]["source_urls"] = ["https://investor.example.test/unlisted"]
        with self.assertRaisesRegex(ValueError, "unlisted source"):
            framework.validate_framework([row], ["NVDA"])

    def holdings(self):
        return [{"ticker": ticker, "name": ticker, "theme": "AI", "priority": "P1", "units": 1, "avg_cost": 10} for ticker in ("NVDA", "AMD")]

    def test_incomplete_framework_response_keeps_previous_snapshot_and_reports_failure(self):
        previous = {"updated_at": "2026-09-10T04:00:00+05:30", "source": "previous", "items": [framework_row(), framework_row("AMD")]}
        path = self.root / "framework.json"
        path.write_text(json.dumps(previous))
        original = path.read_bytes()
        with patch.object(framework, "load_portfolio", return_value=self.holdings()), patch.object(framework, "fetch_price_info", return_value={}), patch.object(framework, "research_json", return_value=[framework_row()]):
            self.assertEqual(run_refresh.run_feed("framework", framework.main), 1)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.document("refresh-status-framework.json")["status"], "failed")

    def test_framework_publishes_review_contract_and_explicit_verification_warning(self):
        rows = [framework_row(), framework_row("AMD")]
        rows[0]["questions"]["cash"]["source_urls"] = []
        with patch.object(framework, "load_portfolio", return_value=self.holdings()), patch.object(framework, "fetch_price_info", return_value={}), patch.object(framework, "research_json", return_value=rows):
            self.assertEqual(run_refresh.run_feed("framework", framework.main), 0)
        document = self.document("framework.json")
        self.assert_envelope(document)
        self.assertEqual(document["items"][0]["overall"], "REVIEW")
        self.assertEqual(document["items"][0]["sources"][0]["published"], PUBLISHED)
        self.assertFalse(document["fundamentals_verified"])
        self.assertEqual(document["refresh_warning"]["code"], "fundamentals_unverified")
        self.assertEqual(document["refresh_warning"]["message"], framework.QUALITY_WARNING)
        self.assertEqual(self.document("refresh-status-framework.json")["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
