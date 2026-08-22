"""The shared per-ticker metric block.

This is the single implementation of what every legacy screener / benchmark /
breadth script computed inline. Semantics (including rounding order and the
`iloc[-5]` look-backs) are kept identical so results are comparable with the
CSV history; `tests/test_metrics_parity.py` checks that against the legacy code.

    close, ret_6m, ret_12m, ret_24m          (fractions; callers scale to %)
    max_dd, persist_frac, vol_63             (percent, rounded 2)
    rel_vol, vol_label                       (HIGH >= 1.5, MED >= 1.0, LOW)
    sma20/50/200 (rounded 4), pass_trend, mqs (rounded 4)
    ret_5 / ret_21 / ret_63                  (fractions, iloc[-5]/[-21]/[-63] look-backs)
    rsi_14, rsi_div, obv_div                 (added 2026-08-23, see rsi_divergence / obv_divergence)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

VOL_HIGH = 1.5
VOL_MED  = 1.0

# Divergence defaults — overridable from universe_config.json "divergence" (studies.py passes it in).
DIVERGENCE = {
    "rsi_period": 14,
    "pivot_left": 5,          # bars each side that must be lower (high pivot) / higher (low pivot)
    "pivot_right": 5,
    "pivot_min_gap": 5,       # bars between the two pivots being compared
    "pivot_max_gap": 60,
    "max_age_bars": 20,       # the newer pivot must be confirmed within this many bars of the last bar
    "obv_window": 21,
    "obv_price_flat_pct": 2.0,     # |fitted price move over the window| below this -> price "flat"
    "obv_flat_avg_days": 3.0,      # |fitted OBV move| below this many average-volume days -> OBV "flat"
}


def vol_label_for(rel_vol) -> str:
    if rel_vol and rel_vol >= VOL_HIGH:
        return "HIGH"
    if rel_vol and rel_vol >= VOL_MED:
        return "MED"
    return "LOW"


def acc_watch_for(price, sma20, sma50, sma200, cap_band) -> str:
    """Accumulation watch — large/mid caps only (legacy rule)."""
    if cap_band not in ("large", "mid"):
        return "-"
    if sma20 is None or sma50 is None or sma200 is None:
        return "-"
    if price < sma20 and price < sma50 and price < sma200:
        return "EARLY"
    if price < sma50 and price < sma200 and price >= sma20:
        return "PROGRESS"
    if price < sma200 and price >= sma50 and price >= sma20:
        return "SHIFT"
    return "-"


def rs_trend_for(values: list) -> str:
    """Ordered RS values (oldest window first) -> STRONG_UP / UP / FLAT / DOWN / STRONG_DOWN."""
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < 2:
        return "FLAT"
    steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    up = sum(1 for s in steps if s > 0)
    dn = sum(1 for s in steps if s < 0)
    if up == len(steps):
        return "STRONG_UP"
    if dn == len(steps):
        return "STRONG_DOWN"
    if up > dn:
        return "UP"
    if dn > up:
        return "DOWN"
    return "FLAT"


def _r(x, nd):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


# ── RSI / OBV divergence ──────────────────────────────────────────────────────
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (same smoothing as TradingView's ta.rsi)."""
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    au = up.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    ad = dn.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = au / ad.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(ad != 0.0, 100.0).where(au.notna() & ad.notna())


def _pivots(x: np.ndarray, left: int, right: int, kind: str) -> list[int]:
    """Indices i where x[i] is the strict max (kind='high') / min ('low') of x[i-left : i+right+1]."""
    n = len(x)
    out = []
    for i in range(left, n - right):
        w = x[i - left:i + right + 1]
        if np.isnan(w).any():
            continue
        c = x[i]
        if kind == "high":
            if c > w[:left].max() and c >= w[left + 1:].max():
                out.append(i)
        else:
            if c < w[:left].min() and c <= w[left + 1:].min():
                out.append(i)
    return out


def rsi_divergence(close: pd.Series, r: pd.Series, cfg: dict | None = None) -> str:
    """TradingView-style divergence: pivots are found on the RSI line (pivot_left / pivot_right
    bars each side) and price is compared at the same bars.

        BEAR      price higher high,  RSI lower high      (regular bearish)
        BULL      price lower low,    RSI higher low      (regular bullish)
        HID_BEAR  price lower high,   RSI higher high     (hidden bearish — down-trend continuation)
        HID_BULL  price higher low,   RSI lower low       (hidden bullish — up-trend continuation)
        -         nothing within max_age_bars of the last bar

    Only the two most recent consecutive pivots are compared (as TradingView's built-in does).
    The newer one must be confirmed (pivot_right bars after it) no more than max_age_bars before
    the last bar, the pair must be pivot_min_gap..pivot_max_gap apart, and the signal is void once
    price has closed beyond the newer pivot (above a pivot high / below a pivot low).
    When both a high-pivot and a low-pivot signal exist the more recent one wins.
    """
    c = {**DIVERGENCE, **(cfg or {})}
    L, R = int(c["pivot_left"]), int(c["pivot_right"])
    px = close.to_numpy(dtype=float)
    rv = r.to_numpy(dtype=float)
    n = len(px)
    if n < L + R + int(c["pivot_min_gap"]) + 2:
        return "-"
    best = None          # (pivot index, label)
    for kind in ("high", "low"):
        piv = _pivots(rv, L, R, kind)
        if len(piv) < 2:
            continue
        i2 = piv[-1]
        if (n - 1) - (i2 + R) > int(c["max_age_bars"]):
            continue
        i1 = piv[-2]
        gap = i2 - i1
        if not (int(c["pivot_min_gap"]) <= gap <= int(c["pivot_max_gap"])):
            continue
        label = None
        if kind == "high":
            if px[i2] > px[i1] and rv[i2] < rv[i1]:
                label = "BEAR"
            elif px[i2] < px[i1] and rv[i2] > rv[i1]:
                label = "HID_BEAR"
            if label and px[i2 + 1:].max() > px[i2]:      # price already broke above the pivot high
                label = None
        else:
            if px[i2] < px[i1] and rv[i2] > rv[i1]:
                label = "BULL"
            elif px[i2] > px[i1] and rv[i2] < rv[i1]:
                label = "HID_BULL"
            if label and px[i2 + 1:].min() < px[i2]:      # price already broke below the pivot low
                label = None
        if label and (best is None or i2 > best[0]):
            best = (i2, label)
    return best[1] if best else "-"


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-balance volume over the bars where both close and volume exist."""
    al = pd.concat([close, volume], axis=1).dropna()
    if al.empty:
        return pd.Series(dtype=float)
    sgn = np.sign(al.iloc[:, 0].diff().fillna(0.0))
    return (sgn * al.iloc[:, 1]).cumsum()


def _fit_move(y: np.ndarray) -> float:
    """Total move implied by the least-squares line through y (slope * (n-1))."""
    n = len(y)
    x = np.arange(n, dtype=float)
    xm, ym = x.mean(), y.mean()
    den = ((x - xm) ** 2).sum()
    if den == 0:
        return 0.0
    return float(((x - xm) * (y - ym)).sum() / den * (n - 1))


def obv_divergence(close: pd.Series, volume: pd.Series, cfg: dict | None = None) -> str:
    """Direction of price vs direction of OBV over the last obv_window bars (least-squares
    slopes, so one noisy day does not flip the label).

        CONV_UP    price up,   OBV up      volume confirms the advance
        CONV_DOWN  price down, OBV down    volume confirms the decline
        BEAR_DIV   price up,   OBV down    advance not supported by volume (distribution)
        BULL_DIV   price down, OBV up      decline on shrinking supply (accumulation)
        ACCUM      price flat, OBV up
        DISTRIB    price flat, OBV down
        -          price or OBV flat / mixed, or fewer than obv_window bars

    "flat" = fitted price move < obv_price_flat_pct (% of the window's mean price) or fitted OBV
    move < obv_flat_avg_days x the window's average daily volume.
    """
    c = {**DIVERGENCE, **(cfg or {})}
    w = int(c["obv_window"])
    al = pd.concat([close, volume], axis=1).dropna()
    if len(al) < w + 1:
        return "-"
    ob = obv(al.iloc[:, 0], al.iloc[:, 1]).to_numpy(dtype=float)[-w:]
    px = al.iloc[-w:, 0].to_numpy(dtype=float)
    vol = al.iloc[-w:, 1].to_numpy(dtype=float)
    if px.mean() <= 0:
        return "-"
    p_move = _fit_move(px) / px.mean() * 100.0
    avg_vol = vol.mean()
    o_move = _fit_move(ob) / avg_vol if avg_vol > 0 else 0.0
    p_dir = 0 if abs(p_move) < float(c["obv_price_flat_pct"]) else (1 if p_move > 0 else -1)
    o_dir = 0 if abs(o_move) < float(c["obv_flat_avg_days"]) else (1 if o_move > 0 else -1)
    table = {(1, 1): "CONV_UP", (-1, -1): "CONV_DOWN", (1, -1): "BEAR_DIV", (-1, 1): "BULL_DIV",
             (0, 1): "ACCUM", (0, -1): "DISTRIB"}
    return table.get((p_dir, o_dir), "-")


def ticker_metrics(prices: pd.DataFrame, prices_24m: pd.DataFrame | None, volumes: pd.DataFrame | None,
                   tickers=None, divergence: dict | None = None) -> pd.DataFrame:
    """Per-ticker metric frame (index = ticker) for every column of `prices` with >= 2 bars
    and a non-zero first price. `prices` is the 12-month adjusted-close matrix.
    `divergence` overrides the DIVERGENCE defaults (RSI/OBV divergence settings)."""
    rows = {}
    cols = list(tickers) if tickers is not None else list(prices.columns)
    rsi_n = int((divergence or {}).get("rsi_period", DIVERGENCE["rsi_period"]))
    for t in cols:
        if t not in prices.columns:
            continue
        tp = prices[t].dropna()
        n = len(tp)
        if n < 2 or tp.iloc[0] == 0:
            continue
        last = float(tp.iloc[-1])
        ret_12m = last / float(tp.iloc[0]) - 1
        ret_6m  = (last / float(tp.iloc[-126]) - 1) if n >= 126 else None
        ret_5   = (last / float(tp.iloc[-5])  - 1) if n >= 5  else None
        ret_21  = (last / float(tp.iloc[-21]) - 1) if n >= 21 else None
        ret_63  = (last / float(tp.iloc[-63]) - 1) if n >= 63 else None

        ret_24m = None
        if prices_24m is not None and t in prices_24m.columns:
            t24 = prices_24m[t].dropna()
            if len(t24) >= 2 and t24.iloc[0] != 0:
                ret_24m = float(t24.iloc[-1]) / float(t24.iloc[0]) - 1

        roll_max = tp.cummax()
        max_dd = _r(((tp - roll_max) / roll_max).min() * 100, 2)

        dr = tp.pct_change().dropna()
        persist_frac = _r((dr > 0).sum() / len(dr) * 100, 2) if len(dr) else None
        vol_63 = _r((dr.tail(63) if n >= 63 else dr).std() * (252 ** 0.5) * 100, 2)

        sma20  = _r(tp.tail(20).mean(), 4)  if n >= 20  else None
        sma50  = _r(tp.tail(50).mean(), 4)  if n >= 50  else None
        sma200 = _r(tp.tail(200).mean(), 4) if n >= 200 else None
        pass_trend = 1 if (sma200 is not None and last > sma200) else 0

        if vol_63 and vol_63 > 0 and np.isfinite(ret_12m) and persist_frac is not None:
            mqs = _r((ret_12m * 100 * persist_frac) / vol_63, 4)
        else:
            mqs = None

        rel_vol = None
        obv_div = "-"
        if volumes is not None and t in volumes.columns:
            tv = volumes[t].dropna()
            if len(tv) >= 1:
                avg63 = float(tv.tail(63).mean())
                rel_vol = _r(float(tv.iloc[-1]) / avg63, 4) if avg63 > 0 else None
            obv_div = obv_divergence(tp, tv, divergence)
        vol_label = vol_label_for(rel_vol)

        rsi_14, rsi_div = None, "-"
        if n > rsi_n:
            rs_line = rsi(tp, rsi_n)
            rsi_14 = _r(rs_line.iloc[-1], 2)
            rsi_div = rsi_divergence(tp, rs_line, divergence)

        rows[t] = dict(close=_r(last, 4), n_bars=n, ret_12m=ret_12m, ret_6m=ret_6m, ret_24m=ret_24m,
                       ret_5=ret_5, ret_21=ret_21, ret_63=ret_63, max_dd=max_dd,
                       persist_frac=persist_frac, vol_63=vol_63, rel_vol=rel_vol, vol_label=vol_label,
                       sma20=sma20, sma50=sma50, sma200=sma200, pass_trend=pass_trend, mqs=mqs,
                       rsi_14=rsi_14, rsi_div=rsi_div, obv_div=obv_div)
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "ticker"
    return df


def peer_rs(metrics: pd.DataFrame, peer_of: pd.Series) -> pd.DataFrame:
    """Sector/commodity peer relative strength for each ticker in `metrics`.

    peer_rs_score : % of same-group peers (excluding self) beaten on ret_12m, 50.0 if none
    rs_5/21/63    : own N-bar return minus the peer median (peers excluding self, with >= N bars)
    """
    out = {}
    groups = peer_of.reindex(metrics.index).fillna("Unknown")
    for grp, idx in groups.groupby(groups).groups.items():
        members = list(idx)
        m = metrics.loc[members]
        r12 = m["ret_12m"].to_numpy(dtype=float)
        for i, t in enumerate(members):
            peers_mask = np.ones(len(members), dtype=bool)
            peers_mask[i] = False
            peers_r12 = r12[peers_mask]
            peers_r12 = peers_r12[np.isfinite(peers_r12)]
            if len(peers_r12):
                score = round(float((r12[i] > peers_r12).sum()) / len(peers_r12) * 100, 2)
            else:
                score = 50.0
            rec = {"peer_rs_score": score}
            for col, nbars in (("ret_5", 5), ("ret_21", 21), ("ret_63", 63)):
                own = m.at[t, col]
                if own is None or (isinstance(own, float) and not np.isfinite(own)):
                    rec["rs_" + col.split("_")[1]] = None
                    continue
                pv = m[col].to_numpy(dtype=float)[peers_mask]
                pv = pv[np.isfinite(pv)]
                med = float(np.median(pv)) if len(pv) else 0.0
                rec["rs_" + col.split("_")[1]] = round(float(own) - med, 4)
            out[t] = rec
    return pd.DataFrame.from_dict(out, orient="index").reindex(metrics.index)


def benchmark_rs(metrics: pd.DataFrame, bench_prices: pd.DataFrame, bench_of: pd.Series) -> pd.DataFrame:
    """RS ratio vs each ticker's benchmark: (1+ret)/(1+bench_ret) at 12m/63/21/5."""
    bm = ticker_metrics(bench_prices, None, None)
    out = {}
    for t in metrics.index:
        b = bench_of.get(t)
        if b is None or b not in bm.index:
            out[t] = {"rs_ratio": None, "rs_5": None, "rs_21": None, "rs_63": None}
            continue
        br = bm.loc[b]
        rec = {"rs_ratio": round((1 + metrics.at[t, "ret_12m"]) / (1 + br["ret_12m"]), 4)}
        for k in ("5", "21", "63"):
            own, bb = metrics.at[t, "ret_" + k], br["ret_" + k]
            rec["rs_" + k] = round((1 + own) / (1 + bb), 4) if (own is not None and bb is not None and
                                                                  np.isfinite(own) and np.isfinite(bb)) else None
        out[t] = rec
    return pd.DataFrame.from_dict(out, orient="index").reindex(metrics.index)
