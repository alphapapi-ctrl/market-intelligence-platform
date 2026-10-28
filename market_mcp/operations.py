"""Bounded, read-only access to the dashboard's stored data. No Streamlit imports."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import io
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def database_path() -> Path:
    return Path(os.environ.get("MARKETDB_PATH", str(ROOT / "data" / "market.db"))).resolve()


@contextmanager
def connection():
    path = database_path()
    if not path.is_file():
        raise ValueError("Market database is missing. Run the project's bootstrap on the server first.")
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def bounds(limit: int, offset: int, maximum: int = 500):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")


def valid_date(value: str | None) -> str | None:
    if value is not None:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Dates must use YYYY-MM-DD")
    return value


def configuration() -> dict:
    return json.loads((ROOT / "marketdb" / "universe_config.json").read_text(encoding="utf-8"))


def universe_key(value: str) -> str:
    if value not in configuration()["universes"]:
        raise ValueError("Unknown universe; use market_catalog to discover valid names")
    return value


def page(con, sql: str, params: list | tuple = (), limit: int = 100, offset: int = 0) -> dict:
    bounds(limit, offset)
    found = [dict(row) for row in con.execute(sql + " LIMIT ? OFFSET ?", (*params, limit + 1, offset))]
    more = len(found) > limit
    return {"rows": found[:limit], "offset": offset, "next_offset": offset + limit if more else None}


def market_catalog() -> dict:
    """Discover universes, stored datasets, report types, freshness, and recent run outcomes."""
    with connection() as con:
        return {
            "database": str(database_path()),
            "universes": configuration()["universes"],
            "rrg_studies": configuration().get("rrg", {}),
            "studies": [dict(r) for r in con.execute(
                "SELECT study,universe,MAX(run_date) AS latest_date FROM study_results GROUP BY study,universe")],
            "reports": [dict(r) for r in con.execute(
                "SELECT kind,MAX(created) AS updated,COUNT(*) AS versions FROM reports GROUP BY kind")],
            "latest_price_date": con.execute("SELECT MAX(date) FROM prices").fetchone()[0],
            "etf_income": {"config_tool": "etf_income_config", "results_tool": "read_etf_income_results",
                "legacy_latest_frame": con.execute("SELECT MAX(name) FROM frames WHERE name GLOB 'etf_income/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'").fetchone()[0],
                "generation_history_kind": "etf_income_run", "backtest_history_kind": "etf_backtest_run",
                "review_history_kind": "etf_income_review",
                "note": "Older scoring outputs exist only in frames; an empty etf_income report list does not imply no cached rankings."},
            "recent_runs": page(con, "SELECT * FROM runs ORDER BY run_id DESC", limit=20)["rows"],
            "units": "Raw database values. Stored screener/benchmark ret_6m/12m/24m, max_dd, persist_frac and vol_63 are percentage values (12 = 12%). Drawdown return and drawdown fields are also percentage values. Breadth values are counts by metric. Prices use each security's quote currency. Report payloads and cached frames retain their source-specific units.",
            "actionable_note": "Stored actionable/high_conv flags and acc_watch are study outputs. The dashboard can apply additional saved or interactive SMA/score filters; these are not reproduced here.",
        }


def search_securities(query: str = "", universe: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    """Search ticker/name. Optional universe membership uses the dashboard's universe resolver."""
    bounds(limit, offset)
    if len(query) > 200:
        raise ValueError("Search text is too long")
    with connection() as con:
        if universe:
            universe_key(universe)
            from marketdb import universe as U
            frame = U.members(universe, con=con)
            if query:
                frame = frame[frame["ticker"].str.contains(query, case=False, regex=False, na=False)
                              | frame["name"].str.contains(query, case=False, regex=False, na=False)]
            frame = frame.sort_values("ticker")
            selected = frame.iloc[offset:offset + limit]
            return {"rows": json.loads(selected.to_json(orient="records")), "offset": offset,
                    "next_offset": offset + limit if len(frame) > offset + limit else None}
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return page(con, "SELECT ticker,name,region,exchange,sector,industry,quote_type,market_cap,cap_band,currency,active "
                    "FROM securities WHERE ticker LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' ORDER BY ticker",
                    [f"%{escaped}%", f"%{escaped}%"], limit, offset)


def read_prices(ticker: str, start: str | None = None, end: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    """Read raw OHLCV, adjusted close, dividends and splits, newest first. No network fetch."""
    valid_date(start)
    valid_date(end)
    if start and end and start > end:
        raise ValueError("start must be on or before end")
    with connection() as con:
        return page(con, "SELECT * FROM prices WHERE ticker=? AND (? IS NULL OR date>=?) "
                    "AND (? IS NULL OR date<=?) ORDER BY date DESC", [ticker.upper(), start, start, end, end], limit, offset)


def read_screener(universe: str, study: str = "screener", run_date: str | None = None,
                  filters: dict | None = None, limit: int = 100, offset: int = 0) -> dict:
    """Read ranked screener/benchmark outputs. Filters are exact stored values; flags accept booleans."""
    universe_key(universe)
    if study not in ("screener", "benchmark"):
        raise ValueError("study must be screener or benchmark")
    valid_date(run_date)
    allowed = {"ticker", "sector", "industry", "commodity", "type", "cap_band", "regime_label", "vol_label", "acc_watch", "rsi_div", "obv_div", "actionable", "high_conv"}
    clauses, params = [], [study, universe]
    for key, value in (filters or {}).items():
        if key not in allowed or not isinstance(value, (str, bool, int)):
            raise ValueError(f"Invalid filter: {key}. Allowed filters: {sorted(allowed)}")
        clauses.append(f" AND {key}=?")
        params.append(value)
    with connection() as con:
        chosen = run_date or con.execute("SELECT MAX(run_date) FROM study_results WHERE study=? AND universe=?", (study, universe)).fetchone()[0]
        result = page(con, "SELECT * FROM study_results WHERE study=? AND universe=?" + "".join(clauses)
                      + " AND run_date=? ORDER BY rank,ticker", [*params, chosen], limit, offset)
        return {"run_date": chosen, "universe": universe, "study": study, **result}


def read_breadth(universe: str, start: str | None = None, end: str | None = None,
                 layer: str = "all", group_type: str = "all", group_key: str = "",
                 metric: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    """Read breadth counts in long format by date/layer/group/metric, newest first."""
    universe_key(universe)
    valid_date(start)
    valid_date(end)
    with connection() as con:
        return page(con, "SELECT * FROM breadth_daily WHERE universe=? AND layer=? AND group_type=? AND group_key=? "
                    "AND (? IS NULL OR metric=?) AND (? IS NULL OR date>=?) AND (? IS NULL OR date<=?) ORDER BY date DESC,metric",
                    [universe, layer, group_type, group_key, metric, metric, start, start, end, end], limit, offset)


def read_rrg(study: str, ticker: str | None = None, start: str | None = None, end: str | None = None,
             limit: int = 100, offset: int = 0) -> dict:
    """Read stored relative rotation coordinates and dated tails; discover study keys in market_catalog."""
    if study not in configuration().get("rrg", {}):
        raise ValueError("Unknown RRG study")
    valid_date(start)
    valid_date(end)
    with connection() as con:
        return page(con, "SELECT * FROM rrg_history WHERE study=? AND (? IS NULL OR ticker=?) "
                    "AND (? IS NULL OR date>=?) AND (? IS NULL OR date<=?) ORDER BY date DESC,ticker",
                    [study, ticker, ticker.upper() if ticker else None, start, start, end, end], limit, offset)


def read_demark(run_date: str | None = None, ticker: str | None = None, signals_only: bool = True,
                limit: int = 100, offset: int = 0) -> dict:
    """Read the latest or dated stored DeMark scan. signals_only selects completed setup9/countdown13 signals."""
    valid_date(run_date)
    with connection() as con:
        chosen = run_date or con.execute("SELECT MAX(run_date) FROM demark_signals").fetchone()[0]
        sql = "SELECT * FROM demark_signals WHERE run_date=? AND (? IS NULL OR ticker=?)"
        if signals_only:
            sql += " AND (d_setup9_buy=1 OR d_setup9_sell=1 OR w_setup9_buy=1 OR w_setup9_sell=1 OR d_cd13_buy=1 OR d_cd13_sell=1 OR w_cd13_buy=1 OR w_cd13_sell=1)"
        return {"run_date": chosen, **page(con, sql + " ORDER BY ticker", [chosen, ticker, ticker.upper() if ticker else None], limit, offset)}


def list_reports(kind: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    """List stored macro/credit/ETF reports with text/payload sizes, without loading their contents."""
    with connection() as con:
        return page(con, "SELECT kind,date,created,length(text) AS text_chars,length(payload) AS payload_chars "
                    "FROM reports WHERE (? IS NULL OR kind=?) ORDER BY created DESC,kind,date DESC", [kind, kind], limit, offset)


def read_report(kind: str, report_date: str | None = None, section: str = "text", offset: int = 0, limit: int = 20000) -> dict:
    """Read text or serialized JSON payload in character chunks. Follow next_offset; latest chosen by creation time."""
    bounds(limit, offset, 20000)
    if section not in ("text", "payload"):
        raise ValueError("section must be text or payload")
    with connection() as con:
        row = con.execute(f"SELECT kind,date,created,length({section}) AS total_chars,substr({section},?,?) AS content "
                          "FROM reports WHERE kind=? AND (? IS NULL OR date=?) ORDER BY created DESC,date DESC LIMIT 1",
                          (offset + 1, limit, kind, report_date, report_date)).fetchone()
        if row is None:
            raise ValueError("Report not found; use list_reports")
        result = dict(row)
        return {**result, "section": section, "offset": offset,
                "next_offset": offset + limit if (result["total_chars"] or 0) > offset + limit else None}


def list_frames(prefix: str = "", limit: int = 100, offset: int = 0) -> dict:
    """Discover cached sentiment, ETF, Burry and other table names and freshness."""
    with connection() as con:
        return page(con, "SELECT name,updated,n_rows FROM frames WHERE substr(name,1,?)=? ORDER BY name", [len(prefix), prefix], limit, offset)


def read_frame(name: str, limit: int = 100, offset: int = 0) -> dict:
    """Read a cached table in row pages. The table index is included; no cache refresh/network calls."""
    bounds(limit, offset)
    with connection() as con:
        meta = con.execute("SELECT updated,n_rows,length(blob) AS size FROM frames WHERE name=?", (name,)).fetchone()
        if meta is None:
            raise ValueError("Frame not found; use list_frames")
        if meta["size"] > 32 * 1024 * 1024:
            raise ValueError("Frame exceeds the 32 MiB MCP read limit; inspect it through the dashboard")
        blob = con.execute("SELECT blob FROM frames WHERE name=?", (name,)).fetchone()[0]
    import pandas as pd
    frame = pd.read_parquet(io.BytesIO(blob))
    selected = frame.iloc[offset:offset + limit].reset_index()
    return {"name": name, "updated": meta["updated"], "total_rows": len(frame), "offset": offset,
            "rows": json.loads(selected.to_json(orient="records", date_format="iso")),
            "next_offset": offset + limit if len(frame) > offset + limit else None}


def read_drawdown(study: str | None = None, period_label: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    """List saved drawdown studies, or read ranked rows for one study and optional period."""
    with connection() as con:
        if study is None:
            return page(con, "SELECT * FROM drawdown_summaries ORDER BY created DESC", limit=limit, offset=offset)
        result = page(con, "SELECT * FROM drawdown_results WHERE study=? AND (? IS NULL OR period_label=?) ORDER BY period_label,rank,ticker",
                      [study, period_label, period_label], limit, offset)
        for row in result["rows"]:
            row["payload"] = json.loads(row["payload"]) if row["payload"] else None
        return result


def read_runs(limit: int = 30, offset: int = 0) -> dict:
    """Read update/study audit records. Daily processes may exit successfully while individual studies fail; check these outcomes."""
    with connection() as con:
        return page(con, "SELECT * FROM runs ORDER BY run_id DESC", limit=limit, offset=offset)
