import io
"""
data/sentiment.py
AAII Investor Sentiment Survey + SPX weekly price data.

AAII publishes the weekly survey results (bullish / neutral / bearish %)
as an Excel file. SPX weekly OHLC comes from the Yahoo Finance chart API.
Both are cached locally in data/cache and refreshed when stale.
"""

from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import requests

CACHE_DIR = Path(__file__).parent / "cache"

AAII_URL = "https://www.aaii.com/files/surveys/sentiment.xls"
AAII_XLS_CACHE = CACHE_DIR / "aaii_sentiment.xls"
AAII_PARQUET = CACHE_DIR / "aaii_sentiment.parquet"

NAAIM_PAGE_URL = "https://naaim.org/programs/naaim-exposure-index/"
NAAIM_XLSX_CACHE = CACHE_DIR / "naaim_exposure.xlsx"
NAAIM_PARQUET = CACHE_DIR / "naaim_exposure.parquet"

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Symbols selectable for the price panel on the Sentiment page
INDEX_SYMBOLS = {
    "S&P 500": "^GSPC",
    "Nasdaq Composite": "^IXIC",
    "Gold (futures)": "GC=F",
    "Silver (futures)": "SI=F",
}

# Farside Investors spot crypto ETF flow tables (daily, USD millions,
# per fund + total, updated the next morning). Same 403-to-bare-clients
# behaviour as AAII — needs the browser headers.
CRYPTO_FLOW_ASSETS = {
    "Bitcoin":  {"key": "btc", "url": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
                 "price": "BTC-USD"},
    "Ethereum": {"key": "eth", "url": "https://farside.co.uk/ethereum-etf-flow-all-data/",
                 "price": "ETH-USD"},
}

# CFTC legacy futures-only COT report (Socrata API, no key required).
# Contract market codes are stable even though market names changed over time.
COT_API_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
COT_MARKETS = {
    "E-mini S&P 500": {"code": "13874A", "price": "^GSPC"},
    "E-mini Nasdaq-100": {"code": "209742", "price": "^IXIC"},
    "Gold (COMEX)": {"code": "088691", "price": "GC=F"},
    "Silver (COMEX)": {"code": "084691", "price": "SI=F"},
}

# AAII serves 403 to bare clients — needs normal browser headers
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.aaii.com/sentimentsurvey",
}

# Survey results post Thursdays — refresh anything older than 3 days
MAX_CACHE_AGE_DAYS = 3


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(days=MAX_CACHE_AGE_DAYS)


# ── marketdb-backed cache (frames table) ────────────────────────────────────
import os as _os, sys as _sys
_BASE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _BASE not in _sys.path:
    _sys.path.insert(0, _BASE)
try:
    from marketdb import results as _mr
    _STORE = True
except Exception as _e:  # pragma: no cover
    print(f"marketdb unavailable ({_e}); sentiment caches will not persist")
    _STORE = False


def _cache_get(name: str, force: bool):
    """-> (df or None, fresh: bool). Fresh means updated within MAX_CACHE_AGE_DAYS."""
    if not _STORE:
        return None, False
    try:
        df = _mr.load_frame("sentiment/" + name)
        if df is None:
            return None, False
        upd = _mr.frame_updated("sentiment/" + name)
        fresh = bool(upd) and (datetime.now() - datetime.strptime(upd, "%Y-%m-%d %H:%M:%S")) < timedelta(days=MAX_CACHE_AGE_DAYS)
        return df, (fresh and not force)
    except Exception:
        return None, False


def _cache_put(name: str, df: pd.DataFrame) -> pd.DataFrame:
    if _STORE:
        try:
            _mr.save_frame("sentiment/" + name, df)
        except Exception as e:
            print(f"sentiment cache write failed ({name}): {e}")
    return df


# ══════════════════════════════════════════════════════════════
# AAII sentiment
# ══════════════════════════════════════════════════════════════

def parse_aaii_xls(source) -> pd.DataFrame:
    """
    Parse the AAII sentiment.xls (SENTIMENT sheet) into a DataFrame with
    columns: date, bullish, neutral, bearish, spread (all pct points).

    `source` is a path or file-like object. The sheet has 4 header rows,
    dates as Excel serials in col 0, fractions in cols 1-3, and footer
    rows ("Count '21" etc.) that are skipped because col 0 is not a number.
    """
    import xlrd

    if hasattr(source, "read"):
        wb = xlrd.open_workbook(file_contents=source.read())
    else:
        wb = xlrd.open_workbook(source)
    sh = wb.sheet_by_name("SENTIMENT")

    rows = []
    for i in range(4, sh.nrows):
        cells = sh.row(i)
        if cells[0].ctype not in (xlrd.XL_CELL_DATE, xlrd.XL_CELL_NUMBER):
            continue
        if any(cells[c].ctype != xlrd.XL_CELL_NUMBER for c in (1, 2, 3)):
            continue  # early weeks with no survey values
        dt = xlrd.xldate_as_datetime(cells[0].value, wb.datemode)
        rows.append({
            "date": dt.date(),
            "bullish": cells[1].value * 100.0,
            "neutral": cells[2].value * 100.0,
            "bearish": cells[3].value * 100.0,
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["spread"] = df["bullish"] - df["bearish"]
    return df.sort_values("date").reset_index(drop=True)


def fetch_aaii(force: bool = False) -> pd.DataFrame:
    """Download (or reuse cached) AAII sentiment data."""
    cached, fresh = _cache_get("aaii", force)
    if fresh:
        return cached
    try:
        resp = requests.get(AAII_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        if b"<html" in resp.content[:200].lower():
            raise RuntimeError("AAII returned an HTML page instead of the xls")
        df = parse_aaii_xls(io.BytesIO(resp.content))
    except Exception:
        # Download blocked/offline — fall back to whatever we have
        if cached is not None:
            return cached
        raise
    return _cache_put("aaii", df)


def import_aaii_file(uploaded) -> pd.DataFrame:
    """Import a manually downloaded sentiment.xls (file-like) and cache it."""
    return _cache_put("aaii", parse_aaii_xls(uploaded))


# ══════════════════════════════════════════════════════════════
# NAAIM Exposure Index
# ══════════════════════════════════════════════════════════════

def fetch_naaim(force: bool = False) -> pd.DataFrame:
    """
    NAAIM Exposure Index (weekly since 2006). The data file is a dated
    xlsx linked from the program page, so scrape the current link first.
    Columns: date, exposure, q1, median, q3.
    """
    import re

    cached, fresh = _cache_get("naaim", force)
    if fresh:
        return cached
    try:
        page = requests.get(NAAIM_PAGE_URL, headers=_HEADERS, timeout=30)
        page.raise_for_status()
        m = re.search(r'href="(https://naaim\.org/wp-content/uploads/[^"]*USE_Data[^"]*\.xlsx)"',
                      page.text)
        if not m:
            raise RuntimeError("Could not find USE_Data xlsx link on the NAAIM page")
        resp = requests.get(m.group(1), headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        raw = pd.read_excel(io.BytesIO(resp.content), sheet_name=0)
    except Exception:
        if cached is not None:
            return cached
        raise

    df = pd.DataFrame({
        "date": pd.to_datetime(raw["Date"]),
        "exposure": raw["NAAIM Number"],
        "q1": raw["Quart 1 (25% at/below)"],
        "median": raw["Quart 2 (median)"],
        "q3": raw["Quart 3 (25% at/above)"],
    }).dropna(subset=["date", "exposure"])
    # file has duplicate rows and is newest-first
    df = (df.drop_duplicates(subset="date", keep="first")
            .sort_values("date").reset_index(drop=True))
    return _cache_put("naaim", df)


# ══════════════════════════════════════════════════════════════
# Index prices (weekly, Yahoo chart API)
# ══════════════════════════════════════════════════════════════

def fetch_index_weekly(symbol: str = "^GSPC", force: bool = False) -> pd.DataFrame:
    """
    Weekly OHLC (full available history) for a Yahoo symbol.
    Columns: date, open, high, low, close.
    """
    safe = "".join(c if c.isalnum() else "_" for c in symbol)
    cached, fresh = _cache_get(f"index_{safe}_weekly", force)
    if fresh:
        return cached
    try:
        # range=max silently downgrades granularity — use explicit epoch bounds
        resp = requests.get(YAHOO_CHART_URL.format(symbol=requests.utils.quote(symbol)),
                            params={"period1": "441763200", "period2": "9999999999",
                                    "interval": "1wk"},
                            headers={"User-Agent": _HEADERS["User-Agent"]}, timeout=30)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
    except Exception:
        if cached is not None:
            return cached
        raise

    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": pd.to_datetime(result["timestamp"], unit="s").normalize(),
        "open": quote["open"], "high": quote["high"],
        "low": quote["low"], "close": quote["close"],
    }).dropna(subset=["close"]).reset_index(drop=True)
    return _cache_put(f"index_{safe}_weekly", df)


def fetch_spx_weekly(force: bool = False) -> pd.DataFrame:
    return fetch_index_weekly("^GSPC", force=force)


def fetch_index_daily(symbol: str, force: bool = False) -> pd.DataFrame:
    """
    Daily OHLC since mid-2023 for a Yahoo symbol (runway for the crypto
    ETF flow panel — spot ETFs launched Jan 2024).
    Columns: date, open, high, low, close.
    """
    safe = "".join(c if c.isalnum() else "_" for c in symbol)
    cached, fresh = _cache_get(f"index_{safe}_daily", force)
    if fresh:
        return cached
    try:
        resp = requests.get(YAHOO_CHART_URL.format(symbol=requests.utils.quote(symbol)),
                            params={"period1": "1688169600", "period2": "9999999999",
                                    "interval": "1d"},
                            headers={"User-Agent": _HEADERS["User-Agent"]}, timeout=30)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
    except Exception:
        if cached is not None:
            return cached
        raise

    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": pd.to_datetime(result["timestamp"], unit="s").normalize(),
        "open": quote["open"], "high": quote["high"],
        "low": quote["low"], "close": quote["close"],
    }).dropna(subset=["close"]).reset_index(drop=True)
    return _cache_put(f"index_{safe}_daily", df)


# ══════════════════════════════════════════════════════════════
# Spot crypto ETF flows (Farside Investors)
# ══════════════════════════════════════════════════════════════

def _farside_num(v) -> float:
    """Farside cells: '1,234.5', '(93.5)' for outflows, footnote marks
    like '9199.3*', '-' / '' for no data."""
    s = str(v).strip().replace(",", "").rstrip("*†‡")
    if s in ("", "-", "nan", "None"):
        return float("nan")
    if s.startswith("(") and s.endswith(")"):
        return -float(s[1:-1])
    return float(s)


def fetch_crypto_etf_flows(asset: str = "Bitcoin", force: bool = False) -> pd.DataFrame:
    """
    Daily net flows for the US spot crypto ETF complex, USD millions.
    Columns: date, one column per fund ticker (IBIT, FBTC, GBTC, ...), total.
    Footer rows (Total / Average / Maximum / Minimum) and the ETH 'Seed'
    row are dropped because their first cell is not a date.
    """
    cfg = CRYPTO_FLOW_ASSETS[asset]
    cached, fresh = _cache_get(f"crypto_flows_{cfg['key']}", force)
    if fresh:
        return cached
    try:
        resp = requests.get(cfg["url"], headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        raw = max(tables, key=len)
        if len(raw) < 50:
            raise RuntimeError(f"Farside {asset} table too small ({len(raw)} rows)")
    except Exception:
        if cached is not None:
            return cached
        raise

    # Columns are a MultiIndex of (mostly Unnamed, ticker, fee[, staking fee]);
    # first column is the date, last is the total.
    def _fund_name(col):
        for part in (col if isinstance(col, tuple) else (col,)):
            p = str(part).strip()
            if (p and not p.startswith("Unnamed") and not p.endswith("%")
                    and p not in ("Fee", "Staking fee", "Total")):
                return p.lower()
        return None

    cols = list(raw.columns)
    out = pd.DataFrame({"date": pd.to_datetime(raw[cols[0]], format="%d %b %Y",
                                               errors="coerce")})
    for col in cols[1:-1]:
        name = _fund_name(col)
        if name:
            out[name] = raw[col].map(_farside_num)
    out["total"] = raw[cols[-1]].map(_farside_num)
    out = (out.dropna(subset=["date", "total"])
              .drop_duplicates(subset="date", keep="last")
              .sort_values("date").reset_index(drop=True))
    if out.empty:
        raise RuntimeError(f"Farside {asset} table parsed to no rows")
    return _cache_put(f"crypto_flows_{cfg['key']}", out)


# ══════════════════════════════════════════════════════════════
# CFTC COT positioning
# ══════════════════════════════════════════════════════════════

def fetch_cot(code: str, force: bool = False) -> pd.DataFrame:
    """
    Weekly legacy futures-only COT data for one contract market code.
    Columns: date, open_interest, noncomm_long, noncomm_short, noncomm_net,
    comm_long, comm_short, comm_net, noncomm_net_pct_oi.
    Reports are as-of Tuesday, published Friday afternoon.
    """
    cached, fresh = _cache_get(f"cot_{code}", force)
    if fresh:
        return cached
    try:
        resp = requests.get(COT_API_URL, params={
            "cftc_contract_market_code": code,
            "$select": ("report_date_as_yyyy_mm_dd,open_interest_all,"
                        "noncomm_positions_long_all,noncomm_positions_short_all,"
                        "comm_positions_long_all,comm_positions_short_all"),
            "$order": "report_date_as_yyyy_mm_dd",
            "$limit": "10000",
        }, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            raise RuntimeError(f"CFTC API returned no rows for code {code}")
    except Exception:
        if cached is not None:
            return cached
        raise

    df = pd.DataFrame(rows).rename(columns={
        "report_date_as_yyyy_mm_dd": "date",
        "open_interest_all": "open_interest",
        "noncomm_positions_long_all": "noncomm_long",
        "noncomm_positions_short_all": "noncomm_short",
        "comm_positions_long_all": "comm_long",
        "comm_positions_short_all": "comm_short",
    })
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open_interest", "noncomm_long", "noncomm_short", "comm_long", "comm_short"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = (df.dropna()
            .drop_duplicates(subset="date", keep="last")
            .sort_values("date").reset_index(drop=True))
    df["noncomm_net"] = df["noncomm_long"] - df["noncomm_short"]
    df["comm_net"] = df["comm_long"] - df["comm_short"]
    df["noncomm_net_pct_oi"] = 100.0 * df["noncomm_net"] / df["open_interest"]
    return _cache_put(f"cot_{code}", df)
