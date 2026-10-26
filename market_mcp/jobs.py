"""Durable, idempotent admission for one background job per database."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
from uuid import uuid4

from .operations import ROOT, bounds, configuration, database_path, universe_key, valid_date, connection as connection_for_audit

ACTIVE = ("starting", "running")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_dir() -> Path:
    # Separate stores for database overrides, even if they share a parent directory.
    digest = hashlib.sha256(str(database_path()).encode()).hexdigest()[:12]
    return database_path().parent / "mcp" / "jobs" / digest


@contextmanager
def store():
    directory = job_dir()
    directory.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(directory / "jobs.sqlite", timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute("CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, "
                    "kind TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL, pid INTEGER, "
                    "created TEXT NOT NULL, started TEXT, finished TEXT, exit_code INTEGER, message TEXT)")
        con.commit()
        yield con
        con.commit()
    finally:
        con.close()


def process_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # access denied is not proof of termination
        try:
            result = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(result)) or result.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def reconcile(con):
    for row in con.execute("SELECT job_id,pid FROM jobs WHERE status IN ('starting','running')").fetchall():
        if row["pid"] and not process_running(row["pid"]):
            con.execute("UPDATE jobs SET status='interrupted',finished=?,message=? WHERE job_id=?",
                        (now(), "Worker exited without recording completion. Inspect the log before starting another request.", row["job_id"]))


def job_value(row) -> dict:
    result = dict(row)
    result["arguments"] = json.loads(result["arguments"])
    return result


def submit(kind: str, arguments: dict, request_id: str) -> dict:
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", request_id):
        raise ValueError("request_id must contain 1–100 letters, digits, dots, dashes or underscores; reuse it only for retries")
    if not database_path().is_file():
        raise ValueError("Market database is missing. Bootstrap the project on the server first.")
    encoded = json.dumps(arguments, sort_keys=True)
    with store() as con:
        con.execute("BEGIN IMMEDIATE")
        reconcile(con)
        previous = con.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
        if previous:
            if previous["kind"] != kind or previous["arguments"] != encoded:
                raise ValueError("request_id already belongs to a different job; choose a new request_id")
            return {**job_value(previous), "reused": True}
        active = con.execute("SELECT job_id FROM jobs WHERE status IN ('starting','running')").fetchone()
        if active:
            raise ValueError(f"A job is already active: {active['job_id']}. Use get_job to check its progress.")
        job_id = uuid4().hex
        con.execute("INSERT INTO jobs(job_id,request_id,kind,arguments,status,created) VALUES(?,?,?,?,?,?)",
                    (job_id, request_id, kind, encoded, "starting", now()))
        environment = dict(os.environ, MARKETDB_PATH=str(database_path()), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            with (job_dir() / f"{job_id}.log").open("ab") as output:
                process = subprocess.Popen([sys.executable, "-m", "market_mcp.worker", job_id],
                    cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                    close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0),
                    start_new_session=os.name != "nt")
            con.execute("UPDATE jobs SET pid=? WHERE job_id=?", (process.pid, job_id))
            # Reap the detached child without polling or tying its lifetime to MCP.
            threading.Thread(target=process.wait, daemon=True, name=f"mcp-job-{job_id[:8]}").start()
        except OSError as exc:
            con.execute("UPDATE jobs SET status='failed',finished=?,message=? WHERE job_id=?", (now(), str(exc), job_id))
        row = con.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return job_value(row)


def start_update(request_id: str, universes: list[str] | None = None, studies: list[str] | None = None,
                 fetch_prices: bool = True, refresh_universe: bool = False,
                 rebuild_breadth: bool = False, end: str | None = None) -> dict:
    """Start prices/studies via marketdb.run_daily. studies=[] means prices only; fetch_prices=False is offline unless refresh_universe=True. Use a unique request_id, reusing it for retries. Follow get_job until completion and inspect read_runs for per-study outcomes."""
    if universes == []:
        raise ValueError("Use null for all universes, or select at least one universe")
    for key in universes or []:
        universe_key(key)
    if studies is not None and (len(studies) > 4 or any(s not in ("screener", "benchmark", "breadth", "rrg") for s in studies)):
        raise ValueError("Studies may contain screener, benchmark, breadth, rrg")
    if universes is not None and (len(universes) > len(configuration()["universes"]) or len(set(universes)) != len(universes)):
        raise ValueError("Supply each selected universe once")
    valid_date(end)
    return submit("update", {"universes": universes, "studies": studies, "fetch_prices": fetch_prices,
                  "refresh_universe": refresh_universe, "rebuild_breadth": rebuild_breadth, "end": end}, request_id)


REPORTS = {"macro_report": "macro/macro_report.py", "consumer_credit": "macro/consumer_credit.py",
           "au_credit": "macro/au_credit.py", "etf_income": "etf/etf_income_data.py", "etf_backtest": "etf/etf_backtest.py"}


def start_report(request_id: str, report: str) -> dict:
    """Generate macro_report, consumer_credit, au_credit, etf_income or etf_backtest using saved server settings. May fetch external data; results replace/update the same stores used by the dashboard."""
    if report not in REPORTS:
        raise ValueError(f"report must be one of {list(REPORTS)}")
    return submit("report", {"report": report}, request_id)


def start_demark(request_id: str, universe: str = "us_total_market", min_cap: float = 0,
                  max_cap: float | None = None, end: str | None = None) -> dict:
    """Run a stored-price DeMark scan and save its results for the dashboard. One job at a time."""
    import math
    universe_key(universe)
    valid_date(end)
    if not math.isfinite(min_cap) or min_cap < 0 or (max_cap is not None and (not math.isfinite(max_cap) or max_cap < min_cap)):
        raise ValueError("Supply finite, non-negative cap bounds with max_cap >= min_cap")
    return submit("demark", {"universe": universe, "min_cap": min_cap, "max_cap": max_cap, "end": end}, request_id)


def start_drawdown(request_id: str, universe: str, periods: list[dict], study_name: str,
                   filter_column: str | None = None, filter_value: str | None = None) -> dict:
    """Run 1–3 periods [{label, date: YYYY-MM-DD}] against stored prices, fetching a missing benchmark if necessary. Saves/replaces the named drawdown study in the dashboard; choose a new study_name to retain an older study."""
    universe_key(universe)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", study_name):
        raise ValueError("study_name must use 1–100 letters, digits, dots, dashes or underscores")
    if not 1 <= len(periods) <= 3:
        raise ValueError("Supply between one and three periods")
    labels = set()
    for period in periods:
        if set(period) != {"label", "date"} or not isinstance(period["label"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,50}", period["label"]):
            raise ValueError("Each period needs a simple label and date")
        valid_date(period["date"])
        if period["date"] is None or period["label"] in labels:
            raise ValueError("Period dates are required and labels must be unique")
        labels.add(period["label"])
    if (filter_column is None) != (filter_value is None) or filter_column not in (None, "sector", "commodity"):
        raise ValueError("Use both filter_column (sector/commodity) and filter_value, or neither")
    return submit("drawdown", {"universe": universe, "periods": periods, "study_name": study_name,
                  "filter_column": filter_column, "filter_value": filter_value}, request_id)


def get_job(job_id: str, log_offset: int | None = None, log_limit: int = 16000) -> dict:
    """Read durable job status and a UTF-8 log chunk. Omit log_offset for the tail, or start at 0 and follow next_log_offset (byte offsets). History persists across MCP restarts; terminated workers become interrupted. completed_with_warnings requires checking logs and read_runs."""
    bounds(log_limit, log_offset or 0, 32000)
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Invalid job ID")
    with store() as con:
        con.execute("BEGIN IMMEDIATE")
        reconcile(con)
        row = con.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Job not found")
        result = job_value(row)
    path = job_dir() / f"{job_id}.log"
    size = path.stat().st_size if path.exists() else 0
    offset = max(0, size - log_limit) if log_offset is None else min(log_offset, size)
    data = b""
    if path.exists():
        with path.open("rb") as source:
            source.seek(offset)
            data = source.read(log_limit)
    return {**result, "log": data.decode("utf-8", errors="replace"), "log_offset": offset,
            "next_log_offset": offset + len(data), "log_bytes": size}


def list_jobs(limit: int = 20, offset: int = 0) -> dict:
    """List background update/study job outcomes, newest first, including interrupted workers."""
    bounds(limit, offset, 100)
    with store() as con:
        con.execute("BEGIN IMMEDIATE")
        reconcile(con)
        rows = con.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT ? OFFSET ?", (limit + 1, offset)).fetchall()
        return {"rows": [job_value(r) for r in rows[:limit]], "offset": offset,
                "next_offset": offset + limit if len(rows) > limit else None}
