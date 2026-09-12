"""No-network regression tests for spend reservations and Responses parsing."""
import base64
import copy
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import requests

import _research as research


DAY = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
NEWS = {"news": [], "youtube": [], "voices": []}


class MemoryLedger:
    """Explicit injected CAS backend; production has no in-memory fallback."""
    def __init__(self):
        self.document = {"version": 1, "months": {}}
        self.version = 1
        self.lock = threading.Lock()
        self.read_count = 0
        self.write_count = 0
        self.conflicts = 0
        self.fail_reserve = False
        self.fail_finish = False
        self.lose_reservation_ack = False
        self.barrier = None

    def read(self):
        with self.lock:
            self.read_count += 1
            result = copy.deepcopy(self.document), str(self.version)
            wait = self.barrier and self.read_count <= 2
        if wait:
            self.barrier.wait(timeout=3)
        return result

    def compare_and_swap(self, doc, sha):
        with self.lock:
            self.write_count += 1
            if self.fail_reserve or (self.fail_finish and self.version > 1):
                raise requests.Timeout("private-ledger-error")
            if self.conflicts:
                self.conflicts -= 1
                return False
            if sha != str(self.version):
                return False
            self.document = copy.deepcopy(doc)
            self.version += 1
            if self.lose_reservation_ack:
                self.lose_reservation_ack = False
                raise requests.Timeout("uncertain write")
            return True


def response_json(document=NEWS):
    return {
        "status": "completed",
        "output": [
            {"type": "web_search_call", "status": "completed", "action": {"type": "search"}},
            {"type": "message", "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(document)}]},
        ],
        "usage": {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 100}, "output_tokens": 500},
    }


def provider(body=None, status=200):
    http = Mock()
    response = Mock(status_code=status)
    response.json.return_value = body if body is not None else response_json()
    http.post.return_value = response
    return http


class ResearchTestCase(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-private-key"}, clear=True)
        self.env.start()
        self.ledger = MemoryLedger()
        self.http = provider()

    def tearDown(self):
        self.env.stop()

    def run_research(self, feed="news", now=DAY, **kwargs):
        return research.research_json(feed, "Return requested JSON from current sources.", ledger=self.ledger, http=self.http, now=lambda: now, **kwargs)

    def entry(self, key="2026-09-12:news", month="2026-09"):
        return self.ledger.document["months"][month]["attempts"][key]

    def assert_code(self, expected, fn):
        with self.assertRaises(research.ResearchUnavailable) as caught:
            fn()
        self.assertEqual(caught.exception.code, expected)
        return caught.exception


class ResearchBudgetTests(ResearchTestCase):
    def test_reservation_is_durable_before_post_and_usage_is_saved(self):
        def post(*args, **kwargs):
            self.assertEqual(self.entry()["status"], "reserved")
            self.assertEqual(self.entry()["estimated_usd"], 0.25)
            return provider().post.return_value
        self.http.post.side_effect = post
        self.assertEqual(self.run_research(), NEWS)
        entry = self.entry()
        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["usage"]["web_search_calls"], 1)
        self.assertAlmostEqual(entry["estimated_usd"], .010827)
        self.assertEqual(self.ledger.document["months"]["2026-09"]["usage_totals"]["input_tokens"], 1000)
        encoded = json.dumps(self.ledger.document)
        self.assertNotIn("unit-test-private-key", encoded)
        self.assertNotIn("Return requested JSON", encoded)
        self.assertNotIn('"output":', encoded)
        self.http.post.assert_called_once()

    def test_exact_request_limits_and_fixed_endpoint(self):
        self.run_research()
        args, kwargs = self.http.post.call_args
        self.assertEqual(args[0], "https://api.openai.com/v1/responses")
        self.assertFalse(kwargs["allow_redirects"])
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["max_tool_calls"], 4)
        self.assertEqual(payload["max_output_tokens"], 6000)
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["service_tier"], "default")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tools"], [{"type": "web_search", "search_context_size": "low"}])

    def test_manual_second_attempt_is_blocked(self):
        self.run_research()
        self.assert_code("daily_research_limit", self.run_research)
        self.http.post.assert_called_once()

    def test_two_concurrent_runs_pay_only_once(self):
        self.ledger.barrier = threading.Barrier(2)
        def worker():
            try:
                self.run_research()
                return "ok"
            except research.ResearchUnavailable as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(outcomes), ["daily_research_limit", "ok"])
        self.http.post.assert_called_once()
        self.assertEqual(len(self.ledger.document["months"]["2026-09"]["attempts"]), 1)

    def test_compare_sha_conflict_can_retry_without_retrying_paid_post(self):
        self.ledger.conflicts = 2
        self.run_research()
        self.assertGreaterEqual(self.ledger.write_count, 4)
        self.http.post.assert_called_once()

    def test_reservation_failure_makes_no_paid_request(self):
        self.ledger.fail_reserve = True
        self.assert_code("budget_guard_unavailable", self.run_research)
        self.http.post.assert_not_called()

    def test_lost_reservation_ack_consumes_slot_but_never_sends_paid_post(self):
        self.ledger.lose_reservation_ack = True
        self.assert_code("budget_guard_unavailable", self.run_research)
        self.assert_code("daily_research_limit", self.run_research)
        self.http.post.assert_not_called()

    def test_lost_provider_response_never_retries_and_keeps_provisional_hold(self):
        self.http.post.side_effect = requests.Timeout("unit-test-private-key in server transport error")
        exc = self.assert_code("provider_unavailable", self.run_research)
        self.assertNotIn("private-key", str(exc))
        self.assertEqual(self.entry()["estimated_usd"], .25)
        self.assertEqual(self.entry()["status"], "uncertain")
        self.assert_code("daily_research_limit", self.run_research)
        self.http.post.assert_called_once()

    def test_usage_write_failure_keeps_reserved_slot_and_prevents_retry(self):
        self.ledger.fail_finish = True
        self.assert_code("budget_guard_unavailable", self.run_research)
        self.assertEqual(self.entry()["status"], "reserved")
        self.ledger.fail_finish = False
        self.assert_code("daily_research_limit", self.run_research)
        self.http.post.assert_called_once()

    def test_missing_key_and_missing_github_guard_never_spend(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assert_code("provider_key_missing", self.run_research)
        self.assertEqual(self.ledger.read_count, 0)
        self.assert_code("budget_guard_unavailable", lambda: research.research_json("news", "prompt", http=self.http))
        self.http.post.assert_not_called()

    def test_unknown_feed_and_oversized_utf8_prompt_rejected_before_reservation(self):
        self.assert_code("research_input_invalid", lambda: self.run_research("extra"))
        self.assert_code("research_input_invalid", lambda: research.research_json("news", "\u20b9" * 7000, ledger=self.ledger, http=self.http))
        self.assertEqual(self.ledger.read_count, 0)
        self.http.post.assert_not_called()

    def test_all_errors_consume_slot_without_provider_retry(self):
        for status, code in [(401, "provider_auth_failed"), (403, "provider_auth_failed"), (429, "provider_unavailable"), (500, "provider_unavailable"), (302, "provider_unavailable")]:
            with self.subTest(status=status):
                self.ledger = MemoryLedger()
                self.http = provider(status=status)
                self.http.post.return_value.json.return_value = {"private": "unit-test-private-key"}
                exc = self.assert_code(code, self.run_research)
                self.assertNotIn("private-key", str(exc))
                self.assert_code("daily_research_limit", self.run_research)
                self.http.post.assert_called_once()

    def test_monthly_stop_and_ist_month_rollover(self):
        self.run_research()
        self.entry()["estimated_usd"] = 8.0
        self.ledger.document["months"]["2026-09"]["estimated_usd"] = 8.0
        self.assert_code("budget_limit", lambda: self.run_research(now=datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)))
        # October begins at 18:30 UTC on September 30 in the configured IST ledger.
        self.run_research(now=datetime(2026, 9, 30, 19, 0, tzinfo=timezone.utc))
        self.assertIn("2026-10-01:news", self.ledger.document["months"]["2026-10"]["attempts"])
        self.assertEqual(self.ledger.document["months"]["2026-09"]["estimated_usd"], 8.0)
        self.assertEqual(self.http.post.call_count, 2)

    def test_framework_limits_and_separate_feed_slots(self):
        self.run_research()
        self.http.post.return_value.json.return_value = response_json([{"ticker": "NVDA"}])
        self.run_research("framework")
        self.assertEqual(self.http.post.call_args.kwargs["json"]["max_tool_calls"], 6)
        self.assertEqual(self.http.post.call_args.kwargs["json"]["max_output_tokens"], 14000)
        self.assertEqual(self.http.post.call_count, 2)

    def test_persistent_conflicts_are_bounded_and_never_spend(self):
        self.ledger.conflicts = 100
        self.assert_code("budget_guard_unavailable", self.run_research)
        self.assertEqual(self.ledger.write_count, research.CAS_ATTEMPTS)
        self.http.post.assert_not_called()

    def test_inconsistent_ledger_totals_fail_closed(self):
        self.run_research()
        self.ledger.document["months"]["2026-09"]["estimated_usd"] = 0
        self.assert_code("budget_guard_unavailable", lambda: self.run_research("themes"))
        self.http.post.assert_called_once()

    def test_pending_hold_blocks_next_call_near_monthly_limit(self):
        self.run_research()
        self.entry()["estimated_usd"] = 7.8
        self.ledger.document["months"]["2026-09"]["estimated_usd"] = 7.8
        self.assert_code("budget_limit", lambda: self.run_research("themes"))
        self.http.post.assert_called_once()


class ResponseValidationTests(ResearchTestCase):
    def test_output_text_across_messages_is_parsed_as_one_json_document(self):
        body = response_json()
        message = body["output"][1]
        message["content"][0]["text"] = '{"news": [],'
        second = copy.deepcopy(message)
        second["content"][0]["text"] = '"youtube": [], "voices": []}'
        body["output"].append(second)
        self.http.post.return_value.json.return_value = body
        self.assertEqual(self.run_research(), NEWS)

    def test_refused_incomplete_malformed_or_training_only_response_is_not_published(self):
        cases = []
        incomplete = response_json(); incomplete["status"] = "incomplete"; cases.append(incomplete)
        refusal = response_json(); refusal["output"][1]["content"] = [{"type": "refusal", "refusal": "no"}]; cases.append(refusal)
        no_search = response_json(); no_search["output"] = no_search["output"][1:]; cases.append(no_search)
        failed_search = response_json(); failed_search["output"][0]["status"] = "failed"; cases.append(failed_search)
        for text in ('not JSON', '{"news":[],"youtube":[],"voices":[],"x":NaN}', '{"news":[],"news":[],"youtube":[],"voices":[]}', '[{}]', '{"news":[],"youtube":[]}'):
            malformed = response_json(); malformed["output"][1]["content"][0]["text"] = text; cases.append(malformed)
        for body in cases:
            self.ledger = MemoryLedger(); self.http = provider(body)
            self.assert_code("research_response_invalid", self.run_research)
            self.assertEqual(self.entry()["status"], "failed")
            self.assertIsNotNone(self.entry()["usage"])
            self.assert_code("daily_research_limit", self.run_research)
            self.http.post.assert_called_once()

    def test_missing_usage_retains_unknown_hold_and_does_not_return_research(self):
        body = response_json(); body.pop("usage")
        self.http = provider(body)
        self.assert_code("provider_response_invalid", self.run_research)
        self.assertEqual(self.entry()["estimated_usd"], .25)
        self.assertIsNone(self.entry()["usage"])

    def test_long_context_cost_uses_higher_rates_and_counts_searches(self):
        body = response_json()
        body["usage"] = {"input_tokens": 300000, "output_tokens": 1000, "input_tokens_details": {"cached_tokens": 0}}
        counts, cost = research._usage_cost(body)
        self.assertEqual(counts["input_tokens"], 300000)
        self.assertAlmostEqual(cost, .1618)


class GitHubLedgerTests(unittest.TestCase):
    def test_fixed_contents_endpoint_main_ref_and_sha_update(self):
        doc = {"version": 1, "months": {}}
        http = Mock()
        http.get.return_value = Mock(status_code=200)
        http.get.return_value.json.return_value = {"sha": "abc123", "encoding": "base64", "content": base64.b64encode(json.dumps(doc).encode()).decode()}
        http.put.return_value = Mock(status_code=200)
        http.put.return_value.json.return_value = {"content": {"sha": "def456"}}
        ledger = research.GitHubLedger(token="github-private", repository="owner/repo", http=http)
        value, sha = ledger.read()
        self.assertEqual(value, doc)
        self.assertEqual(sha, "abc123")
        self.assertEqual(http.get.call_args.args[0], "https://api.github.com/repos/owner/repo/contents/.github/ai-usage.json")
        self.assertEqual(http.get.call_args.kwargs["params"], {"ref": "main"})
        self.assertTrue(ledger.compare_and_swap(doc, sha))
        self.assertEqual(http.put.call_args.kwargs["json"]["sha"], "abc123")
        self.assertEqual(http.put.call_args.kwargs["json"]["branch"], "main")
        self.assertFalse(http.put.call_args.kwargs["allow_redirects"])

    def test_missing_or_invalid_ledger_fails_closed_instead_of_resetting_month(self):
        for status, body in [(404, {}), (200, {"sha": "x", "encoding": "base64", "content": "not-base64"}), (302, {})]:
            http = Mock(); http.get.return_value = Mock(status_code=status); http.get.return_value.json.return_value = body
            ledger = research.GitHubLedger(token="private", repository="owner/repo", http=http)
            with self.assertRaises(research.ResearchUnavailable) as caught:
                ledger.read()
            self.assertEqual(caught.exception.code, "budget_guard_unavailable")
            http.put.assert_not_called()

    def test_only_compare_sha_conflicts_are_retryable(self):
        http = Mock(); ledger = research.GitHubLedger(token="private", repository="owner/repo", http=http)
        for status in (409, 422):
            http.put.return_value = Mock(status_code=status)
            self.assertFalse(ledger.compare_and_swap({"version": 1, "months": {}}, "sha"))
        http.put.return_value = Mock(status_code=403)
        with self.assertRaises(research.ResearchUnavailable):
            ledger.compare_and_swap({"version": 1, "months": {}}, "sha")


if __name__ == "__main__":
    unittest.main()
