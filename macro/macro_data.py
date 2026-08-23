import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
from fredapi import Fred
from datetime import datetime, timedelta
try:
    from _config_check import fred_api_key          # cwd = macro/
except ImportError:
    from macro._config_check import fred_api_key    # imported from the repo root
FRED_API_KEY = fred_api_key()                       # exits with setup steps if config.py is missing

fred     = Fred(api_key=FRED_API_KEY)
TODAY    = datetime.today()
START_1Y = (TODAY - timedelta(days=365)).strftime('%Y-%m-%d')
START_3M = (TODAY - timedelta(days=200)).strftime('%Y-%m-%d')

SNAPSHOT_FILE = 'results/macro_snapshot_prev.json'

# ── Fetch FRED data ───────────────────────────────────────────────────────────
def get_fred(series_id):
    try:
        data = fred.get_series(series_id)
        data = data.dropna()
        return data
    except Exception as e:
        print(f"FRED error {series_id}: {e}")
        return None

def latest_fred(series_id):
    data = get_fred(series_id)
    if data is None:
        return None
    return round(float(data.iloc[-1]), 4)

def change_fred(series_id):
    data = get_fred(series_id)
    if data is None or len(data) < 2:
        return None
    return round(float(data.iloc[-1] - data.iloc[-2]), 4)

# ── Price data: marketdb store first, yfinance fallback ──────────────────────
# Every macro ticker is registered in the store under role 'macro' and refreshed by the
# daily marketdb run, so a macro report normally makes no Yahoo calls at all. Anything
# missing (new ticker, store not yet built) falls back to a single yfinance download.
import sys as _sys
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in _sys.path:
    _sys.path.insert(0, _BASE)
try:
    from marketdb import prices as _mp, fetch as _mf, db as _mdb
    _STORE = True
except Exception as _e:  # marketdb unavailable -> pure yfinance behaviour
    print(f"marketdb unavailable ({_e}); using yfinance directly")
    _STORE = False

_PRICE_CACHE = {}


def _store_close(ticker, start):
    """Adjusted-close Series from the store, refreshed from Yahoo if it is missing or stale."""
    if not _STORE:
        return None
    try:
        s = _mp.get_prices([ticker], start, None)[ticker].dropna()
        stale_cut = (datetime.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        if s.empty or s.index[-1].strftime('%Y-%m-%d') < stale_cut:
            with _mdb.session() as con:
                _mf.ensure_securities([ticker], con, role='macro')
                _mf.update_prices([ticker], con, log=lambda m: None)
            s = _mp.get_prices([ticker], start, None)[ticker].dropna()
        return s if not s.empty else None
    except Exception as e:
        print(f"marketdb read error {ticker}: {e}")
        return None


def get_price(ticker, start=None):
    start = start or START_3M
    key = (ticker, start)
    if key in _PRICE_CACHE:
        return _PRICE_CACHE[key]
    data = _store_close(ticker, start)
    if data is None:
        try:
            df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
            data = None if df.empty else df['Close']
        except Exception as e:
            print(f"yfinance error {ticker}: {e}")
            data = None
    _PRICE_CACHE[key] = data
    return data

def latest_price(ticker):
    data = get_price(ticker)
    if data is None or len(data) == 0:
        return None
    val = data.iloc[-1]
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    return round(float(val), 4)

def price_change_pct(ticker, periods=5):
    data = get_price(ticker)
    if data is None or len(data) < periods:
        return None
    end   = data.iloc[-1]
    start = data.iloc[-periods]
    if isinstance(end, pd.Series):
        end = end.iloc[0]
    if isinstance(start, pd.Series):
        start = start.iloc[0]
    return round(float((end / start - 1) * 100), 2)

# ── Snapshot and alerts ───────────────────────────────────────────────────────
def save_snapshot(data):
    """Rolling 'previous run' snapshot -> marketdb reports(kind='macro_snapshot', date='latest'),
    plus a dated copy for history."""
    snapshot = {k: v for k, v in data.items() if v is not None}
    from marketdb import results as _mr
    _mr.save_report('macro_snapshot', 'latest', payload=snapshot)
    _mr.save_report('macro_snapshot', datetime.today().strftime('%Y-%m-%d'), payload=snapshot)

def load_snapshot():
    try:
        from marketdb import results as _mr
        _, payload, _ = _mr.load_report('macro_snapshot', 'latest')
        if payload:
            return payload
    except Exception as e:
        print(f"marketdb snapshot read error: {e}")
    if os.path.exists(SNAPSHOT_FILE):          # legacy file, first run after migration
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return {}

def get_change_alerts(data, prev):
    alerts = []
    checks = [
        ('us10y',         'US10Y',         0.10, 0.25, 'pts'),
        ('us02y',         'US2Y',          0.10, 0.25, 'pts'),
        ('yield_curve',   'Yield Curve',   0.10, 0.25, 'pts'),
        ('hy_spread',     'HY Spread',     0.20, 0.50, 'pts'),
        ('ig_spread',     'IG Spread',     0.20, 0.50, 'pts'),
        ('vix',           'VIX',           3.0,  5.0,  'pts'),
        ('dxy',           'DXY',           0.5,  1.5,  'pts'),
        ('gold',          'Gold',          1.0,  3.0,  '%'),
        ('copper',        'Copper',        1.0,  3.0,  '%'),
        ('oil',           'Oil',           1.0,  3.0,  '%'),
        ('spx',           'SPX',           0.5,  2.0,  '%'),
        ('cu_gold_ratio', 'Cu/Gold Ratio', 3.0,  6.0,  '%'),
        ('yc_roc_5d',     'Yield Curve V', 0.15, 0.30, 'pts'),
    ]

    for key, label, notable, alert, unit in checks:
        curr     = data.get(key)
        prev_val = prev.get(key)
        if curr is None or prev_val is None:
            continue

        if unit == '%':
            chg = ((curr - prev_val) / prev_val) * 100
        else:
            chg = curr - prev_val

        abs_chg   = abs(chg)
        direction = '▲' if chg > 0 else '▼'

        if abs_chg >= alert:
            alerts.append(f"  ⚠ ALERT  {label:<15} {direction} {abs(round(chg,2))}{unit} (prev: {round(prev_val,2)} → now: {round(curr,2)})")
        elif abs_chg >= notable:
            alerts.append(f"  → WATCH  {label:<15} {direction} {abs(round(chg,2))}{unit} (prev: {round(prev_val,2)} → now: {round(curr,2)})")

    return alerts

# ── Format helpers ────────────────────────────────────────────────────────────
def fmt(val, suffix='', decimals=2):
    if val is None:
        return 'n/a'
    return f"{round(val, decimals)}{suffix}"

def fmt_chg(val):
    if val is None:
        return 'n/a'
    arrow = '▲' if val > 0 else '▼'
    return f"{arrow} {abs(val):.2f}%"

# ── Collect all macro data ────────────────────────────────────────────────────
def collect_macro_data():
    print("Fetching macro data...")
    data = {}

    # Rates
    print("  Rates...")
    data['us10y']       = latest_fred('DGS10')
    data['us02y']       = latest_fred('DGS2')
    data['us03m']       = latest_fred('DGS3MO')
    data['yield_curve'] = latest_fred('T10Y2Y')
    data['fed_funds']   = latest_fred('FEDFUNDS')
    data['au10y']       = latest_fred('IRLTLT01AUM156N')

    # Yield trends
    print("  Yield trends...")
    us10y_series = get_fred('DGS10')
    us02y_series = get_fred('DGS2')
    if us10y_series is not None and len(us10y_series) >= 63:
        data['us10y_trend'] = 'RISING' if us10y_series.iloc[-1] > us10y_series.iloc[-63] else 'FALLING'
        data['us10y_chg_3m']= round(float(us10y_series.iloc[-1] - us10y_series.iloc[-63]), 2)
    if us02y_series is not None and len(us02y_series) >= 63:
        data['us02y_trend'] = 'RISING' if us02y_series.iloc[-1] > us02y_series.iloc[-63] else 'FALLING'
        data['us02y_chg_3m']= round(float(us02y_series.iloc[-1] - us02y_series.iloc[-63]), 2)

    # Fed balance sheet
    print("  Fed balance sheet...")
    data['fed_bs'] = latest_fred('WALCL')

    # Inflation
    print("  Inflation...")
    data['cpi_us']  = latest_fred('CPIAUCSL')
    data['cpi_pct'] = latest_fred('CPIAUCNS')
    cpi_series = get_fred('CPIAUCSL')
    if cpi_series is not None and len(cpi_series) >= 13:
        data['cpi_yoy'] = round(float((cpi_series.iloc[-1] / cpi_series.iloc[-13] - 1) * 100), 2)

    # Credit spreads
    print("  Credit spreads...")
    data['hy_spread'] = latest_fred('BAMLH0A0HYM2')
    data['ig_spread'] = latest_fred('BAMLC0A0CMEY')

    # Economic indicators
    print("  Economic indicators...")
    data['unemployment']       = latest_fred('UNRATE')
    data['nfp']                = latest_fred('PAYEMS')
    data['pmi']                = None
    data['pmi_manual']         = 50.3
    data['consumer_sentiment'] = latest_fred('UMCSENT')

    # Commodities
    print("  Commodities...")
    data['gold']          = latest_price('GC=F')
    data['silver']        = latest_price('SI=F')
    data['copper']        = latest_price('HG=F')
    data['oil']           = latest_price('CL=F')
    data['gold_chg_5d']   = price_change_pct('GC=F', 5)
    data['copper_chg_5d'] = price_change_pct('HG=F', 5)
    data['oil_chg_5d']    = price_change_pct('CL=F', 5)

    # Equities
    print("  Equities...")
    data['spx']          = latest_price('^GSPC')
    data['ndx']          = latest_price('^NDX')
    data['iwm']          = latest_price('IWM')
    data['spx_chg_5d']   = price_change_pct('^GSPC', 5)
    data['ndx_chg_5d']   = price_change_pct('^NDX', 5)
    data['cape_manual']  = 37.5
    data['itb']          = latest_price('ITB')
    data['itb_chg_63d']  = price_change_pct('ITB', 63)
    data['itb_chg_126d'] = price_change_pct('ITB', 126)

    # Presidential Election Cycle
    print("  Presidential cycle...")
    CYCLE_START = '2024-11-01'
    spx_cycle   = get_price('^GSPC')

    if spx_cycle is not None:
        spx_full = get_price('^GSPC', start=CYCLE_START)
        if spx_full is not None and not spx_full.empty:
            spx_val_start = float(spx_full.iloc[0].iloc[0] if isinstance(spx_full.iloc[0], pd.Series) else spx_full.iloc[0])
            spx_val_now   = float(spx_full.iloc[-1].iloc[0] if isinstance(spx_full.iloc[-1], pd.Series) else spx_full.iloc[-1])

            data['pres_cycle_ret'] = round((spx_val_now / spx_val_start - 1) * 100, 2)

            rolling_max = spx_full.cummax()
            drawdowns   = (spx_full - rolling_max) / rolling_max
            if isinstance(drawdowns, pd.DataFrame):
                drawdowns = drawdowns.iloc[:, 0]
            data['pres_cycle_dd']  = round(float(drawdowns.min() * 100), 2)

            cycle_high  = float(spx_full.max().iloc[0] if isinstance(spx_full.max(), pd.Series) else spx_full.max())
            data['pres_cycle_high']   = round(cycle_high, 2)
            data['pres_cycle_dd_now'] = round((spx_val_now / cycle_high - 1) * 100, 2)

            from datetime import date
            start_date = date(2024, 11, 1)
            data['pres_cycle_days'] = (date.today() - start_date).days
            data['pres_cycle_year'] = min(4, (data['pres_cycle_days'] // 365) + 1)

    # Consumer ratios
    print("  Consumer ratios...")
    xly  = get_price('XLY')
    xlp  = get_price('XLP')
    rspd = get_price('RSPD')
    rsps = get_price('RSPS')

    if xly is not None and xlp is not None:
        aligned = pd.concat([xly, xlp], axis=1).dropna()
        aligned.columns = ['xly', 'xlp']
        data['xly_xlp']         = round(float(aligned['xly'].iloc[-1] / aligned['xlp'].iloc[-1]), 4)
        data['xly_xlp_chg_5d']  = round(float((aligned['xly'].iloc[-1] / aligned['xly'].iloc[-5])  / (aligned['xlp'].iloc[-1] / aligned['xlp'].iloc[-5])  - 1) * 100, 2) if len(aligned) >= 5  else None
        data['xly_xlp_chg_63d'] = round(float((aligned['xly'].iloc[-1] / aligned['xly'].iloc[-63]) / (aligned['xlp'].iloc[-1] / aligned['xlp'].iloc[-63]) - 1) * 100, 2) if len(aligned) >= 63 else None

    if rspd is not None and rsps is not None:
        aligned = pd.concat([rspd, rsps], axis=1).dropna()
        aligned.columns = ['rspd', 'rsps']
        data['rspd_rsps']         = round(float(aligned['rspd'].iloc[-1] / aligned['rsps'].iloc[-1]), 4)
        data['rspd_rsps_chg_5d']  = round(float((aligned['rspd'].iloc[-1] / aligned['rspd'].iloc[-5])  / (aligned['rsps'].iloc[-1] / aligned['rsps'].iloc[-5])  - 1) * 100, 2) if len(aligned) >= 5  else None
        data['rspd_rsps_chg_63d'] = round(float((aligned['rspd'].iloc[-1] / aligned['rspd'].iloc[-63]) / (aligned['rsps'].iloc[-1] / aligned['rsps'].iloc[-63]) - 1) * 100, 2) if len(aligned) >= 63 else None

    # US sector ETFs
    print("  US sectors...")
    us_sectors = ['XLE','XLK','XLY','XLF','XLI','XLB','XLU','XLP','XLV','XLC','XLRE']
    for s in us_sectors:
        data[f'{s.lower()}_chg_63d'] = price_change_pct(s, 63)
        data[f'{s.lower()}_chg_20d'] = price_change_pct(s, 20)

    # ASX sectors
    print("  ASX sectors...")
    asx_sector_map = {
        'xej': '^AXEJ',
        'xij': '^AXIJ',
        'xmj': '^AXMJ',
        'xfj': '^AXFJ',
        'xdj': '^AXDJ',
        'xnj': '^AXNJ',
        'xhj': '^AXHJ',
        'xsj': '^AXSJ',
        'xuj': '^AXUJ',
        'xtj': '^AXTJ',
    }
    for key, ticker in asx_sector_map.items():
        data[f'{key}_chg_63d'] = price_change_pct(ticker, 63)
        data[f'{key}_chg_20d'] = price_change_pct(ticker, 20)

    # Risk on/off ratio
    print("  Risk on/off ratio...")
    xlk  = get_price('XLK')
    xlc  = get_price('XLC')
    xly2 = get_price('XLY')
    xlu  = get_price('XLU')
    xlp2 = get_price('XLP')
    xlv  = get_price('XLV')

    if all(x is not None for x in [xlk, xlc, xly2, xlu, xlp2, xlv]):
        aligned = pd.concat([xlk, xlc, xly2, xlu, xlp2, xlv], axis=1).dropna()
        aligned.columns = ['xlk', 'xlc', 'xly', 'xlu', 'xlp', 'xlv']
        aligned['risk_on']  = aligned['xlk'] + aligned['xlc'] + aligned['xly']
        aligned['risk_off'] = aligned['xlu'] + aligned['xlp'] + aligned['xlv']
        aligned['ratio']    = aligned['risk_on'] / aligned['risk_off']
        data['risk_ratio']         = round(float(aligned['ratio'].iloc[-1]), 4)
        data['risk_ratio_chg_5d']  = round(float((aligned['ratio'].iloc[-1] / aligned['ratio'].iloc[-5]  - 1) * 100), 2) if len(aligned) >= 5  else None
        data['risk_ratio_chg_10d'] = round(float((aligned['ratio'].iloc[-1] / aligned['ratio'].iloc[-10] - 1) * 100), 2) if len(aligned) >= 10 else None

    # Cycle ratios
    print("  Cycle ratios...")
    xlf   = get_price('XLF')
    xli   = get_price('XLI')
    xlb   = get_price('XLB')
    xle   = get_price('XLE')
    xlu2  = get_price('XLU')
    xlp3  = get_price('XLP')
    xlv2  = get_price('XLV')
    spx2  = get_price('^GSPC')
    iwm2  = get_price('IWM')
    xly3  = get_price('XLY')

    def calc_ratio_trend(num, den, label):
        if num is None or den is None:
            return
        aligned = pd.concat([num, den], axis=1).dropna()
        aligned.columns = ['num', 'den']
        aligned['ratio'] = aligned['num'] / aligned['den']
        if len(aligned) < 63:
            return
        data[f'{label}_ratio']   = round(float(aligned['ratio'].iloc[-1]), 4)
        data[f'{label}_chg_5d']  = round(float((aligned['ratio'].iloc[-1] / aligned['ratio'].iloc[-5]  - 1) * 100), 2)
        data[f'{label}_chg_20d'] = round(float((aligned['ratio'].iloc[-1] / aligned['ratio'].iloc[-20] - 1) * 100), 2)
        data[f'{label}_chg_63d'] = round(float((aligned['ratio'].iloc[-1] / aligned['ratio'].iloc[-63] - 1) * 100), 2)

    calc_ratio_trend(xly3,  xlp3,  'cyc_xly_xlp')
    calc_ratio_trend(xlf,   xlu2,  'cyc_xlf_xlu')
    calc_ratio_trend(xlk,   spx2,  'cyc_xlk_spx')
    calc_ratio_trend(xli,   spx2,  'cyc_xli_spx')
    calc_ratio_trend(xlb,   spx2,  'cyc_xlb_spx')
    calc_ratio_trend(xle,   spx2,  'cyc_xle_spx')
    calc_ratio_trend(xlp3,  spx2,  'cyc_xlp_spx')
    calc_ratio_trend(xlu2,  spx2,  'cyc_xlu_spx')
    calc_ratio_trend(xlv2,  spx2,  'cyc_xlv_spx')
    calc_ratio_trend(iwm2,  spx2,  'cyc_iwm_spx')
    calc_ratio_trend(xlf,   spx2,  'cyc_xlf_spx')

    # Volatility
    print("  Volatility...")
    data['vix']  = latest_price('^VIX')
    data['vvix'] = latest_price('^VVIX')
    if data['vix'] and data['vvix']:
        data['vix_vvix'] = round(data['vix'] / data['vvix'], 4)
    else:
        data['vix_vvix'] = None
    data['dxy'] = latest_price('DX-Y.NYB')

    # Ratios
    print("  Ratios...")
    gold_prices   = get_price('GC=F')
    spx_prices    = get_price('^GSPC')
    copper_prices = get_price('HG=F')

    if gold_prices is not None and spx_prices is not None:
        aligned = pd.concat([gold_prices, spx_prices], axis=1).dropna()
        aligned.columns = ['gold', 'spx']
        data['gold_spx_ratio'] = round(float(aligned['gold'].iloc[-1] / aligned['spx'].iloc[-1]), 4)

    if gold_prices is not None and copper_prices is not None:
        aligned = pd.concat([gold_prices, copper_prices], axis=1).dropna()
        aligned.columns = ['gold', 'copper']
        data['gold_copper_ratio'] = round(float(aligned['gold'].iloc[-1] / aligned['copper'].iloc[-1]), 4)

    # Valuation ratios
    print("  Valuation ratios...")
    m2_series     = get_fred('M2SL')
    margin_series = get_fred('MVGFD027MNFRBDAL')

    if m2_series is not None and spx_prices is not None:
        m2_latest = float(m2_series.iloc[-1])
        spx_val   = spx_prices.iloc[-1]
        if isinstance(spx_val, pd.Series):
            spx_val = spx_val.iloc[0]
        data['m2_latest'] = round(m2_latest, 0)
        data['spx_m2']    = round(float(spx_val) / m2_latest, 4)

    if margin_series is not None and m2_series is not None:
        aligned = pd.concat([margin_series, m2_series], axis=1).dropna()
        aligned.columns = ['margin', 'm2']
        data['margin_debt'] = round(float(aligned['margin'].iloc[-1]), 0)
        data['margin_m2']   = round(float(aligned['margin'].iloc[-1] / aligned['m2'].iloc[-1]), 4)

    if margin_series is not None:
        margin_clean = margin_series.dropna()
        if len(margin_clean) >= 3:
            data['margin_chg_1m'] = round(float((margin_clean.iloc[-1] / margin_clean.iloc[-2] - 1) * 100), 2)
        if len(margin_clean) >= 4:
            data['margin_chg_3m'] = round(float((margin_clean.iloc[-1] / margin_clean.iloc[-3] - 1) * 100), 2)
        data['margin_peak']      = round(float(margin_clean.max()), 0)
        data['margin_from_peak'] = round(float((margin_clean.iloc[-1] / margin_clean.max() - 1) * 100), 2)

    # Buffett indicator
    print("  Buffett indicator...")
    wilshire = get_fred('NCBEILQ027S')
    gdp      = get_fred('GDP')

    if wilshire is not None and gdp is not None:
        aligned = pd.concat([wilshire, gdp], axis=1, sort=True).dropna()
        aligned.columns = ['wilshire', 'gdp']
        data['buffett'] = round(float((aligned['wilshire'].iloc[-1] / 1000) / aligned['gdp'].iloc[-1]) * 100, 2)

    # ── Copper/Gold ratio ROC ─────────────────────────────────────────────────
    print("  Copper/Gold ratio ROC...")
    if gold_prices is not None and copper_prices is not None and len(gold_prices) > 0 and len(copper_prices) > 0:
        aligned_cg = pd.concat([copper_prices, gold_prices], axis=1).dropna()
        aligned_cg.columns = ['copper', 'gold']
        aligned_cg['cu_gold'] = aligned_cg['copper'] / aligned_cg['gold']
        if len(aligned_cg) >= 6:
            data['cu_gold_ratio']  = round(float(aligned_cg['cu_gold'].iloc[-1]), 6)
            data['cu_gold_chg_5d'] = round(float((aligned_cg['cu_gold'].iloc[-1] / aligned_cg['cu_gold'].iloc[-6]  - 1) * 100), 2)
        if len(aligned_cg) >= 22:
            data['cu_gold_chg_21d'] = round(float((aligned_cg['cu_gold'].iloc[-1] / aligned_cg['cu_gold'].iloc[-22] - 1) * 100), 2)
        if len(aligned_cg) >= 64:
            data['cu_gold_chg_63d'] = round(float((aligned_cg['cu_gold'].iloc[-1] / aligned_cg['cu_gold'].iloc[-64] - 1) * 100), 2)

    # ── Yield curve velocity ──────────────────────────────────────────────────
    print("  Yield curve velocity...")
    yc_series = get_fred('T10Y2Y')
    if yc_series is not None:
        yc_clean = yc_series.dropna()
        if len(yc_clean) >= 6:
            data['yc_roc_5d']  = round(float(yc_clean.iloc[-1] - yc_clean.iloc[-6]),  4)
        if len(yc_clean) >= 22:
            data['yc_roc_21d'] = round(float(yc_clean.iloc[-1] - yc_clean.iloc[-22]), 4)

    # ── Margin debt acceleration ──────────────────────────────────────────────
    margin_1m = data.get('margin_chg_1m')
    margin_3m = data.get('margin_chg_3m')
    if margin_1m is not None and margin_3m is not None:
        data['margin_acceleration'] = round(margin_1m - (margin_3m / 3), 4)

    # ── A/D line divergence from breadth history ──────────────────────────────
    print("  A/D line divergence...")
    try:
        from marketdb import results as _mr
        bh_all = _mr.breadth_history('us_total_market')
    except Exception as e:
        print(f"  breadth read error: {e}")
        bh_all = None
    if bh_all is not None and len(bh_all):
        try:
            bh = bh_all.tail(63).copy()
            if len(bh) >= 22 and 'leader' in bh.columns and 'laggard' in bh.columns and 'weak' in bh.columns:
                bh['ad_daily'] = bh['leader'].astype(int) - bh['laggard'].astype(int) - bh['weak'].astype(int)
                bh['ad_line']  = bh['ad_daily'].cumsum()
                ad_now   = float(bh['ad_line'].iloc[-1])
                ad_21d   = float(bh['ad_line'].iloc[-22])
                ad_trend = 'RISING' if ad_now > ad_21d else 'FALLING'
                data['ad_line_now'] = round(ad_now, 0)
                data['ad_trend']    = ad_trend

                if spx_prices is not None and len(spx_prices) >= 22:
                    spx_now = spx_prices.iloc[-1]
                    spx_21d = spx_prices.iloc[-22]
                    if isinstance(spx_now, pd.Series): spx_now = spx_now.iloc[0]
                    if isinstance(spx_21d, pd.Series): spx_21d = spx_21d.iloc[0]
                    spx_trend = 'RISING' if float(spx_now) > float(spx_21d) else 'FALLING'

                    if ad_trend == 'RISING' and spx_trend == 'FALLING':
                        data['ad_divergence'] = 'BULLISH — breadth improving while price falls'
                    elif ad_trend == 'FALLING' and spx_trend == 'RISING':
                        data['ad_divergence'] = 'BEARISH — breadth deteriorating while price rises'
                    else:
                        data['ad_divergence'] = f'CONFIRMING — breadth and price both {spx_trend}'
        except Exception as e:
            print(f"  A/D line error: {e}")

    print("Done.")
    return data

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    data = collect_macro_data()
    for k, v in data.items():
        print(f"  {k:<25} {v}")