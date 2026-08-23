"""First-time setup on a fresh clone (or a new machine): build data/market.db from scratch.

    python -m marketdb.bootstrap            # ~15 min: seed universe, 3y prices, all studies
    python -m marketdb.bootstrap --quick    # skip the breadth history rebuild (daily run fills it in)

Steps
  1. seed      securities / groups from the tracked legacy watchlists (stocks/watchlist/*.csv)
               and, if present, the legacy result CSVs (screener baselines for delta_rank)
  2. refresh   Yahoo screener -> current AU/US universe, sectors, caps, index memberships
  3. prices    full back-fill (initial_backfill_days, default 3 years) for every ticker
  4. studies   screener / benchmark for every universe, breadth history rebuilt from the
               store, RRG, DeMark
  5. macro     macro report + consumer / AU credit reports (the Macro and Debt Markets pages)
               — only if macro/config.py exists with a FRED key; otherwise prints what to do

Safe to re-run: every step upserts. If you were given a copy of data/market.db instead, skip
this and just run `python -m marketdb.run_daily`.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import db


def main(argv=None) -> int:
    db.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="skip the full breadth history rebuild")
    ap.add_argument("--skip-refresh", action="store_true", help="keep the seeded universe; no Yahoo screener pass")
    args = ap.parse_args(argv)
    t0 = time.time()

    have = db.DB_PATH.exists() and (db.scalar("SELECT COUNT(*) FROM securities") or 0) > 0
    print(f"marketdb bootstrap — {db.DB_PATH} ({'exists, ' + str(db.db_size_mb()) + ' MB' if have else 'new'})")

    print("\n[1/5] seeding universe from legacy watchlists")
    from . import migrate_csv
    with db.session() as con:
        migrate_csv.Migration(con).run(import_breadth=False)

    if not args.skip_refresh:
        print("\n[2/5] monthly universe refresh (Yahoo screener)")
        from . import refresh_universe
        with db.session() as con:
            refresh_universe.refresh(con)
    else:
        print("\n[2/5] universe refresh skipped")

    print("\n[3/5] price back-fill + studies")
    from . import run_daily
    rc = run_daily.main(["--no-refresh-check"] + ([] if args.quick else ["--rebuild-breadth"]))

    print("\n[4/5] DeMark scan")
    try:
        from . import demark
        demark.run_scan(None, "us_total_market", log=lambda m: None)
    except Exception as e:  # noqa: BLE001
        print(f"  DeMark skipped: {e}")

    print("\n[5/5] macro + credit reports")
    run_macro_reports()

    print(f"\nbootstrap done in {(time.time() - t0) / 60:.1f} min — db {db.db_size_mb()} MB")
    return rc


def run_macro_reports() -> None:
    """Macro report + consumer / AU credit reports, if macro/config.py (gitignored, FRED key) exists."""
    import os
    import subprocess
    import sys as _sys
    macro_dir = db.BASE_DIR / "macro"
    _sys.path.insert(0, str(macro_dir))
    try:
        from _config_check import config_problem, SETUP_STEPS
    except ImportError:
        print("  macro/_config_check.py missing — skipped")
        return
    problem = config_problem()
    if problem:
        print(f"  skipped: {problem}\n" + "\n".join("  " + ln for ln in SETUP_STEPS.splitlines()[1:]))
        return
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for script, label in (("macro_report.py", "macro report"), ("consumer_credit.py", "consumer credit"),
                          ("au_credit.py", "AU credit")):
        r = subprocess.run([_sys.executable, script], cwd=str(macro_dir), env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            print(f"  {label}: ok")
        else:
            print(f"  {label}: FAILED — {(r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout).strip() else 'no output'}")


if __name__ == "__main__":
    sys.exit(main())
