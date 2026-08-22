"""SQLite connection + helpers for marketdb.

Everything in the platform that touches the database goes through here so the
location, pragmas and pandas round-tripping are defined once.

    from marketdb import db
    with db.connect() as con:
        df = db.read_df("SELECT * FROM securities WHERE region = ?", ("AU",), con=con)
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

PKG_DIR  = Path(__file__).resolve().parent
BASE_DIR = PKG_DIR.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = Path(os.environ.get("MARKETDB_PATH", DATA_DIR / "market.db"))
SCHEMA   = PKG_DIR / "schema.sql"

_initialised: set[str] = set()


def utf8_console() -> None:
    """Windows consoles default to cp1252; make stdout/stderr UTF-8 so box-drawing output prints."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection, creating the schema on first use.

    Returned connection can be used as a context manager (commits on exit,
    rolls back on exception) — that is sqlite3's own behaviour; it does NOT
    close the connection, so call .close() or use `session()`.
    """
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=60, detect_types=0)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA cache_size = -64000")  # 64 MB
    key = str(p.resolve())
    if key not in _initialised:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        _migrate(con)
        con.commit()
        _initialised.add(key)
    return con


def _migrate(con: sqlite3.Connection) -> None:
    """Additive column migrations for databases created by an earlier schema."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(security_groups)")}
    if "priority" not in cols:
        con.execute("ALTER TABLE security_groups ADD COLUMN priority INTEGER NOT NULL DEFAULT 9")
    cols = {r[1] for r in con.execute("PRAGMA table_info(study_results)")}
    for name, typ in (("rsi_14", "REAL"), ("rsi_div", "TEXT"), ("obv_div", "TEXT")):
        if name not in cols:
            con.execute(f"ALTER TABLE study_results ADD COLUMN {name} {typ}")
    cols = {r[1] for r in con.execute("PRAGMA table_info(securities)")}
    for name in ("business_summary", "summary_updated"):
        if name not in cols:
            con.execute(f"ALTER TABLE securities ADD COLUMN {name} TEXT")


@contextmanager
def session(path: Path | str | None = None):
    """`with db.session() as con:` — commits on success, rolls back on error, always closes."""
    con = connect(path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── pandas helpers ────────────────────────────────────────────────────────────
def read_df(sql: str, params=(), con: sqlite3.Connection | None = None, **kw) -> pd.DataFrame:
    if con is not None:
        return pd.read_sql_query(sql, con, params=params, **kw)
    with session() as c:
        return pd.read_sql_query(sql, c, params=params, **kw)


def scalar(sql: str, params=(), con: sqlite3.Connection | None = None):
    if con is not None:
        row = con.execute(sql, params).fetchone()
    else:
        with session() as c:
            row = c.execute(sql, params).fetchone()
    return None if row is None else row[0]


def upsert_df(df: pd.DataFrame, table: str, con: sqlite3.Connection,
              columns: list[str] | None = None, chunk: int = 5000) -> int:
    """INSERT OR REPLACE every row of df into table. Returns rows written.

    Only columns present in both df and the table are written; NaN -> NULL.
    """
    if df is None or len(df) == 0:
        return 0
    table_cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    cols = [c for c in (columns or list(df.columns)) if c in table_cols]
    if not cols:
        raise ValueError(f"no matching columns for {table}: {list(df.columns)}")
    sub = df[cols].astype(object).where(pd.notna(df[cols]), None)
    placeholders = ",".join("?" * len(cols))
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    rows = [tuple(r) for r in sub.itertuples(index=False, name=None)]
    n = 0
    for i in range(0, len(rows), chunk):
        con.executemany(sql, rows[i:i + chunk])
        n += len(rows[i:i + chunk])
    return n


# ── meta key/value ────────────────────────────────────────────────────────────
def get_meta(key: str, default=None, con: sqlite3.Connection | None = None):
    v = scalar("SELECT value FROM meta WHERE key = ?", (key,), con=con)
    if v is None:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


def set_meta(key: str, value, con: sqlite3.Connection) -> None:
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (key, json.dumps(value, default=str)))


# ── run audit ─────────────────────────────────────────────────────────────────
def start_run(kind: str, universe: str | None, con: sqlite3.Connection,
              n_expected: int | None = None) -> int:
    cur = con.execute(
        "INSERT INTO runs (kind, universe, started, status, n_expected) VALUES (?,?,?,?,?)",
        (kind, universe, now_iso(), "running", n_expected))
    con.commit()
    return int(cur.lastrowid)


def finish_run(run_id: int, status: str, con: sqlite3.Connection,
               n_fetched: int | None = None, notes: str | None = None) -> None:
    con.execute("UPDATE runs SET finished=?, status=?, n_fetched=?, notes=? WHERE run_id=?",
                (now_iso(), status, n_fetched, notes, run_id))
    con.commit()


BOOTSTRAP_HINT = ("marketdb has no data yet. One-off setup (about 15 min):  python -m marketdb.bootstrap  "
                  "— or copy data/market.db from a machine that already has it, then run the daily update.")


def is_empty(con: sqlite3.Connection | None = None) -> bool:
    """True when the store has no securities (fresh clone, DB never built)."""
    try:
        return (scalar("SELECT COUNT(*) FROM securities", con=con) or 0) == 0
    except sqlite3.Error:
        return True


def db_size_mb() -> float:
    return round(DB_PATH.stat().st_size / 1e6, 1) if DB_PATH.exists() else 0.0
