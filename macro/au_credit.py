"""
macro/au_credit.py
==================
Australian debt market health tracker — the AU counterpart to
consumer_credit.py (US). Sources:

- RBA statistical tables (CSV, stable URLs):
    F1  cash rate target (daily)
    F2  Australian Government bond yields 2y/5y/10y (daily)
    F3  non-financial corporate A / BBB bond yields (monthly)
        -> credit spreads computed vs the matching-tenor AGS yield
    E2  household finances selected ratios (quarterly)
    D1  credit growth by category, 12-month ended (monthly)
- FRED: AU general government gross debt %GDP (IMF, annual)
- yfinance: ASX-listed credit/bond ETFs + AUD, AU VIX

Output: results/consumer_credit/YYYYMMDD_au_credit.json in the same
shape as the US snapshot (credit_data / credit_market / alerts).

There is no free AU arrears/delinquency series (APRA property exposure
stats are quarterly xlsx with unstable URLs; S&P SPIN is paid) — household
leverage ratios and credit growth carry the household-stress signal here.
"""

import os
import io
import csv
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime

try:
    from config import FRED_API_KEY
except ImportError:
    from macro.config import FRED_API_KEY

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'results', 'consumer_credit')

RBA_CSV = 'https://www.rba.gov.au/statistics/tables/csv/{}-data.csv'
_HDRS   = {'User-Agent': 'Mozilla/5.0'}

# ── RBA series: key -> (table, title substring, label, history periods) ──────
RBA_SERIES = {
    # Household leverage (E2, quarterly)
    'au_hh_debt_income'     : ('e2', 'Household debt to income',
                               'AU Household Debt to Income %', 20),
    'au_housing_debt_income': ('e2', 'Housing debt to income',
                               'AU Housing Debt to Income %', 20),
    'au_hh_debt_assets'     : ('e2', 'Household debt to assets',
                               'AU Household Debt to Assets %', 20),
    # Credit growth, 12-month ended (D1, monthly)
    'au_housing_credit'     : ('d1', 'Credit; Housing; 12-month',
                               'AU Housing Credit Growth 12m %', 24),
    'au_investor_credit'    : ('d1', 'Credit; Investor housing; 12-month',
                               'AU Investor Housing Credit Growth 12m %', 24),
    'au_personal_credit'    : ('d1', 'Credit; Other personal; 12-month',
                               'AU Personal Credit Growth 12m %', 24),
    'au_business_credit'    : ('d1', 'Credit; Business; 12-month',
                               'AU Business Credit Growth 12m %', 24),
    # Rates & curve (F1/F2, daily) — keep more periods for charts
    'au_cash_rate'          : ('f1', 'Cash Rate Target',
                               'RBA Cash Rate Target %', 60),
    'au_02y'                : ('f2', 'Australian Government 2 year',
                               'AU 2-Year AGS Yield %', 60),
    'au_05y'                : ('f2', 'Australian Government 5 year',
                               'AU 5-Year AGS Yield %', 60),
    'au_10y'                : ('f2', 'Australian Government 10 year',
                               'AU 10-Year AGS Yield %', 60),
    # Corporate yields (F3, monthly) — spreads computed below
    '_nfc_a_5y'             : ('f3', 'A-rated bonds – Yield – 5 year',
                               'AU NFC A-rated 5y Yield %', 60),
    '_nfc_bbb_5y'           : ('f3', 'BBB-rated bonds – Yield – 5 year',
                               'AU NFC BBB-rated 5y Yield %', 60),
}

# ASX credit / bond market ETFs (daily via yfinance)
AU_CREDIT_TICKERS = {
    'CRED.AX': 'AU IG Corporate Bond ETF',
    'QPON.AX': 'AU Floating Rate Bond ETF',
    'HBRD.AX': 'AU Hybrids ETF (HY proxy)',
    'SUBD.AX': 'AU Subordinated Debt ETF',
    'VGB.AX' : 'AU Govt Bond ETF',
    'IAF.AX' : 'AU Composite Bond ETF',
    'AUDUSD=X': 'AUD/USD',
    '^AXVI'  : 'S&P/ASX 200 VIX',
}

# ── Alert thresholds ─────────────────────────────────────────────────────────
THRESHOLDS = {
    'au_hh_debt_income'      : {'warn': 185,  'alert': 200},
    'au_housing_debt_income' : {'warn': 135,  'alert': 150},
    'au_hh_debt_assets'      : {'warn': 20,   'alert': 24},
    'au_housing_credit'      : {'warn': 8.0,  'alert': 10.0},   # overheating
    'au_investor_credit'     : {'warn': 8.0,  'alert': 10.0},
    'au_business_credit'     : {'warn': 10.0, 'alert': 13.0},
    'au_bbb_spread'          : {'warn': 2.5,  'alert': 3.5},
    'au_a_spread'            : {'warn': 1.8,  'alert': 2.5},
    'au_debt_gdp'            : {'warn': 55,   'alert': 65},
    'au_mortgage_arrears'    : {'warn': 1.8,  'alert': 2.3},   # 30+dpd combined
    'au_mortgage_arrears_3089': {'warn': 0.85, 'alert': 1.1},
    'au_mortgage_npl'        : {'warn': 1.2,  'alert': 1.6},
    'au_new_npl_flow'        : {'warn': 0.30, 'alert': 0.45},
}

ROC_THRESHOLDS = {
    'au_bbb_spread'          : {'warn': 0.3,  'alert': 0.6},
    'au_a_spread'            : {'warn': 0.25, 'alert': 0.5},
    'au_hh_debt_income'      : {'warn': 3.0,  'alert': 5.0},
    'au_mortgage_arrears'    : {'warn': 0.10, 'alert': 0.20},
    'au_new_npl_flow'        : {'warn': 0.05, 'alert': 0.10},
}


def get_alert_level(key, current, roc):
    level = 'OK'
    t = THRESHOLDS.get(key)
    if t and current is not None:
        if current >= t['alert']:
            level = 'ALERT'
        elif current >= t['warn']:
            level = 'WARN'
    rt = ROC_THRESHOLDS.get(key)
    if rt and roc is not None and level == 'OK':
        if roc >= rt['alert']:
            level = 'ALERT'
        elif roc >= rt['warn']:
            level = 'WARN'
    return level


def calc_roc(series):
    if series is None or len(series) < 2:
        return None
    return round(float(series.iloc[-1]) - float(series.iloc[-2]), 4)


def calc_roc_3(series):
    if series is None or len(series) < 4:
        return None
    return round(float(series.iloc[-1]) - float(series.iloc[-4]), 4)


# ── RBA CSV parsing ──────────────────────────────────────────────────────────

_table_cache = {}


def _fetch_rba_table(table):
    """Download and parse one RBA table CSV → DataFrame indexed by date."""
    if table in _table_cache:
        return _table_cache[table]
    r = requests.get(RBA_CSV.format(table), timeout=30, headers=_HDRS)
    if r.status_code != 200:
        _table_cache[table] = None
        return None
    rows = list(csv.reader(r.text.splitlines()))
    title_row = next((row for row in rows
                      if row and row[0].strip().lower() == 'title'), None)
    sid_idx = next((i for i, row in enumerate(rows)
                    if row and row[0].strip().lower() == 'series id'), None)
    if title_row is None or sid_idx is None:
        _table_cache[table] = None
        return None
    data_rows = [row for row in rows[sid_idx + 1:] if row and row[0].strip()]
    df = pd.DataFrame(data_rows)
    df.index = pd.to_datetime(df[0], dayfirst=True, format='mixed', errors='coerce')
    df = df[df.index.notna()].drop(columns=[0])
    # column names from title row (may be shorter than data width)
    names = {}
    for i, t in enumerate(title_row):
        if i > 0 and str(t).strip():
            names[i] = str(t).strip()
    df = df.rename(columns=names)
    _table_cache[table] = df
    return df


def fetch_rba_series(table, title_match, periods=20):
    """Return a pd.Series for the first column whose title contains title_match."""
    df = _fetch_rba_table(table)
    if df is None:
        return None
    col = next((c for c in df.columns
                if isinstance(c, str) and title_match.lower() in c.lower()), None)
    if col is None:
        return None
    s = pd.to_numeric(df[col], errors='coerce').dropna()
    return s.tail(periods) if len(s) else None


# ── APRA quarterly property exposures (mortgage arrears) ────────────────────
# Source of Cotality/CoreLogic's arrears headlines. Tab 1b 'Loan performance'
# has 30-89dpd, non-performing, and NEW NPLs per quarter (a flow measure,
# the AU cousin of the NY Fed flow-into-delinquency series).

APRA_PAGE = ('https://www.apra.gov.au/'
             'quarterly-authorised-deposit-taking-institution-statistics')


def _apra_latest_url():
    """Scrape the APRA stats page for the latest property exposures xlsx."""
    import re as _re
    r = requests.get(APRA_PAGE, timeout=30, headers=_HDRS)
    if r.status_code != 200:
        return None
    m = _re.findall(
        r'href="(/system/files/[^"]*property\s*exposures\s*statistics[^"]*\.xlsx)"',
        r.text, _re.IGNORECASE)
    if not m:
        m = _re.findall(
            r'href="(/system/files/[^"]*property%20exposures%20statistics[^"]*\.xlsx)"',
            r.text, _re.IGNORECASE)
    return f"https://www.apra.gov.au{m[0]}" if m else None


def _apra_row(df, label_match, start_row=0):
    """Find the first row whose col-0 label contains label_match."""
    for i in range(start_row, len(df)):
        v = df.iat[i, 0]
        if pd.notna(v) and label_match.lower() in str(v).lower():
            return i
    return None


def fetch_apra_arrears(cache_dir, history_quarters=20):
    """
    Parse mortgage arrears series from APRA property exposures Tab 1b.
    Returns {key: {'label': str, 'series': pd.Series}} indexed by quarter end.
    """
    url = _apra_latest_url()
    if url is None:
        return {}
    os.makedirs(cache_dir, exist_ok=True)
    fname = os.path.basename(url).replace('%20', '_')
    path = os.path.join(cache_dir, fname)
    if not (os.path.exists(path) and os.path.getsize(path) > 100_000):
        r = requests.get(url, timeout=60, headers=_HDRS)
        if r.status_code != 200:
            return {}
        with open(path, 'wb') as f:
            f.write(r.content)

    df = pd.read_excel(path, sheet_name='Tab 1b', header=None)

    # quarter-end dates: first row where most cells from col 2 are datetimes
    date_row = None
    for i in range(min(len(df), 10)):
        parsed = pd.to_datetime(df.iloc[i, 2:], errors='coerce')
        if parsed.notna().sum() >= 4:
            date_row = df.iloc[i]
            break
    if date_row is None:
        return {}
    dates, cols = [], []
    for j in range(2, df.shape[1]):
        d = pd.to_datetime(date_row.iloc[j], errors='coerce')
        if pd.notna(d):
            dates.append(d)
            cols.append(j)

    def _series_at(row_idx):
        if row_idx is None:
            return None
        vals = pd.to_numeric(df.iloc[row_idx, cols], errors='coerce')
        s = pd.Series(vals.values, index=pd.DatetimeIndex(dates)).dropna()
        return s if len(s) else None

    # 'Total credit oustanding' — sic, APRA's own typo; match loosely
    total_i = _apra_row(df, 'Total credit ou')
    perf_i  = _apra_row(df, 'Loan performance')
    dpd_i   = _apra_row(df, '30-89 days past due', start_row=perf_i or 0)
    npl_i   = _apra_row(df, 'Non-performing loans', start_row=perf_i or 0)
    new_i   = _apra_row(df, 'New non-performing loans', start_row=perf_i or 0)

    total = _series_at(total_i)
    dpd   = _series_at(dpd_i)
    npl   = _series_at(npl_i)
    new   = _series_at(new_i)
    if total is None or dpd is None or npl is None:
        return {}

    out = {}
    arrears_3089 = (dpd / total * 100).round(3)
    npl_pct      = (npl / total * 100).round(3)
    combined     = (arrears_3089 + npl_pct).round(3)
    out['au_mortgage_arrears_3089'] = {
        'label': 'AU Mortgage 30-89dpd % (APRA)',
        'series': arrears_3089.tail(history_quarters)}
    out['au_mortgage_npl'] = {
        'label': 'AU Mortgage Non-Performing % (APRA)',
        'series': npl_pct.tail(history_quarters)}
    out['au_mortgage_arrears'] = {
        'label': 'AU Mortgage Arrears Total % (30+dpd, APRA)',
        'series': combined.tail(history_quarters)}
    if new is not None:
        out['au_new_npl_flow'] = {
            'label': 'AU New NPL Flow % of Book (APRA)',
            'series': (new / total * 100).round(3).tail(history_quarters)}
    return out


# ── FRED (AU sovereign debt) ─────────────────────────────────────────────────

def fetch_au_debt_gdp():
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        s = fred.get_series('GGGDTAAUA188N')  # IMF: AU general govt gross debt %GDP
        return s.dropna().tail(15)
    except Exception as e:
        print(f"FRED AU debt/GDP error: {e}")
        return None


# ── ETF / FX / vol daily data ────────────────────────────────────────────────

def fetch_au_credit_market():
    import yfinance as yf
    results = {}
    try:
        data = yf.download(list(AU_CREDIT_TICKERS.keys()), period='1y',
                           progress=False)
        closes = data['Close']
        for ticker, name in AU_CREDIT_TICKERS.items():
            if ticker not in closes.columns:
                continue
            s = closes[ticker].dropna()
            if len(s) < 2:
                continue
            results[ticker] = {
                'name'   : name,
                'price'  : round(float(s.iloc[-1]), 2),
                'ret_1w' : round((s.iloc[-1] / s.iloc[-5]   - 1) * 100, 2) if len(s) >= 5   else None,
                'ret_1m' : round((s.iloc[-1] / s.iloc[-21]  - 1) * 100, 2) if len(s) >= 21  else None,
                'ret_3m' : round((s.iloc[-1] / s.iloc[-63]  - 1) * 100, 2) if len(s) >= 63  else None,
                'ret_12m': round((s.iloc[-1] / s.iloc[-252] - 1) * 100, 2) if len(s) >= 252 else None,
            }
    except Exception as e:
        print(f"AU credit market data error: {e}")
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def _series_entry(key, label, series, alerts):
    current = round(float(series.iloc[-1]), 4)
    prior   = round(float(series.iloc[-2]), 4) if len(series) >= 2 else None
    roc     = calc_roc(series)
    roc_3   = calc_roc_3(series)
    level   = get_alert_level(key, current, roc)
    entry = {
        'label'       : label,
        'current'     : current,
        'prior'       : prior,
        'roc'         : roc,
        'roc_3m'      : roc_3,
        'alert_level' : level,
        'history'     : {str(k.date()): round(float(v), 4)
                         for k, v in series.items()},
    }
    if level in ['ALERT', 'WARN']:
        direction = '▲' if roc and roc > 0 else '▼'
        alerts.append({'type': level, 'key': key,
                       'message': f"{label}: {current} {direction} "
                                  f"{(roc or 0):+.3f} chg"})
        print(f"  {level}: {label} = {current}")
    else:
        print(f"  OK: {label} = {current}")
    return entry


def run_au_credit():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    today  = datetime.today().strftime('%Y%m%d')
    data   = {}
    alerts = []
    raw    = {}

    print("Fetching RBA tables...")
    for key, (table, match, label, periods) in RBA_SERIES.items():
        s = fetch_rba_series(table, match, periods)
        if s is None or not len(s):
            print(f"  MISS: {label} ({table}: '{match}')")
            continue
        raw[key] = s
        if not key.startswith('_'):
            data[key] = _series_entry(key, label, s, alerts)

    # Yield curve: 10y - cash rate (AU version of 10Y-3M)
    if 'au_10y' in raw and 'au_cash_rate' in raw:
        curve = round(float(raw['au_10y'].iloc[-1]) -
                      float(raw['au_cash_rate'].iloc[-1]), 3)
        data['au_yield_curve'] = {
            'label': 'AU 10Y minus Cash Rate %', 'current': curve,
            'prior': None, 'roc': None, 'roc_3m': None,
            'alert_level': 'WARN' if curve < 0 else 'OK', 'history': {},
        }
        print(f"  {'WARN' if curve < 0 else 'OK'}: AU curve (10y-cash) = {curve}")
        if curve < 0:
            alerts.append({'type': 'WARN', 'key': 'au_yield_curve',
                           'message': f"AU 10Y-Cash curve inverted: {curve}%"})

    # Corporate credit spreads: NFC yield minus 5y AGS (monthly vs daily —
    # align by resampling the AGS to month-end)
    if '_nfc_bbb_5y' in raw and 'au_05y' in raw:
        ags_5y_m = fetch_rba_series('f2', 'Australian Government 5 year', 4000)
        if ags_5y_m is not None:
            ags_m = ags_5y_m.resample('ME').last()
            for spread_key, nfc_key, label in [
                    ('au_bbb_spread', '_nfc_bbb_5y', 'AU BBB Corp Spread 5y % (vs AGS)'),
                    ('au_a_spread',   '_nfc_a_5y',   'AU A-rated Corp Spread 5y % (vs AGS)')]:
                if nfc_key not in raw:
                    continue
                nfc = raw[nfc_key]
                nfc_m = nfc.resample('ME').last() if nfc.index.inferred_freq != 'ME' else nfc
                joined = pd.concat([nfc_m, ags_m], axis=1, keys=['nfc', 'ags']).dropna()
                if joined.empty:
                    continue
                spread = (joined['nfc'] - joined['ags']).round(3).tail(24)
                data[spread_key] = _series_entry(spread_key, label, spread, alerts)

    # Mortgage arrears (APRA quarterly property exposures)
    print("Fetching APRA mortgage arrears...")
    try:
        apra = fetch_apra_arrears(os.path.join(RESULTS_DIR, 'apra_cache'))
        for key, d in apra.items():
            data[key] = _series_entry(key, d['label'], d['series'], alerts)
    except Exception as e:
        print(f"APRA arrears fetch failed (non-fatal): {e}")

    # Sovereign debt %GDP (FRED, annual)
    print("Fetching AU sovereign debt (FRED)...")
    debt = fetch_au_debt_gdp()
    if debt is not None and len(debt):
        data['au_debt_gdp'] = _series_entry('au_debt_gdp',
                                            'AU Govt Debt % GDP (IMF)', debt, alerts)

    # ETFs / FX / vol
    print("Fetching ASX credit ETFs...")
    credit_market = fetch_au_credit_market()

    snapshot = {
        'date'         : today,
        'generated'    : datetime.now().isoformat(),
        'credit_data'  : data,
        'credit_market': credit_market,
        'alerts'       : alerts,
    }

    json_file = os.path.join(RESULTS_DIR, f"{today}_au_credit.json")
    with open(json_file, 'w') as f:
        json.dump(snapshot, f, indent=2, default=str)
    print(f"Saved: {json_file}")
    return snapshot


if __name__ == '__main__':
    run_au_credit()
