import unittest
from datetime import datetime
from _research import IST, ResearchUnavailable, _reserve, _validate_ledger
from test_research import MemoryLedger
from tradingagents_runner import choose_ticker, public_report, REPORT_FIELDS

class TradingAgentsTests(unittest.TestCase):
    def test_weekly_slot_includes_cross_month_attempts(self):
        ledger = MemoryLedger()
        _reserve(ledger, 'tradingagents', datetime(2026, 9, 30, tzinfo=IST))
        with self.assertRaises(ResearchUnavailable) as caught:
            _reserve(ledger, 'tradingagents', datetime(2026, 10, 1, tzinfo=IST))
        self.assertEqual(caught.exception.code, 'weekly_research_limit')
        _reserve(ledger, 'tradingagents', datetime(2026, 10, 5, tzinfo=IST))
        self.assertEqual(ledger.document['months']['2026-10']['estimated_usd'], 1)

    def test_shared_budget_blocks_without_reset(self):
        ledger = MemoryLedger()
        for day in (1, 8, 15, 22, 29):
            _reserve(ledger, 'tradingagents', datetime(2026, 9, day, tzinfo=IST))
        for day in (1, 2, 3, 4):
            for feed in ('news', 'themes', 'framework'):
                _reserve(ledger, feed, datetime(2026, 9, day, tzinfo=IST))
        with self.assertRaises(ResearchUnavailable) as caught:
            _reserve(ledger, 'news', datetime(2026, 9, 5, tzinfo=IST))
        self.assertEqual(caught.exception.code, 'budget_limit')
        self.assertEqual(ledger.document['months']['2026-09']['estimated_usd'], 8)

    def test_no_arbitrary_ticker_or_path(self):
        stamp=datetime(2026,9,14,tzinfo=IST)
        portfolio={'holdings':[{'ticker':'NVDA'}, {'ticker':'TSM'}]}
        self.assertIn(choose_ticker(portfolio,'',stamp), ['NVDA','TSM'])
        for ticker in ('../../secrets', 'BTC', 'NVDA;echo secret'):
            with self.assertRaises(ResearchUnavailable): choose_ticker(portfolio,ticker,stamp)

    def test_incomplete_report_not_published_and_no_actions(self):
        stamp=datetime(2026,9,14,tzinfo=IST)
        with self.assertRaises(ResearchUnavailable): public_report({},'Buy','NVDA',stamp)
        state={k:'Evidence needs review' for k in REPORT_FIELDS}
        state['messages']=['private tool trace']
        report=public_report(state,'Buy','NVDA',stamp)
        self.assertFalse(report['actionable'])
        self.assertNotIn('messages',report)
        self.assertEqual(public_report(state,'BUY NOW $5000','NVDA',stamp)['rating'],'REVIEW')

if __name__ == '__main__': unittest.main()

# With optional dependencies installed, prove that the pinned real graph compiles
# and that LangChain propagates the budget exception before its transport is called.
import importlib.util
from unittest.mock import patch

@unittest.skipUnless(importlib.util.find_spec('tradingagents'), 'optional upstream dependency is not installed')
class UpstreamCompatibilityTests(unittest.TestCase):
    def test_real_graph_settings_and_pre_transport_guard(self):
        from tradingagents_runner import run_graph
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        checked=[]
        def inspect(graph, ticker, day):
            self.assertEqual(graph.selected_analysts, ('market', 'fundamentals'))
            llm=graph.quick_thinking_llm
            self.assertEqual(llm.max_retries, 0)
            self.assertFalse(llm.store)
            self.assertEqual(llm.request_timeout, 90)
            self.assertEqual(llm.max_tokens, 3000)
            guard=graph.callbacks[0]
            guard.calls=24
            with patch.object(type(llm), '_generate') as transport:
                with self.assertRaises(ResearchUnavailable): llm.invoke('No request should be sent')
                transport.assert_not_called()
            checked.append(True)
            return {}, 'REVIEW'
        with patch.dict('os.environ', {'OPENAI_API_KEY':'unit-test-not-a-real-key'}), patch.object(TradingAgentsGraph, 'propagate', inspect):
            run_graph('NVDA', datetime(2026, 9, 14, tzinfo=IST))
        self.assertTrue(checked)

class BatchTests(unittest.TestCase):
    def test_batch_slots_reuse_guard_and_budget(self):
        ledger=MemoryLedger()
        stamp=datetime(2026,9,15,tzinfo=IST)
        _reserve(ledger,'tradingagents',stamp)
        for ticker in ('NVDA','TSM','SPCX','SKHY'):
            _reserve(ledger,'tradingagents_'+ticker,stamp)
        self.assertEqual(ledger.document['months']['2026-09']['estimated_usd'],2)
        _validate_ledger(ledger.document)
        with self.assertRaises(ResearchUnavailable):
            _reserve(ledger,'tradingagents_NVDA',stamp)

    def test_reuse_requires_todays_complete_report(self):
        from tradingagents_batch import fresh
        day=datetime(2026,9,15,tzinfo=IST).date()
        item={'updated_at':'2026-09-15T07:00:00+05:30','reports':{k:'report' for k in REPORT_FIELDS}}
        self.assertTrue(fresh(item,day))
        item['updated_at']='2026-09-14T07:00:00+05:30'
        self.assertFalse(fresh(item,day))
        self.assertFalse(fresh({},day))

class QualityTests(unittest.TestCase):
    def test_conflicted_data_does_not_endorse_hold(self):
        from tradingagents_runner import apply_quality_notes
        r={'ticker':'SPCX','rating':'Hold','reports':{'fundamentals_report':'SPCX is a private aerospace company. Material inconsistencies remain.'}}
        apply_quality_notes(r)
        self.assertEqual(r['rating'],'REVIEW')
        self.assertEqual(r['model_rating'],'Hold')
        self.assertIn('outdated',r['quality_notes'][0])
        apply_quality_notes(r)
        self.assertEqual(r['model_rating'],'Hold')
