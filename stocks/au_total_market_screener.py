import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from config.screener.study_au_total_market import config
from data_fetch.screener.data_fetch_au_total_market import load_watchlist, fetch_prices, fetch_volumes

# ── Config ────────────────────────────────────────────────────────────────────
CSV_FILE    = config['csv_file']
RESULTS_DIR = config['results_dir']
STUDY_NAME  = config['name']
END_DATE    = datetime.today().strftime('%Y-%m-%d')
START_DATE  = (datetime.today() - timedelta(days=365)).strftime('%Y-%m-%d')
START_24M   = (datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d')

# ── Calculate Screener ────────────────────────────────────────────────────────
def calculate_screener(prices, prices_24m, volumes, watchlist_df):
    results  = []
    names    = watchlist_df.set_index('ticker')['name']
    sectors  = watchlist_df.set_index('ticker')['sector']
    industry = watchlist_df.set_index('ticker')['industry']
    cap_bands= watchlist_df.set_index('ticker')['cap_band']
    tickers  = [t for t in prices.columns if len(prices[t].dropna()) >= 2]

    # Pre-calculate 12M returns for sector peer RS
    returns_12m = {}
    for ticker in tickers:
        tp = prices[ticker].dropna()
        if len(tp) >= 2 and tp.iloc[0] != 0:
            returns_12m[ticker] = (tp.iloc[-1] / tp.iloc[0]) - 1

    # Group tickers by sector for peer RS
    sector_tickers = {}
    for ticker in tickers:
        sec = sectors.get(ticker, 'Unknown')
        if sec not in sector_tickers:
            sector_tickers[sec] = []
        sector_tickers[sec].append(ticker)

    for ticker in tickers:
        ticker_prices = prices[ticker].dropna()

        if len(ticker_prices) < 2:
            continue

        # 12M return
        if ticker_prices.iloc[0] == 0:
            print(f"Skipping {ticker} - zero base price")
            continue

        ret_12m = (ticker_prices.iloc[-1] / ticker_prices.iloc[0]) - 1

        # Sector peer RS score
        sec          = sectors.get(ticker, 'Unknown')
        sec_peers    = [t for t in sector_tickers.get(sec, []) if t != ticker and t in returns_12m]
        if len(sec_peers) > 0:
            outperforms   = sum(1 for t in sec_peers if ret_12m > returns_12m[t])
            peer_rs_score = round(outperforms / len(sec_peers) * 100, 2)
        else:
            peer_rs_score = 50.0

        # Historical peer RS vs sector median
        def sector_median(n):
            vals = [prices[t].dropna().iloc[-1] / prices[t].dropna().iloc[-n] - 1
                    for t in sec_peers if len(prices[t].dropna()) >= n]
            return np.median(vals) if vals else 0

        rs_5  = round((ticker_prices.iloc[-1] / ticker_prices.iloc[-5]  - 1) - sector_median(5),  4) if len(ticker_prices) >= 5  else None
        rs_21 = round((ticker_prices.iloc[-1] / ticker_prices.iloc[-21] - 1) - sector_median(21), 4) if len(ticker_prices) >= 21 else None
        rs_63 = round((ticker_prices.iloc[-1] / ticker_prices.iloc[-63] - 1) - sector_median(63), 4) if len(ticker_prices) >= 63 else None

        # RS Trend
        rs_values = [r for r in [rs_63, rs_21, rs_5] if r is not None]
        if len(rs_values) >= 2:
            steps    = [rs_values[i+1] - rs_values[i] for i in range(len(rs_values)-1)]
            up_steps = sum(1 for s in steps if s > 0)
            dn_steps = sum(1 for s in steps if s < 0)
            if up_steps == len(steps):
                rs_trend = 'STRONG_UP'
            elif dn_steps == len(steps):
                rs_trend = 'STRONG_DOWN'
            elif up_steps > dn_steps:
                rs_trend = 'UP'
            elif dn_steps > up_steps:
                rs_trend = 'DOWN'
            else:
                rs_trend = 'FLAT'
        else:
            rs_trend = 'FLAT'

        # Relative Volume
        if ticker in volumes.columns:
            ticker_vol  = volumes[ticker].dropna()
            if len(ticker_vol) >= 1:
                avg_vol_63  = ticker_vol.tail(63).mean()
                current_vol = ticker_vol.iloc[-1]
                rel_vol     = round(current_vol / avg_vol_63, 4) if avg_vol_63 > 0 else None
            else:
                rel_vol = None
            vol_label = 'HIGH' if rel_vol and rel_vol >= 1.5 else 'MED' if rel_vol and rel_vol >= 1.0 else 'LOW'
        else:
            rel_vol   = None
            vol_label = 'LOW'

        # 6M return
        ret_6m = (ticker_prices.iloc[-1] / ticker_prices.iloc[-126] - 1) if len(ticker_prices) >= 126 else None

        # 24M return
        ticker_24m = prices_24m[ticker].dropna()
        ret_24m    = (ticker_24m.iloc[-1] / ticker_24m.iloc[0] - 1) if len(ticker_24m) >= 2 else None

        # Max Drawdown
        rolling_max = ticker_prices.cummax()
        drawdowns   = (ticker_prices - rolling_max) / rolling_max
        max_dd      = round(drawdowns.min() * 100, 2)

        # Persistence fraction
        daily_returns = ticker_prices.pct_change().dropna()
        persist_frac  = round((daily_returns > 0).sum() / len(daily_returns) * 100, 2)

        # Volatility
        if len(ticker_prices) >= 63:
            vol_63 = round(ticker_prices.pct_change().dropna().tail(63).std() * (252 ** 0.5) * 100, 2)
        else:
            vol_63 = round(ticker_prices.pct_change().dropna().std() * (252 ** 0.5) * 100, 2)

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

        # Regime Label
        if peer_rs_score >= 75 and pass_trend == 1:
            regime_label = 'LEADER'
        elif peer_rs_score >= 50 and pass_trend == 1:
            regime_label = 'CONTENDER'
        elif peer_rs_score < 50 and pass_trend == 0:
            regime_label = 'WEAK'
        else:
            regime_label = 'LAGGARD'

        # Cap band and drawdown weighting
        cap_band   = cap_bands.get(ticker, 'small')
        dd_weights = {'large': 0.4, 'mid': 0.3, 'small': 0.2, 'ETF': 0.3}
        dd_weight  = dd_weights.get(cap_band, 0.2)

        # Accumulation Watch
        if cap_band in ['large', 'mid']:
            price = ticker_prices.iloc[-1]
            if sma20 is not None and sma50 is not None and sma200 is not None:
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

        # Volume multiplier
        vol_multiplier = {'HIGH': 1.1, 'MED': 1.0, 'LOW': 0.9}

        # RS trend bonus
        rs_trend_bonus = {'STRONG_UP': 1.0, 'UP': 0.5, 'FLAT': 0, 'DOWN': -0.5, 'STRONG_DOWN': -1.0}

        # Regime bonus
        regime_bonus = {'LEADER': 1.0, 'CONTENDER': 0.5, 'LAGGARD': 0, 'WEAK': -0.5}

        # Score Final
        base_score  = (
            (ret_12m * 0.4) +
            (persist_frac * 0.01) +
            (max_dd * -dd_weight) +
            (mqs * 0.2 if mqs is not None else 0) +
            (peer_rs_score * 0.02) +
            rs_trend_bonus[rs_trend] +
            regime_bonus[regime_label])
        score_final = round(base_score * vol_multiplier[vol_label], 4)
        score_final = None if not np.isfinite(score_final) else score_final

        results.append({
            'ticker'       : ticker,
            'name'         : names.get(ticker, ''),
            'sector'       : sec,
            'industry'     : industry.get(ticker, ''),
            'cap_band'     : cap_band,
            'close'        : round(ticker_prices.iloc[-1], 4),
            'peer_rs_score': peer_rs_score,
            'rs_5'         : rs_5,
            'rs_21'        : rs_21,
            'rs_63'        : rs_63,
            'rs_trend'     : rs_trend,
            'ret_6m'       : round(ret_6m * 100, 2) if ret_6m is not None else None,
            'ret_12m'      : round(ret_12m * 100, 2),
            'ret_24m'      : round(ret_24m * 100, 2) if ret_24m is not None else None,
            'max_dd'       : max_dd,
            'persist_frac' : persist_frac,
            'vol_63'       : vol_63,
            'rel_vol'      : rel_vol,
            'vol_label'    : vol_label,
            'acc_watch'    : acc_watch,
            'sma20'        : sma20,
            'sma50'        : sma50,
            'sma200'       : sma200,
            'pass_trend'   : pass_trend,
            'mqs'          : mqs,
            'regime_label' : regime_label,
            'score_final'  : score_final,
        })

    df = pd.DataFrame(results)
    if df.empty or 'score_final' not in df.columns:
        print(f"Warning: no results calculated for {STUDY_NAME}")
        return None
    df = df.sort_values('score_final', ascending=False, na_position='last').reset_index(drop=True)
    df.index += 1
    df.index.name = 'rank'
    return df

def save_results(df, results_dir, study_name):
    if df is None or len(df) == 0:
        print(f"No results to save for {study_name}")
        return None

    os.makedirs(results_dir, exist_ok=True)
    today = datetime.today().strftime('%Y%m%d')

    # Delta rank
    prev_file = f"{results_dir}{study_name}_latest.csv"
    if os.path.exists(prev_file):
        try:
            prev_df    = pd.read_csv(prev_file, index_col='rank')
            prev_ranks = prev_df[['ticker']].reset_index().rename(columns={'rank': 'prev_rank'})
            df         = df.reset_index()
            df         = df.merge(prev_ranks, on='ticker', how='left')
            df['delta_rank'] = df['prev_rank'] - df['rank']
            df['delta_rank'] = df['delta_rank'].fillna(0).astype(int)
            df         = df.set_index('rank')
        except Exception as e:
            print(f"Could not load previous results for delta rank: {e}")
            df['delta_rank'] = 0
    else:
        df['delta_rank'] = 0

    # Reorder columns
    df = df[['delta_rank', 'ticker', 'name', 'sector', 'industry', 'cap_band', 'close',
             'peer_rs_score', 'rs_5', 'rs_21', 'rs_63', 'rs_trend',
             'ret_6m', 'ret_12m', 'ret_24m', 'max_dd', 'persist_frac',
             'vol_63', 'rel_vol', 'vol_label', 'acc_watch',
             'sma20', 'sma50', 'sma200', 'pass_trend', 'mqs', 'regime_label', 'score_final']]

    # Save latest (for delta rank)
    df.to_csv(prev_file)
    print(f"Latest saved to {prev_file}")

    # Save dated snapshot
    snapshot_file = f"{results_dir}{today}_{study_name}.csv"
    df.to_csv(snapshot_file)
    print(f"Snapshot saved to {snapshot_file}")

    # Save top 100
    top100_file = f"{results_dir}{today}_{study_name}_top100.csv"
    df.head(100).to_csv(top100_file)
    print(f"Top 100 saved to {top100_file}")

    # Save per sector
    sector_dir = f"results/screener/au_sectors/"
    os.makedirs(sector_dir, exist_ok=True)
    for sector in df['sector'].unique():
        sec_df   = df[df['sector'] == sector].copy()
        sec_name = str(sector).lower().replace(' ', '_').replace('/', '_')
        sec_file = f"{sector_dir}{today}_{sec_name}.csv"
        sec_df.to_csv(sec_file)
    print(f"Sector files saved to {sector_dir}")

    # Daily actionable — acc_watch not '-' OR vol_label HIGH
    actionable_dir = f"results/daily_actionable/screener/"
    os.makedirs(actionable_dir, exist_ok=True)

    actionable_df = df[
        ((df['acc_watch'] != '-') & 
         (df['cap_band'].isin(['large', 'mid'])) & 
         (df['vol_label'].isin(['HIGH', 'MED'])) &
         (df['regime_label'].isin(['LEADER', 'CONTENDER']))) |
        ((df['vol_label'] == 'HIGH') & 
         (df['regime_label'] == 'LEADER'))
    ].copy()

    # Save actionable CSV
    actionable_file = f"{actionable_dir}{today}_{study_name}_actionable.csv"
    actionable_df.to_csv(actionable_file)
    print(f"Actionable report saved to {actionable_file}")

    # Save TradingView import txt
    def to_tv_format(ticker):
        return 'ASX:' + ticker.replace('.AX', '')

    tv_tickers = ','.join(actionable_df['ticker'].apply(to_tv_format).tolist())
    tv_file    = f"{actionable_dir}{today}_{study_name}_actionable_tvimport.txt"
    with open(tv_file, 'w') as f:
        f.write(tv_tickers)
    print(f"TradingView import saved to {tv_file}")

    # High conviction actionable — HIGH volume + acc_watch
    highconv_df = df[
        (df['vol_label'] == 'HIGH') &
        (df['acc_watch'] != '-') &
        (df['score_final'] > 0)
    ].copy()
    highconv_df.to_csv(f"{actionable_dir}{today}_{study_name}_actionable_highconv.csv")

    tv_highconv = ','.join(highconv_df['ticker'].tolist())
    with open(f"{actionable_dir}{today}_{study_name}_actionable_highconv_tvimport.txt", 'w') as f:
        f.write(tv_highconv)
    print(f"High conviction saved to {actionable_dir}")

    return df

def format_results(df):
    formatted = df.copy()
    for col in ['ret_6m', 'ret_12m', 'ret_24m', 'max_dd', 'persist_frac', 'vol_63']:
        formatted[col] = formatted[col].map(lambda x: f"{x:.2f}%" if pd.notna(x) else '')
    return formatted

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    watchlist   = load_watchlist(CSV_FILE)
    prices      = fetch_prices(watchlist, START_DATE, END_DATE)
    prices_24m  = fetch_prices(watchlist, START_24M, END_DATE)
    volumes     = fetch_volumes(watchlist, START_DATE, END_DATE)
    rs_results = calculate_screener(prices, prices_24m, volumes, watchlist)
    if rs_results is not None:
        rs_results  = save_results(rs_results, RESULTS_DIR, STUDY_NAME)
        if rs_results is not None:
            fmt_results = format_results(rs_results)
            fmt_results.to_csv(f"{RESULTS_DIR}{STUDY_NAME}_latest_formatted.csv")
            print(fmt_results.head(20))
    else:
        print(f"No results generated for {STUDY_NAME} — check price data")