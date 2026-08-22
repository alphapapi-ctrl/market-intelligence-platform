"""Persist and read study results.

Writers (used by run_daily):   save_study, save_breadth, save_rrg, save_demark
Readers (used by the dashboard): latest, formatted, run_dates, actionable, tv_import,
                                 breadth_history, rrg_history, demark_latest, ...
Readers return the same frame shapes the old CSV files had so dashboard code
keeps working with a one-line change per read site.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from . import db, universe as U
from .breadth_format import long_to_wide

LEGACY_ORDER = ["delta_rank", "ticker", "name", "sector", "industry", "commodity", "type", "cap_band", "close",
                "peer_rs_score", "rs_ratio", "rs_5", "rs_21", "rs_63", "rs_trend",
                "ret_6m", "ret_12m", "ret_24m", "max_dd", "persist_frac", "vol_63", "rel_vol", "vol_label",
                "acc_watch", "sma20", "sma50", "sma200", "pass_trend", "mqs",
                "rsi_14", "rsi_div", "obv_div", "regime_label", "score_final",
                "actionable", "high_conv"]
PCT_COLS = ["ret_6m", "ret_12m", "ret_24m", "max_dd", "persist_frac", "vol_63"]


def _con(con):
    return con if con is not None else db.connect()


# ── Screener / benchmark ──────────────────────────────────────────────────────
def run_dates(study: str, universe: str, con: sqlite3.Connection | None = None) -> list[str]:
    c = _con(con)
    try:
        return db.read_df("SELECT DISTINCT run_date FROM study_results WHERE study=? AND universe=? ORDER BY run_date DESC",
                          (study, universe), con=c)["run_date"].tolist()
    finally:
        if con is None:
            c.close()


def save_study(df: pd.DataFrame, study: str, universe: str, con: sqlite3.Connection,
               run_date: str | None = None) -> pd.DataFrame:
    """Write one study run. Computes delta_rank against the most recent earlier run."""
    run_date = run_date or db.today_str()
    out = df.reset_index()                     # rank becomes a column
    prev_dates = [d for d in run_dates(study, universe, con) if d < run_date]
    if prev_dates:
        prev = db.read_df("SELECT ticker, rank AS prev_rank FROM study_results WHERE study=? AND universe=? AND run_date=?",
                          (study, universe, prev_dates[0]), con=con)
        out = out.merge(prev, on="ticker", how="left")
        out["delta_rank"] = (out["prev_rank"] - out["rank"]).fillna(0).astype(int)
        out = out.drop(columns=["prev_rank"])
    else:
        out["delta_rank"] = 0
    out = out.assign(run_date=run_date, study=study, universe=universe)
    con.execute("DELETE FROM study_results WHERE study=? AND universe=? AND run_date=?", (study, universe, run_date))
    db.upsert_df(out, "study_results", con)
    con.commit()
    return out.set_index("rank")


def latest(study: str, universe: str, con: sqlite3.Connection | None = None,
           run_date: str | None = None) -> pd.DataFrame | None:
    """Result frame indexed by rank (like the old *_latest.csv with index_col='rank')."""
    c = _con(con)
    try:
        if run_date is None:
            dates = run_dates(study, universe, c)
            if not dates:
                return None
            run_date = dates[0]
        df = db.read_df("SELECT * FROM study_results WHERE study=? AND universe=? AND run_date=? ORDER BY rank",
                        (study, universe, run_date), con=c)
    finally:
        if con is None:
            c.close()
    if df.empty:
        return None
    df = df.set_index("rank")
    df.attrs["run_date"] = run_date
    cols = [k for k in LEGACY_ORDER if k in df.columns]
    return df[cols]


def format_results(df: pd.DataFrame) -> pd.DataFrame:
    """The old *_latest_formatted.csv look: percent columns rendered as '12.34%'."""
    if df is None:
        return None
    f = df.copy()
    for col in PCT_COLS:
        if col in f.columns:
            f[col] = f[col].map(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
    return f


def formatted(study: str, universe: str, con=None, run_date=None) -> pd.DataFrame | None:
    return format_results(latest(study, universe, con, run_date))


def actionable(study: str, universe: str, con=None, run_date=None, high_conv: bool = False) -> pd.DataFrame | None:
    df = latest(study, universe, con, run_date)
    if df is None:
        return None
    flag = "high_conv" if high_conv else "actionable"
    return df[df[flag] == 1]


def tv_import(df: pd.DataFrame, con: sqlite3.Connection | None = None) -> str:
    """Comma-joined TradingView symbols for the tickers in df."""
    if df is None or len(df) == 0:
        return ""
    c = _con(con)
    try:
        ex = db.read_df("SELECT ticker, exchange FROM securities", con=c)
    finally:
        if con is None:
            c.close()
    exch = dict(zip(ex["ticker"], ex["exchange"]))
    return ",".join(U.tv_symbol(t, exch.get(t)) for t in df["ticker"])


def study_dates_all(con=None) -> pd.DataFrame:
    c = _con(con)
    try:
        return db.read_df("""SELECT study, universe, MAX(run_date) AS run_date, COUNT(DISTINCT run_date) AS runs
                             FROM study_results GROUP BY 1,2 ORDER BY 2,1""", con=c)
    finally:
        if con is None:
            c.close()


# ── Breadth ───────────────────────────────────────────────────────────────────
MIN_UNIVERSE_RATIO = 0.90


def save_breadth(long_df: pd.DataFrame, con: sqlite3.Connection, log=print, replace_all: bool = False) -> int:
    """Upsert long rows, dropping any day whose 'total' is far below the recent baseline
    (a partial fetch would otherwise read as a breadth collapse). replace_all wipes the
    universe's history first (full rebuild) and skips the baseline guard."""
    if long_df is None or long_df.empty:
        return 0
    uni = long_df["universe"].iloc[0]
    if replace_all:
        con.execute("DELETE FROM breadth_daily WHERE universe=?", (uni,))
        n = db.upsert_df(long_df, "breadth_daily", con)
        con.commit()
        return n
    totals = long_df[(long_df["group_type"] == "all") & (long_df["layer"] == "all") & (long_df["metric"] == "total")]
    hist = db.read_df("""SELECT value FROM breadth_daily WHERE universe=? AND layer='all' AND group_type='all'
                         AND metric='total' ORDER BY date DESC LIMIT 60""", (uni,), con=con)
    drop_days = set()
    if len(hist):
        baseline = float(hist["value"].median())
        if baseline > 0:
            for d, v in zip(totals["date"], totals["value"]):
                if v < baseline * MIN_UNIVERSE_RATIO:
                    drop_days.add(d)
                    log(f"    SKIPPED {d} — only {int(v)} tickers vs baseline {int(baseline)}; not written")
    keep = long_df[~long_df["date"].isin(drop_days)]
    if keep.empty:
        return 0
    for d in keep["date"].unique():
        con.execute("DELETE FROM breadth_daily WHERE universe=? AND date=?", (uni, d))
    n = db.upsert_df(keep, "breadth_daily", con)
    con.commit()
    return n


def breadth_history(universe: str, con: sqlite3.Connection | None = None,
                    since: str | None = None) -> pd.DataFrame | None:
    """Wide frame with the legacy column names, sorted by date (what the dashboard reads)."""
    c = _con(con)
    try:
        sql = "SELECT date, layer, group_type, group_key, metric, value FROM breadth_daily WHERE universe=?"
        params = [universe]
        if since:
            sql += " AND date >= ?"; params.append(since)
        df = db.read_df(sql, params, con=c)
    finally:
        if con is None:
            c.close()
    if df.empty:
        return None
    return long_to_wide(df)


def breadth_summary_text(history: pd.DataFrame, title: str) -> str:
    """Console/text summary equivalent to the legacy print_breadth_summary()."""
    if history is None or history.empty:
        return ""
    today = history.iloc[-1]
    today_str = str(today["date"])

    def past(days):
        target = pd.Timestamp(today_str) - pd.Timedelta(days=days)
        p = history[pd.to_datetime(history["date"]) <= target]
        return p.iloc[-1] if len(p) else None

    d5, d20, d63 = past(7), past(28), past(91)

    def delta(key, p):
        if p is None or key not in history.columns:
            return "n/a"
        try:
            v = today[key] - p[key]
            return f"+{int(v)}" if v > 0 else str(int(v))
        except (TypeError, ValueError):
            return "n/a"

    core = [("Total", "total"), ("Leaders", "leader"), ("Contenders", "contender"), ("Laggards", "laggard"),
            ("Weak", "weak"), ("Above 20 SMA", "above_20"), ("Above 50 SMA", "above_50"),
            ("Above 200 SMA", "above_200"), ("High Volume", "high_vol"), ("Acc Early", "acc_early"),
            ("Acc Progress", "acc_progress"), ("Acc Shift", "acc_shift"), ("Large Total", "large_total"),
            ("Large Leaders", "large_leaders"), ("Mid Total", "mid_total"), ("Mid Leaders", "mid_leaders"),
            ("Small Total", "small_total"), ("Small Leaders", "small_leaders")]
    lines = ["═" * 80, f"  {title} BREADTH SUMMARY — {today_str}", "═" * 80,
             f"  {'Metric':<25} {'Today':>8} {'D5':>8} {'D20':>8} {'D63':>8}", "─" * 80]
    for label, key in core:
        try:
            val = int(today[key])
        except (KeyError, TypeError, ValueError):
            val = "n/a"
        lines.append(f"  {label:<25} {str(val):>8} {delta(key, d5):>8} {delta(key, d20):>8} {delta(key, d63):>8}")
    lines.append("─" * 80)
    lines.append("  SECTOR BREADTH")
    lines.append(f"  {'Sector':<25} {'Lead':>6} {'dL5':>6} {'dL63':>6} {'Ab20':>6} {'Ab50':>6} {'Ab200':>6} {'HVol':>6}")
    for col in [c for c in history.columns if c.startswith("sec_") and c.endswith("_total")]:
        k = col[4:-6]
        try:
            lines.append(f"  {k.replace('_', ' ').title()[:24]:<25} {int(today[f'sec_{k}_leaders']):>6} "
                         f"{delta(f'sec_{k}_leaders', d5):>6} {delta(f'sec_{k}_leaders', d63):>6} "
                         f"{int(today[f'sec_{k}_above20']):>6} {int(today[f'sec_{k}_above50']):>6} "
                         f"{int(today[f'sec_{k}_above200']):>6} {int(today[f'sec_{k}_high_vol']):>6}")
        except (KeyError, TypeError, ValueError):
            pass
    lines.append("═" * 80)
    return "\n".join(lines)


# ── RRG ───────────────────────────────────────────────────────────────────────
def save_rrg(df: pd.DataFrame, con: sqlite3.Connection) -> int:
    if df is None or df.empty:
        return 0
    n = db.upsert_df(df, "rrg_history", con)
    con.commit()
    return n


def rrg_history(study: str, con: sqlite3.Connection | None = None) -> pd.DataFrame | None:
    c = _con(con)
    try:
        df = db.read_df("SELECT date, ticker, name, grp AS \"group\", rs_ratio, rs_momentum, close "
                        "FROM rrg_history WHERE study=? ORDER BY date, ticker", (study,), con=c)
    finally:
        if con is None:
            c.close()
    return None if df.empty else df


# ── DeMark ────────────────────────────────────────────────────────────────────
def save_demark(df: pd.DataFrame, report: str, con: sqlite3.Connection, run_date: str | None = None) -> None:
    run_date = run_date or db.today_str()
    d = df.rename(columns={"d_setup": "d_setup_count", "w_setup": "w_setup_count"}).assign(run_date=run_date)
    con.execute("DELETE FROM demark_signals WHERE run_date=?", (run_date,))
    db.upsert_df(d, "demark_signals", con)
    con.execute("INSERT OR REPLACE INTO demark_reports VALUES (?,?)", (run_date, report))
    con.commit()


def demark_dates(con=None) -> list[str]:
    c = _con(con)
    try:
        return db.read_df("SELECT run_date FROM demark_reports ORDER BY run_date DESC", con=c)["run_date"].tolist()
    finally:
        if con is None:
            c.close()


def demark_latest(con=None, run_date: str | None = None) -> tuple[pd.DataFrame | None, str | None]:
    c = _con(con)
    try:
        if run_date is None:
            ds = demark_dates(c)
            if not ds:
                return None, None
            run_date = ds[0]
        df = db.read_df("SELECT * FROM demark_signals WHERE run_date=?", (run_date,), con=c)
        rep = db.scalar("SELECT report FROM demark_reports WHERE run_date=?", (run_date,), con=c)
    finally:
        if con is None:
            c.close()
    df = df.rename(columns={"d_setup_count": "d_setup", "w_setup_count": "w_setup"})
    return (None if df.empty else df), rep


# ── Substantial holders ───────────────────────────────────────────────────────
def holder_notices(con=None, days: int | None = None) -> pd.DataFrame | None:
    c = _con(con)
    try:
        df = db.read_df("SELECT ann_id, date, ticker, company, form, title, url AS pdf_url, payload "
                        "FROM asx_holder_notices ORDER BY date DESC, ann_id DESC", con=c)
    finally:
        if con is None:
            c.close()
    if df.empty:
        return None
    import json
    extra = pd.DataFrame([json.loads(p) if p else {} for p in df["payload"]])
    extra = extra[[c for c in extra.columns if c not in df.columns]]     # payload never overrides core cols
    df = pd.concat([df.drop(columns=["payload"]).reset_index(drop=True), extra.reset_index(drop=True)], axis=1)
    if days:
        cutoff = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        df = df[df["date"].astype(str) >= cutoff]
    return df


def save_holder_notices(df: pd.DataFrame, con: sqlite3.Connection) -> int:
    import json
    core = ["ann_id", "date", "ticker", "form", "title"]
    extra = [c for c in df.columns if c not in core + ["pdf_url", "company"]]
    out = df[core].copy()
    out["url"] = df["pdf_url"] if "pdf_url" in df.columns else None
    out["company"] = df["company"] if "company" in df.columns else None
    out["payload"] = [json.dumps({k: (None if pd.isna(v) else v) for k, v in r.items()})
                      for r in df[extra].to_dict("records")]
    n = db.upsert_df(out.drop_duplicates("ann_id"), "asx_holder_notices", con)
    con.commit()
    return n


# ── Generic reports / frames (macro, ETF, sentiment, Burry screen) ────────────
def save_report(kind: str, date: str, text: str | None = None, payload=None,
                con: sqlite3.Connection | None = None) -> None:
    import json
    c = _con(con)
    try:
        c.execute("INSERT OR REPLACE INTO reports (kind, date, text, payload, created) VALUES (?,?,?,?,?)",
                  (kind, date, text, json.dumps(payload, default=str) if payload is not None else None, db.now_iso()))
        c.commit()
    finally:
        if con is None:
            c.close()


def report_dates(kind: str, con=None) -> list[str]:
    c = _con(con)
    try:
        return db.read_df("SELECT date FROM reports WHERE kind=? ORDER BY date DESC", (kind,), con=c)["date"].tolist()
    finally:
        if con is None:
            c.close()


def load_report(kind: str, date: str | None = None, con=None):
    """-> (text, payload-dict-or-None, date) for the given or latest date; (None, None, None) if absent."""
    import json
    c = _con(con)
    try:
        if date is None:
            ds = report_dates(kind, c)
            if not ds:
                return None, None, None
            date = ds[0]
        row = c.execute("SELECT text, payload FROM reports WHERE kind=? AND date=?", (kind, date)).fetchone()
    finally:
        if con is None:
            c.close()
    if row is None:
        return None, None, None
    return row[0], (json.loads(row[1]) if row[1] else None), date


def report_created(kind: str, date: str | None = None, con=None) -> str | None:
    c = _con(con)
    try:
        if date is None:
            return db.scalar("SELECT MAX(created) FROM reports WHERE kind=?", (kind,), con=c)
        return db.scalar("SELECT created FROM reports WHERE kind=? AND date=?", (kind, date), con=c)
    finally:
        if con is None:
            c.close()


def save_frame(name: str, df: pd.DataFrame, con: sqlite3.Connection | None = None) -> int:
    """Store a DataFrame verbatim (parquet bytes) under a name, e.g. 'sentiment/aaii'."""
    import io
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    c = _con(con)
    try:
        c.execute("INSERT OR REPLACE INTO frames (name, updated, n_rows, blob) VALUES (?,?,?,?)",
                  (name, db.now_iso(), len(df), buf.getvalue()))
        c.commit()
    finally:
        if con is None:
            c.close()
    return len(df)


def load_frame(name: str, con=None) -> pd.DataFrame | None:
    import io
    c = _con(con)
    try:
        row = c.execute("SELECT blob FROM frames WHERE name=?", (name,)).fetchone()
    finally:
        if con is None:
            c.close()
    return None if row is None else pd.read_parquet(io.BytesIO(row[0]))


def frame_updated(name: str, con=None) -> str | None:
    return db.scalar("SELECT updated FROM frames WHERE name=?", (name,), con=con)


def list_frames(prefix: str, con=None) -> pd.DataFrame:
    c = _con(con)
    try:
        return db.read_df("SELECT name, updated, n_rows FROM frames WHERE name LIKE ? ORDER BY name DESC",
                          (prefix + "%",), con=c)
    finally:
        if con is None:
            c.close()


def delete_frame(name: str, con=None) -> None:
    c = _con(con)
    try:
        c.execute("DELETE FROM frames WHERE name=?", (name,)); c.commit()
    finally:
        if con is None:
            c.close()
