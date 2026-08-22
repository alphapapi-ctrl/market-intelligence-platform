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
    chunks: int = 0
    seconds: float = 0.0

    @property
    def coverage(self) -> float:
        return (self.ok / self.expected) if self.expected else 0.0

    def line(self) -> str:
        return (f"fetch: {self.ok}/{self.expected} tickers ({self.coverage:.0%}), "
                f"{self.fetched_rows} rows, {self.chunks} chunks, {self.seconds:.0f}s, "
                f"empty={len(self.empty)}, errors={len(self.errors)}, "
                f"full-refetch={len(self.refetched_full)}, skipped-stale={len(self.skipped_stale)}")


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

    n_calls = sum((len(v) + chunk_size - 1) // chunk_size for v in buckets.values())
    log(f"  fetching {sum(len(v) for v in buckets.values())} tickers in {n_calls} chunks "
        f"({len(buckets)} start buckets; {summ.ok} already current; {len(summ.skipped_stale)} stale skipped)")

    drift_queue: list[str] = []

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

    # securities.last_seen for everything that has data today
    con.execute("""UPDATE securities SET last_seen = (SELECT last_date FROM fetch_log f WHERE f.ticker = securities.ticker)
                   WHERE ticker IN (SELECT ticker FROM fetch_log WHERE status='ok')""")
    summ.seconds = time.time() - t0
    db.finish_run(run_id, "ok" if summ.coverage >= cfg["min_coverage"] else "partial", con,
                  n_fetched=summ.ok, notes=summ.line())
    con.commit()
    log("  " + summ.line())
    return summ


def stale_report(con: sqlite3.Connection) -> pd.DataFrame:
    return db.read_df("""SELECT f.ticker, s.name, s.region, f.last_date, f.consecutive_failures, f.status, f.error
                         FROM fetch_log f LEFT JOIN securities s ON s.ticker=f.ticker
                         WHERE f.consecutive_failures >= 3 ORDER BY f.consecutive_failures DESC""", con=con)
