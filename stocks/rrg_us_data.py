import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
RESULTS_DIR   = 'results/rrg/'
OUTPUT_FILE   = 'results/rrg/us_rrg_history.csv'
BENCHMARK     = 'SPY'
LOOKBACK_DAYS = 400  # for SMA calculations
BACKFILL_DAYS = 500  # 6 months

TICKERS = {
    # US Sectors
    'XLE'  : ('Energy',                  'sector'),
    'XLK'  : ('Technology',              'sector'),
    'XLY'  : ('Consumer Disc',           'sector'),
    'XLF'  : ('Financials',              'sector'),
    'XLI'  : ('Industrials',             'sector'),
    'XLB'  : ('Materials',               'sector'),
    'XLU'  : ('Utilities',               'sector'),
    'XLP'  : ('Consumer Staples',        'sector'),
    'XLV'  : ('Healthcare',              'sector'),
    'XLC'  : ('Comm Services',           'sector'),
    'XLRE' : ('Real Estate',             'sector'),
    # Housing
    'ITB'  : ('Homebuilders ETF',        'housing'),
    '^HGX' : ('Housing Index',           'housing'),
    # AI/Tech Thematic
    'SMH'  : ('Semiconductors',          'thematic'),
    'BOTZ' : ('Robotics & AI',           'thematic'),
    'IGV'  : ('Software',                'thematic'),
    'IBB'  : ('Biotech',                 'thematic'),
    # Commodity ETFs
    'GDX'  : ('Gold Miners',             'commodity'),
    'GDXJ' : ('Junior Gold Miners',      'commodity'),
    'URA'  : ('Uranium',                 'commodity'),
    'LIT'  : ('Lithium',                 'commodity'),
    'COPX' : ('Copper Miners',           'commodity'),
    'SIL'  : ('Silver Miners',           'commodity'),
    'SILJ' : ('Junior Silver Miners',    'commodity'),
    # Banks/Finance
    'KRE'  : ('Regional Banks',          'sector'),
    # Energy/Resources Thematic
    'OIH'  : ('Oil Services',            'thematic'),
    'XOP'  : ('Oil & Gas E&P',           'thematic'),
    'PBW'  : ('Clean Energy',            'thematic'),
    'TAN'  : ('Solar',                   'thematic'),
    'JETS' : ('Airlines',                'thematic'),
    # Agriculture/Water
    'MOO'  : ('Agribusiness',            'thematic'),
    'PHO'  : ('Water',                   'thematic'),
    # Tech/Internet
    'FDN'  : ('Internet',                'thematic'),
    # Commodities
    'URNM' : ('Uranium Miners',          'commodity'),
    'REMX' : ('Rare Earth Metals',       'commodity'),
}

def fetch_prices(tickers, benchmark, start, end):
    all_tickers = list(tickers.keys()) + [benchmark]
    print(f"Fetching {len(all_tickers)} tickers from {start}...")
    raw = yf.download(all_tickers, start=start, end=end,
                      auto_adjust=True, progress=True)
    return raw['Close']

def calculate_rrg(prices, benchmark, tickers):
    results = []
    bench   = prices[benchmark].dropna()

    for ticker, (name, group) in tickers.items():
        if ticker not in prices.columns:
            print(f"  Skipping {ticker} — not in price data")
            continue

        tp = prices[ticker].dropna()
        if len(tp) < 21:
            continue

        # Align with benchmark
        aligned = pd.concat([tp, bench], axis=1).dropna()
        aligned.columns = ['ticker', 'bench']

        if len(aligned) < 21:
            continue

        # Calculate rolling RS ratio — ticker return / benchmark return
        # Use 12-week (63 day) rolling window normalised to 100
        for i in range(len(aligned)):
            if i < 20:
                continue

            date = aligned.index[i]

            # RS ratio — relative performance vs benchmark
            # Using ratio of cumulative returns from start of window
            window_start = max(0, i - 62)
            tick_ret  = aligned['ticker'].iloc[i] / aligned['ticker'].iloc[window_start]
            bench_ret = aligned['bench'].iloc[i]   / aligned['bench'].iloc[window_start]

            if bench_ret == 0:
                continue

            rs_ratio = round(float((tick_ret / bench_ret) * 100), 4)

            # RS Momentum — rate of change of RS ratio over 21 days
            if i < 41:
                rs_momentum = 100.0
            else:
                window_start_21 = max(0, i - 83)
                tick_ret_21  = aligned['ticker'].iloc[i-21] / aligned['ticker'].iloc[window_start_21]
                bench_ret_21 = aligned['bench'].iloc[i-21]  / aligned['bench'].iloc[window_start_21]
                if bench_ret_21 == 0:
                    rs_momentum = 100.0
                else:
                    rs_ratio_21  = float((tick_ret_21 / bench_ret_21) * 100)
                    rs_momentum  = round(float((rs_ratio / rs_ratio_21) * 100), 4) if rs_ratio_21 != 0 else 100.0

            results.append({
                'date'        : str(date.date()),
                'ticker'      : ticker,
                'name'        : name,
                'group'       : group,
                'rs_ratio'    : rs_ratio,
                'rs_momentum' : rs_momentum,
                'close'       : round(float(aligned['ticker'].iloc[i]), 4),
            })

    return pd.DataFrame(results)

def save_history(new_df, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    if os.path.exists(output_file):
        history = pd.read_csv(output_file)
        combined = pd.concat([history, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date','ticker'], keep='last')
        combined = combined.sort_values(['ticker','date']).reset_index(drop=True)
    else:
        combined = new_df.sort_values(['ticker','date']).reset_index(drop=True)

    combined.to_csv(output_file, index=False)
    print(f"Saved {len(combined)} rows to {output_file}")
    return combined

if __name__ == "__main__":
    import time
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    start = time.time()

    end_date   = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=BACKFILL_DAYS)).strftime('%Y-%m-%d')

    if os.path.exists(OUTPUT_FILE):
        history    = pd.read_csv(OUTPUT_FILE)
        last_date  = history['date'].max()
        start_from = last_date
        print(f"Existing history found — processing from {start_from}")
    else:
        start_from = start_date
        print(f"No existing history — backfilling {BACKFILL_DAYS} days from {start_from}")

    prices = fetch_prices(TICKERS, BENCHMARK, start_date, end_date)

    print(f"Calculating RRG data for {len(TICKERS)} tickers...")
    new_df = calculate_rrg(prices, BENCHMARK, TICKERS)
    new_df = new_df[new_df['date'] > start_from] if os.path.exists(OUTPUT_FILE) else new_df
    print(f"New rows: {len(new_df)}")

    history = save_history(new_df, OUTPUT_FILE)

    elapsed = time.time() - start
    print(f"\nCompleted in {int(elapsed//60)}m {int(elapsed%60)}s")