"""MCP regressions against isolated databases; never download data or touch the real store."""
from __future__ import annotations

import io
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import anyio

from market_mcp import config, jobs, operations as op
from market_mcp.server import create_server, http_app


class MarketMCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=op.ROOT / "data")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.db"
        self.env = patch.dict(os.environ, {"MARKETDB_PATH": str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        with closing(sqlite3.connect(self.path)) as con, con:
            con.executescript((op.ROOT / "marketdb/schema.sql").read_text(encoding="utf-8"))
            con.executemany("INSERT INTO securities(ticker,name,region,sector,quote_type,active) VALUES(?,?,?,?,?,1)",
                            [("AAA.AX", "Alpha", "AU", "Materials", "EQUITY"), ("BBB", "Beta", "US", "Technology", "EQUITY")])
            con.executemany("INSERT INTO prices(ticker,date,close,adj_close,volume) VALUES('AAA.AX',?,?,?,100)",
                            [("2026-10-21", 10, 9.5), ("2026-10-22", 11, 10.5)])
            con.executemany("INSERT INTO study_results(run_date,study,universe,ticker,rank,actionable,score_final) VALUES(?,'screener','au_total_market','AAA.AX',1,?,?)",
                            [("2026-10-21", 1, 90), ("2026-10-22", 0, 80)])
            con.execute("INSERT INTO breadth_daily VALUES('2026-10-22','au_total_market','all','all','','above_20',1)")
            con.execute("INSERT INTO rrg_history(date,study,ticker,rs_ratio,rs_momentum) VALUES('2026-10-22','au','AAA.AX',102,101)")
            con.execute("INSERT INTO demark_signals(run_date,ticker,d_setup9_buy) VALUES('2026-10-22','BBB',1)")
            con.execute("INSERT INTO reports VALUES('macro_report','2026-10-22','abcdefghij','{\"vix\":16}','2026-10-22 08:00:00')")
            con.execute("INSERT INTO drawdown_summaries VALUES('sample','au_total_market','[]','summary','2026-10-22')")
            con.execute("INSERT INTO drawdown_results VALUES('sample','p1','2026-01-01','AAA.AX',1,'{\"return\":0.1}','2026-10-22')")

    def test_reads_are_read_only_and_missing_db_is_not_created(self):
        before = self.path.read_bytes()
        op.market_catalog()
        with op.connection() as con:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("DELETE FROM securities")
        self.assertEqual(before, self.path.read_bytes())
        with patch.dict(os.environ, {"MARKETDB_PATH": str(self.path.parent / "missing.db")}):
            with self.assertRaises(ValueError):
                op.market_catalog()
            self.assertFalse(op.database_path().exists())

    def test_price_pages_dates_and_adjustment_fields(self):
        first = op.read_prices("aaa.ax", limit=1)
        self.assertEqual(first["rows"][0]["date"], "2026-10-22")
        self.assertEqual(first["rows"][0]["adj_close"], 10.5)
        self.assertEqual(op.read_prices("AAA.AX", limit=1, offset=first["next_offset"])["rows"][0]["close"], 10)
        self.assertIsNone(op.read_prices("AAA.AX", end="2026-10-21")["next_offset"])
        with self.assertRaises(ValueError):
            op.read_prices("AAA.AX", start="2026-10-23", end="2026-10-21")

    def test_latest_study_does_not_fall_back_to_old_filter_match(self):
        result = op.read_screener("au_total_market", filters={"actionable": True})
        self.assertEqual(result["run_date"], "2026-10-22")
        self.assertEqual(result["rows"], [])
        self.assertEqual(len(op.read_screener("au_total_market", run_date="2026-10-21", filters={"actionable": True})["rows"]), 1)
        for filters in ({"rank; DELETE FROM prices": 1}, {"ticker": {"sql": "x"}}):
            with self.assertRaises(ValueError):
                op.read_screener("au_total_market", filters=filters)

    def test_universe_membership_and_literal_search(self):
        self.assertEqual(op.search_securities("Alpha")["rows"][0]["ticker"], "AAA.AX")
        self.assertEqual(op.search_securities("%") ["rows"], [])
        self.assertEqual([r["ticker"] for r in op.search_securities(universe="au_total_market")["rows"]], ["AAA.AX"])
        self.assertEqual(op.search_securities("' OR 1=1 --")["rows"], [])

    def test_breadth_rrg_demark_drawdown(self):
        self.assertEqual(op.read_breadth("au_total_market")["rows"][0]["value"], 1)
        self.assertEqual(op.read_rrg("au", ticker="aaa.ax")["rows"][0]["rs_ratio"], 102)
        self.assertEqual(op.read_demark()["rows"][0]["ticker"], "BBB")
        self.assertEqual(op.read_drawdown("sample")["rows"][0]["payload"]["return"], .1)

    def test_report_chunks_and_frame_index(self):
        first = op.read_report("macro_report", limit=4)
        self.assertEqual(first["content"], "abcd")
        self.assertEqual(op.read_report("macro_report", offset=first["next_offset"], limit=4)["content"], "efgh")
        self.assertEqual(json.loads(op.read_report("macro_report", section="payload")["content"]), {"vix": 16})
        import pandas as pd
        frame = pd.DataFrame({"bullish": [40., 41.]}, index=pd.DatetimeIndex(["2026-10-21", "2026-10-22"], name="date"))
        blob = io.BytesIO()
        frame.to_parquet(blob)
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("INSERT INTO frames VALUES('sentiment/aaii','2026-10-22',2,?)", (blob.getvalue(),))
        result = op.read_frame("sentiment/aaii", limit=1)
        self.assertTrue(result["rows"][0]["date"].startswith("2026-10-21"))
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(op.list_frames("sentiment/")["rows"][0]["n_rows"], 2)

    def test_bounds_and_job_validation(self):
        for limit in (0, 501, True):
            with self.assertRaises(ValueError):
                op.read_prices("AAA.AX", limit=limit)
        with self.assertRaises(ValueError):
            jobs.start_update("a", universes=[])
        with self.assertRaises(ValueError):
            jobs.start_update("a", studies=["shell"])
        with self.assertRaises(ValueError):
            jobs.start_report("a", "../config.py")
        with self.assertRaises(ValueError):
            jobs.get_job("../../config.py")
        with self.assertRaises(ValueError):
            jobs.start_drawdown("a", "au_total_market", [{"label": "a", "date": None}], "test")

    def test_duplicate_requests_and_concurrency(self):
        with patch("market_mcp.jobs.subprocess.Popen") as spawn, patch("market_mcp.jobs.process_running", return_value=True):
            spawn.return_value.pid = os.getpid()
            first = jobs.start_update("daily-1", fetch_prices=False, studies=[])
            retry = jobs.start_update("daily-1", fetch_prices=False, studies=[])
            self.assertEqual(first["job_id"], retry["job_id"])
            self.assertTrue(retry["reused"])
            self.assertEqual(spawn.call_count, 1)
            with self.assertRaises(ValueError):
                jobs.start_update("daily-2")
            with self.assertRaises(ValueError):
                jobs.start_report("daily-1", "macro_report")
        with patch("market_mcp.jobs.process_running", return_value=False):
            self.assertEqual(jobs.get_job(first["job_id"])["status"], "interrupted")

    def test_real_detached_worker_and_persistent_status(self):
        real_database = op.ROOT / "data/market.db"
        before_real = real_database.stat().st_mtime_ns if real_database.exists() else None
        submitted = jobs.start_update("offline-worker", fetch_prices=False, studies=[], universes=["au_total_market"])
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            result = jobs.get_job(submitted["job_id"], log_offset=0)
            if result["status"] not in jobs.ACTIVE:
                break
            time.sleep(.1)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["exit_code"], 0)
        while jobs.process_running(result["pid"]) and time.monotonic() < deadline:
            time.sleep(.1)
        self.assertFalse(jobs.process_running(result["pid"]))
        self.assertIn(str(self.path), result["log"])
        self.assertEqual(jobs.list_jobs()["rows"][0]["job_id"], submitted["job_id"])
        self.assertTrue(jobs.start_update("offline-worker", fetch_prices=False, studies=[], universes=["au_total_market"])["reused"])
        self.assertEqual(before_real, real_database.stat().st_mtime_ns if real_database.exists() else None)

    def test_worker_surfaces_per_study_failures_despite_zero_exit(self):
        from market_mcp import worker
        with patch("market_mcp.jobs.subprocess.Popen") as spawn:
            spawn.return_value.pid = os.getpid()
            job = jobs.start_update("partial", fetch_prices=False, studies=[])
        def failed_study(kind, args):
            with closing(sqlite3.connect(self.path)) as con, con:
                con.execute("INSERT INTO runs(kind,started,status,notes) VALUES('screener','2026-10-26','error','insufficient coverage')")
            return 0
        with patch.object(worker, "execute", side_effect=failed_study):
            self.assertEqual(worker.main(job["job_id"]), 0)
        self.assertEqual(jobs.get_job(job["job_id"])["status"], "completed_with_warnings")

    def test_settings_renders_without_starting_or_writing(self):
        from streamlit.testing.v1 import AppTest
        from market_mcp import settings_ui, control
        settings_ui._status.clear()
        settings_ui._requirements.clear()
        with patch.object(control, "probe_health", return_value={"running": False}), \
             patch.object(control, "task_status", return_value={"installed": False, "state": "Not installed"}), \
             patch.object(control, "prerequisites", return_value={"windows": True, "python": True, "script": True, "dependencies": True}), \
             patch.object(control, "manage_task") as change, patch.object(config, "save_config") as save:
            app = AppTest.from_string("from market_mcp.settings_ui import show\nshow()", default_timeout=30).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            self.assertEqual([m.value for m in app.metric], ["Not reachable", "Not installed"])
            change.assert_not_called()
            save.assert_not_called()
        settings_ui._status.clear()
        settings_ui._requirements.clear()

    def test_http_protocol_health_and_host_validation(self):
        from starlette.testclient import TestClient
        with TestClient(http_app(create_server(), "127.0.0.1", ["mt5tools"]),
                        base_url="http://mt5tools:8766", client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/health").json()["database"], str(self.path.resolve()))
            self.assertIn(client.get("/health", headers={"Host": "evil.example"}).status_code, (400, 421))
            self.assertEqual(client.get("/health", headers={"Origin": "https://evil.example"}).status_code, 403)
            headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
            initialized = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
            self.assertEqual(initialized.status_code, 200, initialized.text)
            tools = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).json()["result"]["tools"]
            self.assertEqual(len(tools), 19)
            self.assertTrue(next(t for t in tools if t["name"] == "read_prices")["annotations"]["readOnlyHint"])
            self.assertFalse(next(t for t in tools if t["name"] == "start_update")["annotations"]["readOnlyHint"])
            result = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "read_prices", "arguments": {"ticker": "AAA.AX", "limit": 1}}}).json()["result"]
            self.assertFalse(result.get("isError", False), result)
            self.assertEqual(json.loads(result["content"][0]["text"])["rows"][0]["close"], 11)
        with TestClient(http_app(create_server(), "127.0.0.1"), base_url="http://localhost",
                        client=("8.8.8.8", 1234)) as client:
            self.assertEqual(client.get("/health").status_code, 403)

    def test_stdio_protocol(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=[str(op.ROOT / "mcp_server.py"),
                "--transport", "stdio", "--database", str(self.path)], cwd=str(op.ROOT))
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    listed = await client.list_tools()
                    self.assertEqual(len(listed.tools), 19)
                    result = await client.call_tool("read_report", {"kind": "macro_report"})
                    self.assertFalse(result.is_error)
                    self.assertEqual(json.loads(result.content[0].text)["content"], "abcdefghij")
        anyio.run(exercise)

    def test_startup_defaults_and_preview_no_writes(self):
        result = config.normalise()
        self.assertEqual(result["port"], 8766)
        self.assertEqual(result["task_name"], "Market Intelligence MCP")
        self.assertEqual(result["connection_host"], "mt5tools")
        self.assertEqual(result["database"], str(self.path.resolve()))
        target = self.path.parent / "startup.json"
        config.save_config(result, target)
        self.assertEqual(config.load_config(target), result)
        for patch_value in ({"port": 0}, {"allowed_hosts": ["evil/*"]}, {"task_name": "x\n"}):
            with self.assertRaises(ValueError):
                config.normalise(patch_value)


if __name__ == "__main__":
    unittest.main()
