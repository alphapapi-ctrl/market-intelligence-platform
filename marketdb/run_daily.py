"""Daily entrypoint: one price update, then every study.

    python -m marketdb.run_daily                       # everything
    python -m marketdb.run_daily --universe au_total_market au_gold_miners
    python -m marketdb.run_daily --studies breadth rrg --skip-fetch
    python -m marketdb.run_daily --full                # re-pull the whole price history
    python -m marketdb.run_daily --refresh-universe    # force the monthly universe refresh now

Replaces the 16 per-universe scripts the dashboard used to run one after another.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime

import pandas as pd

from . import db, fetch, prices as P, results as R, studies as S, universe as U

ALL_STUDIES = ("screener", "benchmark", "breadth", "rrg")


def _log(msg: str) -> None:
    print(msg, flush=True)


db.utf8_console()


def maybe_refresh_universe(con, force: bool = False) -> bool:
    cfg = U.config()["refresh"]
    last = db.get_meta("last_universe_refresh", con=con)
    age = None
    if last:
        age = (datetime.now() - datetime.strptime(str(last)[:10], "%Y-%m-%d")).days
    due = force or (cfg.get("auto_monthly_refresh", True) and (age is None or age >= int(cfg.get("max_age_days", 31))))
    if not due:
        _log(f"universe: last refreshed {last} ({age} days ago) — no refresh needed")
        return False
    _log(f"universe: {'forced' if force else f'last refreshed {last}'} — running monthly refresh")
    try:
        from . import refresh_universe
        refresh_universe.refresh(con, log=_log)
        return True
    except Exception as e:  # noqa: BLE001 — a refresh failure must not block the daily run
        _log(f"universe refresh FAILED ({type(e).__name__}: {e}); continuing with the existing universe")
        traceback.print_exc()
        return False


def run_fetch(con, universes: list[str], full: bool, force: bool, retry_stale: bool) -> fetch.FetchSummary:
    if set(universes) == set(U.universe_keys()):
        tickers = U.fetch_ticker_set(con)
    else:
        tickers = set()
        for k in universes:
            tickers.update(U.members(k, con)["ticker"])
            tickers.update(U.benchmark_tickers(k))
        for r in U.config().get("rrg", {}).values():
            tickers.add(r["benchmark"])
        tickers.update(db.read_df("SELECT DISTINCT ticker FROM security_groups WHERE group_type IN ('theme','role')",
                                  con=con)["ticker"])
        tickers = sorted(tickers)
    _log(f"prices: updating {len(tickers)} tickers")
    return fetch.update_prices(tickers, con, full=full, force=force, retry_stale=retry_stale, log=_log)


def run_universe(con, key: str, studies: list[str], end: str | None, min_cov: float, rebuild_breadth: bool = False) -> dict:
    cfg = U.universe_cfg(key)
    out = {}
    mem = U.members(key, con)
    w = S._windows(end)
    got, want = P.coverage(mem["ticker"].tolist(), (pd.Timestamp(w["end"]) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                           w["end"], con)
    cov = got / want if want else 0
    _log(f"\n── {cfg['name']} ({key}): {want} members, {got} with recent prices ({cov:.0%})")
    if cov < min_cov:
        _log(f"   SKIPPED — coverage below {min_cov:.0%}; re-run after the price fetch recovers")
        return {"skipped": True}
    wanted = [s for s in studies if s in cfg.get("studies", [])]
    run_date = w["end"]
    for study in wanted:
        t0 = time.time()
        run_id = db.start_run(study, key, con, n_expected=want)
        try:
            if study == "screener":
                df = S.screener(key, con, end, members=mem)
                if df is not None:
                    df = R.save_study(df, "screener", key, con, run_date)
                    _log(f"   screener: {len(df)} ranked, {int(df['actionable'].sum())} actionable, "
                         f"{int(df['high_conv'].sum())} high-conv  ({time.time() - t0:.0f}s)")
                    _log(df.head(10)[["ticker", "name", "regime_label", "vol_label", "acc_watch", "score_final"]].to_string())
                out["screener"] = 0 if df is None else len(df)
            elif study == "benchmark":
                df = S.benchmark(key, con, end, members=mem)
                if df is not None:
                    df = R.save_study(df, "benchmark", key, con, run_date)
                    _log(f"   benchmark: {len(df)} ranked, {int(df['actionable'].sum())} actionable  ({time.time() - t0:.0f}s)")
                out["benchmark"] = 0 if df is None else len(df)
            elif study == "breadth":
                long = S.breadth(key, con, end, rebuild=rebuild_breadth, log=_log)
                n = R.save_breadth(long, con, log=_log, replace_all=rebuild_breadth)
                hist = R.breadth_history(key, con)
                if hist is not None and n:
                    _log(R.breadth_summary_text(hist, cfg["name"].upper()))
                _log(f"   breadth: {n} cells written ({time.time() - t0:.0f}s)")
                out["breadth"] = n
            db.finish_run(run_id, "ok", con)
        except Exception as e:  # noqa: BLE001
            _log(f"   {study} FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                db.finish_run(run_id, "error", con, notes=f"{type(e).__name__}: {e}")
            except Exception as e2:  # noqa: BLE001 — e.g. the store is still locked; don't mask the real error
                _log(f"   (could not record the failed run: {e2})")
    return out


def run_rrg(con, end: str | None) -> None:
    for study in U.config()["rrg"]:
        run_id = db.start_run("rrg", study, con)
        try:
            df = S.rrg(study, con, end)
            n = R.save_rrg(df, con)
            _log(f"   rrg {study}: {n} rows ({df['date'].max() if n else '-'})")
            db.finish_run(run_id, "ok", con, n_fetched=n)
        except Exception as e:  # noqa: BLE001
            db.finish_run(run_id, "error", con, notes=str(e))
            _log(f"   rrg {study} FAILED: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--universe", nargs="*", default=None, help="universe keys (default: all)")
    ap.add_argument("--studies", nargs="*", default=list(ALL_STUDIES), choices=ALL_STUDIES)
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--full", action="store_true", help="re-pull the full price history for every ticker")
    ap.add_argument("--force", action="store_true", help="re-pull today's overlap even if already fetched today")
    ap.add_argument("--retry-stale", action="store_true", help="also fetch tickers flagged stale")
    ap.add_argument("--end", default=None, help="as-of date YYYY-MM-DD (default today)")
    ap.add_argument("--refresh-universe", action="store_true")
    ap.add_argument("--no-refresh-check", action="store_true")
    ap.add_argument("--rebuild-breadth", action="store_true", help="recompute the full breadth history from the price store")
    ap.add_argument("--repair-splits", action="store_true",
                    help="scan the whole store for splits Yahoo left unadjusted and back-adjust them (then exit)")
    args = ap.parse_args(argv)

    t0 = time.time()
    universes = args.universe or U.universe_keys()
    for k in universes:
        U.universe_cfg(k)
    min_cov = float(U.config()["fetch"]["min_coverage"])
    _log(f"marketdb daily run — {db.now_iso()} — db {db.DB_PATH} ({db.db_size_mb()} MB)")

    with db.RunLock() as lock, db.session() as con:
        if not lock:
            _log(f"ERROR: another marketdb run is already writing the store ({lock.holder or 'unknown process'}).\n"
                 "       Wait for it to finish — two runs at once (an Update button plus the scheduled task / "
                 "launcher, or two buttons) end in 'database is locked'.")
            return 3
        if db.is_empty(con):
            _log("ERROR: " + db.BOOTSTRAP_HINT)
            return 2
        if args.repair_splits:
            isl = fetch.repair_price_islands(con, None, log=_log)
            _log(f"island repair: {len(isl)} ticker(s) had stray price blocks scaled back")
            found = fetch._dedupe_splits(fetch.find_unadjusted_splits(con))
            tick = sorted({f["ticker"] for f in found})
            _log(f"split repair: {len(tick)} ticker(s) with an unadjusted split on file: {', '.join(tick)}")
            if tick:
                # full re-fetch first (Yahoo may have adjusted since); update_prices then back-adjusts
                # whatever Yahoo still serves raw
                summ = fetch.update_prices(tick, con, full=True, force=True, log=_log)
                _log(f"split repair: {len(summ.split_repaired)} ticker(s) back-adjusted arithmetically — "
                     "re-run the studies to re-score them")
            return 0
        if not args.no_refresh_check:
            maybe_refresh_universe(con, force=args.refresh_universe)
        if not args.skip_fetch:
            summ = run_fetch(con, universes, args.full, args.force, args.retry_stale)
            if summ.coverage < min_cov:
                _log(f"WARNING: price coverage {summ.coverage:.0%} < {min_cov:.0%} — studies will guard per universe")
        for k in universes:
            run_universe(con, k, args.studies, args.end, min_cov, rebuild_breadth=args.rebuild_breadth)
        if "rrg" in args.studies:
            _log("\n── RRG")
            run_rrg(con, args.end)
        db.set_meta("last_daily_run", db.now_iso(), con)
        con.commit()
        try:
            con.execute("PRAGMA wal_checkpoint(PASSIVE)")   # housekeeping; a busy reader may block it
        except Exception as e:  # noqa: BLE001
            _log(f"(wal checkpoint skipped: {e})")
    _log(f"\ndone in {time.time() - t0:.0f}s — db {db.db_size_mb()} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
