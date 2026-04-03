import subprocess
import os
import sys
from datetime import datetime

# ── Project paths ─────────────────────────────────────────────────────────────
BASE    = os.path.dirname(os.path.abspath(__file__))
MACRO   = os.path.join(BASE, 'macro')
STOCKS  = os.path.join(BASE, 'stocks')

PYTHON = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')

# ── Script registry ───────────────────────────────────────────────────────────
SCRIPTS = {
    # ── Macro ─────────────────────────────────────────────────────────────────
    '1'  : {'label': 'Macro Report',                    'python': PYTHON,  'cwd': MACRO,   'script': 'macro_report.py'},

    # ── AU Market ─────────────────────────────────────────────────────────────
    '2'  : {'label': 'AU Total Market Screener',        'python': PYTHON, 'cwd': STOCKS,  'script': 'au_total_market_screener.py'},
    '3'  : {'label': 'AU Total Market Benchmark',       'python': PYTHON, 'cwd': STOCKS,  'script': 'au_total_market_benchmark.py'},
    '4'  : {'label': 'AU Total Market Breadth',         'python': PYTHON, 'cwd': STOCKS,  'script': 'au_total_market_breadth.py'},

    # ── US Market ─────────────────────────────────────────────────────────────
    '5'  : {'label': 'US Total Market Screener',        'python': PYTHON, 'cwd': STOCKS,  'script': 'us_total_market_screener.py'},
    '6'  : {'label': 'US Total Market Benchmark',       'python': PYTHON, 'cwd': STOCKS,  'script': 'us_total_market_benchmark.py'},
    '7'  : {'label': 'US Total Market Breadth',         'python': PYTHON, 'cwd': STOCKS,  'script': 'us_total_market_breadth.py'},

    # ── Commodities ───────────────────────────────────────────────────────────
    '8'  : {'label': 'All Commodities Screener',        'python': PYTHON, 'cwd': STOCKS,  'script': 'all_major_commodities_screener.py'},
    '9'  : {'label': 'All Commodities Benchmark',       'python': PYTHON, 'cwd': STOCKS,  'script': 'all_major_commodities_benchmark.py'},
    '10' : {'label': 'All Commodities Breadth',         'python': PYTHON, 'cwd': STOCKS,  'script': 'all_major_commodities_breadth.py'},

    # ── Uranium ───────────────────────────────────────────────────────────────
    '11' : {'label': 'Uranium Benchmark',               'python': PYTHON, 'cwd': STOCKS,  'script': 'uranium_benchmark.py'},
    '12' : {'label': 'Uranium Screener',                'python': PYTHON, 'cwd': STOCKS,  'script': 'uranium_screener.py'},

    # ── AU Gold Miners ────────────────────────────────────────────────────────
    '13' : {'label': 'AU Gold Miners Benchmark',        'python': PYTHON, 'cwd': STOCKS,  'script': 'au_gold_miners_benchmark.py'},
    '14' : {'label': 'AU Gold Miners Screener',         'python': PYTHON, 'cwd': STOCKS,  'script': 'au_gold_miners_screener.py'},

    # ── Drawdown Analysis ─────────────────────────────────────────────────────
    '15' : {'label': 'Drawdown Analysis',               'python': PYTHON, 'cwd': STOCKS,  'script': 'drawdown_analysis.py'},

    # ── RRG Graphs        ───────────────────────────────────────────────────── 
    '16' : {'label': 'RRG AU Data',   'python': PYTHON, 'cwd': STOCKS, 'script': 'rrg_au_data.py'},
    '17' : {'label': 'RRG US Data',   'python': PYTHON, 'cwd': STOCKS, 'script': 'rrg_us_data.py'},

    # ── Batch runs ────────────────────────────────────────────────────────────
    'A'  : {'label': 'ALL — Full daily run',            'batch': ['1','2','3','4','5','6','7','8','9','10','11','12','13','14']},
    'B'  : {'label': 'AU — AU market only',             'batch': ['1','2','3','4']},
    'C'  : {'label': 'US — US market only',             'batch': ['1','5','6','7']},
    'D'  : {'label': 'COMM — Commodities only',         'batch': ['8','9','10','11','12','13','14']},
    'E'  : {'label': 'MACRO + BREADTH — Morning run',   'batch': ['1','4','7','10']},
    'F'  : {'label': 'AU — All AU market scripts',  'batch': ['2','3','4','13','14','16']},
    'G'  : {'label': 'US — All US market scripts',  'batch': ['5','6','7','11','12','17']},
    'H' : {'label': 'Weekly — Update ALL Market Caps'},

    # ── Utilities ─────────────────────────────────────────────────────────────
    'U1' : {'label': 'Fetch Market Caps — AU',          'python': PYTHON, 'cwd': os.path.join(BASE, 'utilities'), 'script': 'fetch_market_caps_au.py'},
    'U2' : {'label': 'Fetch Market Caps — US',          'python': PYTHON, 'cwd': os.path.join(BASE, 'utilities'), 'script': 'fetch_market_caps_us.py'},
    'U3' : {'label': 'Fetch Market Caps — Commodities', 'python': PYTHON, 'cwd': os.path.join(BASE, 'utilities'), 'script': 'fetch_market_caps_commodities.py'},
    'U4' : {'label': 'Fetch Market Caps — Uranium',     'python': PYTHON, 'cwd': os.path.join(BASE, 'utilities'), 'script': 'fetch_market_caps_uranium.py'},
    'U5' : {'label': 'Fetch Market Caps — AU Gold',     'python': PYTHON, 'cwd': os.path.join(BASE, 'utilities'), 'script': 'fetch_market_caps_au_gold.py'},
     
}

# ── Run a single script ───────────────────────────────────────────────────────
def run_script(key):
    s       = SCRIPTS[key]
    label   = s['label']
    python  = s['python']
    cwd     = s['cwd']
    script  = os.path.join(cwd, s['script'])
    start   = datetime.now()

    print(f"\n{'─'*60}")
    print(f"  Running: {label}")
    print(f"  Script:  {script}")
    print(f"  Started: {start.strftime('%H:%M:%S')}")
    print(f"{'─'*60}")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'

    result = subprocess.run(
        [python, script],
        cwd=cwd,
        env=env,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    elapsed = (datetime.now() - start).seconds
    mins    = elapsed // 60
    secs    = elapsed % 60

    if result.returncode == 0:
        print(f"  ✓ Completed in {mins}m {secs}s")
    else:
        print(f"  ✗ Failed after {mins}m {secs}s (return code {result.returncode})")

    return result.returncode == 0

# ── Run a batch ───────────────────────────────────────────────────────────────
def run_batch(key):
    batch     = SCRIPTS[key]['batch']
    label     = SCRIPTS[key]['label']
    start     = datetime.now()
    results   = {}

    print(f"\n{'═'*60}")
    print(f"  BATCH: {label}")
    print(f"  Scripts: {len(batch)}")
    print(f"  Started: {start.strftime('%H:%M:%S')}")
    print(f"{'═'*60}")

    for k in batch:
        success      = run_script(k)
        results[k]   = success

    elapsed = (datetime.now() - start).seconds
    mins    = elapsed // 60
    secs    = elapsed % 60

    print(f"\n{'═'*60}")
    print(f"  BATCH COMPLETE — {mins}m {secs}s")
    print(f"{'═'*60}")
    for k, success in results.items():
        status = '✓' if success else '✗'
        print(f"  {status} {SCRIPTS[k]['label']}")
    print(f"{'═'*60}")

# ── Menu ──────────────────────────────────────────────────────────────────────
def show_menu():
    print(f"\n{'═'*60}")
    print(f"  PROJECT LAUNCHER — {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'═'*60}")
    print("")
    print("  INDIVIDUAL SCRIPTS")
    print(f"  {'─'*56}")

    sections = [
        ('MACRO',         ['1']),
        ('AU MARKET',     ['2','3','4']),
        ('US MARKET',     ['5','6','7']),
        ('COMMODITIES',   ['8','9','10']),
        ('URANIUM',       ['11','12']),
        ('AU GOLD',       ['13','14']),
        ('DRAWDOWN',      ['15']),
        ('UTILITIES',     ['U1','U2','U3','U4','U5']),
    ]

    for section, keys in sections:
        print(f"\n  {section}")
        for k in keys:
            print(f"    {k:>3}. {SCRIPTS[k]['label']}")

    print(f"\n  {'─'*56}")
    print("  BATCH RUNS")
    print(f"  {'─'*56}")
    for k in ['A','B','C','D','E','F','G','H']:
        print(f"    {k:>3}. {SCRIPTS[k]['label']}")

    print(f"\n  {'─'*56}")
    print("    Q. Quit")
    print(f"{'═'*60}")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("\n  Enter choice: ").strip().upper()

        if choice == 'Q':
            print("\n  Goodbye.\n")
            break
        elif choice == 'H':
            for key in ['U1','U2','U3','U4','U5']:
                run_script(key)
        elif choice in SCRIPTS:
            if 'batch' in SCRIPTS[choice]:
                run_batch(choice)
            else:
                run_script(choice)
        else:
            print(f"\n  Invalid choice: {choice}")
