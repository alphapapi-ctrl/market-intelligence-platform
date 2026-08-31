"""Monthly universe refresh.

    python -m marketdb.refresh_universe            # full refresh
    python -m marketdb.refresh_universe --dry-run  # report what would change
    python -m marketdb.refresh_universe --indices-only

Steps
  1. Yahoo screener (yf.screen / EquityQuery), region x industry, listed exchanges only
     -> every AU and US equity with name, exchange, quoteType, marketCap, sector, industry
  2. Upsert `securities`; new symbols get first_seen; symbols Yahoo no longer lists AND whose
     prices have stopped are marked inactive (delisted_at). Names/sector/industry/market cap
     refresh every run. Overrides in stocks/universe_overrides.json are applied last.
  2b. Any active equity still without a sector is asked for directly (yf.Ticker.info);
     rows Yahoo reports as a fund are retyped so they leave the equity universes.
  3. Commodity flags from Yahoo industry + name keywords (add-only; legacy/manual flags kept).
  4. Index memberships from isolated providers (S&P 500, Nasdaq-100, ASX 20/50/200; DJIA from
     the RRG Dow list). A provider failure keeps the previous membership.
  5. `universe_history` snapshot, fetch_log failure counters reset for found tickers,
     meta.last_universe_refresh.
"""
from __future__ import annotations

import argparse
import io
import re
import sqlite3
import time
import traceback
from datetime import datetime

import pandas as pd

from . import db, universe as U

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
PAGE = 250
REGION_BENCH = {"AU": "VAS.AX", "US": "SPY"}


_ODD_US = re.compile(r"-(P[A-Z]?|W[ST]?|UN?|RT?)$")      # preferreds, warrants, units, rights


def is_odd_line(ticker: str) -> bool:
    """Symbols that are not ordinary shares: US preferreds/warrants/units, ASX codes longer than
    four characters (deferred-settlement / bonus lines such as HGODB.AX, MAUCA.AX)."""
    t = ticker.upper()
    if t.endswith(".AX"):
        return len(t[:-3]) > 4
    return bool(_ODD_US.search(t))


# ── 1. Yahoo screener ─────────────────────────────────────────────────────────
def _screen_all(query, log=print, label="") -> list[dict]:
    import yfinance as yf
    out, offset = [], 0
    while True:
        last_err = None
        for attempt in range(3):
            try:
                r = yf.screen(query, size=PAGE, offset=offset)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(5 * (attempt + 1))
        else:
            log(f"    {label}: screener failed at offset {offset}: {last_err}")
            break
        quotes = r.get("quotes") or []
        out.extend(quotes)
        total = r.get("total") or 0
        offset += PAGE
        if not quotes or offset >= total or offset >= 10000:
            break
        time.sleep(0.4)
    return out


def pull_region(region: str, log=print) -> pd.DataFrame:
    """Every listed equity for a region, tagged with Yahoo sector/industry."""
    import yfinance as yf
    from yfinance.const import EQUITY_SCREENER_EQ_MAP
    EQ = yf.EquityQuery
    cfg = U.config()["refresh"]
    exchanges = cfg["au_exchanges"] if region == "AU" else cfg["us_exchanges"]
    floor = float(cfg["au_min_market_cap"] if region == "AU" else cfg["us_min_market_cap"])
    usd_only = region == "US" and cfg.get("us_require_usd_financials", True)
    # the validator's vocabulary is authoritative (em-dash names such as "Software—Application")
    industries = [(sec, ind) for sec, inds in EQUITY_SCREENER_EQ_MAP["industry"].items() for ind in sorted(inds)]
    rows, failed = [], []
    for done, (sector, ind) in enumerate(industries, 1):
        parts = [EQ("eq", ["region", region.lower()]), EQ("is-in", ["exchange", *exchanges]),
                 EQ("eq", ["industry", ind])]
        if floor > 0:
            parts.append(EQ("gt", ["intradaymarketcap", floor]))
        try:
            query = EQ("and", parts)
        except ValueError as e:
            failed.append(ind)
            log(f"    {region}/{ind}: query rejected ({e})")
            continue
        for q in _screen_all(query, log, f"{region}/{ind}"):
            rows.append({"ticker": q.get("symbol"), "name": q.get("longName") or q.get("shortName"),
                         "exchange": q.get("exchange"), "quote_type": q.get("quoteType"),
                         "market_cap": q.get("marketCap"), "currency": q.get("currency"),
                         "financial_currency": q.get("financialCurrency"),
                         "sector": sector, "industry": ind.replace("—", " - "),
                         "first_trade": q.get("firstTradeDateMilliseconds")})
        if done % 30 == 0:
            log(f"    {region}: {done}/{len(industries)} industries, {len(rows)} rows")
    if failed:
        log(f"  {region}: {len(failed)} industries could not be queried: {failed[:6]}")
    df = pd.DataFrame(rows).dropna(subset=["ticker"])
    df = df[df["quote_type"].fillna("EQUITY") == "EQUITY"]
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df = df.drop_duplicates("ticker")
    df = df[df["ticker"].map(lambda t: U.region_of(t) == region)]
    odd = df["ticker"].map(is_odd_line)
    if odd.any():
        log(f"  {region}: dropping {int(odd.sum())} preferred/warrant/deferred-settlement lines")
        df = df[~odd]
    if usd_only:
        foreign = df["financial_currency"].notna() & (df["financial_currency"] != "USD")
        log(f"  {region}: dropping {int(foreign.sum())} foreign issuers (financials not in USD, i.e. ADRs/cross-listings)")
        df = df[~foreign]
    log(f"  {region}: {len(df)} listed equities from Yahoo screener")
    return df.reset_index(drop=True)


# ── 2. Upsert securities ──────────────────────────────────────────────────────
def apply_securities(found: pd.DataFrame, region: str, con: sqlite3.Connection, dry: bool, log=print) -> dict:
    today = db.today_str()
    cfg = U.config()["refresh"]
    existing = db.read_df("SELECT ticker, active, quote_type, source, market_cap FROM securities WHERE region=?",
                          (region,), con=con)
    ex_set = set(existing["ticker"])
    new = found[~found["ticker"].isin(ex_set)].copy()
    upd = found[found["ticker"].isin(ex_set)].copy()
    floor = float(cfg["au_min_market_cap"] if region == "AU" else cfg["us_min_market_cap"])

    # not found: equity rows that Yahoo no longer lists
    eq_existing = existing[(existing["quote_type"] == "EQUITY") & (existing["active"] == 1)]
    missing = eq_existing[~eq_existing["ticker"].isin(set(found["ticker"]))]
    fl = db.read_df("SELECT ticker, status, last_date FROM fetch_log", con=con).set_index("ticker")
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    delist, keep = [], []
    for t, mc in zip(missing["ticker"], missing["market_cap"]):
        st = fl["status"].get(t); ld = fl["last_date"].get(t)
        prices_alive = (st == "ok") and ld is not None and str(ld) >= cutoff
        below_floor = (mc or 0) < floor and floor > 0
        if prices_alive and (below_floor or cfg.get("keep_existing_below_floor", True)):
            keep.append(t)       # Yahoo still serves prices -> probably just under the cap floor
        elif prices_alive:
            keep.append(t)
        else:
            delist.append(t)
    log(f"  {region}: {len(new)} new, {len(upd)} updated, {len(delist)} to deactivate, "
        f"{len(keep)} missing-from-screener but still priced (kept)")
    if dry:
        return {"new": new["ticker"].tolist(), "delisted": delist}

    scheme = region
    for r in new.itertuples(index=False):
        con.execute("""INSERT INTO securities (ticker, name, region, exchange, quote_type, sector, industry, market_cap,
                       cap_band, currency, benchmark, active, first_seen, last_seen, mcap_updated, source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,'yahoo_screener')""",
                    (r.ticker, r.name, region, r.exchange, "EQUITY", r.sector, r.industry, r.market_cap,
                     U.cap_band_for(r.market_cap, scheme), r.currency, REGION_BENCH[region], today, today, today))
    for r in upd.itertuples(index=False):
        con.execute("""UPDATE securities SET name=COALESCE(?, name), exchange=COALESCE(?, exchange),
                       sector=?, industry=?, market_cap=COALESCE(?, market_cap), cap_band=?,
                       currency=COALESCE(?, currency), active=1, delisted_at=NULL, last_seen=?, mcap_updated=?,
                       benchmark=COALESCE(benchmark, ?)
                       WHERE ticker=?""",
                    (r.name, r.exchange, r.sector, r.industry, r.market_cap, U.cap_band_for(r.market_cap, scheme),
                     r.currency, today, today, REGION_BENCH[region], r.ticker))
    for t in delist:
        con.execute("UPDATE securities SET active=0, delisted_at=? WHERE ticker=?", (today, t))
    # found tickers get their failure counters reset so stale ones are retried
    con.executemany("UPDATE fetch_log SET consecutive_failures=0 WHERE ticker=? AND consecutive_failures>0",
                    [(t,) for t in found["ticker"]])
    con.commit()
    return {"new": new["ticker"].tolist(), "delisted": delist}


# ── 2b. Sector backfill ───────────────────────────────────────────────────────
SECTOR_SLEEP = 0.15          # polite pause between per-ticker info calls
SECTOR_COMMIT_EVERY = 25


def backfill_sectors(con: sqlite3.Connection, region: str | None = None, limit: int | None = None,
                     dry: bool = False, log=print) -> dict:
    """Fill sector/industry from Yahoo for active equities the screener sweep missed.

    pull_region() only tags what the industry-by-industry screener returns, so a rejected
    industry query or a paging failure leaves real equities (ADI, HD, MU ...) with a NULL
    sector. Those then depend on LEGACY_TO_YAHOO_SECTOR, or land in an "Unknown" breadth
    bucket when no legacy label exists. This asks Yahoo directly for exactly those rows.

    Yahoo's quoteType is trusted here too: anything that comes back as a fund is retyped so
    it stops satisfying the EQUITY filter on the research universes.
    """
    import yfinance as yf

    q = ["SELECT ticker FROM securities WHERE active=1 AND quote_type='EQUITY'",
         "AND (sector IS NULL OR sector = '')"]
    params: list = []
    if region:
        q.append("AND region=?")
        params.append(region)
    q.append("ORDER BY market_cap IS NULL, market_cap DESC")
    if limit:
        q.append(f"LIMIT {int(limit)}")
    tickers = db.read_df(" ".join(q), tuple(params), con=con)["ticker"].tolist()
    label = region or "all"
    if not tickers:
        log(f"  sectors {label}: nothing missing")
        return {"checked": 0, "filled": 0, "retyped": 0, "no_data": 0, "failed": 0}

    log(f"  sectors {label}: {len(tickers)} active equities with no sector — asking Yahoo per ticker")
    out = {"checked": len(tickers), "filled": 0, "retyped": 0, "no_data": 0, "failed": 0}
    for i, t in enumerate(tickers, 1):
        try:
            info = yf.Ticker(t).get_info() or {}
        except Exception as e:  # noqa: BLE001
            out["failed"] += 1
            log(f"    {t}: info failed ({type(e).__name__}: {str(e)[:60]})")
            time.sleep(SECTOR_SLEEP)
            continue

        qt = (info.get("quoteType") or "").upper()
        sector = info.get("sector")
        industry = info.get("industry")

        if qt and qt != "EQUITY":
            out["retyped"] += 1
            if not dry:
                con.execute("UPDATE securities SET quote_type=? WHERE ticker=?", (qt, t))
            log(f"    {t}: Yahoo says {qt}, not EQUITY — retyped")
        elif sector:
            out["filled"] += 1
            if not dry:
                con.execute("UPDATE securities SET sector=?, industry=COALESCE(?, industry) WHERE ticker=?",
                            (sector, (industry or "").replace("\u2014", " - ") or None, t))
        else:
            out["no_data"] += 1

        if not dry and i % SECTOR_COMMIT_EVERY == 0:
            con.commit()
            log(f"    {label}: {i}/{len(tickers)} checked, {out['filled']} filled")
        time.sleep(SECTOR_SLEEP)

    if not dry:
        con.commit()
    log(f"  sectors {label}: {out['filled']} filled, {out['retyped']} retyped, "
        f"{out['no_data']} Yahoo has no sector for, {out['failed']} failed")
    return out


def apply_overrides(con: sqlite3.Connection, log=print) -> None:
    ov = U.load_overrides()
    today = db.today_str()
    for t in ov.get("exclude", []):
        con.execute("UPDATE securities SET active=0, delisted_at=COALESCE(delisted_at, ?) WHERE ticker=?", (today, t))
    for row in ov.get("include", []):
        t = row["ticker"]
        reg = row.get("region") or U.region_of(t)
        if reg is None:
            log(f"  override include {t}: not an AU/US symbol — skipped")
            continue
        con.execute("""INSERT INTO securities (ticker, name, region, quote_type, sector, industry, active, first_seen, source, benchmark)
                       VALUES (?,?,?,?,?,?,1,?, 'manual', ?)
                       ON CONFLICT(ticker) DO UPDATE SET active=1, delisted_at=NULL,
                         name=COALESCE(excluded.name, securities.name)""",
                    (t, row.get("name", t), reg, row.get("quote_type", "EQUITY"), row.get("sector"), row.get("industry"),
                     today, REGION_BENCH.get(reg)))
    for g in ov.get("groups", []):
        con.execute("""INSERT OR REPLACE INTO security_groups (ticker, group_type, group_key, attr, source, updated, priority)
                       VALUES (?,?,?,?,'manual',?,?)""", (g["ticker"], g["group_type"], g["group_key"], g.get("attr"),
                                                         today, int(g.get("priority", 9))))
    for g in ov.get("remove_groups", []):
        con.execute("DELETE FROM security_groups WHERE ticker=? AND group_type=? AND group_key=?",
                    (g["ticker"], g["group_type"], g["group_key"]))
    con.commit()
    if ov:
        log(f"  overrides applied: exclude {len(ov.get('exclude', []))}, include {len(ov.get('include', []))}, "
            f"groups {len(ov.get('groups', []))}, removals {len(ov.get('remove_groups', []))}")


# ── 3. Commodity flags ────────────────────────────────────────────────────────
def apply_commodity_flags(con: sqlite3.Connection, log=print) -> int:
    cfg = U.config()
    ind_map = cfg["industry_to_commodity"]
    kw_map = cfg["name_keyword_to_commodity"]
    sec = db.read_df("SELECT ticker, name, industry FROM securities WHERE active=1 AND quote_type='EQUITY' "
                     "AND region IN ('AU','US')", con=con)
    today = db.today_str()
    rows = []
    for t, name, ind in zip(sec["ticker"], sec["name"].fillna(""), sec["industry"].fillna("")):
        keys = {}                                   # commodity -> type
        if ind in ind_map:
            ck, ctype = ind_map[ind]
            keys[ck] = ctype
        low = name.lower()
        for kw, key in kw_map.items():
            # keyword flags only for mining-type industries, otherwise 'Gold' matches e.g. Goldman Sachs
            if kw in low and ("Mining" in ind or "Metals" in ind or ind in ("Gold", "Silver", "Copper", "Uranium")):
                keys.setdefault(key, "producer")
        for k, ctype in keys.items():
            rows.append((t, "commodity", k, ctype, "yahoo", today))
    if rows:
        con.executemany("""INSERT INTO security_groups (ticker, group_type, group_key, attr, source, updated)
                           VALUES (?,?,?,?,?,?) ON CONFLICT(ticker, group_type, group_key) DO NOTHING""", rows)
        con.commit()
    n = db.scalar("SELECT COUNT(*) FROM security_groups WHERE group_type='commodity'", con=con)
    log(f"  commodity flags: {len(rows)} candidates from Yahoo industry/name, {n} total flags")
    return len(rows)


# ── 4. Index memberships ──────────────────────────────────────────────────────
def _wiki_table(url: str, match: str) -> pd.DataFrame:
    import requests
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    tabs = pd.read_html(io.StringIO(r.text), match=match, flavor="lxml")
    return max(tabs, key=len)


def idx_sp500() -> list[str]:
    t = _wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol")
    return [str(x).strip().replace(".", "-") for x in t["Symbol"] if str(x).strip()]


def idx_ndx100() -> list[str]:
    import requests
    r = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100",
                     headers={**UA, "Accept": "application/json, text/plain, */*"}, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["data"]["rows"]
    syms = [str(x["symbol"]).strip().replace("/", "-") for x in rows]
    if len(syms) < 90:
        raise ValueError(f"only {len(syms)} NDX symbols")
    return syms


def idx_asx(url: str, col: str, n_min: int) -> list[str]:
    t = _wiki_table(url, col)
    if isinstance(t.columns, pd.MultiIndex):
        t.columns = [c[0] if isinstance(c, tuple) else c for c in t.columns]
    c = next(c for c in t.columns if str(c).startswith(col))
    syms = [str(x).strip().upper() + ".AX" for x in t[c] if str(x).strip() and str(x) != "nan"]
    if len(syms) < n_min:
        raise ValueError(f"only {len(syms)} rows from {url}")
    return syms


def idx_djia(con) -> list[str]:
    return db.read_df("SELECT ticker FROM security_groups WHERE group_type='theme' AND group_key='rrg_dow'",
                      con=con)["ticker"].tolist()


INDEX_PROVIDERS = {
    "SP500":  lambda con: idx_sp500(),
    "NDX100": lambda con: idx_ndx100(),
    "ASX200": lambda con: idx_asx("https://en.wikipedia.org/wiki/S%26P/ASX_200", "Code", 150),
    "ASX50":  lambda con: idx_asx("https://en.wikipedia.org/wiki/S%26P/ASX_50", "Symbol", 40),
    "ASX20":  lambda con: idx_asx("https://en.wikipedia.org/wiki/S%26P/ASX_20", "Symbol", 15),
    "DJIA":   idx_djia,
}


def apply_indices(con: sqlite3.Connection, dry: bool, log=print) -> dict:
    today = db.today_str()
    known = set(db.read_df("SELECT ticker FROM securities", con=con)["ticker"])
    report = {}
    for key, fn in INDEX_PROVIDERS.items():
        try:
            syms = fn(con)
        except Exception as e:  # noqa: BLE001
            log(f"  index {key}: provider failed ({type(e).__name__}: {str(e)[:80]}) — previous membership kept")
            report[key] = None
            continue
        in_db = [s for s in syms if s in known]
        report[key] = (len(syms), len(in_db))
        log(f"  index {key}: {len(syms)} constituents, {len(in_db)} in securities")
        if dry:
            continue
        con.execute("DELETE FROM security_groups WHERE group_type='index' AND group_key=?", (key,))
        con.executemany("""INSERT OR REPLACE INTO security_groups (ticker, group_type, group_key, attr, source, updated)
                           VALUES (?,?,?,?,?,?)""",
                        [(s, "index", key, None, "refresh", today) for s in in_db])
        con.commit()
    if not dry and report.get("SP500") and report.get("NDX100"):
        con.execute("DELETE FROM security_groups WHERE group_type='index' AND group_key='SP500_LEGACY'")
        con.commit()
    return report


# ── 5. Snapshot + meta ────────────────────────────────────────────────────────
def snapshot(con: sqlite3.Connection, log=print) -> None:
    today = db.today_str()
    rows = []
    for k in U.universe_keys():
        m = U.members(k, con)
        rows.extend((today, k, t) for t in m["ticker"])
        log(f"  universe {k}: {len(m)} members")
    con.execute("DELETE FROM universe_history WHERE refresh_date=?", (today,))
    con.executemany("INSERT OR REPLACE INTO universe_history VALUES (?,?,?)", rows)
    db.set_meta("last_universe_refresh", today, con)
    con.commit()


def refresh(con: sqlite3.Connection, *, dry: bool = False, indices_only: bool = False,
            sectors_only: bool = False, skip_sectors: bool = False, log=print) -> dict:
    t0 = time.time()
    run_id = db.start_run("refresh", None, con)
    summary = {}
    try:
        if sectors_only:
            for region in ("AU", "US"):
                summary[f"sectors_{region}"] = backfill_sectors(con, region, dry=dry, log=log)
            db.finish_run(run_id, "ok", con, notes=f"sectors-only {time.time() - t0:.0f}s")
            log(f"sector backfill done in {time.time() - t0:.0f}s")
            return summary
        if not indices_only:
            for region in ("AU", "US"):
                log(f"── {region}: pulling Yahoo screener")
                found = pull_region(region, log)
                if len(found) < 200:
                    log(f"  {region}: only {len(found)} rows — looks like a Yahoo outage; skipping securities update")
                    continue
                summary[region] = apply_securities(found, region, con, dry, log)
            if not dry:
                if not skip_sectors:
                    for region in ("AU", "US"):
                        summary[f"sectors_{region}"] = backfill_sectors(con, region, log=log)
                apply_overrides(con, log)
                apply_commodity_flags(con, log)
        log("── index memberships")
        summary["indices"] = apply_indices(con, dry, log)
        if not dry:
            snapshot(con, log)
        db.finish_run(run_id, "ok", con, notes=f"{time.time() - t0:.0f}s")
    except Exception as e:
        db.finish_run(run_id, "error", con, notes=f"{type(e).__name__}: {e}")
        traceback.print_exc()
        raise
    log(f"universe refresh done in {time.time() - t0:.0f}s")
    return summary


def main(argv=None):
    db.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--indices-only", action="store_true")
    ap.add_argument("--sectors-only", action="store_true",
                    help="only fill sector/industry for active equities Yahoo's screener missed")
    ap.add_argument("--skip-sectors", action="store_true",
                    help="skip the per-ticker sector backfill during a full refresh")
    a = ap.parse_args(argv)
    with db.session() as con:
        s = refresh(con, dry=a.dry_run, indices_only=a.indices_only,
                    sectors_only=a.sectors_only, skip_sectors=a.skip_sectors)
        for reg in ("AU", "US"):
            if reg in s:
                print(f"{reg}: new {len(s[reg]['new'])} {s[reg]['new'][:15]}{'...' if len(s[reg]['new']) > 15 else ''}")
                print(f"{reg}: delisted {len(s[reg]['delisted'])} {s[reg]['delisted'][:15]}")


if __name__ == "__main__":
    main()
