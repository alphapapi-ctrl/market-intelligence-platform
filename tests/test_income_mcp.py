"""Income review parity/history tests use only synthetic prices, settings and holdings."""
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from etf import income_config as IC
from etf import etf_income_data as scorer
from etf import etf_backtest as backtest
from etf.income_rules import (allocation_preview, holding_total_return, qualified_ranks,
                              ranking_decision, stop_decision, hedge_signal)
from etf.income_store import save_generation, save_review
from market_mcp import income, jobs, operations as op, worker
from marketdb import db

AS_OF = '2026-10-28T00:00:00+00:00'


class IncomeTests(unittest.TestCase):
    def setUp(self):
        (op.ROOT / 'data/mcp').mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='income-test-', dir=op.ROOT / 'data/mcp')
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to((op.ROOT / 'data/mcp').resolve()))
        self.addCleanup(self.temp.cleanup)
        self.database = self.root / 'market.db'
        self.settings = self.root / 'etf_settings.json'
        self.settings.write_text(json.dumps({'buy_zone': 1, 'stop_loss_pct': .2}))
        self.backtest_settings = self.root / 'backtest_config.json'
        self.backtest_settings.write_text(json.dumps({'rebal_freq': 'quarterly'}))
        for context in (patch.dict(os.environ, MARKETDB_PATH=str(self.database), MARKET_INCOME_CONFIG_DIR=str(self.root)),
                        patch.object(IC, 'ROOT', self.root), patch.object(db, 'DB_PATH', self.database),
                        patch.object(db, 'LOCK_PATH', self.root / 'run.lock')):
            context.start()
            self.addCleanup(context.stop)
        self.rankings = pd.DataFrame([
            {'ticker': 'JEPI', 'rank': 1, 'qualified': True, 'chg_3m': 5., 'price': 100., 'score': 90., 'yield_ttm': 12., 'r_nav3': 1.},
            {'ticker': 'QYLD', 'rank': 2, 'qualified': False, 'chg_3m': -5., 'price': 89., 'score': 80., 'yield_ttm': 18., 'r_nav3': .3},
            {'ticker': 'JEPQ', 'rank': 3, 'qualified': True, 'chg_3m': 2., 'price': 80., 'score': 70., 'yield_ttm': 14., 'r_nav3': .6},
        ])
        with closing(sqlite3.connect(self.database)) as con, con:
            con.executescript((op.ROOT / 'marketdb/schema.sql').read_text())
            for ticker, price in [('JEPI', 100.), ('JEPQ', 80.), ('QYLD', 89.)]:
                con.execute("INSERT INTO securities(ticker,name,region,currency,quote_type) VALUES(?,?,'US','USD','ETF')", (ticker, ticker))
                for day in pd.bdate_range('2026-10-01', '2026-10-27'):
                    div = 1. if ticker == 'JEPI' and day.day in (9, 20) else 0.
                    con.execute("INSERT INTO prices(ticker,date,close,adj_close,dividend,split) VALUES(?,?,?,?,?,0)",
                                (ticker, day.date().isoformat(), price, price, div))
            buf = io.BytesIO()
            self.rankings.to_parquet(buf, index=False)
            con.execute("INSERT INTO frames VALUES('etf_income/20261027','2026-10-27 08:00:00',3,?)", (buf.getvalue(),))

    def holding(self, ticker='JEPI', **changes):
        return {'ticker': ticker, 'shares': 10., 'entry_price': 100., 'entry_date': '2026-10-01', 'quote_currency': 'USD', **changes}

    def preview(self, holdings=None, **kwargs):
        return income.preview_etf_income_review('income-demo-test', holdings=holdings, as_of=AS_OF, **kwargs)

    def test_saved_configuration_defaults_redaction_and_cadences(self):
        self.settings.write_text(json.dumps({'buy_zone': 1, 'stop_loss_pct': .2, 'api_key': 'SECRET', 'unrelated': 'SECRET'}))
        cfg = income.etf_income_config()
        self.assertNotIn('SECRET', json.dumps(cfg))
        self.assertEqual(cfg['strategy']['effective'], scorer.load_strategy(self.settings)['effective'])
        self.assertEqual(cfg['cadence']['saved_backtest_rebalance_cadence'], 'quarterly')
        self.assertEqual(cfg['cadence']['conversation_context']['risk_review_frequency'], 'monthly')
        self.assertEqual(cfg['cadence']['conversation_context']['full_rebalance_cadence'], 'undecided')
        self.assertIsNone(cfg['cadence']['saved_live_full_rebalance_cadence'])
        self.backtest_settings.write_text('{"rebal_freq":"monthly"}')
        cfg = income.etf_income_config()
        self.assertEqual(cfg['cadence']['saved_backtest_rebalance_cadence'], 'monthly')
        self.assertFalse(cfg['cadence']['conversation_context']['quarterly_idea_adopted'])
        self.assertFalse(cfg['capabilities']['settings_write'])

    def test_hold_review_sell_and_qualified_rank_parity(self):
        held = [self.holding(ticker) for ticker in ('JEPI', 'QYLD', 'JEPQ')]
        result = self.preview(held)
        ranks = qualified_ranks(self.rankings)
        self.assertEqual(ranks, {'JEPI': 1, 'JEPQ': 2})
        for output in result['holdings']:
            ticker = output['holding']['ticker']
            row = self.rankings[self.rankings['ticker'] == ticker].iloc[0].to_dict()
            self.assertEqual(output['rule_evidence']['ranking'], ranking_decision(row, ranks.get(ticker), 1))
        self.assertEqual([h['rule_evidence']['ranking']['signal'] for h in result['holdings']], ['HOLD', 'SELL', 'REVIEW'])
        self.assertEqual(result['holdings'][0]['stop_loss']['status'], 'OK')
        self.assertEqual(result['holdings'][0]['rule_evidence']['stop_loss'], result['holdings'][0]['stop_loss'])
        # The page's actual float expression 80/100-1 lies just above -0.20;
        # retain that exact behaviour rather than silently changing a threshold.
        self.assertEqual(result['holdings'][2]['stop_loss']['status'], stop_decision(80 / 100 - 1, .2)['status'])
        self.assertTrue(all(h['rule_evidence']['true_nav_deterioration']['status'] == 'not_assessed' for h in result['holdings']))

    def test_distribution_adjustment_is_not_nav_or_raw_price_stop(self):
        history = pd.DataFrame({'Close': [100., 80.], 'Dividends': [50., 5.]}, index=pd.to_datetime(['2026-01-01', '2026-01-02']))
        tr = holding_total_return(history, 100, '2026-01-01')
        self.assertAlmostEqual(tr, -.15)
        self.assertEqual(stop_decision(tr, .2)['status'], 'NEAR')
        self.assertEqual(stop_decision(-.2, .2)['status'], 'HIT')
        self.assertEqual(stop_decision(None, .2)['status'], 'not_assessed')
        self.assertEqual(stop_decision(-.01, 0)['status'], 'HIT')  # existing live-page semantics
        self.assertEqual(backtest.DEFAULTS['stop_loss_pct'], 0.)  # simulator uses 0 = disabled separately

    def test_split_missing_currency_and_stale_stop_are_not_assessed(self):
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute("UPDATE prices SET split=2 WHERE ticker='JEPI' AND date='2026-10-20'")
        result = self.preview([self.holding()])['holdings'][0]
        self.assertEqual(result['stop_loss']['status'], 'not_assessed')
        self.assertIn('corporate action', result['stop_loss']['reason'])
        self.assertIsNotNone(result['stop_loss']['app_formula_proxy_return_fraction'])
        result = self.preview([self.holding(quote_currency='AUD')])['holdings'][0]
        self.assertIn('currency', result['stop_loss']['reason'])
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute("DELETE FROM prices WHERE date>'2026-10-09'")
        result = self.preview([self.holding('JEPQ')])['holdings'][0]
        self.assertEqual(result['stop_loss']['status'], 'not_assessed')
        self.assertIn('stale', result['stop_loss']['reason'])

    def test_missing_holdings_are_not_an_empty_external_portfolio(self):
        result = self.preview()
        self.assertEqual(result['holdings_source']['status'], 'unavailable')
        self.assertEqual(result['buy_zone_candidates'], [])
        self.assertFalse(result['persisted'])
        explicit = self.preview([])
        self.assertEqual(explicit['holdings_source']['status'], 'explicit_preview_inputs')
        self.assertEqual([row['ticker'] for row in explicit['buy_zone_candidates']], ['JEPI'])
        with self.assertRaises(ValueError):
            income.preview_etf_income_review('growth', holdings=[])

    def test_legacy_cache_remains_discoverable_without_any_reports(self):
        self.assertEqual(op.list_reports('etf_income')['rows'], [])
        result = income.read_etf_income_results(limit=1)
        self.assertEqual(result['total_rows'], 3)
        self.assertEqual(result['next_offset'], 1)
        self.assertFalse(result['source']['configuration_known'])
        self.assertEqual(result['source']['frame'], 'etf_income/20261027')
        self.assertEqual(op.market_catalog()['etf_income']['legacy_latest_frame'], 'etf_income/20261027')

    def test_allocation_is_same_calculator_and_requires_explicit_fx(self):
        allocation = {'tickers': ['JEPI', 'JEPQ'], 'budget_aud': 1000., 'usd_per_aud': .65,
                      'fx_source': 'synthetic fixture', 'fx_observed_at': '2026-10-27T01:00:00+00:00'}
        result = self.preview([], allocation=allocation)['allocation_preview']
        expected = allocation_preview(self.rankings, ['JEPI', 'JEPQ'], 1000., .65)
        self.assertEqual(result['rows'], expected['rows'])
        self.assertEqual([r['hypothetical_whole_shares'] for r in result['rows']], [3, 4])
        self.assertFalse(result['execution_ready'])
        with self.assertRaises(ValueError):
            self.preview([], allocation={'tickers': ['JEPI'], 'budget_aud': 1000.})

    def test_preview_makes_no_db_holdings_or_settings_writes(self):
        before_settings = self.settings.read_bytes()
        with op.connection() as con:
            before = con.execute('SELECT COUNT(*) FROM reports').fetchone()[0]
        result = self.preview([self.holding()])
        self.assertEqual(self.settings.read_bytes(), before_settings)
        self.assertFalse((self.root / 'holdings.json').exists())
        with op.connection() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM reports').fetchone()[0], before)
        self.assertFalse(result['journal_written'])

    def test_immutable_generations_config_history_and_snapshots(self):
        configuration = {'strategy': IC.load_strategy()}
        first = save_generation('etf_income', {'rankings': self.rankings}, configuration)
        self.settings.write_text('{"buy_zone":2,"stop_loss_pct":0.25}')
        second = save_generation('etf_income', {'rankings': self.rankings.iloc[:1]}, {'strategy': IC.load_strategy()})
        self.assertNotEqual(first['run_id'], second['run_id'])
        old = income.read_etf_income_results(run_id=first['run_id'])
        self.assertEqual(old['source']['generation_configuration']['strategy']['effective']['buy_zone'], 1)
        self.assertEqual(old['total_rows'], 3)
        self.assertEqual(len(op.list_reports('etf_income_run')['rows']), 2)
        self.assertEqual(len(op.list_reports('etf_income')['rows']), 1)
        snapshot = income.build_snapshot('income-demo-test', [self.holding()], as_of=AS_OF)
        descriptor = save_review(snapshot)
        self.settings.write_text('{"buy_zone":5}')
        saved = income.read_etf_income_review(descriptor['review_id'])
        self.assertTrue(saved['persisted'])
        self.assertEqual(saved['configuration']['strategy']['effective']['buy_zone'], 2)
        self.assertEqual(save_review(snapshot)['review_id'], descriptor['review_id'])
        self.assertEqual(len(op.list_reports('etf_income_review')['rows']), 1)
        exported = op.read_report('etf_income_review', descriptor['review_id'], section='payload')['content']
        self.assertTrue(exported.startswith('{'))

    def test_scorer_uses_same_metrics_and_saves_both_stores(self):
        dates = pd.bdate_range('2026-06-01', periods=90)
        metrics = scorer.compute_metrics(pd.Series(np.linspace(80, 100, len(dates)), index=dates), pd.Series([1., 1., 1., 1.], index=dates[-4:]))
        self.assertFalse(metrics is None)
        with patch.object(scorer, 'SETTINGS_FILE', str(self.settings)), patch.object(scorer._px, 'prefetch'), \
             patch.object(scorer, 'fetch_underlying_rs', return_value={}), \
             patch.object(scorer, 'fetch_etf_data', side_effect=lambda ticker: dict(metrics)), redirect_stdout(io.StringIO()):
            result = scorer.run()
        expected = scorer.score_universe({ticker: {**metrics, 'name': details[0], 'underlying': details[1], 'freq': details[2], 'underlying_rs': None}
                                         for ticker, details in IC.FULL_UNIVERSE.items() if ticker != 'MSTY'}, weights=IC.load_strategy()['effective']['weights'])
        self.assertEqual(result['ticker'].tolist(), expected.index.tolist())
        self.assertEqual(result['score'].tolist(), expected['score'].tolist())
        self.assertEqual(len(op.list_reports('etf_income_run')['rows']), 1)
        self.assertEqual(income.read_etf_income_results(run_id=result.attrs['income_run']['run_id'])['total_rows'], len(expected))

    def test_backtest_reuses_scorer_and_preserves_summary_discovery(self):
        self.settings.write_text(json.dumps({'excluded': [t for t in IC.FULL_UNIVERSE if t not in ('JEPI', 'JEPQ')]}))
        self.backtest_settings.write_text(json.dumps({'years': 1, 'top_n': 1, 'rebal_freq': 'quarterly', 'start_capital': 10000}))
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=550)
        frame = pd.DataFrame({'Close': np.linspace(80, 120, len(dates)), 'Dividends': np.where(np.arange(len(dates)) % 21 == 0, .5, 0)}, index=dates)
        with patch.object(backtest, 'CONFIG_FILE', str(self.backtest_settings)), \
             patch.object(backtest, 'fetch_history', side_effect=lambda tickers, years: {t: frame for t in tickers}), \
             patch.object(backtest, 'fetch_adj', return_value={}), \
             patch.object(backtest, 'build_cash_rate', side_effect=lambda cal, years: pd.Series(0., index=cal)), \
             patch.object(backtest, 'RESULTS_DIR', str(self.root / 'backtest')), redirect_stdout(io.StringIO()):
            summary = backtest.run_backtest()
        self.assertEqual(summary['rebal_freq'], 'quarterly')
        self.assertEqual(len(op.list_reports('etf_backtest_run')['rows']), 1)
        report = json.loads(op.read_report('etf_backtest_run', section='payload')['content'])
        self.assertEqual(report['configuration']['backtest']['effective']['rebal_freq'], 'quarterly')
        self.assertEqual(report['summary'], summary)
        self.assertEqual(backtest.compute_hedge_signal(pd.Series([11., 10., 9.], index=dates[:3]), pd.Series([10., 10., 10.], index=dates[:3])).tolist(), [True, True, False])

    def test_review_retry_conflict_and_concurrency(self):
        args = {'portfolio_id': 'income-demo-test', 'holdings': [self.holding()], 'as_of': AS_OF}
        with patch('market_mcp.jobs.subprocess.Popen') as spawn, patch.object(jobs, 'process_running', return_value=True):
            spawn.return_value.pid = os.getpid()
            one = jobs.start_etf_income_review('review-1', **args)
            two = jobs.start_etf_income_review('review-1', **args)
            self.assertEqual(one['job_id'], two['job_id'])
            self.assertEqual(spawn.call_count, 1)
            with self.assertRaises(ValueError):
                jobs.start_etf_income_review('review-1', portfolio_id='different', holdings=[], as_of=AS_OF)
            with self.assertRaises(ValueError):
                jobs.start_report('other', 'etf_income')

    def test_invalid_or_unconfigured_settings_are_explicit(self):
        self.settings.write_text('{"stop_loss_pct":NaN}')
        cfg = income.etf_income_config()
        self.assertEqual(cfg['strategy']['state'], 'defaults_invalid_file')
        self.assertFalse(cfg['strategy']['valid_for_review'])
        self.assertEqual(self.preview([self.holding()])['holdings'][0]['stop_loss']['status'], 'not_assessed')
        self.settings.unlink()
        self.assertEqual(income.etf_income_config()['strategy']['state'], 'defaults_missing_file')
        (self.root / 'holdings.json').write_text('{invalid')
        self.assertEqual(self.preview()['holdings_source']['status'], 'invalid')

    def test_stale_ranking_and_unknown_qualification_do_not_become_actions(self):
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute("UPDATE frames SET name='etf_income/20261001'")
        result = self.preview([self.holding()])
        self.assertEqual(result['holdings'][0]['recommendation_status'], 'not_assessed')
        self.assertTrue(any('stale' in warning for warning in result['warnings']))
        self.assertEqual(ranking_decision({'qualified': None}, None, 1)['signal'], 'not_assessed')
        self.assertEqual(ranking_decision({'qualified': False, 'chg_3m': 0}, None, 1)['signal'], 'SELL')
        self.assertFalse(income._diagnostics({'qualified': True, 'chg_3m': -1}, 1, 1)['qualification_consistent_with_observed_gate'])

    def test_successful_script_without_new_artifact_is_not_success(self):
        original_cwd = os.getcwd()
        try:
            with patch.dict(os.environ, MARKET_MCP_JOB_ID='no-output-test'), patch.object(worker.runpy, 'run_path', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'no immutable output'):
                    worker.execute('report', {'report': 'etf_income'})
        finally:
            os.chdir(original_cwd)

    def test_native_preview_tool_schema_and_read_call(self):
        from starlette.testclient import TestClient
        from market_mcp.server import create_server, http_app
        with TestClient(http_app(create_server(), '127.0.0.1'), base_url='http://localhost', client=('127.0.0.1', 1000)) as client:
            headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
            client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'income-test', 'version': '1'}}})
            result = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                'name': 'preview_etf_income_review', 'arguments': {'portfolio_id': 'income-demo-test', 'holdings': [self.holding()], 'as_of': AS_OF}}}).json()['result']
            self.assertFalse(result.get('isError'), result)
            data = json.loads(result['content'][0]['text'])
            self.assertEqual(data['holdings'][0]['rule_evidence']['ranking']['signal'], 'HOLD')
            self.assertFalse(data['persisted'])
            bad = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {
                'name': 'preview_etf_income_review', 'arguments': {'portfolio_id': 'income-demo-test', 'holdings': [{'ticker': 'JEPI', 'unexpected': 1}]}}}).json()['result']
            self.assertTrue(bad['isError'])

    def test_existing_job_history_survives_additive_outcome_upgrade(self):
        directory = jobs.job_dir()
        directory.mkdir(parents=True)
        with closing(sqlite3.connect(directory / 'jobs.sqlite')) as con, con:
            con.execute('CREATE TABLE jobs (job_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL, pid INTEGER, created TEXT NOT NULL, started TEXT, finished TEXT, exit_code INTEGER, message TEXT)')
            con.execute("INSERT INTO jobs(job_id,request_id,kind,arguments,status,created) VALUES(?, 'old', 'update','{}','completed','2026-10-01')", ('a' * 32,))
        old = jobs.list_jobs()['rows'][0]
        self.assertEqual(old['request_id'], 'old')
        self.assertIsNone(old['outcome'])

    def test_real_background_review_only_writes_immutable_review(self):
        job = jobs.start_etf_income_review('offline-income-review', 'income-demo-test', holdings=[self.holding()], as_of=AS_OF)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status = jobs.get_job(job['job_id'])
            if status['status'] not in jobs.ACTIVE:
                break
            time.sleep(.1)
        while jobs.process_running(status['pid']) and time.monotonic() < deadline:
            time.sleep(.1)
        self.assertFalse(jobs.process_running(status['pid']))
        self.assertIn(status['status'], ('completed', 'completed_with_warnings'), status)
        outcome = status['outcome']['steps'][0]
        saved = income.read_etf_income_review(outcome['review_id'])
        self.assertEqual(saved['job_id'], job['job_id'])
        self.assertEqual(saved['configuration']['strategy']['effective']['buy_zone'], 1)
        self.assertFalse((self.root / 'holdings.json').exists())
        with op.connection() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM reports').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
