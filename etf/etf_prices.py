"""Price access for the ETF module — marketdb store first, yfinance fallback.

    from etf_prices import history, adj_close
    hist = history('JEPI', years=3)      # DataFrame[Close, Dividends], naive DatetimeIndex
    s    = adj_close('SPY', years=1)     # Series of adjusted close

Every ticker asked for is registered in the store under role 'etf_income' so the
daily marketdb run keeps it current; anything missing or stale is fetched once here.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

try:
    from marketdb import db as _db, fetch as _fetch, prices as _prices
    STORE = True
except Exception as _e:  # pragma: no cover — marketdb missing -> yfinance only
    print(f"marketdb unavailable ({_e}); ETF module will use yfinance directly")
    STORE = False

_STALE_DAYS = 5


def _ensure_fresh(tickers: list[str]) -> None:
    """Register unknown tickers and pull anything whose last bar is older than a week."""
    if not STORE:
        return
    with _db.session() as con:
        allowed = _fetch.ensure_securities(tickers, con, role="etf_income")
        cutoff = (datetime.today() - timedelta(days=_STALE_DAYS)).strftime("%Y-%m-%d")
        fl = _db.read_df("SELECT ticker, last_date FROM fetch_log", con=con)
        last = dict(zip(fl["ticker"], fl["last_date"]))
        need = [t for t in allowed if not last.get(t) or str(last[t]) < cutoff]
        if need:
            _fetch.update_prices(need, con, log=lambda m: None)


def _start(years: float) -> str:
    return (datetime.today() - timedelta(days=int(365 * years) + 7)).strftime("%Y-%m-%d")


def history(ticker: str, years: float = 1) -> pd.DataFrame | None:
    """Unadjusted Close + Dividends (the scorer's inputs)."""
    if STORE:
        try:
            _ensure_fresh([ticker])
            long = _prices.get_long([ticker], _start(years), None, ("close", "dividend"))
            if len(long):
                df = long.set_index(pd.to_datetime(long["date"]))[["close", "dividend"]]
                df.index.name = "Date"
                df = df.rename(columns={"close": "Close", "dividend": "Dividends"})
                df["Dividends"] = df["Dividends"].fillna(0.0)
                return df.dropna(subset=["Close"])
        except Exception as e:
            print(f"  {ticker}: store read error — {e}; falling back to yfinance")
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period=f"{max(1, int(round(years)))}y", auto_adjust=False)
    if hist is None or hist.empty:
        return None
    hist.index = hist.index.tz_localize(None)
    return hist[["Close", "Dividends"]].dropna(subset=["Close"])


def adj_close(ticker: str, years: float = 1) -> pd.Series | None:
    """Adjusted close (what auto_adjust=True used to give)."""
    if STORE:
        try:
            _ensure_fresh([ticker])
            m = _prices.get_prices([ticker], _start(years), None)
            s = m[ticker].dropna() if ticker in m.columns else pd.Series(dtype=float)
            if len(s):
                s.name = "Close"
                return s
        except Exception as e:
            print(f"  {ticker}: store read error — {e}; falling back to yfinance")
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period=f"{max(1, int(round(years)))}y", auto_adjust=True)
    if hist is None or hist.empty:
        return None
    hist.index = hist.index.tz_localize(None)
    return hist["Close"].dropna()


def prefetch(tickers: list[str]) -> None:
    """One store refresh for a whole list (call before a loop of history()/adj_close())."""
    _ensure_fresh(sorted(set(tickers)))
