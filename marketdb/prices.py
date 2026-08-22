"""Read price matrices out of the DB in the wide shape the studies expect
(index = DatetimeIndex, columns = tickers) — a drop-in for the old
`fetch_prices()` / `fetch_volumes()` without the network.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from . import db

FIELDS = ("open", "high", "low", "close", "adj_close", "volume", "dividend", "split")


def _ticker_temp(con: sqlite3.Connection, tickers: list[str]) -> None:
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _q (ticker TEXT PRIMARY KEY)")
    con.execute("DELETE FROM _q")
    con.executemany("INSERT OR IGNORE INTO _q VALUES (?)", [(t,) for t in tickers])


def get_long(tickers: list[str], start: str | None, end: str | None, fields=("adj_close", "volume"),
             con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Long frame: ticker, date, <fields...>."""
    if con is None:
        with db.session() as c:
            return get_long(tickers, start, end, fields, c)
    tickers = sorted(set(tickers))
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", *fields])
    _ticker_temp(con, tickers)
    cols = ", ".join(f"p.{f}" for f in fields)
    where, params = [], []
    if start:
        where.append("p.date >= ?"); params.append(str(start)[:10])
    if end:
        where.append("p.date <= ?"); params.append(str(end)[:10])
    sql = f"SELECT p.ticker, p.date, {cols} FROM prices p JOIN _q ON _q.ticker = p.ticker"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.date"
    return db.read_df(sql, params, con=con)


def get_matrix(tickers: list[str], start: str | None = None, end: str | None = None,
               field: str = "adj_close", con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Wide frame of one field. Missing (ticker, date) -> NaN, like yf.download."""
    long = get_long(tickers, start, end, (field,), con)
    if long.empty:
        return pd.DataFrame(columns=tickers, index=pd.DatetimeIndex([], name="Date"))
    wide = long.pivot(index="date", columns="ticker", values=field)
    wide.index = pd.to_datetime(wide.index)
    wide.index.name = "Date"
    wide.columns.name = None
    # keep requested column order; add all-NaN columns for tickers with no data
    wide = wide.reindex(columns=tickers)
    return wide.sort_index()


def get_prices(tickers, start=None, end=None, con=None) -> pd.DataFrame:
    """Adjusted close matrix — identical meaning to the old auto_adjust=True 'Close'."""
    return get_matrix(tickers, start, end, "adj_close", con)


def get_volumes(tickers, start=None, end=None, con=None) -> pd.DataFrame:
    return get_matrix(tickers, start, end, "volume", con)


def get_ohlc(ticker: str, start=None, end=None, con=None) -> pd.DataFrame:
    """Single-ticker OHLCV (unadjusted) with Date index — for charts."""
    long = get_long([ticker], start, end, ("open", "high", "low", "close", "adj_close", "volume"), con)
    if long.empty:
        return pd.DataFrame()
    out = long.drop(columns=["ticker"]).set_index(pd.to_datetime(long["date"])).drop(columns=["date"])
    out.index.name = "Date"
    return out.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close",
                               "adj_close": "Adj Close", "volume": "Volume"})


def last_date(con: sqlite3.Connection | None = None, tickers: list[str] | None = None) -> str | None:
    if con is None:
        with db.session() as c:
            return last_date(c, tickers)
    if tickers:
        _ticker_temp(con, tickers)
        return db.scalar("SELECT MAX(p.date) FROM prices p JOIN _q ON _q.ticker=p.ticker", con=con)
    return db.scalar("SELECT MAX(date) FROM prices", con=con)


def coverage(tickers: list[str], start: str, end: str | None = None,
             con: sqlite3.Connection | None = None) -> tuple[int, int]:
    """(tickers with at least one close in the window, tickers requested)."""
    if con is None:
        with db.session() as c:
            return coverage(tickers, start, end, c)
    _ticker_temp(con, sorted(set(tickers)))
    params = [start]
    sql = "SELECT COUNT(DISTINCT p.ticker) FROM prices p JOIN _q ON _q.ticker=p.ticker WHERE p.date >= ?"
    if end:
        sql += " AND p.date <= ?"; params.append(end)
    n = db.scalar(sql, params, con=con) or 0
    return int(n), len(set(tickers))
