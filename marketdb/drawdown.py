"""Drawdown analysis: period-based performance vs benchmark and peers.

Port of stocks/legacy/drawdown_analysis.py onto the price store. The maths is
unchanged; prices come from the DB and studies are stored in drawdown_results /
drawdown_summaries instead of per-study CSV folders.

    python -m marketdb.drawdown --universe au_total_market --period "gold_peak:2025-10-15" --period "low:2026-03-30"
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import db, metrics as M, prices as P, universe as U

# Sector -> benchmark index/ETF. Both the legacy (FactSet/GICS) and Yahoo sector names.
AU_SECTOR_BENCH = {
    "Energy minerals": "^AXEJ", "Energy": "^AXEJ",
    "Finance": "^AXFJ", "Financial Services": "^AXFJ", "Financials": "^AXFJ",
    "Technology services": "^AXIJ", "Electronic technology": "^AXIJ", "Technology": "^AXIJ",
    "Communications": "^AXTJ", "Communication Services": "^AXTJ",
    "Utilities": "^AXUJ",
    "Non-energy minerals": "^AXMJ", "Process industries": "^AXMJ", "Basic Materials": "^AXMJ",
    "Consumer services": "^AXDJ", "Consumer non-durables": "^AXDJ", "Consumer durables": "^AXDJ",
    "Retail trade": "^AXDJ", "Consumer Cyclical": "^AXDJ",
    "Consumer Defensive": "^AXSJ",
    "Health technology": "^AXHJ", "Health services": "^AXHJ", "Healthcare": "^AXHJ",
    "Industrial services": "^AXNJ", "Producer manufacturing": "^AXNJ", "Commercial services": "^AXNJ",
    "Distribution services": "^AXNJ", "Transportation": "^AXNJ", "Industrials": "^AXNJ",
    "Real Estate": "^AXPJ", "Miscellaneous": "^AXJO",
}
US_SECTOR_BENCH = {
    "Energy": "XLE", "Information Technology": "XLK", "Technology": "XLK",
    "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY",
    "Financials": "XLF", "Financial Services": "XLF", "Industrials": "XLI",
    "Materials": "XLB", "Basic Materials": "XLB", "Utilities": "XLU",
    "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
    "Health Care": "XLV", "Healthcare": "XLV",
    "Communication Services": "XLC", "Communication": "XLC", "Real Estate": "XLRE",
}


def sector_benchmark(filter_col: str | None, value: str | None, region: str | None = None) -> str | None:
    if not filter_col or not value:
        return None
    if filter_col == "commodity":
        return U.config()["commodity_benchmarks"].get(str(value).lower())
    if region == "AU":
        return AU_SECTOR_BENCH.get(value)
    if region == "US":
        return US_SECTOR_BENCH.get(value)
    return AU_SECTOR_BENCH.get(value) or US_SECTOR_BENCH.get(value)


# ── Core calculation (legacy semantics) ───────────────────────────────────────
def calculate_period(prices: pd.DataFrame, volumes: pd.DataFrame, members: pd.DataFrame,
                     start_date: str, label: str, bench_ticker: str, weights: dict | None = None):
    w = weights or {}
    w_rs, w_peer, w_dd = w.get("rs_vs_bench", 1.0), w.get("peer_rs_score", 0.5), w.get("dd_vs_bench", 0.5)
    info = members.set_index("ticker")
    peer_col = "commodity" if info["commodity"].notna().any() else "sector"
    peer_map = info[peer_col].fillna("Unknown").to_dict()

    pp = prices[prices.index >= pd.Timestamp(start_date)]
    if len(pp) < 5:
        return None
    trading_days = len(pp)
    if bench_ticker not in pp.columns or pp[bench_ticker].dropna().shape[0] < 2:
        return None
    bp = pp[bench_ticker].dropna()
    bench_ret = round((bp.iloc[-1] / bp.iloc[0] - 1) * 100, 2)
    bench_dd = round(float(((bp - bp.cummax()) / bp.cummax()).min() * 100), 2)

    tickers = [t for t in pp.columns if t in info.index and t != bench_ticker and len(pp[t].dropna()) >= 2]
    period_returns = {}
    for t in tickers:
        tp = pp[t].dropna()
        if tp.iloc[0] != 0:
            period_returns[t] = (tp.iloc[-1] / tp.iloc[0] - 1) * 100
    peer_groups: dict[str, list[str]] = {}
    for t in tickers:
        peer_groups.setdefault(peer_map.get(t, "Unknown"), []).append(t)

    rows = []
    for t in tickers:
        tp = pp[t].dropna()
        if tp.iloc[0] == 0:
            continue
        ret_period = round((tp.iloc[-1] / tp.iloc[0] - 1) * 100, 2)
        rs_vs_bench = round(ret_period - bench_ret, 2)
        dd_period = round(float(((tp - tp.cummax()) / tp.cummax()).min() * 100), 2)
        dd_vs_bench = round(dd_period - bench_dd, 2)
        current_dd = round((tp.iloc[-1] / float(tp.max()) - 1) * 100, 2)
        n = len(tp)
        rs_5 = rs_21 = None
        if n >= 5:
            b5 = (bp.iloc[-1] / bp.iloc[-5] - 1) * 100 if len(bp) >= 5 else 0
            rs_5 = round((tp.iloc[-1] / tp.iloc[-5] - 1) * 100 - b5, 2)
        if n >= 21:
            b21 = (bp.iloc[-1] / bp.iloc[-21] - 1) * 100 if len(bp) >= 21 else 0
            rs_21 = round((tp.iloc[-1] / tp.iloc[-21] - 1) * 100 - b21, 2)
        rs_trend = M.rs_trend_for([rs_vs_bench, rs_21, rs_5])
        group = peer_map.get(t, "Unknown")
        peers = [x for x in peer_groups.get(group, []) if x != t and x in period_returns]
        peer_rs = round(sum(1 for x in peers if ret_period > period_returns[x]) / len(peers) * 100, 2) if peers else 50.0
        rel_vol = None
        if t in volumes.columns:
            tv = volumes[t].dropna()
            if len(tv):
                avg = tv.tail(63).mean()
                rel_vol = round(tv.iloc[-1] / avg, 4) if avg and avg > 0 else None
        vol_label = M.vol_label_for(rel_vol)
        full = prices[t].dropna() if t in prices.columns else tp
        sma200 = round(full.tail(200).mean(), 4) if len(full) >= 200 else None
        sma50 = round(full.tail(50).mean(), 4) if len(full) >= 50 else None
        sma20 = round(full.tail(20).mean(), 4) if len(full) >= 20 else None
        price = float(tp.iloc[-1])
        pass_trend = 1 if sma200 is not None and price > sma200 else 0
        cap_band = info.at[t, "cap_band"]
        acc_watch = M.acc_watch_for(price, sma20, sma50, sma200, cap_band) if (sma20 and sma50 and sma200) else "-"
        score = round(rs_vs_bench * w_rs + peer_rs * w_peer + dd_vs_bench * -w_dd, 4)
        rows.append({"ticker": t, "name": info.at[t, "name"], peer_col: group, "cap_band": cap_band,
                     "close": round(price, 4), "ret_period": ret_period, "bench_ret": bench_ret,
                     "rs_vs_bench": rs_vs_bench, "rs_5d": rs_5, "rs_21d": rs_21, "rs_trend": rs_trend,
                     "max_dd_period": dd_period, "bench_dd": bench_dd, "dd_vs_bench": dd_vs_bench,
                     "current_dd": current_dd, "peer_rs_score": peer_rs, "vol_label": vol_label,
                     "rel_vol": rel_vol, "acc_watch": acc_watch, "pass_trend": pass_trend, "score": score,
                     "period_label": label, "period_start": start_date, "trading_days": trading_days})
    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "rank"
    return df, bench_ret, bench_dd


# ── Orchestration ─────────────────────────────────────────────────────────────
def run_study(universe_key: str, periods: list[dict], con: sqlite3.Connection, *, study_name: str | None = None,
              filter_col: str | None = None, filter_val: str | None = None, weights: dict | None = None,
              bench_override: str | None = None, log=print) -> list[tuple]:
    """periods: [{'label': 'gold_peak', 'date': 'YYYY-MM-DD'}, ...]. Returns [(df, bench_ret, bench_dd, label, date)]."""
    cfg = U.universe_cfg(universe_key)
    mem = U.members(universe_key, con)
    if filter_col and filter_val:
        mem = mem[mem[filter_col] == filter_val]
        log(f"  filtered to {filter_col}={filter_val}: {len(mem)} tickers")
    bench = bench_override or (cfg.get("benchmark") if cfg.get("benchmark") != "per_commodity" else None)
    if bench is None:
        bench = mem["benchmark"].dropna().mode().iloc[0] if mem["benchmark"].notna().any() else None
    if bench is None:
        raise ValueError("no benchmark resolved for this study")
    earliest = min(p["date"] for p in periods)
    start = (min(pd.Timestamp(earliest), pd.Timestamp.today() - timedelta(days=400)) - timedelta(days=300)).strftime("%Y-%m-%d")
    tickers = mem["ticker"].tolist() + [bench]
    prices = P.get_prices(tickers, start, None, con)
    volumes = P.get_volumes(tickers, start, None, con)
    if bench not in prices.columns or prices[bench].dropna().empty:
        # benchmark not in the store yet (e.g. a sector index never used before) -> register + fetch once
        from . import fetch
        log(f"  benchmark {bench} not in price store — fetching")
        fetch.ensure_securities([bench], con, role="benchmark")
        fetch.update_prices([bench], con, log=log)
        bp = P.get_prices([bench], start, None, con)
        if bp.empty or bp[bench].dropna().empty:
            raise ValueError(f"benchmark {bench} has no price data on Yahoo")
        prices[bench] = bp[bench]
        volumes[bench] = np.nan
    out = []
    for p in periods:
        r = calculate_period(prices, volumes, mem, p["date"], p["label"], bench, weights)
        if r is None:
            log(f"  insufficient data for {p['label']} from {p['date']}")
            continue
        out.append((r[0], r[1], r[2], p["label"], p["date"]))
    study = study_name or universe_key
    save_study(study, universe_key, out, con)
    return out


def summary_text(study: str, periods: list[tuple]) -> str:
    lines = ["═" * 80, f"  DRAWDOWN ANALYSIS — {study.upper()}",
             f"  Run: {datetime.today().strftime('%d %b %Y %H:%M')}", "═" * 80]
    for df, bench_ret, bench_dd, label, start in periods:
        lines += ["", f"  {'─' * 76}",
                  f"  PERIOD: {label.upper()}  |  From: {start}  |  {df['trading_days'].iloc[0]} trading days",
                  f"  Benchmark return: {bench_ret:+.2f}%   Benchmark max DD: {bench_dd:.2f}%", f"  {'─' * 76}",
                  f"  {'Rank':<5} {'Ticker':<10} {'Name':<30} {'Ret%':>7} {'vsBench':>8} {'MaxDD':>7} {'DDvBench':>9} {'PeerRS':>7} {'RS Trend':<12} {'AccW':<6}",
                  f"  {'─' * 76}"]
        for title, part in (("", df.head(20)), ("  BOTTOM 10 — Weakest vs benchmark:", df.tail(10))):
            if title:
                lines += ["", title, f"  {'─' * 76}"]
            for rank, row in part.iterrows():
                lines.append(f"  {rank:<5} {row['ticker']:<10} {str(row['name'])[:29]:<30} "
                             f"{row['ret_period']:>+7.1f}% {row['rs_vs_bench']:>+7.1f}% "
                             f"{row['max_dd_period']:>6.1f}% {row['dd_vs_bench']:>+8.1f}% "
                             f"{row['peer_rs_score']:>6.1f}% {row['rs_trend']:<12} {row['acc_watch']:<6}")
    if len(periods) > 1:
        lines += ["", "═" * 80, "  CROSS PERIOD RANK COMPARISON", "═" * 80]
        merged = cross_period(periods)
        header = f"  {'Ticker':<10} {'Name':<25}" + "".join(f" {l[:8]:>8}" for _, _, _, l, _ in periods) + f" {'Trend':<10}"
        lines += [header, "─" * 80]
        for _, row in merged.head(20).iterrows():
            line = f"  {row['ticker']:<10} {str(row['name'])[:24]:<25}"
            for _, _, _, l, _ in periods:
                v = row.get(f"rank_{l}")
                line += f" {str(int(v)) if pd.notna(v) else 'n/a':>8}"
            lines.append(line + f" {row['rank_trend']:<10}")
    lines += ["", "═" * 80]
    return "\n".join(lines)


def cross_period(periods: list[tuple]) -> pd.DataFrame:
    dfs = {}
    for df, _, _, label, _ in periods:
        dfs[label] = df.reset_index()[["rank", "ticker", "name", "score"]].rename(
            columns={"rank": f"rank_{label}", "score": f"score_{label}"})
    first = periods[0][3]
    merged = dfs[first]
    for _, _, _, label, _ in periods[1:]:
        merged = merged.merge(dfs[label][["ticker", f"rank_{label}", f"score_{label}"]], on="ticker", how="outer")
    rank_cols = [f"rank_{p[3]}" for p in periods]

    def trend(row):
        pairs = [(row[rank_cols[i]], row[rank_cols[i + 1]]) for i in range(len(rank_cols) - 1)]
        if all(pd.notna(a) and pd.notna(b) and a > b for a, b in pairs):
            return "IMPROVING"
        if all(pd.notna(a) and pd.notna(b) and a < b for a, b in pairs):
            return "DECLINING"
        return "MIXED"
    merged["rank_trend"] = merged.apply(trend, axis=1)
    return merged.sort_values(f"rank_{periods[-1][3]}")


# ── Persistence ───────────────────────────────────────────────────────────────
def save_study(study: str, universe_key: str, periods: list[tuple], con: sqlite3.Connection) -> None:
    now = db.now_iso()
    con.execute("DELETE FROM drawdown_results WHERE study=?", (study,))
    for df, bench_ret, bench_dd, label, start in periods:
        recs = []
        for rank, row in df.iterrows():
            payload = {k: (None if (isinstance(v, float) and np.isnan(v)) else (v.item() if isinstance(v, np.generic) else v))
                       for k, v in row.items()}
            recs.append((study, label, start, row["ticker"], int(rank), json.dumps(payload), now))
        con.executemany("INSERT OR REPLACE INTO drawdown_results VALUES (?,?,?,?,?,?,?)", recs)
    con.execute("INSERT OR REPLACE INTO drawdown_summaries VALUES (?,?,?,?,?)",
                (study, universe_key, json.dumps([{"label": l, "start": s, "bench_ret": br, "bench_dd": bd}
                                                  for _, br, bd, l, s in periods]),
                 summary_text(study, periods), now))
    con.commit()


def list_studies(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    c = con or db.connect()
    try:
        return db.read_df("SELECT study, universe, periods, created FROM drawdown_summaries ORDER BY created DESC", con=c)
    finally:
        if con is None:
            c.close()


def load_study(study: str, con: sqlite3.Connection | None = None) -> list[tuple]:
    """-> [(df indexed by rank, bench_ret, bench_dd, label, start)] in period order."""
    c = con or db.connect()
    try:
        meta = db.read_df("SELECT periods, summary FROM drawdown_summaries WHERE study=?", (study,), con=c)
        rows = db.read_df("SELECT period_label, rank, payload FROM drawdown_results WHERE study=? ORDER BY period_label, rank",
                          (study,), con=c)
    finally:
        if con is None:
            c.close()
    if meta.empty:
        return []
    out = []
    for p in json.loads(meta["periods"].iloc[0]):
        sub = rows[rows["period_label"] == p["label"]]
        if sub.empty:
            continue
        df = pd.DataFrame([json.loads(x) for x in sub["payload"]], index=sub["rank"].astype(int).values)
        df.index.name = "rank"
        out.append((df, p.get("bench_ret"), p.get("bench_dd"), p["label"], p["start"]))
    return out


def study_summary(study: str, con=None) -> str | None:
    return db.scalar("SELECT summary FROM drawdown_summaries WHERE study=?", (study,), con=con)


def study_zip(study: str, con=None) -> bytes:
    """Zip of per-period CSVs + summary txt (same files the old folder held)."""
    periods = load_study(study, con)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for df, _, _, label, start in periods:
            zf.writestr(f"{study}_{label}_{start.replace('-', '')}_drawdown.csv", df.to_csv())
        summ = study_summary(study, con)
        if summ:
            zf.writestr(f"{study}_drawdown_summary.txt", summ)
    buf.seek(0)
    return buf.getvalue()


def delete_study(study: str, con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM drawdown_results WHERE study=?", (study,))
    con.execute("DELETE FROM drawdown_summaries WHERE study=?", (study,))
    con.commit()


def main(argv=None):
    db.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--universe", required=True, choices=U.universe_keys())
    ap.add_argument("--period", action="append", required=True, help="label:YYYY-MM-DD (repeatable, up to 3)")
    ap.add_argument("--study", default=None)
    ap.add_argument("--filter", default=None, help="sector=<name> or commodity=<name>")
    args = ap.parse_args(argv)
    periods = [{"label": p.split(":", 1)[0], "date": p.split(":", 1)[1]} for p in args.period]
    fcol = fval = None
    if args.filter:
        fcol, fval = args.filter.split("=", 1)
    with db.session() as con:
        res = run_study(args.universe, periods, con, study_name=args.study, filter_col=fcol, filter_val=fval)
        print(summary_text(args.study or args.universe, res))


if __name__ == "__main__":
    main()
