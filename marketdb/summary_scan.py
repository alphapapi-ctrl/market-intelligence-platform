"""Secondary commodity exposures from Yahoo business summaries.

Precious-metal miners often carry a second commodity the Yahoo industry / name flags cannot see
(a gold producer with a lithium project, a silver-gold-copper producer, PGM by-products). This
module

  1. fetches `longBusinessSummary` for the flagged stocks once and stores it in
     securities.business_summary (re-fetched only after summary_scan.max_age_days);
  2. scans the stored summaries for commodity keywords (universe_config.json -> summary_scan)
     and reports candidates the stock is not yet flagged with;
  3. optionally writes them as *secondary* exposures (security_groups, priority 9,
     source='summary', type = the stock's primary type) — never as the primary.

    python -m marketdb.summary_scan                 # fetch missing summaries + report candidates
    python -m marketdb.summary_scan --apply         # ... and write them as secondary exposures
    python -m marketdb.summary_scan --all           # every commodity-flagged stock, not just precious metals
    python -m marketdb.summary_scan --no-fetch      # scan stored summaries only (no network)
    python -m marketdb.summary_scan --refetch       # ignore max_age_days

The candidate list is saved as reports(kind='summary_scan') for the Commodities -> Exposures tab,
where each row can be ticked and applied. Removing an exposure on that tab records a
remove_groups override which this scan respects, so a rejected candidate does not come back.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import db, results as R, universe as U

DEFAULTS = {
    "source_commodities": ["gold", "silver", "platinum", "palladium"],
    "max_age_days": 180,
    "threads": 4,
    "keywords": {
        "gold": ["gold"],
        "silver": ["silver"],
        "copper": ["copper"],
        "nickel": ["nickel"],
        "platinum": ["platinum", "pgm", "pgms", "platinum group"],
        "palladium": ["palladium"],
        "lithium": ["lithium", "spodumene"],
        "uranium": ["uranium"],
        "iron_ore": ["iron ore"],
        "oil_gas": ["oil and gas", "petroleum", "natural gas", "crude oil"],
    },
}
COLS = ["ticker", "name", "cap_band", "primary", "primary_type", "existing", "commodity", "hits", "snippet"]
_SUFFIX = re.compile(r"\b(limited|ltd\.?|corporation|corp\.?|incorporated|inc\.?|plc|nl|group|holdings?|resources|mining|metals|minerals)\b",
                     re.I)


def cfg() -> dict:
    c = {**DEFAULTS, **(U.config().get("summary_scan") or {})}
    c["keywords"] = {**DEFAULTS["keywords"], **((U.config().get("summary_scan") or {}).get("keywords") or {})}
    return c


# ── 1. Summaries ──────────────────────────────────────────────────────────────
def flagged_tickers(con: sqlite3.Connection, commodities: list[str] | None) -> pd.DataFrame:
    """Active AU/US equities carrying any of `commodities` (all commodity-flagged stocks if None)."""
    sql = """SELECT DISTINCT s.ticker, s.name FROM securities s JOIN security_groups g ON g.ticker=s.ticker
             WHERE s.active=1 AND s.quote_type='EQUITY' AND s.region IN ('AU','US') AND g.group_type='commodity'"""
    params: tuple = ()
    if commodities:
        sql += f" AND g.group_key IN ({','.join('?' * len(commodities))})"
        params = tuple(commodities)
    return db.read_df(sql + " ORDER BY s.ticker", params, con=con)


def _fetch_one(ticker: str) -> tuple[str, str | None]:
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info or {}
        return ticker, (info.get("longBusinessSummary") or "").strip()
    except Exception as e:                     # 404 "Quote not found", rate limit, network
        msg = str(e)
        if "Not Found" in msg or "404" in msg:
            return ticker, ""                  # genuinely absent: store '' so it is not retried daily
        return ticker, None                    # transient: leave for next run


def fetch_summaries(tickers: list[str], con: sqlite3.Connection, max_age_days: int = 180,
                    threads: int = 4, refetch: bool = False, log=print) -> dict:
    """Store longBusinessSummary for tickers whose stored copy is missing or older than max_age_days."""
    have = db.read_df("SELECT ticker, summary_updated FROM securities WHERE ticker IN (%s)"
                      % ",".join("?" * len(tickers)), tuple(tickers), con=con) if tickers else pd.DataFrame()
    cutoff = (pd.Timestamp(db.today_str()) - pd.Timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    fresh = set() if refetch else set(have.loc[have["summary_updated"].fillna("") >= cutoff, "ticker"])
    todo = [t for t in tickers if t not in fresh]
    stats = {"requested": len(tickers), "fetched": 0, "empty": 0, "failed": 0, "skipped_fresh": len(tickers) - len(todo)}
    if not todo:
        log(f"  summaries: all {len(tickers)} stored within {max_age_days} days")
        return stats
    log(f"  summaries: fetching {len(todo)} of {len(tickers)} ({threads} threads)")
    today = db.today_str()
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=threads) as ex:
        for t, text in ex.map(_fetch_one, todo):
            done += 1
            if text is None:
                stats["failed"] += 1
            else:
                con.execute("UPDATE securities SET business_summary=?, summary_updated=? WHERE ticker=?", (text, today, t))
                stats["fetched" if text else "empty"] += 1
            if done % 50 == 0 or done == len(todo):
                con.commit()
                log(f"    {done}/{len(todo)}  ({time.time() - t0:.0f}s)")
    con.commit()
    log(f"  summaries: {stats['fetched']} stored, {stats['empty']} empty, {stats['failed']} failed (will retry)")
    return stats


# ── 2. Scan ───────────────────────────────────────────────────────────────────
def _strip_name(text: str, name: str) -> str:
    """Remove the company name (and its stem) so 'Silver Lake Resources' does not flag silver."""
    if not name:
        return text
    out = re.sub(re.escape(name), " ", text, flags=re.I)
    stem = _SUFFIX.sub(" ", name).strip()
    stem = re.sub(r"\s+", " ", stem)
    if len(stem) >= 4:
        out = re.sub(re.escape(stem) + r"(?:'s)?", " ", out, flags=re.I)
    return out


def _hits(text: str, words: list[str]) -> tuple[int, str]:
    n, snippet = 0, ""
    for w in words:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", text, flags=re.I):
            n += 1
            if not snippet:
                a, b = max(0, m.start() - 70), min(len(text), m.end() + 70)
                snippet = ("…" if a else "") + text[a:b].replace("\n", " ") + ("…" if b < len(text) else "")
    return n, snippet


def scan(con: sqlite3.Connection, commodities: list[str] | None = None, log=print) -> pd.DataFrame:
    """Candidate secondary exposures from the stored summaries. Columns:
    ticker, name, cap_band, primary, primary_type, existing, commodity, hits, snippet."""
    c = cfg()
    keywords = {k: v for k, v in c["keywords"].items() if k in U.config()["commodity_benchmarks"] or k in U.commodity_labels()}
    targets = flagged_tickers(con, commodities)
    if targets.empty:
        return pd.DataFrame(columns=COLS)
    tl = targets["ticker"].tolist()
    ph = ",".join("?" * len(tl))
    sec = db.read_df(f"SELECT ticker, name, cap_band, business_summary FROM securities WHERE ticker IN ({ph})", tuple(tl), con=con)
    grp = db.read_df(f"""SELECT ticker, group_key, attr, priority FROM security_groups
                         WHERE group_type='commodity' AND ticker IN ({ph}) ORDER BY ticker, priority""", tuple(tl), con=con)
    rejected = {(g["ticker"], g["group_key"]) for g in (U.load_overrides() or {}).get("remove_groups", [])
                if g.get("group_type") == "commodity"}
    order = list(U.config()["commodity_benchmarks"].keys())
    rows = []
    for t, name, cap, text in zip(sec["ticker"], sec["name"].fillna(""), sec["cap_band"].fillna(""),
                                  sec["business_summary"].fillna("")):
        if not text:
            continue
        g = grp[grp["ticker"] == t]
        existing = list(g["group_key"])
        if not existing:
            continue
        prim = g.sort_values(["priority"], kind="stable")
        prim = prim.assign(_o=prim["group_key"].map(lambda k: order.index(k) if k in order else 99)).sort_values(["priority", "_o"])
        primary, ptype = prim.iloc[0]["group_key"], prim.iloc[0]["attr"] or "producer"
        clean = _strip_name(text, name)
        for key, words in keywords.items():
            if key in existing or (t, key) in rejected:
                continue
            n, snip = _hits(clean, words)
            if n:
                rows.append({"ticker": t, "name": name, "cap_band": cap, "primary": primary, "primary_type": ptype,
                             "existing": ", ".join(existing), "commodity": key, "hits": n, "snippet": snip})
    out = pd.DataFrame(rows, columns=COLS)
    out = out.sort_values(["ticker", "hits"], ascending=[True, False]).reset_index(drop=True)
    n_sum = int((sec["business_summary"].fillna("") != "").sum())
    log(f"  scan: {len(targets)} flagged stocks, {n_sum} with a summary, {len(out)} candidate secondary exposures "
        f"on {out['ticker'].nunique()} stocks")
    return out


# ── 3. Apply ──────────────────────────────────────────────────────────────────
def apply(candidates: pd.DataFrame, con: sqlite3.Connection, log=print) -> int:
    """Write candidate rows (ticker, commodity, primary_type) as secondary exposures, source='summary'.
    Existing flags for the same (ticker, commodity) are left untouched."""
    if candidates is None or len(candidates) == 0:
        return 0
    today = db.today_str()
    # Pin each stock's current primary at priority 0 first: primaries resolve by priority then config
    # order, so adding e.g. 'gold' at priority 9 to a silver miner whose silver flag is also 9 would
    # otherwise make gold the primary.
    order = list(U.config()["commodity_benchmarks"].keys())
    for t in sorted(set(candidates["ticker"])):
        g = db.read_df("SELECT group_key, priority FROM security_groups WHERE ticker=? AND group_type='commodity'",
                       (t,), con=con)
        if g.empty or int(g["priority"].min()) == 0:
            continue
        top = g[g["priority"] == g["priority"].min()]
        prim = sorted(top["group_key"], key=lambda k: order.index(k) if k in order else 99)[0]
        con.execute("UPDATE security_groups SET priority=0 WHERE ticker=? AND group_type='commodity' AND group_key=?",
                    (t, prim))
    rows = [(r["ticker"], "commodity", r["commodity"], r.get("primary_type") or "producer", "summary", today, 9)
            for _, r in candidates.iterrows()]
    before = db.scalar("SELECT COUNT(*) FROM security_groups WHERE group_type='commodity'", con=con)
    con.executemany("""INSERT INTO security_groups (ticker, group_type, group_key, attr, source, updated, priority)
                       VALUES (?,?,?,?,?,?,?) ON CONFLICT(ticker, group_type, group_key) DO NOTHING""", rows)
    con.commit()
    n = db.scalar("SELECT COUNT(*) FROM security_groups WHERE group_type='commodity'", con=con) - before
    log(f"  applied {n} new secondary exposures (source='summary')")
    return n


def save_candidates(cands: pd.DataFrame, con: sqlite3.Connection, stats: dict | None = None) -> None:
    text = (f"Summary scan {db.today_str()}: {len(cands)} candidate secondary exposures on "
            f"{cands['ticker'].nunique() if len(cands) else 0} stocks")
    R.save_report("summary_scan", db.today_str(), text=text,
                  payload={"candidates": cands.to_dict(orient="records"), "fetch": stats or {}}, con=con)


def latest_candidates(con=None) -> tuple[pd.DataFrame | None, str | None]:
    text, payload, date = R.load_report("summary_scan", con=con)
    if payload is None:
        return None, None
    return pd.DataFrame(payload.get("candidates", [])), date


def run(con: sqlite3.Connection, all_commodities: bool = False, fetch: bool = True, refetch: bool = False,
        do_apply: bool = False, threads: int | None = None, log=print) -> pd.DataFrame:
    c = cfg()
    comms = None if all_commodities else list(c["source_commodities"])
    targets = flagged_tickers(con, comms)
    log(f"summary scan over {len(targets)} stocks flagged {'any commodity' if comms is None else '/'.join(comms)}")
    stats = None
    if fetch:
        stats = fetch_summaries(targets["ticker"].tolist(), con, int(c["max_age_days"]),
                                threads or int(c["threads"]), refetch, log)
    cands = scan(con, comms, log)
    save_candidates(cands, con, stats)
    if do_apply:
        apply(cands, con, log)
    return cands


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="scan every commodity-flagged stock, not just precious metals")
    ap.add_argument("--apply", action="store_true", help="write the candidates as secondary exposures")
    ap.add_argument("--no-fetch", action="store_true", help="use stored summaries only")
    ap.add_argument("--refetch", action="store_true", help="re-download summaries even if fresh")
    ap.add_argument("--threads", type=int, default=None)
    a = ap.parse_args(argv)
    db.utf8_console()
    with db.session() as con:
        if db.is_empty(con):
            print(db.BOOTSTRAP_HINT)
            return 2
        cands = run(con, a.all, not a.no_fetch, a.refetch, a.apply, a.threads)
    if len(cands):
        show = cands[["ticker", "primary", "commodity", "hits", "snippet"]].copy()
        show["snippet"] = show["snippet"].str.slice(0, 90)
        print(show.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
