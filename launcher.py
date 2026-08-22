"""CLI twin of the dashboard's Run Scripts page.

    python launcher.py            # interactive menu
    python launcher.py A          # run one entry non-interactively (any key below)
    python launcher.py A M        # several in order

Stocks data collection goes through marketdb (one price fetch, every study);
macro / credit / ETF / sentiment scripts are unchanged.
"""
import os
import subprocess
import sys
from datetime import datetime

# ── Project paths ─────────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.abspath(__file__))
MACRO  = os.path.join(BASE, 'macro')
STOCKS = os.path.join(BASE, 'stocks')
ETF    = os.path.join(BASE, 'etf')
PYTHON = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')


def _mdb(*args):
    """A marketdb.run_daily invocation (cwd = BASE)."""
    return {'python': PYTHON, 'cwd': BASE, 'argv': ['-m', 'marketdb.run_daily', *args]}


def _script(cwd, script):
    return {'python': PYTHON, 'cwd': cwd, 'argv': [script]}


# ── Registry ──────────────────────────────────────────────────────────────────
SCRIPTS = {
    # ── Daily ─────────────────────────────────────────────────────────────────
    '1':  {'label': 'Macro Report',                                   **_script(MACRO, 'macro_report.py')},
    '2':  {'label': 'marketdb — update prices + ALL studies',         **_mdb()},
    '3':  {'label': 'marketdb — update prices only',                  **_mdb('--studies')},
    '4':  {'label': 'marketdb — re-run ALL studies (no fetch)',       **_mdb('--skip-fetch')},

    # ── Per market (fetch + studies for those universes) ──────────────────────
    '5':  {'label': 'AU Total Market (screener, benchmark, breadth)', **_mdb('--universe', 'au_total_market')},
    '6':  {'label': 'US Total Market (screener, benchmark, breadth)', **_mdb('--universe', 'us_total_market')},
    '7':  {'label': 'Nasdaq 100',                                     **_mdb('--universe', 'nasdaq100')},
    '8':  {'label': 'All Major Commodities',                          **_mdb('--universe', 'all_major_commodities')},
    '9':  {'label': 'Uranium',                                        **_mdb('--universe', 'uranium')},
    '10': {'label': 'AU Gold Miners',                                 **_mdb('--universe', 'au_gold_miners')},
    '11': {'label': 'Breadth only — all universes',                   **_mdb('--studies', 'breadth')},
    '12': {'label': 'RRG — all four studies',                         **_mdb('--studies', 'rrg')},

    # ── Other stocks tools ────────────────────────────────────────────────────
    '13': {'label': 'DeMark Scan — US ≥ $1B',   'python': PYTHON, 'cwd': BASE,   'argv': ['-m', 'marketdb.demark']},
    '14': {'label': 'ASX substantial holders',  **_script(STOCKS, 'asx_substantial_holders.py')},
    '15': {'label': 'Drawdown Analysis (see --help for periods)', 'python': PYTHON, 'cwd': BASE,
           'argv': ['-m', 'marketdb.drawdown', '--help']},

    # ── Macro / credit / ETF ──────────────────────────────────────────────────
    '16': {'label': 'Consumer Credit Report',   **_script(MACRO, 'consumer_credit.py')},
    '17': {'label': 'AU Credit Report',         **_script(MACRO, 'au_credit.py')},
    '18': {'label': 'ETF Income scoring',       **_script(ETF, 'etf_income_data.py')},

    # ── Batch runs ────────────────────────────────────────────────────────────
    'A': {'label': 'ALL — Full daily run (macro + marketdb)',          'batch': ['1', '2']},
    'B': {'label': 'AU — AU market only',                              'batch': ['5', '10']},
    'C': {'label': 'US — US market only',                              'batch': ['6', '7', '9']},
    'D': {'label': 'COMM — Commodities only',                          'batch': ['8', '9', '10']},
    'E': {'label': 'MACRO + BREADTH — Morning run',                    'batch': ['1', '11']},
    'M': {'label': 'MONTHLY — refresh universe (new listings, delistings, sectors, caps, indices)',
          **_mdb('--refresh-universe', '--skip-fetch', '--studies')},
    'R': {'label': 'MAINTENANCE — re-pull full price history (slow)', **_mdb('--full', '--studies')},
    'S': {'label': 'SETUP — bootstrap a fresh machine (one-off, ~15 min)', 'python': PYTHON, 'cwd': BASE,
          'argv': ['-m', 'marketdb.bootstrap']},
}

MENU_SECTIONS = [
    ('DAILY',            ['1', '2', '3', '4']),
    ('PER MARKET',       ['5', '6', '7', '8', '9', '10', '11', '12']),
    ('OTHER STOCK TOOLS', ['13', '14', '15']),
    ('MACRO / CREDIT / ETF', ['16', '17', '18']),
]
BATCH_KEYS = ['A', 'B', 'C', 'D', 'E', 'M', 'R', 'S']


# ── Runner ────────────────────────────────────────────────────────────────────
def run_script(key):
    s = SCRIPTS[key]
    print(f"\n{'═' * 60}")
    print(f"  {s['label']}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 60}")
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run([s['python'], *s['argv']], cwd=s['cwd'], env=env)
    status = 'OK' if result.returncode == 0 else f'FAILED (exit {result.returncode})'
    print(f"\n  → {status}")
    return result.returncode == 0


def run_batch(key):
    keys = SCRIPTS[key]['batch']
    print(f"\n  Running batch: {SCRIPTS[key]['label']} ({len(keys)} steps)")
    ok = 0
    for k in keys:
        if run_script(k):
            ok += 1
    print(f"\n  Batch complete — {ok}/{len(keys)} succeeded")


def show_menu():
    print(f"\n{'═' * 60}")
    print("  MARKET INTELLIGENCE — SCRIPT LAUNCHER")
    print(f"{'═' * 60}")
    for section, keys in MENU_SECTIONS:
        print(f"\n  {section}")
        for k in keys:
            print(f"    {k:>3}. {SCRIPTS[k]['label']}")
    print(f"\n  {'─' * 56}")
    print("  BATCH RUNS")
    print(f"  {'─' * 56}")
    for k in BATCH_KEYS:
        print(f"    {k:>3}. {SCRIPTS[k]['label']}")
    print(f"\n  {'─' * 56}")
    print("    Q. Quit")
    print(f"{'═' * 60}")


def dispatch(choice):
    choice = choice.strip().upper()
    if choice not in SCRIPTS:
        print(f"\n  Invalid choice: {choice}")
        return
    if 'batch' in SCRIPTS[choice]:
        run_batch(choice)
    else:
        run_script(choice)


if __name__ == "__main__":
    if len(sys.argv) > 1:                       # non-interactive: python launcher.py A M
        for c in sys.argv[1:]:
            dispatch(c)
        sys.exit(0)
    while True:
        show_menu()
        choice = input("\n  Enter choice: ").strip().upper()
        if choice == 'Q':
            print("\n  Goodbye.\n")
            break
        dispatch(choice)
