from datetime import datetime
from config import FRED_API_KEY
import os as _os, sys as _sys
_MARKETDB_BASE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _MARKETDB_BASE not in _sys.path:
    _sys.path.insert(0, _MARKETDB_BASE)   # marketdb lives one level up

# ── Current Date ──────────────────────────────────────────────────────────────
TODAY = datetime.today()
YEAR  = TODAY.year + (TODAY.month - 1) / 12  # decimal year for cycle math

# ── Cycle Definitions ─────────────────────────────────────────────────────────
cycles = {

    'land_cycle': {
        'name'        : '18-21 Year Land Cycle',
        'last_peak'   : 2006.5,
        'duration'    : (18, 21),
        'current_year': YEAR - 2006.5,
        'phase_map'   : [
            (0,   5,  'RECOVERY',     'Real estate recovering, credit expanding'),
            (5,   10, 'EXPANSION',    'Land prices rising, construction accelerating'),
            (10,  15, 'MID CYCLE',    'Speculation increasing, vacancy rates falling'),
            (15,  18, 'WINNERS CURSE','Peak speculation, credit at max, smart money exiting'),
            (18,  21, 'DOWNTURN',     'Credit contraction, real estate stress, recession risk'),
        ],
        'next_signals': [
            'Commercial real estate distress accelerating',
            'Credit tightening for property development',
            'Rising vacancy rates in office/retail',
            'Regional bank stress from CRE exposure',
        ]
    },

    'rate_cycle': {
        'name'        : '40/80 Year Rate Cycle (US10Y)',
        'last_bottom' : 2020.5,
        'last_peak'   : 1981.5,
        'full_cycle'  : 80,
        'half_cycle'  : 40,
        'years_into_up': YEAR - 2020.5,
        'phase_map'   : [
            (0,  10, 'EARLY UP',     'Rates rising from historic lows, structural shift'),
            (10, 20, 'MID UP',       'Rates elevated, economy adjusting to higher cost of capital'),
            (20, 30, 'LATE UP',      'Rates at cycle highs, credit stress emerging'),
            (30, 40, 'PEAK/TURN',    'Rate cycle peak, beginning of structural decline'),
        ],
        'current_level': 4.25,
        'key_levels'   : {
            'structural_shift': 4.0,
            'mid_cycle'       : 6.0,
            'cycle_peak'      : 8.0,
        },
        'next_signals': [
            'US10Y holding above 4% confirms structural up cycle',
            'Watch for break above 5% = acceleration signal',
            'AU10Y tracking US — RBA forced to follow',
            'Bond market pricing inflation re-acceleration',
        ]
    },

    'commodity_equity_cycle': {
        'name'         : 'Commodity vs Equity Alternating Cycle (Gold/Dow)',
        'cycle_duration': (10, 15),
        'last_equity_peak' : 2021.5,
        'commodity_start'  : 2020.5,
        'years_into_commodity': YEAR - 2020.5,
        'phase_map'    : [
            (0,  3,  'EARLY',        'Precious metals lead — gold/silver breakout'),
            (3,  7,  'MID',          'Industrial metals accelerate — copper/nickel lead'),
            (7,  10, 'LATE',         'Energy dominates — agriculture late cycle'),
            (10, 15, 'PEAK/TURN',    'Commodity speculation peaks, equity cycle begins'),
        ],
        'supercycle_phase': 'METALS RUN → ENERGY MID CYCLE',
        'metals_rotation' : [
            'Tier 1: Copper (electrification backbone)',
            'Tier 1: Lithium (battery/storage)',
            'Tier 2: Uranium (nuclear baseload)',
            'Tier 2: Rare Earths (EV/defence)',
            'Tier 3: Manganese/Cobalt (supply chain)',
        ],
        'next_signals': [
            'SPGSCI/DJI ratio breaking higher = commodity cycle confirmed',
            'Gold/Dow ratio declining from highs = equity cycle returning',
            'Copper breakout above prior highs = Phase 2 acceleration',
            'Agriculture ETFs breaking out = late cycle signal',
        ]
    },

    'presidential_cycle': {
        'name'          : 'US Presidential/Election Cycle',
        'election_year' : 2024,
        'term_start'    : 2025,
        'cycle_year'    : YEAR - 2025 + 1,
        'phase_map'     : [
            (1, 1.9, 'YEAR 1', 'Policy uncertainty, historically weakest year for SPX'),
            (2, 2.9, 'YEAR 2', 'Mid-term year, choppy and poor SPX returns historically'),
            (3, 3.9, 'YEAR 3', 'Pre-election stimulus, historically strongest year'),
            (4, 4.9, 'YEAR 4', 'Election year, volatile but generally positive'),
        ],
        'next_signals': [
            'Mid-term elections Nov 2026 — watch policy shift',
            'SPX historically underperforms in year 1-2',
            'Tariff/trade policy changes = volatility catalyst',
            'Fed independence risk = bond market vigilantes',
        ]
    },

    'business_cycle': {
        'name'    : 'Business/Economic Cycle',
        'current' : 'LATE CYCLE / EARLY CONTRACTION',
        'phase_map': [
            'EARLY EXPANSION  — Credit expanding, employment rising, yields low',
            'MID EXPANSION    — GDP strong, profits rising, inflation moderate',
            'LATE EXPANSION   — Inflation rising, Fed tightening, yield curve flattening',
            'EARLY CONTRACTION— Yield curve inverted, credit tightening, PMI falling',
            'RECESSION        — GDP negative, unemployment rising, Fed cutting',
            'EARLY RECOVERY   — Credit loosening, leading indicators turning up',
        ],
        'current_signals': [
            'Yield curve recently un-inverted — historically 6-18 months to recession',
            'Fed cutting but inflation sticky — stagflation risk',
            'PMI manufacturing sub-50 in some months',
            'Consumer credit stress emerging',
        ],
        'next_signals': [
            'Unemployment rate rising above 4.5% = recession confirmed',
            'Yield curve re-inversion = double dip risk',
            'Credit spreads widening above 500bps = stress signal',
            'Fed pivoting to QE = late cycle confirmed',
        ]
    },

    'fed_cycle': {
        'name'   : 'Fed QT/QE Cycle',
        'current': 'QT SLOWING — PRE PIVOT',
        'balance_sheet_peak' : 8.9,  # trillion USD
        'balance_sheet_now'  : 7.0,  # approximate
        'fed_funds_rate'     : 4.25,
        'phase_map': [
            'QE ACTIVE     — Balance sheet expanding, liquidity injected',
            'QE TAPERING   — Asset purchases slowing, liquidity reducing',
            'QT ACTIVE     — Balance sheet shrinking, liquidity withdrawn',
            'QT SLOWING    — Pace of reduction slowing, pivot approaching',
            'PIVOT         — First QE signal, market historically front-runs',
        ],
        'next_signals': [
            'Fed balance sheet stabilising = QT effectively over',
            'First repo market stress = forced QE pivot',
            'Fed funds rate below 3% = full easing cycle',
            'Watch SOFR spreads for liquidity stress signals',
        ]
    },
}

# ── Determine current phase ───────────────────────────────────────────────────
def get_current_phase(cycle_key):
    c = cycles[cycle_key]

    if cycle_key == 'land_cycle':
        yr = c['current_year']
        for start, end, phase, desc in c['phase_map']:
            if start <= yr < end:
                return phase, desc, yr
        return 'DOWNTURN', 'Beyond typical cycle duration', yr

    elif cycle_key == 'rate_cycle':
        yr = c['years_into_up']
        for start, end, phase, desc in c['phase_map']:
            if start <= yr < end:
                return phase, desc, yr
        return 'EARLY UP', 'New cycle beginning', yr

    elif cycle_key == 'commodity_equity_cycle':
        yr = c['years_into_commodity']
        for start, end, phase, desc in c['phase_map']:
            if start <= yr < end:
                return phase, desc, yr
        return 'MID', 'Mid commodity cycle', yr

    elif cycle_key == 'presidential_cycle':
        yr = c['cycle_year']
        for start, end, phase, desc in c['phase_map']:
            if start <= yr < end:
                return phase, desc, yr
        return 'YEAR 1', 'Early term', yr

    else:
        return c['current'], '', 0

# ── Print cycle report ────────────────────────────────────────────────────────
def print_cycle_report():
    lines = []
    lines.append("═"*70)
    lines.append(f"  MACRO CYCLE TRACKER — {TODAY.strftime('%d %b %Y')}")
    lines.append("═"*70)

    for key in cycles:
        c     = cycles[key]
        lines.append("")
        lines.append(f"  {'─'*66}")
        lines.append(f"  {c['name'].upper()}")
        lines.append(f"  {'─'*66}")

        if key in ['land_cycle', 'rate_cycle', 'commodity_equity_cycle', 'presidential_cycle']:
            phase, desc, years = get_current_phase(key)
            lines.append(f"  Phase:    {phase}")
            lines.append(f"  Context:  {desc}")
            lines.append(f"  Years in: {round(years, 1)}")
        else:
            lines.append(f"  Phase:    {c['current']}")

        if key == 'commodity_equity_cycle':
            lines.append(f"  Supercycle: {c['supercycle_phase']}")
            lines.append("  Metals rotation order:")
            for m in c['metals_rotation']:
                lines.append(f"    → {m}")

        if key == 'rate_cycle':
            lines.append(f"  US10Y now: {c['current_level']}%")
            lines.append(f"  Key levels: Structural shift={c['key_levels']['structural_shift']}% | Mid cycle={c['key_levels']['mid_cycle']}% | Peak={c['key_levels']['cycle_peak']}%")

        if key == 'fed_cycle':
            lines.append(f"  Fed Funds: {c['fed_funds_rate']}%")
            lines.append(f"  Balance sheet: ~${c['balance_sheet_now']}T (peak ${c['balance_sheet_peak']}T)")

        if key == 'business_cycle':
            lines.append("  Current signals:")
            for s in c['current_signals']:
                lines.append(f"    • {s}")

        lines.append("  Watch for next phase:")
        for s in c['next_signals']:
            lines.append(f"    → {s}")

    lines.append("")
    lines.append("═"*70)
    return "\n".join(lines)

# ── Save report ───────────────────────────────────────────────────────────────
def save_report(output):
    from marketdb import results as _mr
    _mr.save_report('cycle_tracker', TODAY.strftime('%Y-%m-%d'), text=output)
    print(f"Report saved to marketdb (cycle_tracker {TODAY.strftime('%Y-%m-%d')})")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    report = print_cycle_report()
    print(report)
    save_report(report)