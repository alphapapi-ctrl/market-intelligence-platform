"""
macro/nyfed_hhdc.py
===================
NY Fed Quarterly Report on Household Debt and Credit (Equifax consumer panel).
https://www.newyorkfed.org/microeconomics/hhdc

Complements the FRED bank call-report series in consumer_credit.py:
- FRED delinquency rates are STOCK measures from commercial banks (lagging)
- HHDC flow-into-delinquency series are TRANSITION rates across all lenders
  (leading), plus originations by credit score (subprime share of new lending)

The underlying data xlsx is published quarterly at a stable URL pattern:
  .../householdcredit/data/xls/HHD_C_Report_<YYYY>Q<n>.xlsx
"""

import os
import re
import requests
import pandas as pd
from datetime import datetime

HHDC_URL = ('https://www.newyorkfed.org/medialibrary/interactives/'
            'householdcredit/data/xls/HHD_C_Report_{}.xlsx')

_QUARTER_RE = re.compile(r'^\d{2}:Q[1-4]$')

# key: (sheet, column, label, scale)
HHDC_SERIES = {
    'flow90_cc':       ('Page 14 Data', 'CC',           'CC Flow into 90+ Delinq % (NY Fed)',        1),
    'flow90_auto':     ('Page 14 Data', 'AUTO',         'Auto Flow into 90+ Delinq % (NY Fed)',      1),
    'flow90_mortgage': ('Page 14 Data', 'MORTGAGE',     'Mortgage Flow into 90+ Delinq % (NY Fed)',  1),
    'flow90_student':  ('Page 14 Data', 'STUDENT LOAN', 'Student Flow into 90+ Delinq % (NY Fed)',   1),
    'flow30_cc':       ('Page 13 Data', 'CC',           'CC Flow into 30+ Delinq % (NY Fed)',        1),
    'flow30_auto':     ('Page 13 Data', 'AUTO',         'Auto Flow into 30+ Delinq % (NY Fed)',      1),
    'flow30_mortgage': ('Page 13 Data', 'MORTGAGE',     'Mortgage Flow into 30+ Delinq % (NY Fed)',  1),
    'hh_debt_total':   ('Page 3 Data',  'Total',        'Total Household Debt $T (NY Fed)',          1),
}

# computed series: subprime (<620 score) share of origination volume
SUBPRIME_SHEETS = {
    'mortgage_subprime_share': ('Page 6 Data', 'Mortgage Subprime Origination Share % (NY Fed)'),
    'auto_subprime_share':     ('Page 8 Data', 'Auto Subprime Origination Share % (NY Fed)'),
}


def _candidate_quarters(n=6):
    """Yield quarter strings (e.g. '2026Q1') from the most recent backwards.
    The report lags ~1 quarter (Q1 data is released in May)."""
    now = datetime.today()
    year, q = now.year, (now.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        q -= 1
        if q == 0:
            year -= 1
            q = 4
        out.append(f"{year}Q{q}")
    return out


def download_latest(cache_dir):
    """Download the most recent HHDC data file (cached per quarter).
    Returns (path, quarter) or (None, None)."""
    os.makedirs(cache_dir, exist_ok=True)
    for quarter in _candidate_quarters():
        path = os.path.join(cache_dir, f"HHD_C_Report_{quarter}.xlsx")
        if os.path.exists(path) and os.path.getsize(path) > 100_000:
            return path, quarter
        try:
            r = requests.get(HHDC_URL.format(quarter), timeout=60,
                             headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200 and len(r.content) > 100_000:
                with open(path, 'wb') as f:
                    f.write(r.content)
                return path, quarter
        except Exception:
            continue
    return None, None


def _parse_sheet(path, sheet):
    """Parse an HHDC data sheet into a DataFrame indexed by quarter ('2003Q1')."""
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    first = None
    for i in range(min(len(df), 15)):
        v = df.iat[i, 0]
        if isinstance(v, str) and _QUARTER_RE.match(v.strip()):
            first = i
            break
    if first is None:
        return None
    header = df.iloc[first - 1].tolist()
    data = df.iloc[first:].copy()
    data.columns = [str(h).strip() if pd.notna(h) else f'col{i}'
                    for i, h in enumerate(header)]
    qcol = data.columns[0]
    data = data[data[qcol].astype(str).str.strip().str.match(_QUARTER_RE)]
    # '03:Q1' → '2003Q1'
    data.index = data[qcol].astype(str).str.strip().map(
        lambda s: f"20{s[:2]}Q{s[-1]}")
    return data.drop(columns=[qcol])


def fetch_hhdc_series(cache_dir, history_quarters=20):
    """
    Fetch all HHDC series. Returns (series_map, quarter) where series_map is
    {key: {'label': str, 'series': pd.Series}} with the series indexed by
    quarter strings, trimmed to the last `history_quarters`.
    """
    path, quarter = download_latest(cache_dir)
    if path is None:
        return {}, None

    out = {}
    sheet_cache = {}

    def _sheet(name):
        if name not in sheet_cache:
            sheet_cache[name] = _parse_sheet(path, name)
        return sheet_cache[name]

    for key, (sheet, col, label, scale) in HHDC_SERIES.items():
        df = _sheet(sheet)
        if df is None or col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors='coerce').dropna() * scale
        if len(s):
            out[key] = {'label': label, 'series': s.tail(history_quarters).round(3)}

    # subprime share = <620 bucket / TOTAL originations
    for key, (sheet, label) in SUBPRIME_SHEETS.items():
        df = _sheet(sheet)
        if df is None:
            continue
        sub_col = next((c for c in df.columns if '<620' in str(c)), None)
        tot_col = next((c for c in df.columns if str(c).upper().startswith('TOTAL')), None)
        if not sub_col or not tot_col:
            continue
        sub = pd.to_numeric(df[sub_col], errors='coerce')
        tot = pd.to_numeric(df[tot_col], errors='coerce')
        share = (sub / tot * 100).dropna()
        if len(share):
            out[key] = {'label': label, 'series': share.tail(history_quarters).round(2)}

    return out, quarter


if __name__ == '__main__':
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'results', 'consumer_credit', 'hhdc_cache')
    series, quarter = fetch_hhdc_series(cache)
    print(f"HHDC report quarter: {quarter}")
    for key, d in series.items():
        s = d['series']
        print(f"  {key:<26} {d['label']:<44} latest={s.iloc[-1]:>8.2f}  ({s.index[-1]})")
