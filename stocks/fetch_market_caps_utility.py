# save as fetch_market_caps_uranium.py
import yfinance as yf
import pandas as pd
import time

WATCHLIST_FILE = 'watchlist/au_gold_miners_watchlist.csv'
OUTPUT_FILE    = 'watchlist/au_gold_miners_watchlist.csv'

def get_cap_band(market_cap):
    if market_cap is None or pd.isna(market_cap):
        return 'small'
    elif market_cap > 5_000_000_000:
        return 'large'
    elif market_cap >= 500_000_000:
        return 'mid'
    else:
        return 'small'

df          = pd.read_csv(WATCHLIST_FILE)
tickers     = df['ticker'].tolist()
market_caps = {}

print(f"Fetching market caps for {len(tickers)} tickers...")
for ticker in tickers:
    try:
        info = yf.Ticker(ticker).info
        market_caps[ticker] = info.get('marketCap', None)
    except Exception as e:
        market_caps[ticker] = None
    time.sleep(0.5)

df['market_cap'] = df['ticker'].map(market_caps)
df['cap_band']   = df['market_cap'].apply(get_cap_band)
df.to_csv(OUTPUT_FILE, index=False)
print(df['cap_band'].value_counts())