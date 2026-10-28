"""
etf/etf_income_data.py
======================
Income ETF universe scoring for quarterly rebalancing.

Fetches price + distribution history for a universe of income ETFs,
scores each on NAV trend, distribution quality, and risk-adjusted return,
and saves ranked results to CSV.

Score components:
  - NAV trend (3m and 12m price change) — negative 3m = disqualified
  - Sharpe ratio (90d daily returns)
  - TTM distribution yield
  - Distribution slope (is the payout growing or shrinking)
  - Distribution consistency (1 - coefficient of variation)

Usage:
    python etf/etf_income_data.py
"""

import os
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
try:
    from . import etf_prices as _px
except ImportError:
    import etf_prices as _px

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE, 'results', 'etf_income')

# Definitions and effective settings are shared with the dashboard and MCP.
try:
    from .income_config import FULL_UNIVERSE, DEFAULT_WEIGHTS, load_strategy
except ImportError:  # direct script / existing dashboard import
    from income_config import FULL_UNIVERSE, DEFAULT_WEIGHTS, load_strategy

UNIVERSE = dict(FULL_UNIVERSE)
SETTINGS_FILE = os.path.join(BASE, 'etf_settings.json')
DEFAULT_EXCLUDED = ['MSTY']

def load_etf_settings():
    return load_strategy(SETTINGS_FILE)["effective"]

# ── Underlying proxies ────────────────────────────────────────────────────────
# Maps non-ticker underlyings to a tradeable/index proxy for RS calculation.
# None = no meaningful underlying (themes) — scores neutral on the RS component.
UNDERLYING_PROXY = {
    'SPX'        : '^GSPC',
    'NDX'        : '^NDX',
    'RUT'        : '^RUT',
    'mag7'       : 'QQQ',
    'diversified': None,
    'VIX-short'  : None,
}

# Apply settings: weights, blocklist
_settings = load_etf_settings()
WEIGHTS = _settings['weights']
EXCLUDED = set(_settings['excluded'])
for _t in EXCLUDED:
    UNIVERSE.pop(_t, None)


def compute_metrics(close, divs):
    """Compute score inputs from a 12m close series + distribution series.

    Used by both the live scorer and the backtest engine so historical
    scoring is identical to live scoring. Returns None if insufficient data.
    """
    close = close.dropna()
    if len(close) < 63:
        return None

    price = float(close.iloc[-1])

    # NAV trend
    chg_3m  = float((close.iloc[-1] / close.iloc[-min(63, len(close))] - 1) * 100)
    chg_12m = float((close.iloc[-1] / close.iloc[0] - 1) * 100)

    # Sharpe on last ~3 months of daily returns
    recent = close.tail(63)
    rets = recent.pct_change().dropna()
    sharpe = float((rets.mean() / rets.std()) * np.sqrt(252)) if len(rets) > 10 and rets.std() > 0 else 0.0

    # Distribution metrics
    n_dists = len(divs) if divs is not None else 0
    if n_dists >= 4:
        dist_sum = float(divs.sum())
        # annualise yield by the span the close series covers
        span_days = max((close.index[-1] - close.index[0]).days, 1)
        yield_ttm = (dist_sum / price) * 100 * (365.0 / span_days)

        # slope: linear regression on payout amounts, normalised to % of mean per period
        y = np.asarray(divs.values, dtype=float)
        x = np.arange(len(y))
        slope_raw = float(np.polyfit(x, y, 1)[0])
        mean_dist = float(np.mean(y))
        dist_slope = (slope_raw / mean_dist) * 100 if mean_dist > 0 else 0.0

        # consistency: 1 - CV, clamped to [0, 1]
        cv = float(np.std(y) / mean_dist) if mean_dist > 0 else 1.0
        dist_consist = max(0.0, min(1.0, 1.0 - cv))
    else:
        yield_ttm = 0.0
        dist_slope = 0.0
        dist_consist = 0.0

    # total return: price change + distributions (not reinvested)
    first_price = float(close.iloc[0])
    dist_sum_all = float(divs.sum()) if n_dists > 0 else 0.0
    total_ret_12m = ((price - first_price + dist_sum_all) / first_price) * 100

    return {
        'price'        : round(price, 2),
        'chg_3m'       : round(chg_3m, 2),
        'chg_12m'      : round(chg_12m, 2),
        'sharpe'       : round(sharpe, 2),
        'yield_ttm'    : round(yield_ttm, 2),
        'dist_slope'   : round(dist_slope, 2),
        'dist_consist' : round(dist_consist, 2),
        'n_dists'      : n_dists,
        'total_ret_12m': round(total_ret_12m, 2),
    }


def resolve_underlying(underlying):
    """Map an underlying label to a fetchable ticker, or None for themes."""
    if underlying in UNDERLYING_PROXY:
        return UNDERLYING_PROXY[underlying]
    return underlying


def underlying_rs_from_series(und_close, spy_close):
    """Blended relative return of underlying vs SPY: 0.5 * 3m + 0.5 * 12m.

    Positive = underlying outperforming SPY. Percentage points.
    Returns None if either series is too short.
    """
    und = und_close.dropna()
    spy = spy_close.dropna()
    if len(und) < 63 or len(spy) < 63:
        return None

    def _rel(n):
        u = (und.iloc[-1] / und.iloc[-min(n, len(und))] - 1) * 100
        s = (spy.iloc[-1] / spy.iloc[-min(n, len(spy))] - 1) * 100
        return float(u - s)

    rel_3m  = _rel(63)
    rel_12m = _rel(min(252, len(und)))
    return round(0.5 * rel_3m + 0.5 * rel_12m, 2)


def fetch_underlying_rs(underlyings, metadata=None):
    """Fetch 12m history for each unique underlying proxy and compute RS vs SPY.

    Returns {underlying_label: rs or None}.
    """
    metadata = {} if metadata is None else metadata
    proxies = {}
    for u in underlyings:
        t = resolve_underlying(u)
        if t:
            proxies[u] = t

    try:
        _px.prefetch(['SPY'] + list(proxies.values()))
        spy_close = _px.adj_close('SPY', 1)
        if spy_close is None:
            raise ValueError('no SPY data')
        metadata['SPY'] = {'first_price_date': spy_close.index[0].isoformat(), 'last_price_date': spy_close.index[-1].isoformat(), 'basis': 'adjusted close'}
    except Exception:
        return {u: None for u in underlyings}

    rs = {}
    for label, ticker in proxies.items():
        try:
            und_close = _px.adj_close(ticker, 1)
            rs[label] = underlying_rs_from_series(und_close, spy_close) if und_close is not None else None
            metadata[ticker] = {'first_price_date': und_close.index[0].isoformat(), 'last_price_date': und_close.index[-1].isoformat(), 'basis': 'adjusted close'} if und_close is not None and len(und_close) else None
        except Exception:
            rs[label] = None
    for u in underlyings:
        if u not in rs:
            rs[u] = None
    return rs


def fetch_etf_data(ticker):
    """Fetch 12m price history and distributions for one ETF."""
    try:
        hist = _px.history(ticker, 1)
        if hist is None or len(hist) < 63:
            return None

        close = hist['Close'].dropna()
        divs = hist['Dividends']
        divs = divs[divs > 0]
        # limit to last 12 months
        if divs is not None and len(divs) > 0:
            cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
            divs = divs[divs.index >= cutoff]

        metrics = compute_metrics(close, divs)
        if metrics is not None:
            metrics['source_data'] = {
                'first_price_date': close.index[0].isoformat(), 'last_price_date': close.index[-1].isoformat(),
                'price_bars': len(close), 'distribution_count': len(divs),
                'basis': hist.attrs.get('provenance', {'source': 'legacy ETF price adapter; exact split adjustment not recorded'}),
                'true_fund_nav': False,
            }
        return metrics
    except Exception as e:
        print(f"  {ticker}: error — {e}")
        return None


def score_universe(data, weights=None):
    """Rank-based composite scoring. Higher = better."""
    weights = WEIGHTS if weights is None else weights
    df = pd.DataFrame(data).T
    if df.empty:
        return df

    # underlying RS: themes/missing get 0 (= matching SPY, neutral)
    if 'underlying_rs' not in df.columns:
        df['underlying_rs'] = 0.0
    df['underlying_rs'] = pd.to_numeric(df['underlying_rs'], errors='coerce').fillna(0.0)

    # rank each component (pct=True gives 0-1, higher is better)
    df['r_nav3']    = df['chg_3m'].rank(pct=True)
    df['r_nav12']   = df['chg_12m'].rank(pct=True)
    df['r_sharpe']  = df['sharpe'].rank(pct=True)
    df['r_yield']   = df['yield_ttm'].rank(pct=True)
    df['r_slope']   = df['dist_slope'].rank(pct=True)
    df['r_consist'] = df['dist_consist'].rank(pct=True)
    df['r_und']     = df['underlying_rs'].rank(pct=True)

    df['score'] = (
        df['r_nav3']    * weights['nav_3m'] +
        df['r_nav12']   * weights['nav_12m'] +
        df['r_sharpe']  * weights['sharpe'] +
        df['r_yield']   * weights['yield_ttm'] +
        df['r_slope']   * weights['dist_slope'] +
        df['r_consist'] * weights['dist_consist'] +
        df['r_und']     * weights['underlying_rs']
    ) * 100

    # disqualify: negative 3m NAV change
    df['qualified'] = df['chg_3m'] > 0

    df = df.sort_values('score', ascending=False)
    df['rank'] = range(1, len(df) + 1)
    return df


def run():
    strategy = load_strategy(SETTINGS_FILE)
    if not strategy['valid_for_review']:
        raise ValueError('Invalid ETF settings: ' + '; '.join(strategy['warnings']))
    universe = {ticker: details for ticker, details in FULL_UNIVERSE.items()
                if ticker not in strategy['effective']['excluded']}
    today = datetime.today().strftime('%Y%m%d')
    _px.prefetch(list(universe.keys()))

    # underlying RS vs SPY (one fetch per unique underlying)
    uniq_und = sorted({u for _, u, _ in universe.values()})
    print(f"Fetching underlying RS for {len(uniq_und)} underlyings...")
    underlying_sources = {}
    und_rs = fetch_underlying_rs(uniq_und, metadata=underlying_sources)
    for u in uniq_und:
        v = und_rs.get(u)
        print(f"  {u}: {'n/a (neutral)' if v is None else f'{v:+.1f} vs SPY'}")

    print(f"\nFetching {len(universe)} income ETFs...")
    data = {}
    for ticker, (name, underlying, freq) in universe.items():
        d = fetch_etf_data(ticker)
        if d is None:
            print(f"  {ticker}: no data — skipped")
            continue
        d['name'] = name
        d['underlying'] = underlying
        d['freq'] = freq
        d['underlying_rs'] = und_rs.get(underlying)
        data[ticker] = d
        flag = 'OK' if d['chg_3m'] > 0 else 'NEG-NAV'
        print(f"  {ticker}: {d['chg_3m']:+.1f}% 3m, yield {d['yield_ttm']:.1f}%, "
              f"slope {d['dist_slope']:+.2f}%/pd  [{flag}]")

    df = score_universe(data, weights=strategy['effective']['weights'])
    if df.empty:
        print("No data fetched")
        return

    cols = ['rank', 'name', 'underlying', 'freq', 'price', 'score', 'qualified',
            'chg_3m', 'chg_12m', 'total_ret_12m', 'sharpe', 'yield_ttm',
            'dist_slope', 'dist_consist', 'underlying_rs', 'n_dists',
            'r_nav3', 'r_nav12', 'r_sharpe', 'r_yield', 'r_slope', 'r_consist', 'r_und']
    out = df[cols].reset_index().rename(columns={'index': 'ticker'})

    try:
        from .income_store import save_generation
    except ImportError:
        from etf.income_store import save_generation
    artifact = save_generation('etf_income', {'rankings': out}, {'strategy': strategy},
        sources={'per_ticker': {ticker: d.get('source_data') for ticker, d in data.items()},
                 'missing_tickers': sorted(set(universe) - set(data)),
                 'underlying_rs_sources': underlying_sources,
                 'underlying_rs_before_neutral_fill': und_rs,
                 'missing_underlying_rs': [u for u in uniq_und if resolve_underlying(u) and und_rs.get(u) is None],
                 'metric': '3-month market-price trend proxy; not verified fund NAV'})
    out.attrs['income_run'] = artifact
    print(f"Immutable Income run: {artifact['run_id']}")
    print(f"\nSaved: marketdb frame etf_income/{today}")

    q = out[out['qualified'] == True]
    print(f"\nQualified (positive 3m NAV): {len(q)} of {len(out)}")
    print(q[['rank', 'ticker', 'score', 'chg_3m', 'yield_ttm', 'dist_slope']].head(15).to_string(index=False))
    return out


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run()
