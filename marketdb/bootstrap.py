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

    print("\n[1/4] seeding universe from legacy watchlists")
    from . import migrate_csv
    with db.session() as con:
        migrate_csv.Migration(con).run(import_breadth=False)

    if not args.skip_refresh:
        print("\n[2/4] monthly universe refresh (Yahoo screener)")
        from . import refresh_universe
        with db.session() as con:
            refresh_universe.refresh(con)
    else:
        print("\n[2/4] universe refresh skipped")

    print("\n[3/4] price back-fill + studies")
    from . import run_daily
    rc = run_daily.main(["--no-refresh-check"] + ([] if args.quick else ["--rebuild-breadth"]))

    print("\n[4/4] DeMark scan")
    try:
        from . import demark
        demark.run_scan(None, "us_total_market", log=lambda m: None)
    except Exception as e:  # noqa: BLE001
        print(f"  DeMark skipped: {e}")

    print(f"\nbootstrap done in {(time.time() - t0) / 60:.1f} min — db {db.db_size_mb()} MB")
    return rc


if __name__ == "__main__":
    sys.exit(main())
