"""Shared, descriptive risk rules for the Macro page and daily report.

Thresholds are dashboard heuristics, not probabilities or a backtested model.
Consumer ratios share one vote; overlapping participation signals share another.
"""
from math import isfinite
import re


RISK_INPUT_KEYS = (
    'vix', 'vvix', 'vix_vvix', 'vix3m', 'vix_vix3m', 'vix_as_of',
    'xly_xlp', 'xly_xlp_chg_5d', 'xly_xlp_chg_63d',
    'rspd_rsps', 'rspd_rsps_chg_5d', 'rspd_rsps_chg_63d',
    'risk_ratio', 'risk_ratio_chg_5d', 'risk_ratio_chg_10d',
    'cyc_iwm_spx_ratio', 'cyc_iwm_spx_chg_63d', 'ad_divergence', 'hy_spread',
)


def parse_risk_inputs(text, snapshot=None):
    """Read legacy reports, preserving down arrows; prefer same-report numbers."""
    data = {}
    for key, label in (('vix', 'VIX'), ('vvix', 'VVIX'), ('vix_vvix', 'VIX/VVIX'),
                       ('hy_spread', 'HY Spread')):
        match = re.search(r'(?<![\w/])' + re.escape(label) + r':\s*([\d.]+)', text)
        if match:
            data[key] = float(match.group(1))
    for key, label, windows in (
        ('xly_xlp', 'XLY/XLP ratio', (5, 63)),
        ('rspd_rsps', 'RSPD/RSPS ratio', (5, 63)),
        ('risk_ratio', 'Sector Groups Risk On/Off ratio', (5, 10)),
    ):
        match = re.search(re.escape(label) + r':\s*([\d.]+)([^\n]*)', text)
        if not match:
            continue
        data[key] = float(match.group(1))
        for window in windows:
            change = re.search(r'([▲▼+\-]?)\s*(\d+(?:\.\d+)?)%\s*' + str(window) + r'd\b', match.group(2))
            if change:
                data[f'{key}_chg_{window}d'] = float(change.group(2)) * (-1 if change.group(1) in ('▼', '-') else 1)
    match = re.search(r'A/D Line:\s*(?:⚠|✓|→)\s*([^\n]+)', text)
    if match:
        data['ad_divergence'] = match.group(1).strip()
    # Explicit nulls in a new report must clear legacy text, not revive an old reading.
    if snapshot:
        data.update({key: snapshot[key] for key in RISK_INPUT_KEYS if key in snapshot})
    return data


def volatility_snapshot(vix_prices, vvix_prices, vix3m_prices):
    """Use same-session closes for comparisons; never forward-fill volatility."""
    import pandas as pd

    def clean(prices):
        if prices is None or prices.empty:
            return pd.Series(dtype=float)
        if isinstance(prices, pd.DataFrame):
            prices = prices.iloc[:, 0]
        prices = pd.to_numeric(prices, errors='coerce').dropna()
        prices = prices[(prices > 0) & prices.map(isfinite)].copy()
        prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
        return prices.sort_index().groupby(level=0).last()

    series = {key: clean(prices) for key, prices in
              (('vix', vix_prices), ('vvix', vvix_prices), ('vix3m', vix3m_prices))}
    result = dict.fromkeys(('vix', 'vvix', 'vix3m', 'vix_vvix', 'vix_vix3m', 'vix_as_of'))
    if series['vix'].empty:
        return result
    day = series['vix'].index[-1]
    result['vix_as_of'] = day.strftime('%Y-%m-%d')
    for key, prices in series.items():
        if day in prices.index:
            result[key] = round(float(prices.loc[day]), 4)
    for denominator, key in (('vvix', 'vix_vvix'), ('vix3m', 'vix_vix3m')):
        if result[denominator] is not None:
            result[key] = round(result['vix'] / result[denominator], 4)
    return result


RISK_METHODOLOGY = (
    "Five groups: volatility, consumer leadership, sector rotation, participation, "
    "and credit. XLY/XLP and RSPD/RSPS share one vote. Conflicting signals within "
    "a group mean caution. Two risk-off groups mean RISK OFF; VIX >25 or HY "
    "spread >=6% also means RISK OFF. Any other warning means CAUTIOUS. "
    "RISK ON requires at least three supportive groups, including volatility and "
    "consumer leadership, with no warnings. Otherwise the reading is MIXED; fewer "
    "than three available groups means INSUFFICIENT DATA unless stress overrides. "
    "Missing inputs are unavailable, never clear. These are descriptive dashboard "
    "rules, not a recession probability or a validated trading model."
)


def number(data, key):
    """Accept finite numeric observations; keep absent/invalid data unknown."""
    value = data.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def get_vix_regime(vix, vvix=None, vix_vvix=None):
    """Volatility context only; broader risk comes from build_risk_monitor."""
    vix = number({'v': vix}, 'v')
    vvix = number({'v': vvix}, 'v')
    ratio = number({'v': vix_vvix}, 'v')
    if vix is None or vix <= 0:
        return 'UNKNOWN', 'VIX unavailable', []
    if ratio is None and vvix is not None and vvix > 0:
        ratio = vix / vvix
    if ratio is not None and ratio <= 0:
        ratio = None
    missing = ' VVIX comparison unavailable.' if ratio is None else ''
    if vix > 25:
        return 'VOLATILITY STRESS', 'VIX above 25; elevated expected volatility.' + missing, []
    if vix >= 20:
        return 'ELEVATED VOLATILITY', 'VIX between 20 and 25; caution.' + missing, []
    if ratio is not None and ratio < 0.17:
        return ('COMPLACENCY WARNING', 'Low VIX relative to VVIX; monitor for fragility.',
                ['VIX/VVIX below 0.17 is a dashboard warning, not a forecast of a spike.'])
    if ratio is not None and ratio < 0.18:
        return 'VOLATILITY — MONITOR', 'VIX/VVIX between 0.17 and 0.18; caution.', []
    label = 'LOW VOLATILITY' if vix < 15 else 'NORMAL VOLATILITY'
    return label, 'VIX below 20; check consumer leadership and other risk signals.' + missing, []


def build_risk_monitor(data):
    """Return display rows and a consensus; no fetching or persistence."""
    rows = []

    def add(key, label, group, value, status, detail):
        rows.append(dict(key=key, label=label, group=group, value=value,
                         status=status, detail=detail))

    vix = number(data, 'vix')
    vvix = number(data, 'vvix')
    ratio = number(data, 'vix_vvix')
    if ratio is None and vix is not None and vvix is not None and vvix > 0:
        ratio = vix / vvix
    vol_label, vol_context, _ = get_vix_regime(vix, vvix, ratio)
    vol_status = ('UNAVAILABLE' if vix is None or vix <= 0 else
                  'RISK OFF' if vix > 25 else 'CAUTION' if vix >= 20 else 'SUPPORTIVE')
    add('vix', 'VIX', 'Volatility', f'{vix:.2f}' if vix is not None and vix > 0 else 'n/a',
        vol_status, 'VIX >25: stress; 20–25: caution; below 20: calm volatility.')
    add('vix_vvix', 'VIX/VVIX', 'Volatility', f'{ratio:.4f}' if ratio is not None and ratio > 0 else 'n/a',
        'UNAVAILABLE' if ratio is None or ratio <= 0 else
        'CAUTION' if vix is not None and 0 < vix < 20 and ratio < 0.18 else 'NEUTRAL',
        'With VIX <20: ratio <0.17 warns of complacency; 0.17–0.18 means monitor.')
    term = number(data, 'vix_vix3m')
    add('vix_vix3m', 'VIX/VIX3M', 'Volatility', f'{term:.3f}' if term is not None and term > 0 else 'n/a',
        'UNAVAILABLE' if term is None or term <= 0 else 'RISK OFF' if term >= 1 else 'NEUTRAL',
        'Ratio >=1: inverted volatility term structure; below 1: contango.')

    def trend(key, label, group, level_key=None, window=63, band=5):
        change = number(data, key)
        level = number(data, level_key) if level_key else None
        value = f'{level:.4f} | ' if level is not None else ''
        value += f'{change:+.2f}% / {window}d' if change is not None else f'{window}d trend n/a'
        status = ('UNAVAILABLE' if change is None else 'RISK OFF' if change < -band else
                  'CAUTION' if change < 0 else 'SUPPORTIVE' if change > band else 'NEUTRAL')
        # Consumer ratios use the existing positive-trend rule rather than a +5% hurdle.
        if group == 'Consumer leadership' and change is not None and change > 0:
            status = 'SUPPORTIVE'
        add(key, label, group, value, status,
            f'{window}d ratio change: below -{band}% risk off; negative caution; '
            + ('positive supportive; zero neutral.' if group == 'Consumer leadership' else
               f'above +{band}% supportive; otherwise neutral.'))

    trend('xly_xlp_chg_63d', 'XLY/XLP', 'Consumer leadership', 'xly_xlp')
    trend('rspd_rsps_chg_63d', 'RSPD/RSPS (equal weight)', 'Consumer leadership', 'rspd_rsps')
    trend('risk_ratio_chg_10d', 'Sector Risk On/Off', 'Sector rotation', 'risk_ratio', 10, 3)
    trend('cyc_iwm_spx_chg_63d', 'IWM/SPX', 'Participation', 'cyc_iwm_spx_ratio')
    breadth = str(data.get('ad_divergence') or '').strip()
    # This stored series uses leader/laggard counts, not exchange advances/declines.
    breadth_status = ('RISK OFF' if 'BEARISH' in breadth or 'both FALLING' in breadth else
                      'SUPPORTIVE' if 'BULLISH' in breadth or 'both RISING' in breadth else
                      'NEUTRAL' if breadth.startswith('CONFIRMING') else 'UNAVAILABLE')
    add('ad_divergence', 'Internal breadth proxy', 'Participation', breadth or 'n/a', breadth_status,
        'Leader-minus-laggard/weak proxy versus SPX; not a traditional exchange A/D line.')
    hy = number(data, 'hy_spread')
    if hy is not None and hy < 0:
        hy = None
    add('hy_spread', 'HY credit spread', 'Credit', f'{hy:.2f}%' if hy is not None else 'n/a',
        'UNAVAILABLE' if hy is None else 'RISK OFF' if hy >= 6 else 'CAUTION' if hy >= 4 else 'SUPPORTIVE',
        'Spread level: >=4% caution; >=6% stress. A low level does not measure widening.')

    groups = []
    for name in dict.fromkeys(row['group'] for row in rows):
        statuses = {row['status'] for row in rows if row['group'] == name} - {'UNAVAILABLE'}
        status = ('UNAVAILABLE' if not statuses else
                  'CAUTION' if 'RISK OFF' in statuses and 'SUPPORTIVE' in statuses else
                  'RISK OFF' if 'RISK OFF' in statuses else 'CAUTION' if 'CAUTION' in statuses else
                  'SUPPORTIVE' if 'SUPPORTIVE' in statuses else 'NEUTRAL')
        groups.append(dict(name=name, status=status))

    available = sum(g['status'] != 'UNAVAILABLE' for g in groups)
    off = sum(g['status'] == 'RISK OFF' for g in groups)
    caution = sum(g['status'] == 'CAUTION' for g in groups)
    supportive = sum(g['status'] == 'SUPPORTIVE' for g in groups)
    stress = (vix is not None and vix > 25) or (hy is not None and hy >= 6)
    group_status = {g['name']: g['status'] for g in groups}
    if stress or off >= 2:
        regime = 'RISK OFF'
        context = 'Volatility/credit stress override.' if stress else 'Defensive signals across at least two groups.'
    elif available < 3:
        regime, context = 'INSUFFICIENT DATA', 'At least three groups are needed for a broad risk reading.'
    elif off or caution:
        regime, context = 'CAUTIOUS', 'Warnings or conflicting signals; calm VIX does not clear broader risk.'
    elif (supportive >= 3 and group_status['Volatility'] == 'SUPPORTIVE'
          and group_status['Consumer leadership'] == 'SUPPORTIVE'):
        regime, context = 'RISK ON', 'Consumer leadership and calm volatility have broader confirmation.'
    else:
        regime, context = 'MIXED', 'Available signals do not show clear agreement.'

    return dict(regime=regime, context=context, rows=rows, groups=groups,
                available=available, total=len(groups), risk_off=off, caution=caution,
                supportive=supportive,
                available_signals=sum(row['status'] != 'UNAVAILABLE' for row in rows),
                volatility_regime=vol_label, volatility_context=vol_context)


def format_risk_monitor(monitor):
    """Plain text equivalent of the dashboard monitor for exports and AI context."""
    lines = [f"  MARKET RISK REGIME: {monitor['regime']}", f"  {monitor['context']}",
             f"  Coverage: {monitor['available']}/{monitor['total']} groups; "
             f"{monitor['risk_off']} risk off, {monitor['caution']} caution, "
             f"{monitor['supportive']} supportive"]
    for row in monitor['rows']:
        lines.append(f"  {row['label']}: {row['value']} | {row['status']}")
    lines.append(f"  Rules: {RISK_METHODOLOGY}")
    return lines
