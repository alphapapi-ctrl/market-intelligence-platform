import yfinance as yf
import pandas as pd

# ── Load tickers ──────────────────────────────────────────────────────────────
def load_watchlist(csv_file):
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    df['ticker'] = df['ticker'].str.strip()
    df = df.dropna(subset=['ticker'])
    df['name'] = df['name'].astype(str).str.strip().str.replace('\n', ' ').str.replace('\r', ' ')
    return df

# ── Fetch price data ──────────────────────────────────────────────────────────
def fetch_prices(watchlist_df, start, end):
    tickers = watchlist_df['ticker'].tolist()
    print(f"Fetching data for {len(tickers)} tickers...")
    raw          = yf.download(tickers, start=start, end=end, auto_adjust=True)
    close_prices = raw['Close']
    print(f"Data fetched: {len(close_prices)} trading days")
    return close_prices

# ── Fetch volume data ─────────────────────────────────────────────────────────
def fetch_volumes(watchlist_df, start, end):
    tickers = watchlist_df['ticker'].tolist()
    raw     = yf.download(tickers, start=start, end=end, auto_adjust=True)
    return raw['Volume']