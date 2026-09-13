"""Read-only adapter for pinned TauricResearch/TradingAgents. Never submits orders."""
from __future__ import annotations
import argparse
import copy
import io
import json
import os
import re
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta
from pathlib import Path
from _research import GitHubLedger, IST, MODEL, ResearchUnavailable, _reserve, _finish

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'be952b8eccb49720509af544c6675233bc1f10d0'
REPORT_FIELDS = ('market_report', 'fundamentals_report', 'investment_plan', 'trader_investment_plan', 'final_trade_decision')


def choose_ticker(portfolio, requested, stamp):
    tickers = sorted({h['ticker'] for h in portfolio['holdings'] if re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}', h.get('ticker', ''))})
    if not tickers or (requested and requested not in tickers):
        raise ResearchUnavailable('invalid_holding', 'Select a current public-stock holding from your portfolio.')
    if requested:
        return requested
    return tickers[(stamp.date().toordinal() // 7) % len(tickers)]


def public_report(state, signal, ticker, stamp):
    reports = {k: state.get(k, '') for k in REPORT_FIELDS}
    if any(not isinstance(v, str) or not v.strip() for v in reports.values()):
        raise ResearchUnavailable('incomplete_report', 'TradingAgents did not finish all required reports. No new assessment was published.')
    debate = state.get('investment_debate_state', {})
    reports['bull_case'] = str(debate.get('bull_history', ''))
    reports['bear_case'] = str(debate.get('bear_history', ''))
    reports['risk_review'] = str(state.get('risk_debate_state', {}).get('judge_decision', ''))
    # Text only, capped. Never expose raw graph messages, tool traces, or local paths.
    reports = {k: v[:40000] for k, v in reports.items()}
    return {'ticker': ticker, 'updated_at': stamp.isoformat(), 'rating': str(signal) if str(signal) in {'Buy', 'Overweight', 'Hold', 'Underweight', 'Sell', 'REVIEW'} else 'REVIEW',
            'reports': reports, 'actionable': False,
            'limitation': 'Single-stock research, not a portfolio allocation decision. Check source dates and account freshness; retain cash until you approve any change.'}


def run_graph(ticker, stamp):
    from langchain_core.callbacks import BaseCallbackHandler
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    class Guard(BaseCallbackHandler):
        raise_error = True
        run_inline = True
        calls = 0
        def on_chat_model_start(self, serialized, messages, **kwargs):
            # Runs before every LLM request, including structured-output agents.
            size = len(str(messages).encode('utf-8'))
            if self.calls >= 24 or size > 64000:
                raise ResearchUnavailable('run_budget_limit', 'TradingAgents reached its per-run request/context limit; no new assessment was published.')
            self.calls += 1

    guard = Guard()
    with tempfile.TemporaryDirectory(prefix='hvm-research-') as tmp:
        config = copy.deepcopy(DEFAULT_CONFIG)
        config.update({'llm_provider': 'openai', 'backend_url': 'https://api.openai.com/v1',
                       'deep_think_llm': MODEL, 'quick_think_llm': MODEL,
                       'openai_reasoning_effort': 'low', 'llm_max_retries': 0, 'max_tokens': 3000,
                       'max_debate_rounds': 1, 'max_risk_discuss_rounds': 1, 'max_recur_limit': 60,
                       'checkpoint_enabled': False, 'results_dir': tmp, 'data_cache_dir': tmp + '/cache',
                       'memory_log_path': tmp + '/memory.md', 'news_article_limit': 3,
                       'data_vendors': {'core_stock_apis': 'yfinance', 'technical_indicators': 'yfinance',
                                        'fundamental_data': 'yfinance', 'news_data': 'yfinance'}, 'tool_vendors': {}})
        # No social/news analyst: lower cost, no additional vendor keys. Reports explicitly disclose scope.
        graph = TradingAgentsGraph(selected_analysts=['market', 'fundamentals'], config=config, callbacks=[guard])
        # Bound each SDK request and avoid storing Responses. Models are shared by graph nodes.
        for llm in (graph.deep_thinking_llm, graph.quick_thinking_llm):
            llm.request_timeout = 90
            llm.store = False
        return graph.propagate(ticker, stamp.date().isoformat())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', default='')
    args = parser.parse_args()
    stamp = datetime.now(IST)
    path = ROOT / 'data/tradingagents.json'
    previous = json.loads(path.read_text()) if path.exists() else {'items': [], 'updated_at': None}
    packet = {**previous, 'last_attempt_at': stamp.isoformat(), 'engine': 'TauricResearch/TradingAgents', 'upstream_commit': UPSTREAM,
              'scope': 'Market + fundamentals analysts, bull/bear debate and risk review. One holding per week; manual runs share the same weekly allowance.',
              'budget': 'Shares the $8 monthly estimated guard. Each attempt reserves $1 conservatively, including failed attempts. Maximum one attempt per IST week.',
              'workflow_url': 'https://github.com/harshvm59/war-room/actions/workflows/tradingagents.yml'}
    failure = None
    try:
        portfolio = json.loads((ROOT / 'data/portfolio.json').read_text())
        ticker = choose_ticker(portfolio, args.ticker, stamp)
        packet['requested_ticker'] = ticker
        if not os.environ.get('OPENAI_API_KEY'):
            raise ResearchUnavailable('provider_key_missing', 'OpenAI API key is missing in GitHub Actions. Add funded OPENAI_API_KEY to enable TradingAgents.')
        # Import/validate dependency before taking a paid slot; never install dynamically here.
        import tradingagents.graph.trading_graph  # noqa: F401
        ledger = GitHubLedger()
        reservation = _reserve(ledger, 'tradingagents', stamp)
        try:
            # Upstream stdout can contain tool traces. Only sanitized reports are published.
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                state, signal = run_graph(ticker, stamp)
            report = public_report(state, signal, ticker, datetime.now(IST))
            items = [i for i in previous.get('items', []) if i.get('ticker') != ticker]
            packet.update(items=[report] + items[:16], updated_at=report['updated_at'], status='ready', error=None)
        except Exception:
            raise ResearchUnavailable('research_failed', 'TradingAgents could not complete a grounded report within its limits. The weekly slot remains used; previous reports are retained.') from None
        finally:
            # Retain the full $1 allowance; do not underestimate multi-agent token usage.
            # No fake usage totals. The ledger transparently records an unreconciled conservative hold.
            _finish(ledger, reservation, None, None, ResearchUnavailable('conservative_run_allowance', 'Full $1 research allowance retained.'), datetime.now(IST))
    except ResearchUnavailable as exc:
        failure = exc
    except Exception:
        failure = ResearchUnavailable('setup_unavailable', 'TradingAgents dependencies or data could not be loaded; no new assessment was published.')
    if failure:
        packet.update(status='blocked', error={'code': failure.code, 'message': failure.message})
    path.write_text(json.dumps(packet, indent=2) + '\n')
    print('TradingAgents: ' + packet['status'])
    return 1 if failure else 0

if __name__ == '__main__':
    raise SystemExit(main())
