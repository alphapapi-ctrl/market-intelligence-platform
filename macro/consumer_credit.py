import pandas as pd
import numpy as np
import yfinance as yf
import os
import json
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
try:
    from config import FRED_API_KEY, ANTHROPIC_API_KEY
except ImportError:
    from macro.config import FRED_API_KEY, ANTHROPIC_API_KEY

from fredapi import Fred

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', 'consumer_credit')

# ── FRED Series ───────────────────────────────────────────────────────────────
FRED_SERIES = {
    # Consumer credit
    'cc_delinquency'    : ('DRCCLACBS',   'Credit Card Delinquency Rate %'),
    'cc_chargeoff'      : ('CORCACBS',    'Credit Card Charge-Off Rate %'),
    'auto_delinquency'  : ('DRALACBS',    'Auto Loan Delinquency Rate %'),
    'mortgage_delinquency':('DRSFRMACBS', 'Mortgage Delinquency Rate %'),
    'consumer_credit'   : ('TOTALSL',     'Total Consumer Credit $B'),
    # Corporate credit
    'hy_spread'         : ('BAMLH0A0HYM2','HY Spread %'),
    'ig_spread'         : ('BAMLC0A0CM',  'IG Spread %'),
    # Sovereign
    'debt_gdp'          : ('GFDEGDQ188S', 'Federal Debt % GDP'),
    'deficit_gdp'       : ('FYFSGDA188S', 'Federal Deficit % GDP'),
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

# ── Alert thresholds ──────────────────────────────────────────────────────────
THRESHOLDS = {
    'cc_delinquency'     : {'warn': 2.5,  'alert': 3.5},
    'cc_chargeoff'       : {'warn': 3.0,  'alert': 4.5},
    'auto_delinquency'   : {'warn': 1.5,  'alert': 2.5},
    'mortgage_delinquency': {'warn': 1.5, 'alert': 2.5},
    'hy_spread'          : {'warn': 4.0,  'alert': 6.0},
    'ig_spread'          : {'warn': 1.5,  'alert': 2.5},
    'debt_gdp'           : {'warn': 110,  'alert': 130},
}

ROC_THRESHOLDS = {
    'cc_delinquency'     : {'warn': 0.15, 'alert': 0.3},
    'auto_delinquency'   : {'warn': 0.1,  'alert': 0.2},
    'mortgage_delinquency': {'warn': 0.1, 'alert': 0.2},
    'hy_spread'          : {'warn': 0.5,  'alert': 1.0},
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

    # PE/BDC data
    print("Fetching PE/BDC data...")
    pe_data = fetch_pe_data()

    # Build snapshot
    snapshot = {
        'date'       : today,
        'generated'  : datetime.now().isoformat(),
        'credit_data': data,
        'pe_data'    : pe_data,
        'alerts'     : alerts,
    }

    # Save JSON snapshot
    json_file = os.path.join(RESULTS_DIR, f"{today}_consumer_credit.json")
    with open(json_file, 'w') as f:
        json.dump(snapshot, f, indent=2, default=str)
    print(f"Saved: {json_file}")

    # Save alerts to shared macro alerts file
    alerts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'results', 'credit_alerts.json')
    with open(alerts_file, 'w') as f:
        json.dump({'date': today, 'alerts': alerts}, f, indent=2)
    print(f"Alerts saved: {alerts_file}")

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
        'CORPORATE CREDIT' : ['hy_spread', 'ig_spread'],
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

    report_lines.append('  PRIVATE EQUITY & BDC')
    report_lines.append('  ' + '─' * 66)
    for ticker, pe in pe_data.items():
        ret_str = f"1m: {pe['ret_1m']:+.1f}%" if pe['ret_1m'] else ''
        report_lines.append(f"  {ticker:<6} {pe['name']:<30} ${pe['price']:>8.2f}  {ret_str}")

    report_lines += ['', '═' * 70]
    report   = '\n'.join(report_lines)
    rpt_file = os.path.join(RESULTS_DIR, f"{today}_consumer_credit_report.txt")
    with open(rpt_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(report)
    print(f"Report: {rpt_file}")

    return snapshot

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run_consumer_credit()