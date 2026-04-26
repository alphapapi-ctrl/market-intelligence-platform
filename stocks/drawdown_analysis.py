import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime, timedelta
from data_fetch.benchmark.data_fetch_generic import load_watchlist, fetch_prices, fetch_volumes

AU_SECTOR_BENCH_MAP = {
    'Energy minerals'       : '^AXEJ',
    'Finance'               : '^AXFJ',
    'Technology services'   : '^AXIJ',
    'Electronic technology' : '^AXIJ',
    'Communications'        : '^AXTJ',
    'Utilities'             : '^AXUJ',
    'Non-energy minerals'   : '^AXMJ',
    'Process industries'    : '^AXMJ',
    'Consumer services'     : '^AXDJ',
    'Consumer non-durables' : '^AXDJ',
    'Consumer durables'     : '^AXDJ',
    'Retail trade'          : '^AXDJ',
    'Health technology'     : '^AXHJ',
    'Health services'       : '^AXHJ',
    'Industrial services'   : '^AXNJ',
    'Producer manufacturing': '^AXNJ',
    'Commercial services'   : '^AXNJ',
    'Distribution services' : '^AXNJ',
    'Transportation'        : '^AXNJ',
    'Miscellaneous'         : '^AXJO',
}

US_SECTOR_BENCH_MAP = {
    'Energy'                 : 'XLE',
    'Information Technology' : 'XLK',
    'Technology'             : 'XLK',
    'Consumer Discretionary' : 'XLY',
    'Financials'             : 'XLF',
    'Industrials'            : 'XLI',
    'Materials'              : 'XLB',
    'Utilities'              : 'XLU',
    'Consumer Staples'       : 'XLP',
    'Health Care'            : 'XLV',
    'Communication Services' : 'XLC',
    'Communication'          : 'XLC',
    'Real Estate'            : 'XLRE',
}

COMMODITY_BENCH_MAP = {
    'gold'      : 'GDX',
    'silver'    : 'SIL',
    'copper'    : 'COPX',
    'uranium'   : 'URA',
    'lithium'   : 'LIT',
    'platinum'  : 'ETPMPT.AX',
    'palladium' : 'ETPMPD.AX',
}

def get_sector_benchmark(filter_col, filter_val):
    """Return the appropriate benchmark ETF ticker for a sector/commodity filter"""
    if filter_col == 'sector':
        # Try AU map first then US map
        bench = AU_SECTOR_BENCH_MAP.get(filter_val) or US_SECTOR_BENCH_MAP.get(filter_val)
        return bench
    elif filter_col == 'commodity':
        return COMMODITY_BENCH_MAP.get(filter_val)
    return None

# ── Runtime prompts ───────────────────────────────────────────────────────────
def get_inputs():
    print("\n" + "═"*60)
    print("  DRAWDOWN ANALYSIS TOOL")
    print("═"*60)

    # Watchlist
    print("\nAvailable watchlists:")
    watchlists = glob.glob('watchlist/*.csv')
    for i, w in enumerate(watchlists):
        print(f"  {i+1}. {w}")
    csv_input = input("\nEnter watchlist path (or number): ").strip()
    if csv_input.isdigit():
        csv_file = watchlists[int(csv_input) - 1]
    else:
        csv_file = csv_input
    print(f"Using: {csv_file}")

    # Study name
    study_name = input("\nStudy name (e.g. au_gold_miners): ").strip()

    # Number of periods
    while True:
        try:
            n_periods = int(input("\nHow many periods to analyse? (1-3): ").strip())
            if 1 <= n_periods <= 3:
                break
            print("Please enter 1, 2 or 3")
        except:
            print("Please enter a number")

    # Periods
    periods = []
    for i in range(n_periods):
        print(f"\n--- Period {i+1} ---")
        while True:
            date_str = input(f"  Start date (YYYY-MM-DD) or blank for today-63 days: ").strip()
            if date_str == '':
                date_str = (datetime.today() - timedelta(days=91)).strftime('%Y-%m-%d')
                print(f"  Using: {date_str}")
                break
            try:
                entered = datetime.strptime(date_str, '%Y-%m-%d')
                if entered.date() >= datetime.today().date():
                    date_str = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
                    print(f"  Date adjusted to yesterday: {date_str}")
                break
            except:
                print("  Invalid date format — use YYYY-MM-DD")
        reason = input(f"  Label/reason (e.g. gold_peak): ").strip()
        reason = reason.lower().replace(' ', '_')
        periods.append({'date': date_str, 'label': reason})

    # Build results folder name
    period_labels = '_'.join([p['label'] for p in periods])
    results_dir   = f"results/drawdown_analysis/{study_name}_{period_labels}/"

    return csv_file, study_name, periods, results_dir

# ── Calculate drawdown analysis for one period ────────────────────────────────
def calculate_period(prices, volumes, watchlist_df, start_date, label, bench_override=None, weights=None):
    names     = watchlist_df.set_index('ticker')['name']
    sectors   = watchlist_df.set_index('ticker')['sector'].to_dict() if 'sector' in watchlist_df.columns else {}
    commodity = watchlist_df.set_index('ticker')['commodity'].to_dict() if 'commodity' in watchlist_df.columns else {}
    cap_bands = watchlist_df.set_index('ticker')['cap_band'].to_dict()
    benchmarks= watchlist_df.set_index('ticker')['benchmark'].to_dict()

    prices_period = prices[prices.index >= start_date]
    if len(prices_period) < 5:
        print(f"  Warning: only {len(prices_period)} trading days in period from {start_date}")
        return None

    trading_days = len(prices_period)
    print(f"  Period: {start_date} to {prices_period.index[-1].date()} ({trading_days} trading days)")

    # Use bench_override if provided else fall back to watchlist benchmark row
    if bench_override:
        bench_ticker = bench_override
        print(f"  Benchmark: {bench_ticker} (sector/commodity ETF)")
    else:
        bench_row = watchlist_df[watchlist_df['benchmark'] == 'benchmark']
        if len(bench_row) == 0:
            print("  ERROR: No benchmark row found")
            return None
        bench_ticker = bench_row['ticker'].iloc[0]
        print(f"  Benchmark: {bench_ticker}")

    # Fetch benchmark prices if not in prices dataframe
    if bench_ticker not in prices_period.columns:
        import yfinance as yf
        from datetime import datetime, timedelta
        fetch_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        fetch_end   = datetime.today().strftime('%Y-%m-%d')
        print(f"  Fetching benchmark {bench_ticker} prices...")
        bench_raw   = yf.download(bench_ticker, start=fetch_start, end=fetch_end,
                                  auto_adjust=True, progress=False)
        if len(bench_raw) > 0:
            bench_prices_full            = bench_raw['Close'].squeeze()
            prices_period                = prices_period.copy()
            prices_period[bench_ticker]  = bench_prices_full
        else:
            print(f"  ERROR: Could not fetch benchmark {bench_ticker}")
            return None

    if bench_ticker not in prices_period.columns:
        print(f"  ERROR: Benchmark {bench_ticker} not in price data")
        return None

    bench_prices = prices_period[bench_ticker].dropna()
    if len(bench_prices) < 2:
        return None

    # Benchmark metrics
    bench_ret         = round((bench_prices.iloc[-1] / bench_prices.iloc[0] - 1) * 100, 2)
    bench_rolling_max = bench_prices.cummax()
    bench_dd          = round(float(((bench_prices - bench_rolling_max) / bench_rolling_max).min() * 100), 2)

    # Exclude benchmark from universe
    tickers = [t for t in prices_period.columns
               if benchmarks.get(t) != 'benchmark'
               and t != bench_ticker
               and len(prices_period[t].dropna()) >= 2]

    # Pre-calculate period returns for peer RS
    period_returns = {}
    for ticker in tickers:
        tp = prices_period[ticker].dropna()
        if len(tp) >= 2 and tp.iloc[0] != 0:
            period_returns[ticker] = (tp.iloc[-1] / tp.iloc[0] - 1) * 100

    # Group by peer column
    peer_col    = 'commodity' if 'commodity' in watchlist_df.columns else 'sector'
    peer_map    = commodity   if peer_col == 'commodity'             else sectors
    peer_groups = {}
    for ticker in tickers:
        group = peer_map.get(ticker, 'Unknown')
        if group not in peer_groups:
            peer_groups[group] = []
        peer_groups[group].append(ticker)

    results = []
    for ticker in tickers:
        tp = prices_period[ticker].dropna()
        if len(tp) < 2 or tp.iloc[0] == 0:
            continue

        # Period return
        ret_period  = round((tp.iloc[-1] / tp.iloc[0] - 1) * 100, 2)

        # RS vs benchmark
        rs_vs_bench = round(ret_period - bench_ret, 2)

        # Max drawdown in period
        rolling_max  = tp.cummax()
        dd_period    = round(float(((tp - rolling_max) / rolling_max).min() * 100), 2)
        dd_vs_bench  = round(dd_period - bench_dd, 2)

        # Current drawdown from period high
        period_high  = float(tp.max())
        current_dd   = round((tp.iloc[-1] / period_high - 1) * 100, 2)

        # RS trend within period
        n     = len(tp)
        rs_5  = None
        rs_21 = None
        if n >= 5:
            tick_5  = (tp.iloc[-1] / tp.iloc[-5]  - 1) * 100
            bench_5 = (bench_prices.iloc[-1] / bench_prices.iloc[-5]  - 1) * 100 if len(bench_prices) >= 5  else 0
            rs_5    = round(tick_5 - bench_5, 2)
        if n >= 21:
            tick_21  = (tp.iloc[-1] / tp.iloc[-21] - 1) * 100
            bench_21 = (bench_prices.iloc[-1] / bench_prices.iloc[-21] - 1) * 100 if len(bench_prices) >= 21 else 0
            rs_21    = round(tick_21 - bench_21, 2)

        # RS trend direction
        rs_vals = [r for r in [rs_vs_bench, rs_21, rs_5] if r is not None]
        if len(rs_vals) >= 2:
            steps    = [rs_vals[i+1] - rs_vals[i] for i in range(len(rs_vals)-1)]
            up_steps = sum(1 for s in steps if s > 0)
            dn_steps = sum(1 for s in steps if s < 0)
            if up_steps == len(steps):   rs_trend = 'STRONG_UP'
            elif dn_steps == len(steps): rs_trend = 'STRONG_DOWN'
            elif up_steps > dn_steps:    rs_trend = 'UP'
            elif dn_steps > up_steps:    rs_trend = 'DOWN'
            else:                        rs_trend = 'FLAT'
        else:
            rs_trend = 'FLAT'

        # Peer RS score
        group   = peer_map.get(ticker, 'Unknown')
        peers   = [t for t in peer_groups.get(group, []) if t != ticker and t in period_returns]
        if len(peers) > 0:
            outperforms   = sum(1 for t in peers if ret_period > period_returns[t])
            peer_rs_score = round(outperforms / len(peers) * 100, 2)
        else:
            peer_rs_score = 50.0

        # Volume
        if ticker in volumes.columns:
            tv          = volumes[ticker].dropna()
            avg_vol     = tv.tail(63).mean() if len(tv) >= 1 else None
            current_vol = tv.iloc[-1]        if len(tv) >= 1 else None
            rel_vol     = round(current_vol / avg_vol, 4) if avg_vol and avg_vol > 0 else None
            vol_label   = 'HIGH' if rel_vol and rel_vol >= 1.5 else 'MED' if rel_vol and rel_vol >= 1.0 else 'LOW'
        else:
            rel_vol   = None
            vol_label = 'LOW'

        # SMAs from full price history
        prices_full = prices[ticker].dropna() if ticker in prices.columns else tp
        sma200      = round(prices_full.tail(200).mean(), 4) if len(prices_full) >= 200 else None
        pass_trend  = 1 if sma200 is not None and float(tp.iloc[-1]) > sma200 else 0

        # Cap band
        cap_band = cap_bands.get(ticker, 'small')

        # Accumulation watch
        sma20 = round(prices_full.tail(20).mean(), 4) if len(prices_full) >= 20 else None
        sma50 = round(prices_full.tail(50).mean(), 4) if len(prices_full) >= 50 else None
        price = float(tp.iloc[-1])
        if cap_band in ['large', 'mid'] and sma20 and sma50 and sma200:
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

        # Final score — using configurable weights
        score = round(
            (rs_vs_bench   * w_rs_bench) +
            (peer_rs_score * w_peer_rs) +
            (dd_vs_bench   * -w_dd_bench),
            4)

        results.append({
            'ticker'       : ticker,
            'name'         : names.get(ticker, ''),
            peer_col       : group,
            'cap_band'     : cap_band,
            'close'        : round(float(tp.iloc[-1]), 4),
            'ret_period'   : ret_period,
            'bench_ret'    : bench_ret,
            'rs_vs_bench'  : rs_vs_bench,
            'rs_5d'        : rs_5,
            'rs_21d'       : rs_21,
            'rs_trend'     : rs_trend,
            'max_dd_period': dd_period,
            'bench_dd'     : bench_dd,
            'dd_vs_bench'  : dd_vs_bench,
            'current_dd'   : current_dd,
            'peer_rs_score': peer_rs_score,
            'vol_label'    : vol_label,
            'rel_vol'      : rel_vol,
            'acc_watch'    : acc_watch,
            'pass_trend'   : pass_trend,
            'score'        : score,
            'period_label' : label,
            'period_start' : start_date,
            'trading_days' : trading_days,
        })

    df = pd.DataFrame(results)
    df = df.sort_values('score', ascending=False, na_position='last').reset_index(drop=True)
    df.index += 1
    df.index.name = 'rank'
    return df, bench_ret, bench_dd

# ── Save and print results ────────────────────────────────────────────────────
def save_period(df, bench_ret, bench_dd, results_dir, study_name, label, start_date):
    os.makedirs(results_dir, exist_ok=True)
    today    = datetime.today().strftime('%Y%m%d')
    filename = f"{results_dir}{study_name}_{label}_{start_date.replace('-','')}_drawdown.csv"
    df.to_csv(filename)
    print(f"  Saved to {filename}")
    return df

def save_history(all_periods, results_dir, study_name):
    history_file = f"{results_dir}{study_name}_drawdown_history.csv"
    all_df       = pd.concat(all_periods, ignore_index=True)
    all_df.to_csv(history_file, index=False)
    print(f"History saved to {history_file}")
    return all_df

def print_summary(all_periods_data, results_dir, study_name):
    lines = []
    lines.append("═"*80)
    lines.append(f"  DRAWDOWN ANALYSIS — {study_name.upper()}")
    lines.append(f"  Run: {datetime.today().strftime('%d %b %Y %H:%M')}")
    lines.append("═"*80)

    for df, bench_ret, bench_dd, label, start_date in all_periods_data:
        lines.append("")
        lines.append(f"  {'─'*76}")
        lines.append(f"  PERIOD: {label.upper()}  |  From: {start_date}  |  {df['trading_days'].iloc[0]} trading days")
        lines.append(f"  Benchmark return: {bench_ret:+.2f}%   Benchmark max DD: {bench_dd:.2f}%")
        lines.append(f"  {'─'*76}")
        lines.append(f"  {'Rank':<5} {'Ticker':<10} {'Name':<30} {'Ret%':>7} {'vsBench':>8} {'MaxDD':>7} {'DDvBench':>9} {'PeerRS':>7} {'RS Trend':<12} {'AccW':<6}")
        lines.append(f"  {'─'*76}")

        for rank, row in df.head(20).iterrows():
            lines.append(
                f"  {rank:<5} {row['ticker']:<10} {str(row['name'])[:29]:<30} "
                f"{row['ret_period']:>+7.1f}% {row['rs_vs_bench']:>+7.1f}% "
                f"{row['max_dd_period']:>6.1f}% {row['dd_vs_bench']:>+8.1f}% "
                f"{row['peer_rs_score']:>6.1f}% {row['rs_trend']:<12} {row['acc_watch']:<6}"
            )

        lines.append("")
        lines.append(f"  BOTTOM 10 — Weakest vs benchmark:")
        lines.append(f"  {'─'*76}")
        for rank, row in df.tail(10).iterrows():
            lines.append(
                f"  {rank:<5} {row['ticker']:<10} {str(row['name'])[:29]:<30} "
                f"{row['ret_period']:>+7.1f}% {row['rs_vs_bench']:>+7.1f}% "
                f"{row['max_dd_period']:>6.1f}% {row['dd_vs_bench']:>+8.1f}% "
                f"{row['peer_rs_score']:>6.1f}% {row['rs_trend']:<12} {row['acc_watch']:<6}"
            )

    # Cross period rank comparison
    if len(all_periods_data) > 1:
        lines.append("")
        lines.append("═"*80)
        lines.append("  CROSS PERIOD RANK COMPARISON")
        lines.append("═"*80)

        # Build comparison table
        period_dfs = {}
        for df, _, _, label, _ in all_periods_data:
            period_dfs[label] = df[['ticker', 'name', 'score']].rename(
                columns={'score': f'score_{label}'}
            ).reset_index().rename(columns={'rank': f'rank_{label}'})

        first_label = all_periods_data[0][3]
        merged      = period_dfs[first_label]
        for df, _, _, label, _ in all_periods_data[1:]:
            merged = merged.merge(
                period_dfs[label][['ticker', f'rank_{label}', f'score_{label}']],
                on='ticker', how='outer'
            )

        # Calculate trend
        rank_cols = [f'rank_{df[3]}' for df in all_periods_data]
        merged['rank_trend'] = merged.apply(
            lambda row: 'IMPROVING' if all(
                pd.notna(row[rank_cols[i]]) and pd.notna(row[rank_cols[i+1]]) and
                row[rank_cols[i]] > row[rank_cols[i+1]]
                for i in range(len(rank_cols)-1)
            ) else 'DECLINING' if all(
                pd.notna(row[rank_cols[i]]) and pd.notna(row[rank_cols[i+1]]) and
                row[rank_cols[i]] < row[rank_cols[i+1]]
                for i in range(len(rank_cols)-1)
            ) else 'MIXED', axis=1
        )

        merged = merged.sort_values(f'rank_{all_periods_data[-1][3]}')

        header = f"  {'Ticker':<10} {'Name':<25}"
        for df, _, _, label, start in all_periods_data:
            header += f" {label[:8]:>8}"
        header += f" {'Trend':<10}"
        lines.append(header)
        lines.append("─"*80)

        for _, row in merged.head(20).iterrows():
            line = f"  {row['ticker']:<10} {str(row['name'])[:24]:<25}"
            for df, _, _, label, _ in all_periods_data:
                rank_val = row.get(f'rank_{label}', 'n/a')
                line += f" {str(int(rank_val)) if pd.notna(rank_val) else 'n/a':>8}"
            line += f" {row['rank_trend']:<10}"
            lines.append(line)

    lines.append("")
    lines.append("═"*80)

    output   = "\n".join(lines)
    print("\n" + output)
    txt_file = f"{results_dir}{study_name}_drawdown_summary.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"\nSummary saved to {txt_file}")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    start = time.time()

    csv_file, study_name, periods, results_dir = get_inputs()

    # Load data — fetch enough history for all periods
    earliest_date = min(p['date'] for p in periods)
    fetch_start   = (datetime.strptime(earliest_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
    fetch_start_200 = (datetime.today() - timedelta(days=400)).strftime('%Y-%m-%d')
    end_date      = datetime.today().strftime('%Y-%m-%d')

    print(f"\nLoading watchlist from {csv_file}...")
    watchlist = load_watchlist(csv_file)

    print(f"Fetching price data from {fetch_start_200}...")
    prices  = fetch_prices(watchlist, fetch_start_200, end_date)
    volumes = fetch_volumes(watchlist, fetch_start_200, end_date)
 
    # Run each period
    all_periods_data = []
    all_dfs          = []

    for p in periods:
        print(f"\nAnalysing period: {p['label']} from {p['date']}...")
        result = calculate_period(prices, volumes, watchlist, p['date'], p['label'], bench_override=None)
        if result is None:
            print(f"  Skipping period {p['label']} — insufficient data")
            continue
        df, bench_ret, bench_dd = result
        save_period(df, bench_ret, bench_dd, results_dir, study_name, p['label'], p['date'])
        all_periods_data.append((df, bench_ret, bench_dd, p['label'], p['date']))
        all_dfs.append(df.reset_index())

    if all_dfs:
        save_history(all_dfs, results_dir, study_name)
        print_summary(all_periods_data, results_dir, study_name)

    elapsed = time.time() - start
    print(f"\nCompleted in {int(elapsed//60)}m {int(elapsed%60)}s")