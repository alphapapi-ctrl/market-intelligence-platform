"""The only module that downloads daily bars from Yahoo.

    from marketdb import fetch
    with db.session() as con:
        summary = fetch.update_prices(tickers, con)

Behaviour
  * incremental: a ticker with history is fetched from last_date - overlap; a new one
    is back-filled `initial_backfill_days`
  * chunked (150) with a pause between chunks and exponential back-off retries
  * adjustment-drift detection on the overlap window -> full re-fetch of that ticker
  * fetch_log bookkeeping (status, consecutive failures) for delisting detection
  * returns a FetchSummary the studies use for their coverage guard
"""
from __future__ import annotations

import logging
import sqlite3
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import db, universe

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)   # per-ticker "possibly delisted" chatter


@dataclass
class FetchSummary:
    expected: int = 0
    ok: int = 0                      # tickers with data after this run (fresh or already current)
    fetched_rows: int = 0
    empty: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    refetched_full: list[str] = field(default_factory=list)
    skipped_stale: list[str] = field(default_factory=list)
    split_repaired: list[str] = field(default_factory=list)
    island_repaired: list[str] = field(default_factory=list)
    chunks: int = 0
    seconds: float = 0.0

    @property
    def coverage(self) -> float:
        return (self.ok / self.expected) if self.expected else 0.0

    def line(self) -> str:
        return (f"fetch: {self.ok}/{self.expected} tickers ({self.coverage:.0%}), "
                f"{self.fetched_rows} rows, {self.chunks} chunks, {self.seconds:.0f}s, "
                f"empty={len(self.empty)}, errors={len(self.errors)}, "
                f"full-refetch={len(self.refetched_full)}, skipped-stale={len(self.skipped_stale)}, "
                f"split-repaired={len(self.split_repaired)}, island-repaired={len(self.island_repaired)}")


def _cfg() -> dict:
    return universe.config()["fetch"]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ── Yahoo download with retries ───────────────────────────────────────────────
def _download(tickers: list[str], start: str, end: str, retries: int) -> pd.DataFrame | None:
    import yfinance as yf
    delay = 8
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            raw = yf.download(tickers, start=start, end=end, auto_adjust=False, actions=True,
                              group_by="column", threads=True, progress=False, ignore_tz=True)
            if raw is None or raw.empty:
                if len(tickers) == 1:
                    return raw          # a single delisted ticker legitimately returns nothing
                raise RuntimeError("empty frame for whole chunk")
            return raw
        except Exception as e:            # noqa: BLE001 — rate limit / network / Yahoo hiccup
            last_err = e
            name = type(e).__name__
            if attempt < retries:
                wait = delay * (3 ** (attempt - 1))
                print(f"    chunk download failed ({name}: {str(e)[:80]}); retry {attempt}/{retries - 1} in {wait}s")
                time.sleep(wait)
    print(f"    chunk FAILED after {retries} attempts: {last_err}")
    return None


def _to_long(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """yfinance frame -> long rows (ticker, date, open, high, low, close, adj_close, volume, dividend, split)."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    fields = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close",
              "Volume": "volume", "Dividends": "dividend", "Stock Splits": "split"}
    frames = []
    multi = isinstance(raw.columns, pd.MultiIndex)
    for t in tickers:
        try:
            sub = raw.xs(t, axis=1, level=1) if multi else raw
        except KeyError:
            continue
        if sub is None or sub.empty or "Close" not in sub.columns:
            continue
        sub = sub.rename(columns=fields)
        sub = sub[[c for c in fields.values() if c in sub.columns]].copy()
        sub = sub.dropna(subset=["close"])
        if sub.empty:
            continue
        sub.insert(0, "date", pd.to_datetime(sub.index).strftime("%Y-%m-%d"))
        sub.insert(0, "ticker", t)
        frames.append(sub.reset_index(drop=True))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    for c in ("open", "high", "low", "close", "adj_close", "volume", "dividend", "split"):
        if c not in out.columns:
            out[c] = None
    return out[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume", "dividend", "split"]]


# ── Drift detection ───────────────────────────────────────────────────────────
def _drifted(new: pd.DataFrame, con: sqlite3.Connection, tol: float) -> list[str]:
    """Tickers whose stored adj_close on overlapping dates differs from the fresh pull."""
    if new.empty:
        return []
    tickers = new["ticker"].unique().tolist()
    lo, hi = new["date"].min(), new["date"].max()
    con.execute("CREATE TEMP TABLE IF NOT EXISTS _t (ticker TEXT PRIMARY KEY)")
    con.execute("DELETE FROM _t")
    con.executemany("INSERT INTO _t VALUES (?)", [(t,) for t in tickers])
    old = db.read_df("""SELECT p.ticker, p.date, p.adj_close FROM prices p JOIN _t ON _t.ticker = p.ticker
                        WHERE p.date BETWEEN ? AND ?""", (lo, hi), con=con)
    if old.empty:
        return []
    m = new[["ticker", "date", "adj_close"]].merge(old, on=["ticker", "date"], suffixes=("_new", "_old"))
    m = m.dropna()
    m = m[m["adj_close_old"].abs() > 0]
    rel = ((m["adj_close_new"] - m["adj_close_old"]).abs() / m["adj_close_old"].abs())
    bad = m.loc[rel > tol, "ticker"].unique().tolist()
    return bad


# ── Public API ────────────────────────────────────────────────────────────────
def ensure_securities(tickers: list[str], con: sqlite3.Connection, role: str | None = None,
                      names: dict[str, str] | None = None) -> list[str]:
    """Insert minimal rows for unknown tickers (used by macro/etf helpers). Returns the
    subset that is allowed in the DB (AU/US/GLOBAL)."""
    allowed = []
    today = db.today_str()
    for t in tickers:
        reg = universe.region_of(t)
        if reg is None:
            continue
        allowed.append(t)
        exists = db.scalar("SELECT 1 FROM securities WHERE ticker=?", (t,), con=con)
        if not exists:
            qt = "INDEX" if t.startswith("^") else "FUTURE" if t.endswith("=F") else \
                 "CURRENCY" if (t.endswith("=X") or t == "DX-Y.NYB") else "EQUITY"
            con.execute("""INSERT INTO securities (ticker, name, region, quote_type, active, first_seen, source)
                           VALUES (?,?,?,?,1,?,'manual')""", (t, (names or {}).get(t, t), reg, qt, today))
        if role:
            con.execute("""INSERT OR IGNORE INTO security_groups (ticker, group_type, group_key, attr, source, updated)
                           VALUES (?,?,?,?,?,?)""", (t, "role", role, (names or {}).get(t), "runtime", today))
    con.commit()
    return allowed


def update_prices(tickers: list[str], con: sqlite3.Connection, *, full: bool = False,
                  end: str | None = None, retry_stale: bool = False, force: bool = False,
                  log=print) -> FetchSummary:
    """full=True re-pulls the whole backfill window; force=True re-pulls the overlap even
    for tickers already fetched today."""
    cfg = _cfg()
    chunk_size = int(cfg["chunk_size"])
    pause      = float(cfg["pause_between_chunks_sec"])
    overlap    = int(cfg["incremental_overlap_days"])
    backfill   = int(cfg["initial_backfill_days"])
    tol        = float(cfg["adjustment_tolerance"])
    retries    = int(cfg["retries"])
    delist_n   = int(universe.config()["refresh"].get("delist_after_consecutive_failures", 10))

    t0 = time.time()
    tickers = sorted(set(t for t in tickers if t))
    summ = FetchSummary(expected=len(tickers))
    today = datetime.today()
    end_dt = (pd.Timestamp(end) if end else today) + timedelta(days=1)
    end_s = end_dt.strftime("%Y-%m-%d")
    full_start = (today - timedelta(days=backfill)).strftime("%Y-%m-%d")

    log_df = db.read_df("SELECT ticker, last_date, first_date, consecutive_failures FROM fetch_log", con=con)
    last = dict(zip(log_df["ticker"], log_df["last_date"]))
    first = dict(zip(log_df["ticker"], log_df["first_date"]))
    fails = dict(zip(log_df["ticker"], log_df["consecutive_failures"]))
    deep = {k: v for k, v in cfg.get("deep_history", {}).items() if not k.startswith("_")}
    as_of = end_dt - timedelta(days=1)                       # the end date itself
    back = {0: 3, 6: 2}.get(as_of.weekday(), 1)              # Mon -> Fri, Sun -> Fri, else yesterday
    prev_weekday = pd.Timestamp((as_of - timedelta(days=back)).date())

    run_id = db.start_run("fetch", None, con, n_expected=len(tickers))

    # ── partition ──
    buckets: dict[str, list[str]] = {}        # start date -> tickers
    for t in tickers:
        if not retry_stale and fails.get(t, 0) >= delist_n:
            summ.skipped_stale.append(t)
            continue
        ld = last.get(t)
        deep_start = deep.get(t)
        if deep_start and (not ld or full or (first.get(t) and str(first[t]) > deep_start[:4] + "-12-31")):
            # deep-history ticker whose stored history starts too late -> refetch from its deep start
            con.execute("DELETE FROM prices WHERE ticker=?", (t,))
            con.execute("UPDATE fetch_log SET n_rows=0, first_date=NULL, last_date=NULL WHERE ticker=?", (t,))
            buckets.setdefault(deep_start, []).append(t)
            continue
        if full or not ld:
            start = full_start
        else:
            start = (pd.Timestamp(ld) - timedelta(days=overlap)).strftime("%Y-%m-%d")
            # already current: has the previous weekday's bar (or today's). A ticker whose
            # latest bar is older is re-pulled every run, so a morning run that lands before
            # a market's close has posted is simply completed by the next run.
            if not force and pd.Timestamp(ld) >= prev_weekday:
                summ.ok += 1
                continue
        # bucket starts to the week so incremental tickers share calls
        key = start if start == full_start else pd.Timestamp(start).to_period("W").start_time.strftime("%Y-%m-%d")
        buckets.setdefault(key, []).append(t)

    deep_starts_pre = set(deep.values())
    n_calls = sum((len(v) + chunk_size - 1) // chunk_size for v in buckets.values())
    log(f"  fetching {sum(len(v) for v in buckets.values())} tickers in {n_calls} chunks "
        f"({len(buckets)} start buckets; {summ.ok} already current; {len(summ.skipped_stale)} stale skipped)")

    drift_queue: list[str] = []
    pulled_full: set[str] = {t for s_, grp in buckets.items() if s_ == full_start or s_ in deep_starts_pre for t in grp}

    def _process(chunk: list[str], start: str, allow_drift_check: bool) -> None:
        raw = _download(chunk, start, end_s, retries)
        summ.chunks += 1
        if raw is None:
            for t in chunk:
                summ.errors[t] = "download failed"
                _mark(t, None, "error", "download failed")
            return
        new = _to_long(raw, chunk)
        got = set(new["ticker"].unique()) if not new.empty else set()
        if allow_drift_check and not new.empty:
            bad = _drifted(new, con, tol)
            if bad:
                drift_queue.extend(bad)
                new = new[~new["ticker"].isin(bad)]
                got -= set(bad)
        if not new.empty:
            summ.fetched_rows += db.upsert_df(new, "prices", con)
        for t in chunk:
            if t in got:
                sub = new[new["ticker"] == t]
                _mark(t, sub, "ok", None)
                summ.ok += 1
            elif t in drift_queue:
                pass
            else:
                summ.empty.append(t)
                _mark(t, None, "empty", "no rows returned")
        con.commit()

    def _mark(t: str, sub: pd.DataFrame | None, status: str, err: str | None) -> None:
        now = db.now_iso()
        if status == "ok" and sub is not None and len(sub):
            first_new, last_new, n_new = sub["date"].min(), sub["date"].max(), len(sub)
            con.execute("""INSERT INTO fetch_log (ticker, last_fetch_at, first_date, last_date, n_rows, status, error, consecutive_failures)
                           VALUES (?,?,?,?,?,?,NULL,0)
                           ON CONFLICT(ticker) DO UPDATE SET
                             last_fetch_at=excluded.last_fetch_at,
                             first_date=MIN(COALESCE(fetch_log.first_date, excluded.first_date), excluded.first_date),
                             last_date=MAX(COALESCE(fetch_log.last_date, excluded.last_date), excluded.last_date),
                             n_rows=COALESCE(fetch_log.n_rows,0)+excluded.n_rows,
                             status='ok', error=NULL, consecutive_failures=0""",
                        (t, now, first_new, last_new, n_new, status))
        else:
            con.execute("""INSERT INTO fetch_log (ticker, last_fetch_at, status, error, consecutive_failures)
                           VALUES (?,?,?,?,1)
                           ON CONFLICT(ticker) DO UPDATE SET
                             last_fetch_at=excluded.last_fetch_at, status=excluded.status, error=excluded.error,
                             consecutive_failures=fetch_log.consecutive_failures+1""",
                        (t, now, status, err))

    # ── run buckets ──
    done = 0
    deep_starts = set(deep.values())
    for start, group in sorted(buckets.items()):
        incremental = start != full_start and start not in deep_starts
        for chunk in _chunks(group, chunk_size):
            _process(chunk, start, allow_drift_check=incremental)
            done += 1
            if done % 5 == 0 or done == n_calls:
                log(f"    {done}/{n_calls} chunks, {summ.fetched_rows} rows, {time.time() - t0:.0f}s")
            if done < n_calls:
                time.sleep(pause)

    # ── drift -> full refetch ──
    if drift_queue:
        drift_queue = sorted(set(drift_queue))
        log(f"  adjustment drift on {len(drift_queue)} tickers -> full re-fetch")
        for chunk in _chunks(drift_queue, chunk_size):
            con.execute("CREATE TEMP TABLE IF NOT EXISTS _t (ticker TEXT PRIMARY KEY)")
            con.execute("DELETE FROM _t")
            con.executemany("INSERT INTO _t VALUES (?)", [(t,) for t in chunk])
            con.execute("DELETE FROM prices WHERE ticker IN (SELECT ticker FROM _t)")
            con.execute("UPDATE fetch_log SET n_rows=0, first_date=NULL, last_date=NULL, full_refetch_at=? "
                        "WHERE ticker IN (SELECT ticker FROM _t)", (db.now_iso(),))
            _process(chunk, full_start, allow_drift_check=False)
            summ.refetched_full.extend(chunk)
            time.sleep(pause)

    # ── unadjusted splits ──
    # Yahoo records a split but the earlier bars still show the raw jump: either Yahoo has not
    # back-adjusted yet (US names a few days after a split — a full re-fetch fixes it, and also
    # cleans any half-adjusted bars the overlap window picked up meanwhile) or it never will
    # (ASX consolidations) -> arithmetic back-adjustment as the fallback.
    summ.island_repaired = repair_price_islands(con, tickers, log=log)
    found = _dedupe_splits(find_unadjusted_splits(con, tickers))
    if found:
        pulled_full |= set(summ.refetched_full)
        need = sorted({f["ticker"] for f in found} - pulled_full)
        if need:
            log(f"  unadjusted split(s) on {len(need)} ticker(s) -> full re-fetch: "
                f"{', '.join(need[:8])}{'…' if len(need) > 8 else ''}")
            for chunk in _chunks(need, chunk_size):
                con.execute("CREATE TEMP TABLE IF NOT EXISTS _t (ticker TEXT PRIMARY KEY)")
                con.execute("DELETE FROM _t")
                con.executemany("INSERT INTO _t VALUES (?)", [(t,) for t in chunk])
                con.execute("DELETE FROM prices WHERE ticker IN (SELECT ticker FROM _t)")
                con.execute("UPDATE fetch_log SET n_rows=0, first_date=NULL, last_date=NULL, full_refetch_at=? "
                            "WHERE ticker IN (SELECT ticker FROM _t)", (db.now_iso(),))
                for t in chunk:                       # deep-history tickers keep their long start
                    if t in deep:
                        _process([t], deep[t], allow_drift_check=False)
                rest = [t for t in chunk if t not in deep]
                if rest:
                    _process(rest, full_start, allow_drift_check=False)
                summ.refetched_full.extend(chunk)
                time.sleep(pause)
        summ.split_repaired = repair_unadjusted_splits(con, sorted({f["ticker"] for f in found}), log=log)

    # securities.last_seen for everything that has data today
    con.execute("""UPDATE securities SET last_seen = (SELECT last_date FROM fetch_log f WHERE f.ticker = securities.ticker)
                   WHERE ticker IN (SELECT ticker FROM fetch_log WHERE status='ok')""")
    summ.seconds = time.time() - t0
    db.finish_run(run_id, "ok" if summ.coverage >= cfg["min_coverage"] else "partial", con,
                  n_fetched=summ.ok, notes=summ.line())
    con.commit()
    log("  " + summ.line())
    return summ


# ── Price islands ──────────────────────────────────────────────────────────────
# Yahoo feeds around corporate actions sometimes carry short blocks of bars at exactly 2x / 0.5x
# (or 1/split) the surrounding level that revert a few days later (MNST, AGL, MGRT 2026). A block
# of <= ISLAND_MAX_BARS that starts with a jump of >= ISLAND_MIN_JUMP and ends with the inverse
# jump (within ISLAND_TOL) is scaled back to its neighbours; a genuine move never round-trips
# that exactly.
ISLAND_MIN_JUMP = 1.8
ISLAND_TOL = 1.05
ISLAND_MAX_BARS = 10
ISLAND_MIN_PRICE = 0.10        # below this a 2x round-trip can be a one-tick / one-trade spike, not a feed glitch
ISLAND_CLEAN_RATIOS = (2, 3, 4, 5, 8, 10, 20, 25, 40, 50, 100)   # scale glitches are clean ratios (or inverses)
ISLAND_RATIO_TOL = 1.05        # ... give or take the day's real move
ISLAND_NOISE_BARS = 30         # neighbourhood used to measure the stock's typical daily move
ISLAND_NOISE_MULT = 8          # the jump must be this many times the median non-zero |daily move| nearby —
                               # in a tick-quantised penny stock the "jump" IS the typical move


def find_price_islands(con: sqlite3.Connection, tickers: list[str] | None = None) -> list[dict]:
    """-> [{ticker, start, end, n, mult}] blocks whose bars must be multiplied by mult."""
    sql = "SELECT ticker, date, close FROM prices WHERE close IS NOT NULL AND close > 0"
    if tickers:
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _s (ticker TEXT PRIMARY KEY)")
        con.execute("DELETE FROM _s")
        con.executemany("INSERT OR IGNORE INTO _s VALUES (?)", [(t,) for t in tickers])
        sql += " AND ticker IN (SELECT ticker FROM _s)"
    df = db.read_df(sql + " ORDER BY ticker, date", con=con)
    out = []
    min_j, tol = np.log(ISLAND_MIN_JUMP), np.log(ISLAND_TOL)
    for t, g in df.groupby("ticker", sort=False):
        c = g["close"].to_numpy(dtype=float)
        if len(c) < 4:
            continue
        d = g["date"].tolist()
        r = np.log(c[1:] / c[:-1])                       # r[i] = jump into bar i+1
        i = 0
        while i < len(r):
            if abs(r[i]) >= min_j:
                for j in range(i + 1, min(i + 1 + ISLAND_MAX_BARS, len(r))):
                    if abs(r[j] + r[i]) < tol:           # inverse jump closes the island
                        mult = float(np.exp(-r[i]))
                        clean = any(abs(np.log(mult * q)) < np.log(ISLAND_RATIO_TOL) or
                                    abs(np.log(mult / q)) < np.log(ISLAND_RATIO_TOL) for q in ISLAND_CLEAN_RATIOS)
                        nb = np.abs(np.concatenate([r[max(0, i - ISLAND_NOISE_BARS):i], r[j + 1:j + 1 + ISLAND_NOISE_BARS]]))
                        nb = nb[nb > 0]
                        quiet = len(nb) >= 5 and abs(r[i]) >= ISLAND_NOISE_MULT * float(np.median(nb))
                        if (clean and quiet and np.all(np.abs(r[i + 1:j]) < min_j)
                                and c[max(0, i - 1):j + 2].min() >= ISLAND_MIN_PRICE):
                            out.append({"ticker": t, "start": d[i + 1], "end": d[j], "n": j - i, "mult": mult})
                            i = j
                        break
            i += 1
    return out


def repair_price_islands(con: sqlite3.Connection, tickers: list[str] | None = None, dry: bool = False,
                         log=print) -> list[str]:
    found = find_price_islands(con, tickers)
    fixed = []
    for f in found:
        log(f"  island repair {f['ticker']}: {f['n']} bar(s) {f['start']}..{f['end']} x{f['mult']:.4g}{' [dry]' if dry else ''}")
        if dry:
            continue
        con.execute("""UPDATE prices SET open=open*?, high=high*?, low=low*?, close=close*?, adj_close=adj_close*?,
                       volume=volume/? WHERE ticker=? AND date BETWEEN ? AND ?""",
                    (f["mult"],) * 6 + (f["ticker"], f["start"], f["end"]))
        fixed.append(f["ticker"])
    if fixed:
        con.commit()
    return sorted(set(fixed))


# ── Unadjusted splits ─────────────────────────────────────────────────────────
SPLIT_SEARCH_BARS = 7          # bars either side of Yahoo's split date searched for the raw jump / classified old-new
SPLIT_MATCH_TOL = 1.10         # the jump bar must move within 10% of 1/split vs the bar before it (log-scale)
SPLIT_LEVEL_BARS = 10          # bars either side of the jump whose medians define the old and new price levels
SPLIT_LEVEL_TOL = 1.5          # those levels must differ by 1/split within a factor of 1.5 (guards a one-day crash)
SPLIT_MIN_FACTOR = 1.5         # ignore stock-dividend "splits" below 1.5x — undetectable against daily noise, immaterial


def find_unadjusted_splits(con: sqlite3.Connection, tickers: list[str] | None = None) -> list[dict]:
    """Splits on file whose surrounding bars still sit on the pre-split price level.

    Yahoo's split value is new/old shares (0.025 = 1-for-40 consolidation, 2.0 = 2-for-1 split),
    so old-scale bars are `factor = 1/split` times the new scale. The raw jump is the bar near the
    split date that moves ~factor against the previous bar; medians of the bars either side of it
    give the old and new price levels, and every bar in the window is classified by the level it
    is closer to — Yahoo feeds around a split often contain stray bars already on the new scale
    (MNST 2026) and the odd old-scale straggler after the transition, so bars are fixed
    individually rather than by a date cut.

    Returns one dict per (ticker, split): {ticker, split_date, split, factor, jump_date,
    cut_date, old_dates, n_before} where every bar before cut_date plus the listed old_dates
    needs adjusting and jump_date is the first bar of the persistent new scale.
    """
    sql = "SELECT ticker, date, split FROM prices WHERE split IS NOT NULL AND split NOT IN (0, 1)"
    params: tuple = ()
    if tickers:
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _s (ticker TEXT PRIMARY KEY)")
        con.execute("DELETE FROM _s")
        con.executemany("INSERT OR IGNORE INTO _s VALUES (?)", [(t,) for t in tickers])
        sql += " AND ticker IN (SELECT ticker FROM _s)"
    splits = db.read_df(sql + " ORDER BY ticker, date", params, con=con)
    out = []
    for t, grp in splits.groupby("ticker"):
        bars = db.read_df("SELECT date, close FROM prices WHERE ticker=? AND close IS NOT NULL AND close > 0 ORDER BY date",
                          (t,), con=con)
        if len(bars) < 6:
            continue
        dates = bars["date"].tolist()
        closes = bars["close"].to_numpy(dtype=float)
        for sd, s in zip(grp["date"], grp["split"]):
            factor = 1.0 / float(s)
            if max(factor, 1.0 / factor) < SPLIT_MIN_FACTOR:
                continue
            idx = int(np.searchsorted(dates, sd))
            lo, hi = max(1, idx - SPLIT_SEARCH_BARS), min(len(closes) - 1, idx + SPLIT_SEARCH_BARS)
            if lo >= hi:
                continue
            # 1. the raw jump: some bar near the split date moves ~factor vs the bar before it
            ratios = np.log(closes[lo:hi + 1] / closes[lo - 1:hi])
            j = int(np.argmin(np.abs(ratios - np.log(factor))))
            k = lo + j
            old_level = float(np.median(closes[max(0, k - SPLIT_LEVEL_BARS):k]))
            new_level = float(np.median(closes[k:k + SPLIT_LEVEL_BARS]))
            if (abs(ratios[j] - np.log(factor)) > np.log(SPLIT_MATCH_TOL) or
                    abs(np.log(new_level / old_level) - np.log(factor)) > np.log(SPLIT_LEVEL_TOL)):
                # History already adjusted. Still catch lone stray bars Yahoo left at the wrong
                # scale (TECX 2024-06-21 = 1.40 amid 16-17; RAP.AX 2025-11-03 double-adjusted).
                win = closes[lo:hi + 1]
                level = float(np.median(win))
                dev = np.log(win / level)
                strays = {}
                for jj in range(len(win)):
                    if abs(dev[jj] + np.log(factor)) < np.log(SPLIT_MATCH_TOL):      # bar = level / factor
                        strays[dates[lo + jj]] = factor
                    elif abs(dev[jj] - np.log(factor)) < np.log(SPLIT_MATCH_TOL):    # bar = level * factor
                        strays[dates[lo + jj]] = 1.0 / factor
                if strays and len(strays) <= 2:
                    out.append({"ticker": t, "split_date": sd, "split": float(s), "factor": factor,
                                "jump_date": min(strays), "cut_date": None, "old_dates": [],
                                "strays": strays, "n_before": 0})
                continue
            # 3. classify every bar in the window by the level it sits on
            wlo, whi = max(0, k - SPLIT_SEARCH_BARS), min(len(closes) - 1, k + SPLIT_SEARCH_BARS)
            win = closes[wlo:whi + 1]
            is_old = np.abs(np.log(win / old_level)) < np.abs(np.log(win / new_level))
            m = len(win)
            for jj in range(len(win) - 1, -1, -1):
                if is_old[jj]:
                    break
                m = jj
            jump_date = dates[wlo + m] if m < len(win) else dates[whi]
            old_dates = [dates[wlo + jj] for jj in range(len(win)) if is_old[jj]]
            out.append({"ticker": t, "split_date": sd, "split": float(s), "factor": factor,
                        "jump_date": jump_date, "cut_date": dates[wlo], "old_dates": old_dates,
                        "strays": {}, "n_before": wlo + len(old_dates)})
    return out


def _dedupe_splits(found: list[dict]) -> list[dict]:
    """Yahoo sometimes files the same event twice (JNS, LAT): keep one per (ticker, jump date)."""
    seen, uniq = set(), []
    for f in found:
        if (f["ticker"], f["jump_date"]) not in seen:
            seen.add((f["ticker"], f["jump_date"]))
            uniq.append(f)
    return uniq


def repair_unadjusted_splits(con: sqlite3.Connection, tickers: list[str] | None = None,
                             dry: bool = False, log=print) -> list[str]:
    """Arithmetic fallback: multiply open/high/low/close/adj_close by the factor (and divide volume)
    for every bar before cut_date plus the old-scale stragglers inside the window, oldest split
    first. Idempotent: once adjusted the two levels agree and nothing is detected. Prefer a full
    re-fetch first (update_prices does) so bars Yahoo has already adjusted are never touched."""
    uniq = _dedupe_splits(find_unadjusted_splits(con, tickers))
    fixed = []
    for f in uniq:
        if f["cut_date"] is None:
            log(f"  split repair {f['ticker']}: stray bar(s) at the wrong scale near the {f['split_date']} split: "
                + ", ".join(f"{d} x{m:g}" for d, m in f["strays"].items()) + (" [dry]" if dry else ""))
        else:
            log(f"  split repair {f['ticker']}: {f['split']:g} on {f['split_date']} (x{f['factor']:g} on "
                f"{f['n_before']} bars up to {f['jump_date']}){' [dry]' if dry else ''}")
        if dry:
            continue
        if f["cut_date"] is not None:
            ph = ",".join("?" * len(f["old_dates"])) or "''"
            con.execute(f"""UPDATE prices SET open=open*?, high=high*?, low=low*?, close=close*?, adj_close=adj_close*?,
                            volume=volume/? WHERE ticker=? AND (date<? OR date IN ({ph}))""",
                        (f["factor"],) * 6 + (f["ticker"], f["cut_date"], *f["old_dates"]))
        for d, m in f["strays"].items():
            con.execute("""UPDATE prices SET open=open*?, high=high*?, low=low*?, close=close*?, adj_close=adj_close*?,
                           volume=volume/? WHERE ticker=? AND date=?""", (m,) * 6 + (f["ticker"], d))
        fixed.append(f["ticker"])
    if fixed:
        con.commit()
    return sorted(set(fixed))


def stale_report(con: sqlite3.Connection) -> pd.DataFrame:
    return db.read_df("""SELECT f.ticker, s.name, s.region, f.last_date, f.consecutive_failures, f.status, f.error
                         FROM fetch_log f LEFT JOIN securities s ON s.ticker=f.ticker
                         WHERE f.consecutive_failures >= 3 ORDER BY f.consecutive_failures DESC""", con=con)
