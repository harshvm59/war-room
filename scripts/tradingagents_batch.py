"""Explicit full-portfolio run. Independent processes isolate upstream global config."""
import io
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from _research import GitHubLedger, IST, ResearchUnavailable, _reserve, _finish
from tradingagents_runner import ROOT, UPSTREAM, run_graph, public_report


def holding_tickers(portfolio):
    from tradingagents_runner import choose_ticker
    tickers = {row['ticker'] for row in portfolio['holdings']}
    # User-confirmed holdings; both ADR/IPO identities verified against issuer records.
    tickers.update({'SKHY', 'SPCX'})
    for ticker in tickers:
        choose_ticker({'holdings': [{'ticker': t} for t in tickers]}, ticker, datetime.now(IST))
    return sorted(tickers)


def fresh(item, day):
    try:
        return datetime.fromisoformat(item['updated_at']).astimezone(IST).date() == day and all(item.get('reports', {}).get(k) for k in ('market_report', 'fundamentals_report', 'final_trade_decision'))
    except (ValueError, KeyError, TypeError):
        return False


def review_one(ticker, reservation):
    ledger = GitHubLedger()
    failure = None
    report = None
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            state, signal = run_graph(ticker, datetime.now(IST), budget=0.25)
        report = public_report(state, signal, ticker, datetime.now(IST))
    except ResearchUnavailable as exc:
        failure = {'code': exc.code, 'message': exc.message}
    except Exception:
        failure = {'code': 'research_failed', 'message': 'Research could not finish within its data, time or spending limits. No completed review is claimed.'}
    finally:
        try:
            _finish(ledger, reservation, None, None, ResearchUnavailable('conservative_run_allowance', 'Full $0.25 stock allowance retained.'), datetime.now(IST))
        except Exception:
            pass  # The durable reservation remains charged to the guard even if finalization fails.
    return ticker, report, failure


def run_batch():
    if not os.environ.get('OPENAI_API_KEY'):
        raise ResearchUnavailable('provider_key_missing', 'Funded OpenAI key required.')
    import tradingagents.graph.trading_graph  # Validate before reserving money.
    stamp = datetime.now(IST)
    path = ROOT / 'data/tradingagents.json'
    packet = json.loads(path.read_text())
    tickers = holding_tickers(json.loads((ROOT / 'data/portfolio.json').read_text()))
    reports = {i['ticker']: i for i in packet.get('items', []) if i['ticker'] in tickers}
    errors = {}
    packet.update(engine='TauricResearch/TradingAgents', upstream_commit=UPSTREAM,
                  last_attempt_at=stamp.isoformat(), requested_tickers=tickers,
                  scope='Market and fundamentals research, bull/bear debate and risk review. Full-portfolio reviews run on request; scheduled reviews rotate weekly.',
                  budget='Shared $8 monthly estimated guard. Full-portfolio runs retain $0.25 per new stock attempt; completed reports from today are reused.')
    def save(running=False):
        completed = [t for t in tickers if fresh(reports.get(t, {}), stamp.date())]
        packet.update(items=[reports[t] for t in tickers if t in reports],
                      coverage={'total': len(tickers), 'completed_today': len(completed), 'pending': [t for t in tickers if t not in completed and t not in errors], 'failed': errors},
                      status='running' if running else 'ready' if len(completed) == len(tickers) else 'partial',
                      error=None if not errors else {'code':'partial_research', 'message':'Some holdings could not complete. See coverage details; previous reports are retained.'})
        if reports:
            packet['updated_at'] = max(i['updated_at'] for i in reports.values())
        path.write_text(json.dumps(packet, indent=2) + '\n')
    # Reserve serially before dispatch: avoids CAS contention and never duplicates today's stock slot.
    work = []
    ledger = GitHubLedger()
    for ticker in tickers:
        if fresh(reports.get(ticker, {}), stamp.date()):
            continue
        try:
            work.append((ticker, _reserve(ledger, 'tradingagents_' + ticker, stamp)))
        except ResearchUnavailable as exc:
            errors[ticker] = {'code': exc.code, 'message': exc.message}
    save(True)
    print(f"Starting {len(work)} reviews; reusing {len(tickers) - len(work) - len(errors)} completed today.", flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(review_one, ticker, reservation): ticker for ticker, reservation in work}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                ticker, report, failure = future.result()
                if report:
                    reports[ticker] = report
                if failure:
                    errors[ticker] = failure
            except Exception:
                errors[ticker] = {'code':'worker_failed', 'message':'Worker stopped; budget hold retained.'}
            save(True)
            print(ticker + ': ' + ('completed' if ticker not in errors else errors[ticker]['code']), flush=True)
    save()
    print(json.dumps(packet['coverage']), flush=True)
    return 0 if packet['status'] == 'ready' else 1
