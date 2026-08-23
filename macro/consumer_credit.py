import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
try:
    from _config_check import fred_api_key, optional_key
except ImportError:
    from macro._config_check import fred_api_key, optional_key
FRED_API_KEY = fred_api_key()
ANTHROPIC_API_KEY = optional_key("ANTHROPIC_API_KEY")

from fredapi import Fred
import os as _os, sys as _sys
_MARKETDB_BASE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _MARKETDB_BASE not in _sys.path:
    _sys.path.insert(0, _MARKETDB_BASE)   # marketdb lives one level up

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', 'consumer_credit')

# ── FRED Series ───────────────────────────────────────────────────────────────
FRED_SERIES = {
    # Consumer credit
    'cc_delinquency'    : ('DRCCLACBS',   'Credit Card Delinquency Rate %'),
    'cc_chargeoff'      : ('CORCACBS',    'Credit Card Charge-Off Rate %'),
    'auto_delinquency'  : ('DRALACBS',    'Auto Loan Delinquency Rate %'),
    'mortgage_delinquency':('DRSFRMACBS', 'Mortgage Delinquency Rate %'),
    'consumer_credit'   : ('TOTALSL',     'Total Consumer Credit $B'),
    # Corporate credit (aligned with macro_data.py)
    'hy_spread'         : ('BAMLH0A0HYM2','HY OAS Spread %'),
    'ig_spread'         : ('BAMLC0A0CMEY','IG OAS Spread %'),
    # Sovereign
    'debt_gdp'          : ('GFDEGDQ188S', 'Federal Debt % GDP'),
    'deficit_gdp'       : ('FYFSGDA188S', 'Federal Deficit % GDP'),
    # Rates (aligned with macro_data.py — daily)
    'us10y'             : ('DGS10',       'US 10-Year Yield %'),
    'us02y'             : ('DGS2',        'US 2-Year Yield %'),
    'us03m'             : ('DGS3MO',      'US 3-Month Yield %'),
    'yield_curve'       : ('T10Y2Y',      '10Y-2Y Yield Curve %'),
    'fed_funds'         : ('FEDFUNDS',    'Fed Funds Rate %'),
    # Inflation (daily)
    'breakeven_5y'      : ('T5YIE',       '5Y Breakeven Inflation %'),
    'breakeven_10y'     : ('T10YIE',      '10Y Breakeven Inflation %'),
}

# ── PE/BDC ETF Tickers ────────────────────────────────────────────────────────
PE_TICKERS = {
    'BX'   : 'Blackstone',
    'KKR'  : 'KKR & Co',
    'APO'  : 'Apollo Global',
    'CG'   : 'Carlyle Group',
    'PSP'  : 'Listed PE ETF',
    'BIZD' : 'BDC ETF',
    'ARCC' : 'Ares Capital (BDC)',
    'MAIN' : 'Main Street Capital (BDC)',
    'BKLN' : 'Leveraged Loan ETF',
}

# Daily credit market ETFs and volatility
CREDIT_MARKET_TICKERS = {
    'HYG'  : 'HY Corporate Bond ETF',
    'JNK'  : 'HY Bond ETF (SPDR)',
    'LQD'  : 'IG Corporate Bond ETF',
    'TLT'  : '20+ Year Treasury ETF',
    'SHY'  : '1-3 Year Treasury ETF',
    'EMB'  : 'EM Bond ETF',
    '^MOVE': 'MOVE Index (Bond Vol)',
}

# ── Alert thresholds ──────────────────────────────────────────────────────────
THRESHOLDS = {
    'cc_delinquency'     : {'warn': 2.5,  'alert': 3.5},
    'cc_chargeoff'       : {'warn': 3.0,  'alert': 4.5},
    'auto_delinquency'   : {'warn': 1.5,  'alert': 2.5},
    'mortgage_delinquency': {'warn': 1.5, 'alert': 2.5},
    'hy_spread'          : {'warn': 4.0,  'alert': 6.0},
    'ig_spread'          : {'warn': 1.5,  'alert': 2.5},
    'debt_gdp'           : {'warn': 110,  'alert': 130},
    'breakeven_5y'       : {'warn': 2.8,  'alert': 3.5},
    'breakeven_10y'      : {'warn': 2.6,  'alert': 3.2},
    # NY Fed HHDC flow-into-delinquency (transition rates, all lenders)
    'flow90_cc'          : {'warn': 7.0,  'alert': 9.5},
    'flow90_auto'        : {'warn': 2.5,  'alert': 4.0},
    'flow90_mortgage'    : {'warn': 2.0,  'alert': 4.0},
    'flow90_student'     : {'warn': 8.0,  'alert': 12.0},
    'flow30_cc'          : {'warn': 9.0,  'alert': 12.0},
    'flow30_auto'        : {'warn': 8.5,  'alert': 10.5},
    'flow30_mortgage'    : {'warn': 5.0,  'alert': 8.0},
    'mortgage_subprime_share': {'warn': 8.0, 'alert': 12.0},
    'auto_subprime_share'    : {'warn': 22.0, 'alert': 28.0},
}

ROC_THRESHOLDS = {
    'cc_delinquency'     : {'warn': 0.15, 'alert': 0.3},
    'auto_delinquency'   : {'warn': 0.1,  'alert': 0.2},
    'mortgage_delinquency': {'warn': 0.1, 'alert': 0.2},
    'hy_spread'          : {'warn': 0.5,  'alert': 1.0},
    'flow90_cc'          : {'warn': 0.4,  'alert': 0.8},
    'flow90_auto'        : {'warn': 0.2,  'alert': 0.4},
    'flow90_mortgage'    : {'warn': 0.15, 'alert': 0.3},
}

def fetch_fred_series(fred, series_id, periods=20):
    """Fetch FRED series and return recent values"""
    try:
        data = fred.get_series(series_id)
        data = data.dropna().tail(periods)
        return data
    except Exception as e:
        print(f"FRED error for {series_id}: {e}")
        return None

def calc_roc(series):
    """Rate of change — latest vs prior period"""
    if series is None or len(series) < 2:
        return None
    return round(float(series.iloc[-1]) - float(series.iloc[-2]), 4)

def calc_roc_3m(series):
    """Rate of change over 3 periods"""
    if series is None or len(series) < 4:
        return None
    return round(float(series.iloc[-1]) - float(series.iloc[-4]), 4)

def get_alert_level(key, value, roc):
    """Return ALERT, WARN, or OK"""
    if value is None:
        return 'UNKNOWN'
    thresh = THRESHOLDS.get(key, {})
    roc_thresh = ROC_THRESHOLDS.get(key, {})

    # Check level thresholds
    if thresh:
        if value >= thresh.get('alert', 999):
            return 'ALERT'
        if value >= thresh.get('warn', 999):
            return 'WARN'

    # Check ROC thresholds
    if roc is not None and roc_thresh:
        if roc >= roc_thresh.get('alert', 999):
            return 'ALERT'
        if roc >= roc_thresh.get('warn', 999):
            return 'WARN'

    return 'OK'

def fetch_pe_data():
    """Fetch PE/BDC ETF price data"""
    tickers  = list(PE_TICKERS.keys())
    end_date = datetime.today().strftime('%Y-%m-%d')
    start    = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    results  = {}

    try:
        raw    = yf.download(tickers, start=start, end=end_date,
                             auto_adjust=True, progress=False)
        closes = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw

        if isinstance(closes.columns, pd.MultiIndex):
            closes.columns = closes.columns.get_level_values(-1)

        for ticker, name in PE_TICKERS.items():
            if ticker not in closes.columns:
                continue
            series = closes[ticker].dropna()
            if len(series) < 2:
                continue
            price    = round(float(series.iloc[-1]), 2)
            ret_1m   = round((series.iloc[-1] / series.iloc[-21] - 1) * 100, 2) if len(series) >= 21 else None
            ret_3m   = round((series.iloc[-1] / series.iloc[-63] - 1) * 100, 2) if len(series) >= 63 else None
            ret_12m  = round((series.iloc[-1] / series.iloc[-252] - 1) * 100, 2) if len(series) >= 252 else None
            results[ticker] = {
                'name'   : name,
                'price'  : price,
                'ret_1m' : ret_1m,
                'ret_3m' : ret_3m,
                'ret_12m': ret_12m,
            }
    except Exception as e:
        print(f"PE data error: {e}")

    return results

def fetch_credit_market_data():
    """Fetch daily credit ETF and MOVE index data"""
    tickers  = list(CREDIT_MARKET_TICKERS.keys())
    end_date = datetime.today().strftime('%Y-%m-%d')
    start    = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
    results  = {}

    try:
        raw    = yf.download(tickers, start=start, end=end_date,
                             auto_adjust=True, progress=False)
        closes = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw

        if isinstance(closes.columns, pd.MultiIndex):
            closes.columns = closes.columns.get_level_values(-1)

        for ticker, name in CREDIT_MARKET_TICKERS.items():
            if ticker not in closes.columns:
                continue
            series = closes[ticker].dropna()
            if len(series) < 2:
                continue
            price    = round(float(series.iloc[-1]), 2)
            ret_1w   = round((series.iloc[-1] / series.iloc[-5] - 1) * 100, 2) if len(series) >= 5 else None
            ret_1m   = round((series.iloc[-1] / series.iloc[-21] - 1) * 100, 2) if len(series) >= 21 else None
            ret_3m   = round((series.iloc[-1] / series.iloc[-63] - 1) * 100, 2) if len(series) >= 63 else None
            ret_12m  = round((series.iloc[-1] / series.iloc[-252] - 1) * 100, 2) if len(series) >= 252 else None
            results[ticker] = {
                'name'   : name,
                'price'  : price,
                'ret_1w' : ret_1w,
                'ret_1m' : ret_1m,
                'ret_3m' : ret_3m,
                'ret_12m': ret_12m,
            }
    except Exception as e:
        print(f"Credit market data error: {e}")

    return results


def run_consumer_credit():
    """Main function — fetch all data, calculate signals, save results"""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    today    = datetime.today().strftime('%Y%m%d')
    fred     = Fred(api_key=FRED_API_KEY)

    print("Fetching FRED data...")
    data     = {}
    alerts   = []

    for key, (series_id, label) in FRED_SERIES.items():
        series = fetch_fred_series(fred, series_id, periods=20)
        if series is None or len(series) == 0:
            continue

        current = round(float(series.iloc[-1]), 4)
        prior   = round(float(series.iloc[-2]), 4) if len(series) >= 2 else None
        roc     = calc_roc(series)
        roc_3m  = calc_roc_3m(series)

        # Convert consumer credit from millions to billions
        if key == 'consumer_credit':
            current = round(current / 1000, 2)
            if prior:  prior  = round(prior / 1000, 2)
            if roc:    roc    = round(roc / 1000, 2)
            if roc_3m: roc_3m = round(roc_3m / 1000, 2)

        level   = get_alert_level(key, current, roc)

        data[key] = {
            'label'       : label,
            'current'     : current,
            'prior'       : prior,
            'roc'         : roc,
            'roc_3m'      : roc_3m,
            'alert_level' : level,
            'history'     : {str(k): round(float(v), 4)
                             for k, v in series.items()},
        }

        if level in ['ALERT', 'WARN']:
            direction = '▲' if roc and roc > 0 else '▼'
            alerts.append({
                'type'   : level,
                'key'    : key,
                'message': f"{label}: {current} {direction} {roc:+.3f} qoq",
            })
            print(f"  {level}: {label} = {current} (roc: {roc:+.3f})")
        else:
            print(f"  OK: {label} = {current}")

    # NY Fed Household Debt & Credit (Equifax panel — flows lead the FRED stocks)
    print("Fetching NY Fed HHDC data...")
    hhdc_quarter = None
    try:
        try:
            from nyfed_hhdc import fetch_hhdc_series
        except ImportError:
            from macro.nyfed_hhdc import fetch_hhdc_series
        _hhdc_cache = os.path.join(RESULTS_DIR, 'hhdc_cache')
        hhdc_series, hhdc_quarter = fetch_hhdc_series(_hhdc_cache)
        for key, d in hhdc_series.items():
            series  = d['series']
            current = round(float(series.iloc[-1]), 4)
            prior   = round(float(series.iloc[-2]), 4) if len(series) >= 2 else None
            roc     = calc_roc(series)
            roc_3m  = calc_roc_3m(series)
            level   = get_alert_level(key, current, roc)

            data[key] = {
                'label'       : d['label'],
                'current'     : current,
                'prior'       : prior,
                'roc'         : roc,
                'roc_3m'      : roc_3m,
                'alert_level' : level,
                'history'     : {str(k): round(float(v), 4)
                                 for k, v in series.items()},
            }

            if level in ['ALERT', 'WARN']:
                direction = '▲' if roc and roc > 0 else '▼'
                alerts.append({
                    'type'   : level,
                    'key'    : key,
                    'message': f"{d['label']}: {current} {direction} {roc:+.3f} qoq",
                })
                print(f"  {level}: {d['label']} = {current} (roc: {roc:+.3f})")
            else:
                print(f"  OK: {d['label']} = {current}")
        if hhdc_quarter:
            print(f"  HHDC report quarter: {hhdc_quarter}")
    except Exception as e:
        print(f"NY Fed HHDC fetch failed (non-fatal): {e}")

    # PE/BDC data
    print("Fetching PE/BDC data...")
    pe_data = fetch_pe_data()

    # Credit market ETFs and MOVE
    print("Fetching credit market ETFs & MOVE...")
    credit_market = fetch_credit_market_data()

    # Build snapshot
    snapshot = {
        'date'         : today,
        'generated'    : datetime.now().isoformat(),
        'credit_data'  : data,
        'pe_data'      : pe_data,
        'credit_market': credit_market,
        'alerts'       : alerts,
        'hhdc_quarter' : hhdc_quarter,
    }

    # Save snapshot + shared alerts to marketdb
    from marketdb import results as _mr
    _iso = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    _mr.save_report('consumer_credit', _iso, payload=snapshot)
    _mr.save_report('credit_alerts', 'latest', payload={'date': today, 'alerts': alerts})
    print(f"Saved: marketdb consumer_credit {_iso}")

    # Build text report
    report_lines = [
        '═' * 70,
        f'  CONSUMER CREDIT HEALTH REPORT — {datetime.today().strftime("%d %b %Y")}',
        '═' * 70,
        '',
    ]

    sections = {
        'CONSUMER CREDIT'  : ['cc_delinquency', 'cc_chargeoff',
                               'auto_delinquency', 'mortgage_delinquency',
                               'consumer_credit'],
        'HOUSEHOLD DEBT FLOWS (NY FED)': ['flow90_cc', 'flow90_auto',
                               'flow90_mortgage', 'flow90_student',
                               'flow30_cc', 'flow30_auto', 'flow30_mortgage',
                               'mortgage_subprime_share', 'auto_subprime_share',
                               'hh_debt_total'],
        'CORPORATE CREDIT' : ['hy_spread', 'ig_spread'],
        'RATES & CURVE'    : ['us10y', 'us02y', 'us03m', 'yield_curve', 'fed_funds'],
        'INFLATION EXPECTATIONS': ['breakeven_5y', 'breakeven_10y'],
        'SOVEREIGN CREDIT' : ['debt_gdp', 'deficit_gdp'],
    }

    for section, keys in sections.items():
        report_lines.append(f'  {section}')
        report_lines.append('  ' + '─' * 66)
        for key in keys:
            if key not in data:
                continue
            d     = data[key]
            arrow = '▲' if d['roc'] and d['roc'] > 0 else '▼' if d['roc'] and d['roc'] < 0 else '→'
            flag  = '⚠' if d['alert_level'] == 'ALERT' else '!' if d['alert_level'] == 'WARN' else '✓'
            report_lines.append(
                f"  {flag} {d['label']:<40} {d['current']:>8.2f}  "
                f"{arrow} {d['roc']:+.3f} qoq  {d['alert_level']}"
            )
        report_lines.append('')

    report_lines.append('  CREDIT MARKET (DAILY)')
    report_lines.append('  ' + '─' * 66)
    for ticker, cm in credit_market.items():
        parts = []
        if cm.get('ret_1w') is not None: parts.append(f"1w: {cm['ret_1w']:+.1f}%")
        if cm.get('ret_1m') is not None: parts.append(f"1m: {cm['ret_1m']:+.1f}%")
        if cm.get('ret_3m') is not None: parts.append(f"3m: {cm['ret_3m']:+.1f}%")
        ret_str = '  '.join(parts)
        report_lines.append(f"  {ticker:<6} {cm['name']:<28} {cm['price']:>8.2f}  {ret_str}")
    report_lines.append('')

    report_lines.append('  PRIVATE EQUITY & BDC')
    report_lines.append('  ' + '─' * 66)
    for ticker, pe in pe_data.items():
        ret_str = f"1m: {pe['ret_1m']:+.1f}%" if pe['ret_1m'] else ''
        report_lines.append(f"  {ticker:<6} {pe['name']:<30} ${pe['price']:>8.2f}  {ret_str}")

    report_lines += ['', '═' * 70]
    report   = '\n'.join(report_lines)
    _mr.save_report('consumer_credit', _iso, text=report, payload=snapshot)
    print(report)
    print(f"Report: marketdb consumer_credit {_iso}")

    return snapshot

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run_consumer_credit()