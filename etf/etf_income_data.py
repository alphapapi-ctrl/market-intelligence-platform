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

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE, 'results', 'etf_income')

# ── Universe ──────────────────────────────────────────────────────────────────
# ticker: (name, underlying/theme, pay frequency)
UNIVERSE = {
    # YieldMax single-stock covered call
    'TSLY': ('YieldMax TSLA', 'TSLA', 'weekly'),
    'NVDY': ('YieldMax NVDA', 'NVDA', 'weekly'),
    'CONY': ('YieldMax COIN', 'COIN', 'weekly'),
    'MSTY': ('YieldMax MSTR', 'MSTR', 'weekly'),
    'AMZY': ('YieldMax AMZN', 'AMZN', 'weekly'),
    'APLY': ('YieldMax AAPL', 'AAPL', 'weekly'),
    'GOOY': ('YieldMax GOOGL', 'GOOGL', 'weekly'),
    'MSFO': ('YieldMax MSFT', 'MSFT', 'weekly'),
    'AMDY': ('YieldMax AMD', 'AMD', 'weekly'),
    'PYPY': ('YieldMax PYPL', 'PYPL', 'weekly'),
    'MRNY': ('YieldMax MRNA', 'MRNA', 'weekly'),
    'AIYY': ('YieldMax AI', 'AI', 'weekly'),
    'ULTY': ('YieldMax Ultra', 'diversified', 'weekly'),
    'YMAX': ('YieldMax Universe FoF', 'diversified', 'weekly'),
    'YMAG': ('YieldMax Mag7 FoF', 'mag7', 'weekly'),
    'XOMO': ('YieldMax XOM', 'XOM', 'weekly'),
    'JPMO': ('YieldMax JPM', 'JPM', 'weekly'),
    # Defiance index income
    'QQQY': ('Defiance Nasdaq Income', 'QQQ', 'weekly'),
    'IWMY': ('Defiance R2K Income', 'IWM', 'weekly'),
    'SPYT': ('Defiance S&P Target Income', 'SPY', 'monthly'),
    # Roundhill
    'QDTE': ('Roundhill Nasdaq 0DTE', 'QQQ', 'weekly'),
    'XDTE': ('Roundhill S&P 0DTE', 'SPY', 'weekly'),
    'RDTE': ('Roundhill R2K 0DTE', 'IWM', 'weekly'),
    # Monthly payers — index covered call / premium income
    'JEPI': ('JPM Equity Premium Income', 'SPX', 'monthly'),
    'JEPQ': ('JPM Nasdaq Premium Income', 'NDX', 'monthly'),
    'QYLD': ('Global X Nasdaq Covered Call', 'NDX', 'monthly'),
    'XYLD': ('Global X S&P Covered Call', 'SPX', 'monthly'),
    'RYLD': ('Global X R2K Covered Call', 'RUT', 'monthly'),
    'DIVO': ('Amplify CWP Enhanced Div', 'diversified', 'monthly'),
    'SVOL': ('Simplify Volatility Premium', 'VIX-short', 'monthly'),
    'SPYI': ('NEOS S&P High Income', 'SPX', 'monthly'),
    'QQQI': ('NEOS Nasdaq High Income', 'NDX', 'monthly'),
}

# Full universe before exclusions — the Settings UI needs this to edit the blocklist
FULL_UNIVERSE = dict(UNIVERSE)

# ── Settings (etf_settings.json overrides the defaults below) ─────────────────
SETTINGS_FILE = os.path.join(BASE, 'etf_settings.json')

DEFAULT_EXCLUDED = ['MSTY']   # extreme NAV decay on leveraged-equity underlying

def load_etf_settings():
    """Load strategy settings with defaults. Weights merge over defaults so a
    partial settings file stays valid."""
    s = {
        'weights'      : dict(DEFAULT_WEIGHTS),
        'excluded'     : list(DEFAULT_EXCLUDED),
        'stop_loss_pct': 0.20,   # live total-return stop from entry
        'buy_zone'     : 8,      # rank threshold for HOLD vs REVIEW signals
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                saved = json.load(f)
            s['weights'].update(saved.get('weights', {}))
            for k in ('excluded', 'stop_loss_pct', 'buy_zone'):
                if k in saved:
                    s[k] = saved[k]
        except Exception:
            pass
    return s

# NOTE: _settings is applied below, after DEFAULT_WEIGHTS is defined.

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

# ── Score weights (defaults — etf_settings.json overrides) ────────────────────
DEFAULT_WEIGHTS = {
    'nav_3m'       : 0.20,   # 3m price change rank
    'nav_12m'      : 0.10,   # 12m price change rank
    'sharpe'       : 0.15,   # 90d sharpe rank
    'yield_ttm'    : 0.10,   # trailing yield rank (deliberately low — yield alone misleads)
    'dist_slope'   : 0.15,   # distribution trend rank
    'dist_consist' : 0.10,   # distribution consistency rank
    'underlying_rs': 0.20,   # underlying's relative strength vs SPY
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


def fetch_underlying_rs(underlyings):
    """Fetch 12m history for each unique underlying proxy and compute RS vs SPY.

    Returns {underlying_label: rs or None}.
    """
    proxies = {}
    for u in underlyings:
        t = resolve_underlying(u)
        if t:
            proxies[u] = t

    try:
        spy_close = yf.Ticker('SPY').history(period='1y', auto_adjust=True)['Close']
    except Exception:
        return {u: None for u in underlyings}

    rs = {}
    for label, ticker in proxies.items():
        try:
            und_close = yf.Ticker(ticker).history(period='1y', auto_adjust=True)['Close']
            rs[label] = underlying_rs_from_series(und_close, spy_close)
        except Exception:
            rs[label] = None
    for u in underlyings:
        if u not in rs:
            rs[u] = None
    return rs


def fetch_etf_data(ticker):
    """Fetch 12m price history and distributions for one ETF."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='1y', auto_adjust=False)
        if hist is None or len(hist) < 63:
            return None

        close = hist['Close'].dropna()
        divs = t.dividends
        # limit to last 12 months
        if divs is not None and len(divs) > 0:
            cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
            divs = divs[divs.index >= cutoff]

        return compute_metrics(close, divs)
    except Exception as e:
        print(f"  {ticker}: error — {e}")
        return None


def score_universe(data):
    """Rank-based composite scoring. Higher = better."""
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
        df['r_nav3']    * WEIGHTS['nav_3m'] +
        df['r_nav12']   * WEIGHTS['nav_12m'] +
        df['r_sharpe']  * WEIGHTS['sharpe'] +
        df['r_yield']   * WEIGHTS['yield_ttm'] +
        df['r_slope']   * WEIGHTS['dist_slope'] +
        df['r_consist'] * WEIGHTS['dist_consist'] +
        df['r_und']     * WEIGHTS['underlying_rs']
    ) * 100

    # disqualify: negative 3m NAV change
    df['qualified'] = df['chg_3m'] > 0

    df = df.sort_values('score', ascending=False)
    df['rank'] = range(1, len(df) + 1)
    return df


def run():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    today = datetime.today().strftime('%Y%m%d')

    # underlying RS vs SPY (one fetch per unique underlying)
    uniq_und = sorted({u for _, u, _ in UNIVERSE.values()})
    print(f"Fetching underlying RS for {len(uniq_und)} underlyings...")
    und_rs = fetch_underlying_rs(uniq_und)
    for u in uniq_und:
        v = und_rs.get(u)
        print(f"  {u}: {'n/a (neutral)' if v is None else f'{v:+.1f} vs SPY'}")

    print(f"\nFetching {len(UNIVERSE)} income ETFs...")
    data = {}
    for ticker, (name, underlying, freq) in UNIVERSE.items():
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

    df = score_universe(data)
    if df.empty:
        print("No data fetched")
        return

    cols = ['rank', 'name', 'underlying', 'freq', 'price', 'score', 'qualified',
            'chg_3m', 'chg_12m', 'total_ret_12m', 'sharpe', 'yield_ttm',
            'dist_slope', 'dist_consist', 'underlying_rs', 'n_dists']
    out = df[cols].reset_index().rename(columns={'index': 'ticker'})

    csv_file = os.path.join(RESULTS_DIR, f"{today}_etf_income.csv")
    out.to_csv(csv_file, index=False)
    print(f"\nSaved: {csv_file}")

    q = out[out['qualified'] == True]
    print(f"\nQualified (positive 3m NAV): {len(q)} of {len(out)}")
    print(q[['rank', 'ticker', 'score', 'chg_3m', 'yield_ttm', 'dist_slope']].head(15).to_string(index=False))
    return out


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run()
