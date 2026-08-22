import yfinance as yf
import pandas as pd
import time
import os

# ── Config ────────────────────────────────────────────────────────────────────
BASE           = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_FILE = os.path.join(BASE, 'stocks', 'watchlist', 'au_gold_miners_watchlist.csv')
OUTPUT_FILE    = WATCHLIST_FILE

# ── Cap band thresholds — AU gold miners ──────────────────────────────────────
def get_cap_band(market_cap):
    if market_cap is None or pd.isna(market_cap):
        return 'small'
    elif market_cap > 5_000_000_000:
        return 'large'
    elif market_cap >= 500_000_000:
        return 'mid'
    else:
        return 'small'

# ── Fetch market caps ─────────────────────────────────────────────────────────
def fetch_market_caps(watchlist_df, batch_size=50, delay=1):
    tickers     = watchlist_df['ticker'].tolist()
    market_caps = {}
    total       = len(tickers)
    batches     = [tickers[i:i+batch_size] for i in range(0, total, batch_size)]

    print(f"Fetching market caps for {total} tickers in {len(batches)} batches...")
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}/{len(batches)}...")
        for ticker in batch:
            try:
                info = yf.Ticker(ticker).info
                market_caps[ticker] = info.get('marketCap', None)
            except Exception as e:
                print(f"    {ticker}: error — {e}")
                market_caps[ticker] = None
        time.sleep(delay)
    return market_caps

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print(f"Loading: {WATCHLIST_FILE}")
    df = pd.read_csv(WATCHLIST_FILE)
    df.columns = df.columns.str.strip()
    df['ticker'] = df['ticker'].str.strip()

    market_caps = fetch_market_caps(df)
    df['market_cap'] = df['ticker'].map(market_caps)
    df['cap_band']   = df['market_cap'].apply(get_cap_band)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"Cap band distribution:")
    print(df['cap_band'].value_counts())