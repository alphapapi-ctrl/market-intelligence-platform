"""Study calculators: screener, benchmark, breadth, RRG.

Each takes price matrices (from marketdb.prices) + the universe member frame
(from marketdb.universe) and returns DataFrames; marketdb.results persists them.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import db, metrics as M, prices as P, universe as U

RANK_SETTINGS = db.BASE_DIR / "rank_settings.json"

RESULT_COLS = ["ticker", "name", "sector", "industry", "commodity", "type", "cap_band", "close",
               "peer_rs_score", "rs_ratio", "rs_5", "rs_21", "rs_63", "rs_trend",
               "ret_6m", "ret_12m", "ret_24m", "max_dd", "persist_frac", "vol_63", "rel_vol",
               "vol_label", "acc_watch", "sma20", "sma50", "sma200", "pass_trend", "mqs",
               "rsi_14", "rsi_div", "obv_div", "regime_label", "score_final"]


# Divergence bonuses (added to the score before the volume multiplier, both modes).
# Regular RSI divergence and OBV divergence = +/-1.0 (same scale as the rs_trend bonus);
# hidden / confirming / flat-price signals = +/-0.5. Override per universe in rank_settings.json.
DIVERGENCE_DEFAULTS = {
    "rsi_div_bull": 1.0, "rsi_div_hid_bull": 0.5, "rsi_div_bear": -1.0, "rsi_div_hid_bear": -0.5,
    "obv_conv_up": 0.5, "obv_bull_div": 1.0, "obv_accum": 0.5,
    "obv_conv_down": -0.5, "obv_bear_div": -1.0, "obv_distrib": -0.5,
}
_RSI_KEY = {"BULL": "rsi_div_bull", "HID_BULL": "rsi_div_hid_bull", "BEAR": "rsi_div_bear", "HID_BEAR": "rsi_div_hid_bear"}
_OBV_KEY = {"CONV_UP": "obv_conv_up", "BULL_DIV": "obv_bull_div", "ACCUM": "obv_accum",
            "CONV_DOWN": "obv_conv_down", "BEAR_DIV": "obv_bear_div", "DISTRIB": "obv_distrib"}


def divergence_bonus(row, rs: dict) -> float:
    b = 0.0
    k = _RSI_KEY.get(row.get("rsi_div"))
    if k:
        b += float(rs.get(k, DIVERGENCE_DEFAULTS[k]))
    k = _OBV_KEY.get(row.get("obv_div"))
    if k:
        b += float(rs.get(k, DIVERGENCE_DEFAULTS[k]))
    return b


def load_rank_settings(key: str) -> dict:
    try:
        return json.loads(RANK_SETTINGS.read_text(encoding="utf-8")).get(key, {}) or {}
    except (OSError, ValueError):
        return {}


def _windows(end: str | None = None) -> dict:
    end_dt = pd.Timestamp(end) if end else pd.Timestamp(datetime.today().date())
    return {"end": end_dt.strftime("%Y-%m-%d"),
            "start_12m": (end_dt - timedelta(days=365)).strftime("%Y-%m-%d"),
            "start_24m": (end_dt - timedelta(days=730)).strftime("%Y-%m-%d"),
            "start_400": (end_dt - timedelta(days=400)).strftime("%Y-%m-%d")}


def _pct(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(x * 100, 2)


def _clean(r: pd.Series) -> dict:
    """Row -> dict with NaN normalised to None (the legacy code used None throughout)."""
    out = {}
    for k, v in r.items():
        if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)):
            out[k] = None
        elif isinstance(v, np.generic):
            out[k] = v.item()
        else:
            out[k] = v
    return out


# ── Scoring (shared by screener / benchmark) ──────────────────────────────────
def _score(row, rs: dict, mode: str) -> float | None:
    dd_weights = {"large": rs.get("dd_weight_large", 0.4), "mid": rs.get("dd_weight_mid", 0.3),
                  "small": rs.get("dd_weight_small", 0.2), "ETF": rs.get("dd_weight_etf", 0.3)}
    vol_mult = {"HIGH": rs.get("vol_high", 1.1), "MED": rs.get("vol_med", 1.0), "LOW": rs.get("vol_low", 0.9)}
    rs_trend_bonus = {"STRONG_UP": rs.get("rs_trend_strong_up", 1.0), "UP": rs.get("rs_trend_up", 0.5),
                      "FLAT": rs.get("rs_trend_flat", 0.0), "DOWN": rs.get("rs_trend_down", -0.5),
                      "STRONG_DOWN": rs.get("rs_trend_strong_down", -1.0)}
    dd_w = dd_weights.get(row["cap_band"], 0.2)
    base = ((row["ret_12m"] * rs.get("ret_12m_weight", 0.4)) +
            ((row["persist_frac"] or 0) * rs.get("persist_weight", 0.01)) +
            ((row["max_dd"] or 0) * -dd_w) +
            ((row["mqs"] * rs.get("mqs_weight", 0.2)) if row["mqs"] is not None else 0) +
            rs_trend_bonus[row["rs_trend"]])
    if mode == "screener":
        regime_bonus = {"LEADER": rs.get("regime_bonus_leader", 1.0), "CONTENDER": rs.get("regime_bonus_contender", 0.5),
                        "LAGGARD": rs.get("regime_bonus_laggard", 0.0), "WEAK": rs.get("regime_bonus_weak", -0.5)}
        base += (row["peer_rs_score"] * rs.get("peer_rs_weight", 0.02)) + regime_bonus[row["regime_label"]]
    else:
        base += (rs.get("trend_bonus", 1.0) if row["pass_trend"] == 1 else 0)
        base += (rs.get("lead_bonus", 1.0) if (row["rs_ratio"] or 0) > 1.0 else 0)
    base += divergence_bonus(row, rs)
    score = round(base * vol_mult[row["vol_label"]], 4)
    return None if not np.isfinite(score) else score


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("score_final", ascending=False, na_position="last").reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "rank"
    return df


def actionable_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Legacy actionable / high-conviction rules, stored as 0/1 flags."""
    lead = df["regime_label"].isin(["LEADER", "CONTENDER", "TREND+LEAD", "TREND_ONLY"])
    top  = df["regime_label"].isin(["LEADER", "TREND+LEAD"])
    act = ((df["acc_watch"] != "-") & df["cap_band"].isin(["large", "mid"]) &
           df["vol_label"].isin(["HIGH", "MED"]) & lead) | ((df["vol_label"] == "HIGH") & top)
    hc = (df["vol_label"] == "HIGH") & (df["acc_watch"] != "-") & (df["score_final"].fillna(-1) > 0)
    return df.assign(actionable=act.astype(int), high_conv=hc.astype(int))


# ── Screener ──────────────────────────────────────────────────────────────────
def screener(universe_key: str, con: sqlite3.Connection, end: str | None = None,
             members: pd.DataFrame | None = None) -> pd.DataFrame | None:
    cfg = U.universe_cfg(universe_key)
    mem = members if members is not None else U.members(universe_key, con)
    w = _windows(end)
    tickers = mem["ticker"].tolist()
    p12 = P.get_prices(tickers, w["start_12m"], w["end"], con)
    p24 = P.get_prices(tickers, w["start_24m"], w["end"], con)
    vol = P.get_volumes(tickers, w["start_12m"], w["end"], con)
    m = M.ticker_metrics(p12, p24, vol, divergence=U.config().get("divergence"))
    if m.empty:
        return None
    peer_key = cfg.get("peer_key", "sector")
    if peer_key == "commodity":
        m = m[m.index.isin(mem.loc[mem["commodity"].notna(), "ticker"])]
        m = m[np.isfinite(m["ret_12m"].astype(float))]
    peer_of = mem.set_index("ticker")[peer_key]
    pr = M.peer_rs(m, peer_of)
    m = m.join(pr)
    info = mem.set_index("ticker")
    rs = load_rank_settings(cfg["rank_keys"]["screener"])
    out = []
    for t, r in m.iterrows():
        r = _clean(r)
        rs_trend = M.rs_trend_for([r["rs_63"], r["rs_21"], r["rs_5"]])
        if r["peer_rs_score"] >= 75 and r["pass_trend"] == 1:
            regime = "LEADER"
        elif r["peer_rs_score"] >= 50 and r["pass_trend"] == 1:
            regime = "CONTENDER"
        elif r["peer_rs_score"] < 50 and r["pass_trend"] == 0:
            regime = "WEAK"
        else:
            regime = "LAGGARD"
        cap = info.at[t, "cap_band"]
        row = {"ticker": t, "name": info.at[t, "name"], "sector": info.at[t, "sector"],
               "industry": info.at[t, "industry"], "commodity": info.at[t, "commodity"],
               "type": info.at[t, "type"], "cap_band": cap, "close": r["close"],
               "peer_rs_score": r["peer_rs_score"], "rs_ratio": None,
               "rs_5": r["rs_5"], "rs_21": r["rs_21"], "rs_63": r["rs_63"], "rs_trend": rs_trend,
               "ret_6m": _pct(r["ret_6m"]), "ret_12m": _pct(r["ret_12m"]), "ret_24m": _pct(r["ret_24m"]),
               "max_dd": r["max_dd"], "persist_frac": r["persist_frac"], "vol_63": r["vol_63"],
               "rel_vol": r["rel_vol"], "vol_label": r["vol_label"],
               "acc_watch": M.acc_watch_for(r["close"], r["sma20"], r["sma50"], r["sma200"], cap),
               "sma20": r["sma20"], "sma50": r["sma50"], "sma200": r["sma200"],
               "pass_trend": int(r["pass_trend"]), "mqs": r["mqs"],
               "rsi_14": r["rsi_14"], "rsi_div": r["rsi_div"], "obv_div": r["obv_div"],
               "regime_label": regime}
        row["score_final"] = _score({**row, "ret_12m": r["ret_12m"]}, rs, "screener")
        out.append(row)
    df = pd.DataFrame(out, columns=RESULT_COLS)
    return actionable_flags(_finish(df))


# ── Benchmark ─────────────────────────────────────────────────────────────────
def benchmark(universe_key: str, con: sqlite3.Connection, end: str | None = None,
              members: pd.DataFrame | None = None) -> pd.DataFrame | None:
    cfg = U.universe_cfg(universe_key)
    mem = members if members is not None else U.members(universe_key, con)
    w = _windows(end)
    tickers = mem["ticker"].tolist()
    bench_list = sorted(set(mem["benchmark"].dropna()))
    p12 = P.get_prices(tickers, w["start_12m"], w["end"], con)
    p24 = P.get_prices(tickers, w["start_24m"], w["end"], con)
    vol = P.get_volumes(tickers, w["start_12m"], w["end"], con)
    bp  = P.get_prices(bench_list, w["start_12m"], w["end"], con)
    m = M.ticker_metrics(p12, p24, vol, divergence=U.config().get("divergence"))
    if m.empty:
        return None
    if cfg.get("peer_key") == "commodity":
        m = m[m.index.isin(mem.loc[mem["commodity"].notna(), "ticker"])]
        m = m[np.isfinite(m["ret_12m"].astype(float))]
    bench_of = mem.set_index("ticker")["benchmark"]
    br = M.benchmark_rs(m, bp, bench_of)
    m = m.join(br)
    m = m[m["rs_ratio"].notna()]
    info = mem.set_index("ticker")
    rs = load_rank_settings(cfg["rank_keys"]["benchmark"])
    out = []
    for t, r in m.iterrows():
        r = _clean(r)
        rs_trend = M.rs_trend_for([r["rs_63"], r["rs_21"], r["rs_5"]])
        if r["pass_trend"] == 1 and r["rs_ratio"] > 1.0:
            regime = "TREND+LEAD"
        elif r["pass_trend"] == 1:
            regime = "TREND_ONLY"
        else:
            regime = "WEAK"
        cap = info.at[t, "cap_band"]
        row = {"ticker": t, "name": info.at[t, "name"], "sector": info.at[t, "sector"],
               "industry": info.at[t, "industry"], "commodity": info.at[t, "commodity"],
               "type": info.at[t, "type"], "cap_band": cap, "close": r["close"],
               "peer_rs_score": None, "rs_ratio": r["rs_ratio"],
               "rs_5": r["rs_5"], "rs_21": r["rs_21"], "rs_63": r["rs_63"], "rs_trend": rs_trend,
               "ret_6m": _pct(r["ret_6m"]), "ret_12m": _pct(r["ret_12m"]), "ret_24m": _pct(r["ret_24m"]),
               "max_dd": r["max_dd"], "persist_frac": r["persist_frac"], "vol_63": r["vol_63"],
               "rel_vol": r["rel_vol"], "vol_label": r["vol_label"],
               "acc_watch": M.acc_watch_for(r["close"], r["sma20"], r["sma50"], r["sma200"], cap),
               "sma20": r["sma20"], "sma50": r["sma50"], "sma200": r["sma200"],
               "pass_trend": int(r["pass_trend"]), "mqs": r["mqs"],
               "rsi_14": r["rsi_14"], "rsi_div": r["rsi_div"], "obv_div": r["obv_div"],
               "regime_label": regime}
        row["score_final"] = _score({**row, "ret_12m": r["ret_12m"]}, rs, "benchmark")
        out.append(row)
    df = pd.DataFrame(out, columns=RESULT_COLS)
    return actionable_flags(_finish(df))


# ── Breadth ───────────────────────────────────────────────────────────────────
# Every trading day is computed from the same vectorised panel, so a one-day increment and a
# full rebuild produce identical rows. Per ticker/day: rolling SMAs (20/50/200), rolling 252-bar
# return (first-bar base for younger listings), rel_vol vs 63-day mean volume, accumulation watch,
# sector/commodity peer RS rank -> LEADER / CONTENDER / LAGGARD / WEAK.
STALE_DAYS = 10          # a ticker drops out of the counts this many bars after its last real print


def _slug(s) -> str:
    return str(s).lower().replace(" ", "_").replace("/", "_").replace("&", "and")


def breadth_panel(prices: pd.DataFrame, volumes: pd.DataFrame, info: pd.DataFrame, peer_key: str) -> pd.DataFrame:
    """Long frame, one row per (date, ticker) that is live on that day."""
    P = prices.sort_index()
    real = P.notna()
    Pf = P.ffill()
    pos = np.arange(len(P))[:, None]
    last_real = pd.DataFrame(np.where(real, pos, np.nan), index=P.index, columns=P.columns).ffill()
    live = Pf.notna() & ((pos - last_real) <= STALE_DAYS)

    sma20 = Pf.rolling(20, min_periods=20).mean()
    sma50 = Pf.rolling(50, min_periods=50).mean()
    sma200 = Pf.rolling(200, min_periods=200).mean()
    first = Pf.apply(lambda c: c.loc[c.first_valid_index()] if c.first_valid_index() is not None else np.nan)
    base = Pf.shift(252)
    base = base.where(base.notna(), first, axis=1)
    ret12 = Pf / base - 1

    V = volumes.reindex(index=P.index, columns=P.columns)
    rel_vol = V / V.rolling(63, min_periods=1).mean()

    def stack(df, name):
        s = df.where(live).stack(future_stack=True)
        s.name = name
        return s

    long = pd.concat([stack(Pf, "close"), stack(sma20, "sma20"), stack(sma50, "sma50"), stack(sma200, "sma200"),
                      stack(ret12, "ret_12m"), stack(rel_vol, "rel_vol")], axis=1)
    long = long[long["close"].notna()]
    long.index.names = ["date", "ticker"]
    long = long.reset_index()
    long["date"] = long["date"].dt.strftime("%Y-%m-%d")
    cols = ["sector", "industry", "cap_band", "commodity", "type"]
    long = long.merge(info[cols].reset_index(), on="ticker", how="left")
    long["sector"] = long["sector"].fillna("Unknown")

    long["above_20"] = (long["close"] > long["sma20"]).astype(int)
    long["above_50"] = (long["close"] > long["sma50"]).astype(int)
    long["pass_trend"] = (long["close"] > long["sma200"]).astype(int)
    rv = long["rel_vol"]
    long["vol_label"] = np.select([rv >= M.VOL_HIGH, rv >= M.VOL_MED], ["HIGH", "MED"], default="LOW")
    c, s20, s50, s200 = long["close"], long["sma20"], long["sma50"], long["sma200"]
    have = s20.notna() & s50.notna() & s200.notna() & long["cap_band"].isin(["large", "mid"])
    long["acc_watch"] = np.select(
        [have & (c < s20) & (c < s50) & (c < s200),
         have & (c < s50) & (c < s200) & (c >= s20),
         have & (c < s200) & (c >= s50) & (c >= s20)],
        ["EARLY", "PROGRESS", "SHIFT"], default="-")

    # peer RS: % of same-group peers (excluding self) beaten on the 12m return, 50 when alone
    grp = long[peer_key].fillna("Unknown") if peer_key in long.columns else long["sector"]
    ok = long["ret_12m"].notna() & np.isfinite(long["ret_12m"])
    g = long[ok].groupby([long.loc[ok, "date"], grp[ok]])["ret_12m"]
    rank = g.rank(method="min")
    n = g.transform("count")
    score = pd.Series(50.0, index=long.index)
    score.loc[ok] = np.where(n > 1, (rank - 1) / (n - 1) * 100, 50.0)
    long["peer_rs_score"] = score
    long["regime_label"] = np.select(
        [(score >= 75) & (long["pass_trend"] == 1), (score >= 50) & (long["pass_trend"] == 1),
         (score < 50) & (long["pass_trend"] == 0)], ["LEADER", "CONTENDER", "WEAK"], default="LAGGARD")
    return long


_FLAGS = {"leader": ("regime_label", "LEADER"), "contender": ("regime_label", "CONTENDER"),
          "laggard": ("regime_label", "LAGGARD"), "weak": ("regime_label", "WEAK"),
          "high_vol": ("vol_label", "HIGH"), "acc_early": ("acc_watch", "EARLY"),
          "acc_progress": ("acc_watch", "PROGRESS"), "acc_shift": ("acc_watch", "SHIFT")}


def _with_flags(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel
    out = pd.DataFrame({"date": p["date"], "total": 1, "above_20": p["above_20"], "above_50": p["above_50"],
                        "above_200": p["pass_trend"]})
    for k, (col, val) in _FLAGS.items():
        out[k] = (p[col] == val).astype(int)
    out["leaders"] = out["leader"]; out["above20"] = out["above_20"]; out["above50"] = out["above_50"]
    out["above200"] = out["above_200"]
    return out


def _emit(flags: pd.DataFrame, keys: pd.Series | None, metrics: list[str], universe: str, layer: str,
          group_type: str, key_fn=None) -> pd.DataFrame:
    by = [flags["date"]] + ([keys] if keys is not None else [])
    agg = flags.groupby(by, observed=True)[metrics].sum().reset_index()
    if keys is None:
        agg["group_key"] = ""
    else:
        agg = agg.rename(columns={keys.name: "group_key"})
        agg["group_key"] = agg["group_key"].map(key_fn or _slug)
    out = agg.melt(id_vars=["date", "group_key"], value_vars=metrics, var_name="metric", value_name="value")
    out["universe"] = universe; out["layer"] = layer; out["group_type"] = group_type
    return out[["date", "universe", "layer", "group_type", "group_key", "metric", "value"]]


ALL_METRICS = ["total", "leader", "contender", "laggard", "weak", "above_20", "above_50", "above_200",
               "high_vol", "acc_early", "acc_progress", "acc_shift"]
LAYER_METRICS = ALL_METRICS[:-2]
CAP_METRICS = ["total", "leaders", "above200"]
SEC_METRICS = ["total", "leaders", "above20", "above50", "above200", "high_vol"]


def breadth_rows(panel: pd.DataFrame, universe: str, cfg: dict, layers: dict[str, set] | None) -> pd.DataFrame:
    """Aggregate the panel into breadth_daily rows (long format) for every date it contains."""
    groups = cfg.get("breadth_groups", ["cap", "sector", "industry"])
    f = _with_flags(panel)
    parts = [_emit(f, None, ALL_METRICS, universe, "all", "all")]
    if "cap" in groups:
        parts.append(_emit(f, panel["cap_band"].rename("k"), CAP_METRICS, universe, "all", "cap", lambda x: x))
    if "sector" in groups:
        parts.append(_emit(f, panel["sector"].rename("k"), SEC_METRICS, universe, "all", "sector"))
    if "industry" in groups:
        ind = panel["industry"].fillna("").astype(str).str.strip()
        m = ind != ""
        parts.append(_emit(f[m], ind[m].rename("k"), CAP_METRICS, universe, "all", "industry"))
    if "commodity" in groups:
        comm = panel["commodity"].fillna("")
        m = comm != ""
        parts.append(_emit(f[m], comm[m].rename("k"), SEC_METRICS + ["acc_early"], universe, "all", "commodity"))
        ct = (comm + "_" + panel["type"].fillna("").map(_slug)).rename("k")
        parts.append(_emit(f[m], ct[m], CAP_METRICS, universe, "all", "commodity", lambda x: x))
        cb = (comm + "_" + panel["cap_band"].fillna("")).rename("k")
        parts.append(_emit(f[m], cb[m], CAP_METRICS, universe, "all", "commodity", lambda x: x))
    if "type" in groups:
        parts.append(_emit(f, panel["type"].fillna("").rename("k"), CAP_METRICS, universe, "all", "type"))
    for layer, tickers in (layers or {}).items():
        m = panel["ticker"].isin(tickers)
        fl, pl = f[m], panel[m]
        parts.append(_emit(fl, None, LAYER_METRICS, universe, layer, "all"))
        parts.append(_emit(fl, pl["cap_band"].rename("k"), CAP_METRICS, universe, layer, "cap", lambda x: x))
        parts.append(_emit(fl, pl["sector"].rename("k"), SEC_METRICS, universe, layer, "sector"))
        if layer == "sp":
            ind = pl["industry"].fillna("").astype(str).str.strip()
            mi = ind != ""
            parts.append(_emit(fl[mi], ind[mi].rename("k"), CAP_METRICS, universe, layer, "industry"))
    out = pd.concat(parts, ignore_index=True)
    out["value"] = out["value"].astype(float)
    return out


def breadth_layers(universe_key: str, con: sqlite3.Connection, members: pd.DataFrame) -> dict[str, set]:
    cfg = U.universe_cfg(universe_key)
    out = {}
    idx = db.read_df("SELECT ticker, group_key FROM security_groups WHERE group_type='index'", con=con)
    all_members = set(members["ticker"])
    for layer, spec in (cfg.get("breadth_layers") or {}).items():
        if "index_any" in spec:
            keep = set(idx[idx["group_key"].isin(spec["index_any"])]["ticker"])
        elif "not_index_any" in spec:
            keep = all_members - set(idx[idx["group_key"].isin(spec["not_index_any"])]["ticker"])
        else:
            keep = all_members
        out[layer] = keep & all_members
    return out


def breadth(universe_key: str, con: sqlite3.Connection, end: str | None = None, backfill_days: int = 400,
            reprocess_last: int = 2, rebuild: bool = False, log=print) -> pd.DataFrame:
    """Compute breadth rows for the days that are missing (or every day when rebuild=True).

    Uses every member that has ever had prices (inactive ones included) so delisted names count
    while they traded; a ticker leaves the counts STALE_DAYS bars after its last print.
    """
    cfg = U.universe_cfg(universe_key)
    mem = U.members(universe_key, con, include_inactive=True)
    w = _windows(end)
    tickers = mem["ticker"].tolist()
    existing = set() if rebuild else set(
        db.read_df("SELECT DISTINCT date FROM breadth_daily WHERE universe=?", (universe_key,), con=con)["date"])
    if existing:
        for d in sorted(existing)[-reprocess_last:]:
            existing.discard(d)
    first_date = db.scalar("SELECT MIN(date) FROM prices", con=con)
    if rebuild:
        start = first_date
    else:
        start = (pd.Timestamp(w["end"]) - timedelta(days=backfill_days + 400)).strftime("%Y-%m-%d")
    prices = P.get_prices(tickers, start, w["end"], con)
    if prices.empty:
        log(f"  breadth {universe_key}: no price data")
        return pd.DataFrame()
    volumes = P.get_volumes(tickers, start, w["end"], con)
    # warm-up: the first ~200 bars only feed the rolling windows
    warm = prices.index[min(len(prices) - 1, 200)].strftime("%Y-%m-%d") if rebuild else \
        (pd.Timestamp(w["end"]) - timedelta(days=backfill_days)).strftime("%Y-%m-%d")
    days = [d for d in prices.index.strftime("%Y-%m-%d") if d >= warm and d not in existing]
    if not days:
        log(f"  breadth {universe_key}: up to date")
        return pd.DataFrame()
    log(f"  breadth {universe_key}: computing {len(days)} day(s) ({days[0]} to {days[-1]}) over {len(tickers)} tickers")
    info = mem.set_index("ticker")
    panel = breadth_panel(prices, volumes, info, cfg.get("peer_key", "sector"))
    panel = panel[panel["date"].isin(set(days))]
    rows = breadth_rows(panel, universe_key, cfg, breadth_layers(universe_key, con, mem))
    return rows


# ── RRG ───────────────────────────────────────────────────────────────────────
def rrg(study: str, con: sqlite3.Connection, end: str | None = None, lookback_days: int = 500) -> pd.DataFrame:
    """Homegrown RRG: rs_ratio = (P_t/P_{t-62})/(B_t/B_{t-62})*100, momentum = ratio_t/ratio_{t-21}*100."""
    cfg = U.config()["rrg"][study]
    bench = cfg["benchmark"]
    mem = U.theme_members(con, cfg["theme"])
    grp = db.read_df("SELECT ticker, group_key FROM security_groups WHERE group_type='theme' AND group_key LIKE ?",
                     (cfg["theme"] + ":%",), con=con)
    grp_of = {t: k.split(":", 1)[1] for t, k in zip(grp["ticker"], grp["group_key"])}
    w = _windows(end)
    start = (pd.Timestamp(w["end"]) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    tickers = mem["ticker"].tolist()
    prices = P.get_prices(tickers + [bench], start, w["end"], con)
    if bench not in prices.columns or prices[bench].dropna().empty:
        print(f"  rrg {study}: benchmark {bench} has no data")
        return pd.DataFrame()
    b = prices[bench].dropna()
    out = []
    for t, name in zip(mem["ticker"], mem["name"]):
        if t not in prices.columns:
            continue
        tp = prices[t].dropna()
        if len(tp) < 21:
            continue
        al = pd.concat([tp, b], axis=1).dropna()
        al.columns = ["ticker", "bench"]
        rs_ratio = (al["ticker"] / al["ticker"].shift(62)) / (al["bench"] / al["bench"].shift(62)) * 100
        rs_mom = rs_ratio / rs_ratio.shift(21) * 100
        df = pd.DataFrame({"date": al.index.strftime("%Y-%m-%d"), "ticker": t, "name": name,
                           "grp": grp_of.get(t, ""), "rs_ratio": rs_ratio.round(4).values,
                           "rs_momentum": rs_mom.round(4).values, "close": al["ticker"].round(4).values})
        out.append(df.dropna(subset=["rs_ratio", "rs_momentum"]))
    if not out:
        return pd.DataFrame()
    return pd.concat(out, ignore_index=True).assign(study=study)
