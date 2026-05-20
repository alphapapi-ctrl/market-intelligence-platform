import yfinance as yf
import pandas as pd
import time
import argparse
import os

def get_cap_band(market_cap):
    if market_cap is None or pd.isna(market_cap):
        return 'small'
    elif market_cap > 10_000_000_000:
        return 'large'
    elif market_cap >= 2_000_000_000:
        return 'mid'
    else:
        return 'small'

def fetch_market_caps(watchlist_file, output_file=None, delay=0.5):
    if output_file is None:
        output_file = watchlist_file

    df      = pd.read_csv(watchlist_file)
    tickers = df['ticker'].dropna().tolist()

    # Skip benchmark/index rows
    if 'sector' in df.columns:
        skip = df[df['sector'].isin(['index', 'benchmark'])]['ticker'].tolist()
        tickers = [t for t in tickers if t not in skip]

    print(f"Fetching market caps for {len(tickers)} tickers from {watchlist_file}...")
    market_caps = {}

    for i, ticker in enumerate(tickers, 1):
        try:
            info = yf.Ticker(ticker).info
            market_caps[ticker] = info.get('marketCap', None)
            cap = market_caps[ticker]
            band = get_cap_band(cap)
            cap_str = f"${cap/1e9:.1f}B" if cap else "N/A"
            print(f"  [{i:>3}/{len(tickers)}] {ticker:<12} {cap_str:<12} → {band}")
        except Exception as e:
            market_caps[ticker] = None
            print(f"  [{i:>3}/{len(tickers)}] {ticker:<12} ERROR: {e}")
        time.sleep(delay)

    df['market_cap'] = df['ticker'].map(market_caps).combine_first(df.get('market_cap', pd.Series(dtype=float)))
    df['cap_band']   = df['market_cap'].apply(get_cap_band)

    # Preserve existing cap_band for index/benchmark rows
    if 'sector' in df.columns:
        index_mask = df['sector'].isin(['index', 'benchmark'])
        df.loc[index_mask, 'cap_band'] = df.loc[index_mask, 'cap_band'].fillna('')

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    df.to_csv(output_file, index=False)

    print(f"\nSaved to {output_file}")
    print(df['cap_band'].value_counts().to_string())
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch market caps and update cap_band in a watchlist CSV.')
    parser.add_argument('--watchlist', '-w', required=True,
                        help='Path to the watchlist CSV file (e.g. watchlist/nasdaq100.csv)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output path (defaults to same file as --watchlist)')
    parser.add_argument('--delay', '-d', type=float, default=0.5,
                        help='Delay in seconds between requests (default: 0.5)')
    args = parser.parse_args()

    fetch_market_caps(args.watchlist, args.output, args.delay)
