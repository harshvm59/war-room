"""Regression tests for real refresh failures, source dates and quote timestamps."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import Mock, patch

import _common
import agent_heartbeat
import analyze_daily
import run_refresh
import update_news_youtube as news
import update_themes as themes


class RefreshHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(_common, "DATA_DIR", self.temp.name), patch.object(run_refresh, "DATA_DIR", self.temp.name)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def seed(self, feed):
        for name in run_refresh.FEEDS[feed][1]:
            (self.root / name).write_text(json.dumps({"updated_at": "2026-05-22T05:04:33+05:30", "items": [{"old": True}], "source": "prior"}))

    def status(self, feed):
        return json.loads((self.root / ("refresh-status-%s.json" % feed)).read_text())

    def test_credit_failure_is_nonzero_and_preserves_last_success(self):
        self.seed("framework")
        original = (self.root / "framework.json").read_bytes()
        def fail():
            _common.write_json("framework.json", {"corrupt": True})
            raise RuntimeError("Your credit balance is too low to access the Anthropic API. secret-response-not-for-publishing")
        with patch("traceback.print_exc"):
            self.assertEqual(run_refresh.run_feed("framework", fail), 1)
        state = self.status("framework")
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["error"]["code"], "provider_credits_exhausted")
        self.assertEqual(state["last_success_at"], "2026-05-22T05:04:33+05:30")
        self.assertNotIn("secret-response", json.dumps(state))
        self.assertEqual((self.root / "framework.json").read_bytes(), original)

    def test_fallback_has_current_success_and_degraded_health(self):
        self.seed("news")
        def succeed():
            for name in run_refresh.FEEDS["news"][1]:
                _common.write_json(name, {"updated_at": "2026-09-12T14:00:00+05:30", "items": [], "source": "rss", "provider_error": {"code": "provider_credits_exhausted", "message": "Credits exhausted"}})
            return 0
        self.assertEqual(run_refresh.run_feed("news", succeed), 0)
        self.assertEqual(self.status("news")["status"], "degraded")
        self.assertEqual(self.status("news")["last_success_at"], "2026-09-12T14:00:00+05:30")

    def test_silent_noop_is_failure(self):
        self.seed("framework")
        with patch("traceback.print_exc"):
            self.assertEqual(run_refresh.run_feed("framework", lambda: 0), 1)
        self.assertEqual(self.status("framework")["status"], "failed")

    def test_system_exit_restores_every_file_in_partial_bundle(self):
        self.seed("news")
        before = {p.name: p.read_bytes() for p in self.root.glob("*.json")}
        def fail():
            _common.write_json("news.json", {"partial": True})
            raise SystemExit(2)
        with patch("traceback.print_exc"):
            self.assertEqual(run_refresh.run_feed("news", fail), 1)
        self.assertEqual({name: (self.root / name).read_bytes() for name in before}, before)


class SourceDateTests(unittest.TestCase):
    def test_source_dates_reject_missing_old_future_and_timezone_less_values(self):
        now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
        self.assertTrue(_common.is_recent("2026-09-12T09:00:00Z", now=now))
        for invalid in (None, "unknown", "2026-09-12", "2026-09-10T09:00:00Z", "2026-09-12T11:00:00Z"):
            self.assertFalse(_common.is_recent(invalid, now=now))

    def test_news_and_themes_skip_old_items_even_when_rss_returns_them_first(self):
        now = datetime.now(timezone.utc)
        old = format_datetime(now - timedelta(days=20))
        recent = format_datetime(now - timedelta(hours=2))
        xml = ('<rss><channel><item><title>old</title><link>https://example.com/old</link><pubDate>%s</pubDate></item>'
               '<item><title>recent</title><link>https://example.com/recent</link><pubDate>%s</pubDate></item></channel></rss>') % (old, recent)
        response = Mock(content=xml.encode())
        with patch.object(news.requests, "get", return_value=response):
            news_rows = news.rss("query", 1)
            theme_rows = themes.rss("query", 1)
        self.assertEqual([row["title"] for row in news_rows], ["recent"])
        self.assertEqual([row["title"] for row in theme_rows], ["recent"])
        self.assertEqual(news_rows[0]["published"], recent)
        self.assertEqual(news.date_label({"published": "Fri, 11 Sep 2026 01:00:00 GMT"}), "2026-09-11")
        self.assertEqual(news.date_label({}), "Unknown publication date")


class QuoteFreshnessTests(unittest.TestCase):
    def test_retained_undated_and_stale_quotes_do_not_influence_fresh_momentum(self):
        recent = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        rows = [
            {"change_pct": 5, "price_status": "fetched", "price_as_of": recent},
            {"change_pct": 100, "price_status": "retained", "price_as_of": recent},
            {"change_pct": 200, "price_status": "fetched", "price_as_of": old},
            {"change_pct": 300, "price_status": "fetched", "price_as_of": None},
        ]
        self.assertEqual(themes.fresh_daily_moves(rows), [5.0])

    def test_themes_refresh_already_known_quotes_and_retain_dated_fallback(self):
        old = {"NVDA": {"price": 10, "as_of": "2026-09-10T20:00:00Z"}, "AMD": {"price": 20, "as_of": "2026-09-10T20:00:00Z"}}
        def quote(ticker):
            return ticker, {"price": 30 if ticker == "NVDA" else None, "as_of": "2026-09-11T20:00:00Z", "status": "fetched"}
        with patch.object(themes, "fetch_quote", side_effect=quote) as fetch:
            result = themes.quote_universe(set(old), old)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result["NVDA"]["price"], 30)
        self.assertEqual(result["AMD"]["price"], 20)
        self.assertEqual(result["AMD"]["as_of"], "2026-09-10T20:00:00Z")
        self.assertEqual(result["AMD"]["status"], "retained")

    def test_yahoo_daily_change_uses_previous_day_and_keeps_market_timestamp(self):
        response = Mock()
        response.json.return_value = {"chart": {"result": [{"meta": {"regularMarketPrice": 110, "chartPreviousClose": 80, "regularMarketTime": 1789156800}, "indicators": {"quote": [{"close": [80, 90, 100, 110]}]}}]}}
        with patch.object(themes.requests, "get", return_value=response):
            ticker, quote = themes.fetch_quote("NVDA")
        self.assertEqual(quote["change_pct"], 10)
        self.assertEqual(quote["as_of"], datetime.fromtimestamp(1789156800, timezone.utc).isoformat())

    def test_incomplete_portfolio_does_not_publish_partial_valuation_or_notify(self):
        with patch.object(analyze_daily, "load_portfolio", return_value={"NVDA": {}, "AMD": {}}), patch.object(analyze_daily, "analyze_ticker", side_effect=[{"holding": {"current_price": 100}, "ta": {"rsi14": 50}}, None]), patch.object(analyze_daily, "write_json") as write, patch.object(analyze_daily, "notify_telegram") as notify:
            self.assertEqual(analyze_daily.main(), 1)
            write.assert_not_called()
            notify.assert_not_called()


class GuardianScopeTests(unittest.TestCase):
    def packet(self):
        return {
            "portfolio": {"holdings": [{"ticker": "NVDA"}], "meta": {"broker_synced_at": "2026-09-12T09:00:00Z"}},
            "prices": {"updated_at": "2026-09-12T09:00:00Z", "prices": {"NVDA": {"price": 100, "as_of": "2026-09-11T20:00:00Z"}}},
            "actions_updated_at": "2026-09-12T09:00:00Z",
        }

    def test_available_weekend_market_data_does_not_claim_reconciliation(self):
        result = agent_heartbeat.guardian_checks(self.packet(), datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "files_available")
        self.assertFalse(result["broker_reconciliation_verified"])

    def test_equal_quote_count_cannot_hide_missing_ticker_or_stale_broker(self):
        packet = self.packet()
        packet["portfolio"]["meta"]["broker_synced_at"] = "2026-09-10T09:00:00Z"
        packet["prices"]["prices"] = {"AMD": {"price": 100}}
        result = agent_heartbeat.guardian_checks(packet, datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Missing prices: NVDA", result["issues"])
        self.assertIn("Broker snapshot is older than 30 hours", result["issues"])

    def test_fresh_file_does_not_hide_missing_or_old_market_quote_date(self):
        packet = self.packet()
        for quote_time in (None, "2026-09-06T20:00:00Z"):
            packet["prices"]["prices"]["NVDA"]["as_of"] = quote_time
            result = agent_heartbeat.guardian_checks(packet, datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any("NVDA market quote" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
