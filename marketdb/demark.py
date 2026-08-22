"""DeMark TD Setup 9 / Countdown 13 scanner over the price store.

Port of stocks/legacy/demark_scan.py: identical (simplified) signal rules, no
downloads, results stored in demark_signals / demark_reports.

    python -m marketdb.demark [--universe us_total_market] [--min-cap 1e9] [--max-cap 5e9] [--end YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import db, prices as P, results as R, universe as U

DAYS_HISTORY = 200
DAYS_HISTORY_WEEKLY = 500
MIN_CAP_FLOOR = 1_000_000_000


def calc_td_setup(close: pd.Series) -> pd.Series:
    n = len(close)
    setup = np.zeros(n, dtype=int)
    c = close.to_numpy()
    buy = sell = 0
    for i in range(4, n):
        if c[i] < c[i - 4]:
            buy += 1; sell = 0
        elif c[i] > c[i - 4]:
            sell += 1; buy = 0
        else:
            buy = sell = 0
        setup[i] = buy if buy > 0 else -sell
    return pd.Series(setup, index=close.index)


def calc_td_countdown(close: pd.Series, setup: pd.Series) -> pd.Series:
    n = len(close)
    cd = np.zeros(n, dtype=int)
    c = close.to_numpy(); s = setup.to_numpy()
    buy = sell = 0
    in_buy = in_sell = False
    for i in range(2, n):
        if s[i] == 9:
            in_buy, buy = True, 0
        if s[i] == -9:
            in_sell, sell = True, 0
        if s[i] == 9 and in_sell:
            in_sell, sell = False, 0
        if s[i] == -9 and in_buy:
            in_buy, buy = False, 0
        if in_buy and c[i] < c[i - 2]:
            buy += 1
            if buy >= 13:
                cd[i] = 13; in_buy, buy = False, 0
            else:
                cd[i] = buy
        if in_sell and c[i] > c[i - 2]:
            sell += 1
            if sell >= 13:
                cd[i] = -13; in_sell, sell = False, 0
            else:
                cd[i] = -sell
    return pd.Series(cd, index=close.index)


def check_signals(close: pd.Series) -> dict | None:
    if len(close) < 50:
        return None
    setup = calc_td_setup(close)
    cd = calc_td_countdown(close, setup)
    ls, lc = int(setup.iloc[-1]), int(cd.iloc[-1])
    return {"setup9_buy": ls == 9, "setup9_sell": ls == -9, "countdown13_buy": lc == 13,
            "countdown13_sell": lc == -13, "setup_val": ls, "countdown_val": lc}


def run_scan(con: sqlite3.Connection | None = None, universe_key: str = "us_total_market",
             market_cap_min: float = 0, market_cap_max: float | None = None, end_date: str | None = None,
             log=print):
    """-> (df, report) and persists both. Universe filtered to >= $1B like the legacy scanner."""
    if con is None:
        with db.session() as c:
            return run_scan(c, universe_key, market_cap_min, market_cap_max, end_date, log)
    end_date = end_date or db.today_str()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    start_d = (end_dt - timedelta(days=DAYS_HISTORY)).strftime("%Y-%m-%d")
    start_w = (end_dt - timedelta(days=DAYS_HISTORY_WEEKLY)).strftime("%Y-%m-%d")

    mem = U.members(universe_key, con)
    mem = mem[mem["market_cap"].fillna(0) >= max(MIN_CAP_FLOOR, market_cap_min or 0)]
    if market_cap_max:
        mem = mem[mem["market_cap"].fillna(0) <= market_cap_max]
    tickers = mem["ticker"].tolist()
    log(f"DeMark: scanning {len(tickers)} tickers ({universe_key}, >= $1B)")
    daily = P.get_prices(tickers, start_d, end_date, con)
    weekly_src = P.get_prices(tickers, start_w, end_date, con)
    weekly = weekly_src.resample("W-FRI").last().dropna(how="all")
    info = mem.set_index("ticker")
    rows = []
    for t in tickers:
        if t not in daily.columns:
            continue
        dc = daily[t].dropna()
        wc = weekly[t].dropna() if t in weekly.columns else pd.Series(dtype=float)
        ds = check_signals(dc) if len(dc) >= 50 else None
        ws = check_signals(wc) if len(wc) >= 15 else None
        if ds is None and ws is None:
            continue
        mc = info.at[t, "market_cap"]
        row = {"ticker": t, "name": info.at[t, "name"], "sector": info.at[t, "sector"],
               "cap_band": info.at[t, "cap_band"], "market_cap": mc,
               "market_cap_b": round(mc / 1e9, 2) if pd.notna(mc) and mc else None,
               "close": round(float(dc.iloc[-1]), 4) if len(dc) else None}
        for pfx, sig in (("d", ds), ("w", ws)):
            if sig:
                row.update({f"{pfx}_setup": sig["setup_val"], f"{pfx}_countdown": sig["countdown_val"],
                            f"{pfx}_setup9_buy": sig["setup9_buy"], f"{pfx}_setup9_sell": sig["setup9_sell"],
                            f"{pfx}_cd13_buy": sig["countdown13_buy"], f"{pfx}_cd13_sell": sig["countdown13_sell"]})
            else:
                row.update({f"{pfx}_setup": 0, f"{pfx}_countdown": 0, f"{pfx}_setup9_buy": False,
                            f"{pfx}_setup9_sell": False, f"{pfx}_cd13_buy": False, f"{pfx}_cd13_sell": False})
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        log("DeMark: no results")
        return None, None
    for c in [c for c in df.columns if c.endswith(("_buy", "_sell"))]:
        df[c] = df[c].astype(int)

    def tl(mask):
        return ",".join(sorted(df[mask.astype(bool)]["ticker"].tolist()))

    report = (f"{'═' * 70}\n  DEMARK SIGNAL REPORT — {end_dt.strftime('%d %b %Y')}\n"
              f"  Universe: {len(df)} stocks scanned\n{'═' * 70}\n\n"
              f"DM9 Top Daily:\n{tl(df['d_setup9_sell'])}\n\nDM9 Bottom Daily:\n{tl(df['d_setup9_buy'])}\n\n"
              f"DM9 Top Weekly:\n{tl(df['w_setup9_sell'])}\n\nDM9 Bottom Weekly:\n{tl(df['w_setup9_buy'])}\n\n"
              f"DM13 Top Daily:\n{tl(df['d_cd13_sell'])}\n\nDM13 Bottom Daily:\n{tl(df['d_cd13_buy'])}\n\n"
              f"DM13 Top Weekly:\n{tl(df['w_cd13_sell'])}\n\nDM13 Bottom Weekly:\n{tl(df['w_cd13_buy'])}\n\n{'═' * 70}\n")
    run_id = db.start_run("demark", universe_key, con, n_expected=len(tickers))
    R.save_demark(df, report, con, run_date=end_date)
    db.finish_run(run_id, "ok", con, n_fetched=len(df))
    log(report)
    return df, report


def main(argv=None):
    db.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--universe", default="us_total_market", choices=U.universe_keys())
    ap.add_argument("--min-cap", type=float, default=0)
    ap.add_argument("--max-cap", type=float, default=None)
    ap.add_argument("--end", default=None)
    a = ap.parse_args(argv)
    run_scan(None, a.universe, a.min_cap, a.max_cap, a.end)


if __name__ == "__main__":
    main()
