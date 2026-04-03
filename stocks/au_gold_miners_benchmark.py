import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from config.benchmark.study_au_gold_miners import config
from data_fetch.benchmark.data_fetch_au_gold_miners import load_watchlist, fetch_prices, fetch_volumes

# ── Config ────────────────────────────────────────────────────────────────────
CSV_FILE    = config['csv_file']
RESULTS_DIR = config['results_dir']
STUDY_NAME  = config['name']
END_DATE    = datetime.today().strftime('%Y-%m-%d')
START_DATE  = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
START_24M   = (datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d')

# ── Calculate Benchmark RS ────────────────────────────────────────────────────
def calculate_benchmark(prices, prices_24m, volumes, watchlist_df):
    results   = []
    names     = watchlist_df.set_index('ticker')['name']
    sectors   = watchlist_df.set_index('ticker')['sector'].to_dict()
    cap_bands = watchlist_df.set_index('ticker')['cap_band'].to_dict()

    # Benchmark
    bench_row    = watchlist_df[watchlist_df['benchmark'] == 'benchmark']
    bench_ticker = bench_row['ticker'].iloc[0]
    bench_prices = prices[bench_ticker].dropna()
    print(f"Benchmark: {bench_ticker}")

    bench_12m = (bench_prices.iloc[-1] / bench_prices.iloc[0]) - 1
    bench_5d  = (bench_prices.iloc[-1] / bench_prices.iloc[-5]  - 1) if len(bench_prices) >= 5  else 0
    bench_21d = (bench_prices.iloc[-1] / bench_prices.iloc[-21] - 1) if len(bench_prices) >= 21 else 0
    bench_63d = (bench_prices.iloc[-1] / bench_prices.iloc[-63] - 1) if len(bench_prices) >= 63 else 0

    tickers = [t for t in prices.columns
               if t != bench_ticker
               and sectors.get(t) != 'index'
               and len(prices[t].dropna()) >= 2]

    for ticker in tickers:
        ticker_prices = prices[ticker].dropna()

        if len(ticker_prices) < 2:
            continue
        if ticker_prices.iloc[0] == 0:
            continue

        ret_12m = (ticker_prices.iloc[-1] / ticker_prices.iloc[0]) - 1
        if not np.isfinite(ret_12m):
            continue

        # RS Ratio
        rs_ratio = round((1 + ret_12m) / (1 + bench_12m), 4)
        rs_5     = round((1 + (ticker_prices.iloc[-1] / ticker_prices.iloc[-5]  - 1)) / (1 + bench_5d),  4) if len(ticker_prices) >= 5  else None
        rs_21    = round((1 + (ticker_prices.iloc[-1] / ticker_prices.iloc[-21] - 1)) / (1 + bench_21d), 4) if len(ticker_prices) >= 21 else None
        rs_63    = round((1 + (ticker_prices.iloc[-1] / ticker_prices.iloc[-63] - 1)) / (1 + bench_63d), 4) if len(ticker_prices) >= 63 else None

        # RS Trend
        rs_values = [r for r in [rs_63, rs_21, rs_5] if r is not None]
        if len(rs_values) >= 2:
            steps    = [rs_values[i+1] - rs_values[i] for i in range(len(rs_values)-1)]
            up_steps = sum(1 for s in steps if s > 0)
            dn_steps = sum(1 for s in steps if s < 0)
            if up_steps == len(steps):   rs_trend = 'STRONG_UP'
            elif dn_steps == len(steps): rs_trend = 'STRONG_DOWN'
            elif up_steps > dn_steps:    rs_trend = 'UP'
            elif dn_steps > up_steps:    rs_trend = 'DOWN'
            else:                        rs_trend = 'FLAT'
        else:
            rs_trend = 'FLAT'

        # Volume
        if ticker in volumes.columns:
            ticker_vol  = volumes[ticker].dropna()
            avg_vol_63  = ticker_vol.tail(63).mean() if len(ticker_vol) >= 1 else None
            current_vol = ticker_vol.iloc[-1] if len(ticker_vol) >= 1 else None
            rel_vol     = round(current_vol / avg_vol_63, 4) if avg_vol_63 and avg_vol_63 > 0 else None
            vol_label   = 'HIGH' if rel_vol and rel_vol >= 1.5 else 'MED' if rel_vol and rel_vol >= 1.0 else 'LOW'
        else:
            rel_vol   = None
            vol_label = 'LOW'

        # Returns
        ret_6m      = round((ticker_prices.iloc[-1] / ticker_prices.iloc[-126] - 1) * 100, 2) if len(ticker_prices) >= 126 else None
        ret_12m_pct = round(ret_12m * 100, 2)
        ticker_24m  = prices_24m[ticker].dropna()
        ret_24m     = round((ticker_24m.iloc[-1] / ticker_24m.iloc[0] - 1) * 100, 2) if len(ticker_24m) >= 2 else None

        # Max Drawdown
        rolling_max = ticker_prices.cummax()
        drawdowns   = (ticker_prices - rolling_max) / rolling_max
        max_dd      = round(drawdowns.min() * 100, 2)

        # Persistence
        daily_returns = ticker_prices.pct_change().dropna()
        persist_frac  = round((daily_returns > 0).sum() / len(daily_returns) * 100, 2)

        # Volatility
        vol_63 = round(ticker_prices.pct_change().dropna().tail(63).std() * (252 ** 0.5) * 100, 2) if len(ticker_prices) >= 63 else None

        # SMAs
        sma20      = round(ticker_prices.tail(20).mean(), 4) if len(ticker_prices) >= 20  else None
        sma50      = round(ticker_prices.tail(50).mean(), 4) if len(ticker_prices) >= 50  else None
        sma200     = round(ticker_prices.tail(200).mean(), 4) if len(ticker_prices) >= 200 else None
        pass_trend = 1 if sma200 is not None and ticker_prices.iloc[-1] > sma200 else 0

        # MQS
        if vol_63 and vol_63 > 0 and np.isfinite(ret_12m):
            mqs = round((ret_12m * 100 * persist_frac) / vol_63, 4)
            mqs = None if not np.isfinite(mqs) else mqs
        else:
            mqs = None

        # Cap band
        cap_band   = cap_bands.get(ticker, 'small')
        dd_weights = {'large': 0.4, 'mid': 0.3, 'small': 0.2, 'ETF': 0.3}
        dd_weight  = dd_weights.get(cap_band, 0.2)

        # Accumulation Watch
        if cap_band in ['large', 'mid']:
            price = ticker_prices.iloc[-1]
            if sma20 and sma50 and sma200:
                if price < sma20 and price < sma50 and price < sma200:
                    acc_watch = 'EARLY'
                elif price < sma50 and price < sma200 and price >= sma20:
                    acc_watch = 'PROGRESS'
                elif price < sma200 and price >= sma50 and price >= sma20:
                    acc_watch = 'SHIFT'
                else:
                    acc_watch = '-'
            else:
                acc_watch = '-'
        else:
            acc_watch = '-'

        # Regime
        if rs_ratio > 1.0 and pass_trend == 1:
            regime_label = 'TREND+LEAD'
        elif pass_trend == 1:
            regime_label = 'TREND_ONLY'
        else:
            regime_label = 'WEAK'

        # Score
        vol_multiplier = {'HIGH': 1.1, 'MED': 1.0, 'LOW': 0.9}
        rs_trend_bonus = {'STRONG_UP': 1.0, 'UP': 0.5, 'FLAT': 0, 'DOWN': -0.5, 'STRONG_DOWN': -1.0}
        trend_bonus    = 1.0 if pass_trend == 1 else 0
        lead_bonus     = 1.0 if rs_ratio > 1.0 else 0

        base_score  = (
            (ret_12m * 0.4) +
            (persist_frac * 0.01) +
            (max_dd * -dd_weight) +
            (mqs * 0.2 if mqs is not None else 0) +
            trend_bonus + lead_bonus +
            rs_trend_bonus[rs_trend])
        score_final = round(base_score * vol_multiplier[vol_label], 4)
        score_final = None if not np.isfinite(score_final) else score_final

        results.append({
            'ticker'      : ticker,
            'name'        : names.get(ticker, ''),
            'sector'      : sectors.get(ticker, ''),
            'cap_band'    : cap_band,
            'close'       : round(ticker_prices.iloc[-1], 4),
            'rs_ratio'    : rs_ratio,
            'rs_5'        : rs_5,
            'rs_21'       : rs_21,
            'rs_63'       : rs_63,
            'rs_trend'    : rs_trend,
            'ret_6m'      : ret_6m,
            'ret_12m'     : ret_12m_pct,
            'ret_24m'     : ret_24m,
            'max_dd'      : max_dd,
            'persist_frac': persist_frac,
            'vol_63'      : vol_63,
            'rel_vol'     : rel_vol,
            'vol_label'   : vol_label,
            'acc_watch'   : acc_watch,
            'sma20'       : sma20,
            'sma50'       : sma50,
            'sma200'      : sma200,
            'pass_trend'  : pass_trend,
            'mqs'         : mqs,
            'regime_label': regime_label,
            'score_final' : score_final,
        })

    df = pd.DataFrame(results)
    df = df.sort_values('score_final', ascending=False, na_position='last').reset_index(drop=True)
    df.index += 1
    df.index.name = 'rank'
    return df

def save_results(df, results_dir, study_name):
    os.makedirs(results_dir, exist_ok=True)
    today = datetime.today().strftime('%Y%m%d')

    prev_file = f"{results_dir}{study_name}_latest.csv"
    if os.path.exists(prev_file):
        prev_df    = pd.read_csv(prev_file, index_col='rank')
        prev_ranks = prev_df['ticker'].reset_index().rename(columns={'rank': 'prev_rank'})
        df         = df.reset_index()
        df         = df.merge(prev_ranks, on='ticker', how='left')
        df['delta_rank'] = df['prev_rank'] - df['rank']
        df['delta_rank'] = df['delta_rank'].fillna(0).astype(int)
        df         = df.set_index('rank')
    else:
        df['delta_rank'] = 0

    df = df[['delta_rank', 'ticker', 'name', 'sector', 'cap_band', 'close',
             'rs_ratio', 'rs_5', 'rs_21', 'rs_63', 'rs_trend',
             'ret_6m', 'ret_12m', 'ret_24m', 'max_dd', 'persist_frac',
             'vol_63', 'rel_vol', 'vol_label', 'acc_watch',
             'sma20', 'sma50', 'sma200', 'pass_trend', 'mqs', 'regime_label', 'score_final']]

    df.to_csv(prev_file)
    df.to_csv(f"{results_dir}{today}_{study_name}.csv")
    df.head(100).to_csv(f"{results_dir}{today}_{study_name}_top100.csv")

    actionable_dir = 'results/daily_actionable/screener/'
    os.makedirs(actionable_dir, exist_ok=True)

    actionable_df = df[
        ((df['acc_watch'] != '-') & (df['cap_band'].isin(['large', 'mid']))) |
        ((df['vol_label'] == 'HIGH') & (df['regime_label'].isin(['TREND+LEAD', 'TREND_ONLY'])))
    ].copy()
    actionable_df.to_csv(f"{actionable_dir}{today}_au_gold_miners_actionable.csv")

    tv_tickers = ','.join(actionable_df['ticker'].tolist())
    with open(f"{actionable_dir}{today}_au_gold_miners_actionable_tvimport.txt", 'w') as f:
        f.write(tv_tickers)

    print(f"Results saved to {results_dir}")
    return df

def format_results(df):
    formatted = df.copy()
    for col in ['ret_6m', 'ret_12m', 'ret_24m', 'max_dd', 'persist_frac', 'vol_63']:
        formatted[col] = formatted[col].map(lambda x: f"{x:.2f}%" if pd.notna(x) else '')
    return formatted

if __name__ == "__main__":
    import time
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    start      = time.time()
    watchlist  = load_watchlist(CSV_FILE)
    prices     = fetch_prices(watchlist, START_DATE, END_DATE)
    prices_24m = fetch_prices(watchlist, START_24M, END_DATE)
    volumes    = fetch_volumes(watchlist, START_DATE, END_DATE)
    bm_results = calculate_benchmark(prices, prices_24m, volumes, watchlist)
    bm_results = save_results(bm_results, RESULTS_DIR, STUDY_NAME)
    fmt_results = format_results(bm_results)
    fmt_results.to_csv(f"{RESULTS_DIR}{STUDY_NAME}_latest_formatted.csv")
    print(fmt_results.head(20))
    elapsed = time.time() - start
    print(f"\nCompleted in {int(elapsed//60)}m {int(elapsed%60)}s")