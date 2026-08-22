import yfinance as yf
import pandas as pd

# ── Load tickers ──────────────────────────────────────────────────────────────
def load_watchlist(csv_file):
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    df['ticker'] = df['ticker'].str.strip()
    df = df.dropna(subset=['ticker'])
    return df

# ── Shared download ───────────────────────────────────────────────────────────
# fetch_prices() and fetch_volumes() are both called on every run with the same
# arguments. Downloading the universe twice doubles the runtime and the chance
# of hitting a Yahoo rate limit mid-run (which returns a partial frame), so the
# result is fetched once and reused.
_DOWNLOAD_CACHE = {}

def _download(tickers, start, end):
    key = (tuple(tickers), start, end)
    if key not in _DOWNLOAD_CACHE:
        _DOWNLOAD_CACHE[key] = yf.download(tickers, start=start, end=end,
                                           auto_adjust=True, progress=False)
    return _DOWNLOAD_CACHE[key]

# ── Fetch price data ──────────────────────────────────────────────────────────
def fetch_prices(watchlist_df, start, end):
    tickers = watchlist_df['ticker'].tolist()
    print(f"Fetching data for {len(tickers)} tickers...")
    raw          = _download(tickers, start, end)
    close_prices = raw['Close']
    print(f"Data fetched: {len(close_prices)} trading days")
    return close_prices

# ── Fetch volume data ─────────────────────────────────────────────────────────
def fetch_volumes(watchlist_df, start, end):
    tickers = watchlist_df['ticker'].tolist()
    raw     = _download(tickers, start, end)
    return raw['Volume']