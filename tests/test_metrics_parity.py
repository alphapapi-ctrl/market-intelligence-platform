"""Parity check: marketdb.studies vs the legacy per-universe scripts on identical input.

    .venv/Scripts/python.exe tests/test_metrics_parity.py [universe]

Loads the price matrices from the DB, feeds them to the legacy calculate_screener() /
calculate_rs() (imported from stocks/legacy) and to marketdb.studies, and reports any
per-ticker differences. Rank order is compared via score_final, not position.
"""
import sys, os, importlib
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from marketdb import db, universe as U, prices as P, studies as S

# The legacy scripts have no RSI/OBV divergence term (added 2026-08-23); zero those bonuses
# so score_final still compares like-for-like.
_orig_load = S.load_rank_settings
S.load_rank_settings = lambda key: {**_orig_load(key), **{k: 0.0 for k in S.DIVERGENCE_DEFAULTS}}

LEGACY_DIR = BASE / "stocks" / "legacy" if (BASE / "stocks" / "legacy").exists() else BASE / "stocks"


def load_legacy(modname):
    sys.path.insert(0, str(LEGACY_DIR))
    cwd = os.getcwd(); os.chdir(LEGACY_DIR)
    try:
        return importlib.import_module(modname)
    finally:
        os.chdir(cwd)


def compare(a, b, label, cols):
    a = a.reset_index().set_index("ticker"); b = b.reset_index().set_index("ticker")
    common = a.index.intersection(b.index)
    print(f"{label}: legacy {len(a)} rows, new {len(b)} rows, common {len(common)}; "
          f"only-legacy {sorted(set(a.index)-set(b.index))[:5]} only-new {sorted(set(b.index)-set(a.index))[:5]}")
    bad = 0
    for c in cols:
        if c not in a.columns or c not in b.columns: continue
        x, y = a.loc[common, c], b.loc[common, c]
        if x.dtype == object or y.dtype == object:
            diff = (x.fillna("∅").astype(str) != y.fillna("∅").astype(str))
        else:
            diff = ~np.isclose(x.astype(float).fillna(-9e9), y.astype(float).fillna(-9e9), atol=1e-6)
        n = int(diff.sum())
        if n:
            bad += n
            ex = common[diff][:3]
            print(f"   {c}: {n} diffs e.g. {[(t, x[t], y[t]) for t in ex]}")
    print(f"   -> {'OK' if bad == 0 else f'{bad} cell differences'}")
    return bad


def run(universe_key):
    with db.session() as con:
        mem = U.members(universe_key, con)
        w = S._windows()
        t = mem["ticker"].tolist()
        cfg = U.universe_cfg(universe_key)
        bench = sorted(set(mem["benchmark"].dropna()))
        p12 = P.get_prices(t + bench, w["start_12m"], w["end"], con)
        p24 = P.get_prices(t + bench, w["start_24m"], w["end"], con)
        vol = P.get_volumes(t + bench, w["start_12m"], w["end"], con)
        new_s = S.screener(universe_key, con); new_b = S.benchmark(universe_key, con)
    wl = mem.rename(columns={})[["ticker","name","sector","industry","cap_band","benchmark","commodity","type"]].copy()
    if cfg["peer_key"] == "sector":
        leg_s = load_legacy({"au_total_market":"au_total_market_screener","us_total_market":"us_total_market_screener",
                             "nasdaq100":"nasdaq100_screener"}[universe_key])
        leg_b = load_legacy({"au_total_market":"au_total_market_benchmark","us_total_market":"us_total_market_benchmark",
                             "nasdaq100":"us_nasdaq_benchmark"}[universe_key])
        ls = leg_s.calculate_screener(p12[t], p24[t], vol[t], wl)
        wlb = wl.copy(); wlb.loc[len(wlb)] = [bench[0], bench[0], "index", "index", "small", "benchmark", None, None]
        if hasattr(leg_b, "calculate_rs"):
            lb = leg_b.calculate_rs(p12[t+bench], p24[t+bench], vol[t+bench], bench[0], wlb)
        elif universe_key == "nasdaq100":
            lb = leg_b.calculate_benchmark(p12[t+bench], p24[t+bench], vol[t+bench], wlb, bench[0])
        else:
            lb = leg_b.calculate_benchmark(p12[t+bench], p24[t+bench], vol[t+bench], wlb)
        lb = lb[lb["ticker"] != bench[0]]
    else:
        leg_s = load_legacy({"all_major_commodities":"all_major_commodities_screener","uranium":"uranium_screener",
                             "au_gold_miners":"au_gold_miners_screener"}[universe_key])
        leg_b = load_legacy({"all_major_commodities":"all_major_commodities_benchmark","uranium":"uranium_benchmark",
                             "au_gold_miners":"au_gold_miners_benchmark"}[universe_key])
        wl["sector"] = wl["commodity"].str.title()
        ls = leg_s.calculate_screener(p12[t], p24[t], vol[t], wl)
        wlb = wl.copy()
        if universe_key == "all_major_commodities":
            bmap = U.config()["commodity_benchmarks"]
            for comm, bt in bmap.items():
                wlb.loc[len(wlb)] = [bt, bt, comm.title(), "", "ETF", "benchmark", comm, "ETF"]
        else:
            wlb.loc[len(wlb)] = [bench[0], bench[0], "index", "", "small", "benchmark", None, None]
        lb = leg_b.calculate_benchmark(p12[t+bench], p24[t+bench], vol[t+bench], wlb)
        lb = lb[~lb["ticker"].isin(bench)] if lb is not None else None
    cols = ["close","peer_rs_score","rs_ratio","rs_5","rs_21","rs_63","rs_trend","ret_6m","ret_12m","ret_24m","max_dd",
            "persist_frac","vol_63","rel_vol","vol_label","acc_watch","sma20","sma50","sma200","pass_trend","mqs",
            "regime_label","score_final"]
    bad = compare(ls, new_s, f"{universe_key} screener", cols)
    if lb is not None:
        bad += compare(lb, new_b, f"{universe_key} benchmark", cols)
    return bad


if __name__ == "__main__":
    keys = sys.argv[1:] or ["au_total_market"]
    total = sum(run(k) for k in keys)
    sys.exit(1 if total else 0)
