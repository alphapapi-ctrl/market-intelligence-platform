"""Universe resolution: turn a universe key from universe_config.json into the
member DataFrame the studies consume (ticker, name, sector, industry, commodity,
type, cap_band, market_cap, benchmark, region, exchange).
"""
from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import db

CONFIG_PATH    = Path(__file__).resolve().parent / "universe_config.json"
OVERRIDES_PATH = db.BASE_DIR / "stocks" / "universe_overrides.json"


@lru_cache(maxsize=1)
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def universe_keys() -> list[str]:
    return list(config()["universes"].keys())


def universe_cfg(key: str) -> dict:
    try:
        return config()["universes"][key]
    except KeyError:
        raise KeyError(f"unknown universe '{key}'; known: {universe_keys()}") from None


# ── Region / exchange helpers ─────────────────────────────────────────────────
_AU_SUFFIX = re.compile(r"\.AX$")
_US_INDEX  = {"^GSPC", "^NDX", "^DJI", "^IXIC", "^RUT", "^VIX", "^VVIX", "^VIX3M", "^TNX", "^IRX",
              "^FVX", "^TYX", "^MOVE", "^HGX", "^SPGSIK"}
_AU_INDEX  = {"^AXJO", "^AORD", "^AXVI", "^AXKO", "^AXMD", "^AXSO"}


def region_of(ticker: str) -> str | None:
    """AU / US for listed securities, GLOBAL for reference indices, futures and FX
    (they never enter an equity universe but the price store keeps them for macro),
    None for any other exchange listing — those are not allowed in the DB."""
    t = ticker.strip().upper()
    if _AU_SUFFIX.search(t) or t in _AU_INDEX or t.startswith("^AX"):
        return "AU"
    if t in _US_INDEX:
        return "US"
    if t.startswith("^") or "=" in t:  # ^N225, GC=F, AUDUSD=X, DX-Y.NYB handled below
        return "GLOBAL"
    if t == "DX-Y.NYB":
        return "GLOBAL"
    if "." in t:                       # any other exchange suffix: .TO .V .L .HK ...
        return None
    return "US"


def cap_band_for(market_cap, scheme: str) -> str:
    bands = config()["cap_bands"].get(scheme) or config()["cap_bands"]["US"]
    if market_cap is None or pd.isna(market_cap):
        return "small"
    if market_cap > bands["large"]:
        return "large"
    if market_cap >= bands["mid"]:
        return "mid"
    return "small"


def tv_symbol(ticker: str, exchange: str | None) -> str:
    """TradingView import symbol from the Yahoo ticker + Yahoo exchange code."""
    t = ticker.upper()
    if t.endswith(".AX"):
        return "ASX:" + t[:-3]
    ex = (exchange or "").upper()
    prefix = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NYQ": "NYSE", "ASE": "AMEX",
              "PCX": "AMEX", "BTS": "AMEX", "ASX": "ASX"}.get(ex)
    if prefix is None:
        prefix = "NYSE"
    return f"{prefix}:{t.replace('-', '.')}"


# ── Legacy sector vocabularies -> Yahoo's 11 sectors ──────────────────────────
# Used for tickers the Yahoo screener did not tag (delisted names, thin ASX lines). Keeps every
# breadth series on one vocabulary so no ticker ever lands in an "Unknown" bucket.
LEGACY_TO_YAHOO_SECTOR = {
    # AU (FactSet-style, from the old asx_all watchlist)
    "Non-energy minerals": "Basic Materials", "Process industries": "Basic Materials",
    "Energy minerals": "Energy", "Finance": "Financial Services", "Miscellaneous": "Financial Services",
    "Technology services": "Technology", "Electronic technology": "Technology",
    "Health technology": "Healthcare", "Health services": "Healthcare",
    "Commercial services": "Industrials", "Industrial services": "Industrials",
    "Producer manufacturing": "Industrials", "Transportation": "Industrials",
    "Distribution services": "Industrials",
    "Consumer services": "Consumer Cyclical", "Consumer durables": "Consumer Cyclical",
    "Retail trade": "Consumer Cyclical", "Consumer non-durables": "Consumer Defensive",
    "Communications": "Communication Services", "Utilities": "Utilities",
    # US (GICS-style, from the old us_all / nasdaq100 watchlists)
    "Financials": "Financial Services", "Health Care": "Healthcare",
    "Information Technology": "Technology", "Technology": "Technology",
    "Consumer Discretionary": "Consumer Cyclical", "Consumer Staples": "Consumer Defensive",
    "Materials": "Basic Materials", "Basic Materials": "Basic Materials",
    "Communication": "Communication Services", "Communication Services": "Communication Services",
    "Telecommunications": "Communication Services", "Energy": "Energy", "Industrials": "Industrials",
    "Real Estate": "Real Estate",
}


def yahoo_sector(sector, legacy_sector) -> str:
    if sector and sector == sector:            # not None / NaN
        return sector
    if legacy_sector and legacy_sector == legacy_sector:
        return LEGACY_TO_YAHOO_SECTOR.get(str(legacy_sector).strip(), "Unknown")
    return "Unknown"


# ── Overrides (user-maintained) ───────────────────────────────────────────────
def load_overrides() -> dict:
    """stocks/universe_overrides.json — manual flags the monthly refresh must respect.

    {
      "exclude": ["XYZ.AX"],
      "include": [{"ticker": "ABC", "region": "US", "name": "...", "quote_type": "EQUITY"}],
      "groups":  [{"ticker": "PLS.AX", "group_type": "commodity", "group_key": "lithium", "attr": "producer"}],
      "remove_groups": [{"ticker": "...", "group_type": "commodity", "group_key": "gold"}]
    }
    """
    if OVERRIDES_PATH.exists():
        try:
            return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"WARNING: {OVERRIDES_PATH} is not valid JSON ({e}); ignoring overrides")
    return {}


# ── Membership ────────────────────────────────────────────────────────────────
_BASE_SQL = """
SELECT s.ticker, s.name, s.region, s.exchange, s.quote_type, s.sector, s.industry,
       s.legacy_sector, s.legacy_industry, s.market_cap, s.cap_band, s.benchmark, s.active
FROM securities s
"""


def _group_map(con: sqlite3.Connection, group_type: str) -> pd.DataFrame:
    return db.read_df("SELECT ticker, group_key, attr, priority FROM security_groups WHERE group_type = ?",
                      (group_type,), con=con)


def members(key: str, con: sqlite3.Connection | None = None,
            include_inactive: bool = False) -> pd.DataFrame:
    """Resolve a universe to its member frame (benchmark rows excluded)."""
    if con is None:
        with db.session() as c:
            return members(key, c, include_inactive)

    cfg = universe_cfg(key)
    flt = cfg.get("filter", {})
    df  = db.read_df(_BASE_SQL, con=con)
    if not include_inactive:
        df = df[df["active"] == 1]

    def _as_list(v):
        return v if isinstance(v, list) else [v]

    if "region" in flt:
        df = df[df["region"].isin(_as_list(flt["region"]))]
    if "quote_type" in flt:
        df = df[df["quote_type"].isin(_as_list(flt["quote_type"]))]
    if "exchange" in flt:
        df = df[df["exchange"].isin(_as_list(flt["exchange"]))]
    if "index_any" in flt:
        idx = _group_map(con, "index")
        keep = set(idx[idx["group_key"].isin(flt["index_any"])]["ticker"])
        df = df[df["ticker"].isin(keep)]
    if "theme_any" in flt:
        th = _group_map(con, "theme")
        keep = set(th[th["group_key"].isin(flt["theme_any"])]["ticker"])
        df = df[df["ticker"].isin(keep)]
    if "min_market_cap" in flt:
        df = df[df["market_cap"].fillna(0) >= float(flt["min_market_cap"])]

    comm = _group_map(con, "commodity")
    if "commodity_any" in flt:
        comm = comm[comm["group_key"].isin(flt["commodity_any"])]
        df = df[df["ticker"].isin(set(comm["ticker"]))]

    # one PRIMARY commodity / type per ticker for the study frame: lowest priority (0 = set as
    # primary in Settings), then config order. All exposures stay available via exposures().
    order = {k: i for i, k in enumerate(config()["commodity_benchmarks"].keys())}
    if len(comm):
        comm = comm.assign(_o=comm["group_key"].map(order).fillna(99)).sort_values(["ticker", "priority", "_o"])
        first = comm.drop_duplicates("ticker")
        df = df.merge(first[["ticker", "group_key", "attr"]].rename(
            columns={"group_key": "commodity", "attr": "type"}), on="ticker", how="left")
    else:
        df = df.assign(commodity=None, type=None)

    # cap band under this universe's scheme
    scheme = cfg.get("cap_scheme", "US")
    df["cap_band"] = [cap_band_for(mc, scheme) for mc in df["market_cap"]]

    # benchmark per ticker (per-commodity ETF, else the commodity group's default ETF)
    bench = cfg.get("benchmark")
    if bench == "per_commodity":
        bmap = dict(config()["commodity_benchmarks"])
        for g in commodity_groups().values():
            for ck in g.get("commodities", []):
                bmap.setdefault(ck, g.get("benchmark"))
        df["benchmark"] = df["commodity"].map(bmap)
    else:
        df["benchmark"] = bench

    # one sector vocabulary (Yahoo); legacy labels are mapped, never used raw.
    # industry is Yahoo-only (legacy industries were a different, incompatible list).
    df["sector"]   = [yahoo_sector(a, b) for a, b in zip(df["sector"], df["legacy_sector"])]
    df["industry"] = df["industry"].fillna("")
    df = df.drop(columns=["active"]).reset_index(drop=True)
    return df


def benchmark_tickers(key: str) -> list[str]:
    cfg = universe_cfg(key)
    b = cfg.get("benchmark")
    if b == "per_commodity":
        etfs = set(config()["commodity_benchmarks"].values())
        etfs.update(g.get("benchmark") for g in commodity_groups().values() if g.get("benchmark"))
        return sorted(t for t in etfs if t)
    return [b] if b else []


def role_tickers(con: sqlite3.Connection, role: str) -> list[str]:
    return db.read_df("SELECT ticker FROM security_groups WHERE group_type='role' AND group_key=?",
                      (role,), con=con)["ticker"].tolist()


def theme_members(con: sqlite3.Connection, theme: str) -> pd.DataFrame:
    """Tickers in a theme group with their display name (attr) — used by RRG."""
    return db.read_df("""SELECT g.ticker, COALESCE(g.attr, s.name) AS name
                         FROM security_groups g LEFT JOIN securities s ON s.ticker = g.ticker
                         WHERE g.group_type='theme' AND g.group_key=? ORDER BY g.ticker""",
                      (theme,), con=con)


def fetch_ticker_set(con: sqlite3.Connection) -> list[str]:
    """Every symbol the daily fetch must keep current: all active securities in any
    universe, every benchmark, and anything carrying a 'role' group."""
    tickers: set[str] = set()
    for k in universe_keys():
        tickers.update(members(k, con)["ticker"])
        tickers.update(benchmark_tickers(k))
    roles = db.read_df("SELECT DISTINCT ticker FROM security_groups WHERE group_type='role'", con=con)
    tickers.update(roles["ticker"])
    themes = db.read_df("SELECT DISTINCT ticker FROM security_groups WHERE group_type='theme'", con=con)
    tickers.update(themes["ticker"])
    for r in config().get("rrg", {}).values():
        tickers.add(r["benchmark"])
    return sorted(t for t in tickers if t)


def summary(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """One row per universe: member count + benchmark — for the dashboard."""
    if con is None:
        with db.session() as c:
            return summary(c)
    rows = []
    for k in universe_keys():
        m = members(k, con)
        rows.append({"universe": k, "name": universe_cfg(k)["name"], "members": len(m),
                     "large": int((m["cap_band"] == "large").sum()),
                     "mid": int((m["cap_band"] == "mid").sum()),
                     "small": int((m["cap_band"] == "small").sum()),
                     "benchmark": universe_cfg(k).get("benchmark")})
    return pd.DataFrame(rows)


# ── Commodity exposures (many-to-many flags, edited from Settings) ───────────
def commodity_labels() -> dict:
    return config().get("commodity_labels", {k: k.title() for k in config()["commodity_benchmarks"]})


def commodity_groups() -> dict:
    """{'metals': {'name': 'Metals', 'commodities': [...]}, 'energy': {...}}"""
    return config().get("commodity_groups", {})


def exposures(ticker: str, con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """All commodity flags for one ticker: group_key, attr (type), priority, source."""
    if con is None:
        with db.session() as c:
            return exposures(ticker, c)
    order = {k: i for i, k in enumerate(config()["commodity_benchmarks"].keys())}
    df = db.read_df("""SELECT group_key AS commodity, attr AS type, priority, source, updated
                       FROM security_groups WHERE ticker=? AND group_type='commodity'""", (ticker,), con=con)
    if df.empty:
        return df
    df["_o"] = df["commodity"].map(order).fillna(99)
    return df.sort_values(["priority", "_o"]).drop(columns="_o").reset_index(drop=True)


def _save_override(kind: str, entry: dict, remove_from: str | None = None) -> None:
    """Append an entry to stocks/universe_overrides.json (and drop its opposite)."""
    ov = load_overrides() or {}
    ov.setdefault("exclude", []); ov.setdefault("include", []); ov.setdefault("groups", []); ov.setdefault("remove_groups", [])
    key = (entry["ticker"], entry["group_type"], entry["group_key"])
    for lst in (kind, remove_from):
        if lst:
            ov[lst] = [g for g in ov[lst] if (g.get("ticker"), g.get("group_type"), g.get("group_key")) != key]
    ov[kind].append(entry)
    OVERRIDES_PATH.write_text(json.dumps(ov, indent=2), encoding="utf-8")


def set_exposure(ticker: str, commodity: str, ctype: str = "producer", primary: bool = False,
                 con: sqlite3.Connection | None = None) -> None:
    """Add/update one commodity exposure. Persists to the DB and to universe_overrides.json."""
    if con is None:
        with db.session() as c:
            return set_exposure(ticker, commodity, ctype, primary, c)
    today = db.today_str()
    if primary:
        con.execute("UPDATE security_groups SET priority=9 WHERE ticker=? AND group_type='commodity'", (ticker,))
    con.execute("""INSERT INTO security_groups (ticker, group_type, group_key, attr, source, updated, priority)
                   VALUES (?,?,?,?,'manual',?,?)
                   ON CONFLICT(ticker, group_type, group_key) DO UPDATE SET
                     attr=excluded.attr, source='manual', updated=excluded.updated,
                     priority=CASE WHEN ? THEN 0 ELSE security_groups.priority END""",
                (ticker, "commodity", commodity, ctype, today, 0 if primary else 9, 1 if primary else 0))
    con.commit()
    _save_override("groups", {"ticker": ticker, "group_type": "commodity", "group_key": commodity,
                              "attr": ctype, "priority": 0 if primary else 9}, remove_from="remove_groups")


def remove_exposure(ticker: str, commodity: str, con: sqlite3.Connection | None = None) -> None:
    if con is None:
        with db.session() as c:
            return remove_exposure(ticker, commodity, c)
    con.execute("DELETE FROM security_groups WHERE ticker=? AND group_type='commodity' AND group_key=?",
                (ticker, commodity))
    con.commit()
    _save_override("remove_groups", {"ticker": ticker, "group_type": "commodity", "group_key": commodity},
                   remove_from="groups")


def search_securities(text: str, con: sqlite3.Connection | None = None, limit: int = 25) -> pd.DataFrame:
    if con is None:
        with db.session() as c:
            return search_securities(text, c, limit)
    q = f"%{text.strip()}%"
    return db.read_df("""SELECT ticker, name, region, sector, industry, cap_band, active FROM securities
                         WHERE (ticker LIKE ? OR name LIKE ?) AND quote_type='EQUITY'
                         ORDER BY active DESC, market_cap DESC LIMIT ?""", (q, q, limit), con=con)


def add_commodity(key: str, label: str, group: str, benchmark: str | None = None,
                  industries: list[str] | None = None, keywords: list[str] | None = None) -> dict:
    """Register a new commodity in universe_config.json (labels, group, optional ETF benchmark,
    optional Yahoo industries / name keywords that auto-flag it on the monthly refresh) and make
    sure every commodity universe filter includes it. Returns the updated config."""
    key = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
    if not key:
        raise ValueError("commodity key is empty")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg.setdefault("commodity_labels", {})[key] = label.strip() or key.replace("_", " ").title()
    if benchmark:
        cfg.setdefault("commodity_benchmarks", {})[key] = benchmark.strip().upper()
    groups = cfg.setdefault("commodity_groups", {})
    for g in groups.values():                       # a commodity belongs to exactly one group
        g["commodities"] = [c for c in g.get("commodities", []) if c != key]
    groups.setdefault(group, {"name": group.title(), "commodities": []})["commodities"].append(key)
    for ind in industries or []:
        cfg.setdefault("industry_to_commodity", {})[ind] = [key, "producer"]
    for kw in keywords or []:
        cfg.setdefault("name_keyword_to_commodity", {})[kw.strip().lower()] = key
    for u in cfg["universes"].values():
        flt = u.get("filter", {})
        if "commodity_any" in flt and u.get("peer_key") == "commodity" and len(flt["commodity_any"]) > 1:
            if key not in flt["commodity_any"]:
                flt["commodity_any"].append(key)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    config.cache_clear()
    return cfg


def yahoo_industries() -> list[str]:
    """Every Yahoo industry name (hyphen form), for the Settings pickers."""
    try:
        from yfinance.const import EQUITY_SCREENER_EQ_MAP
        return sorted(i.replace("—", " - ") for inds in EQUITY_SCREENER_EQ_MAP["industry"].values() for i in inds)
    except Exception:
        return []
