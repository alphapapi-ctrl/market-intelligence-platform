import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from config.breadth.study_us_total_market import config
from data_fetch.breadth.data_fetch_us_total_market import load_watchlist, fetch_prices, fetch_volumes
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

# ── Config ────────────────────────────────────────────────────────────────────
CSV_FILE    = config['csv_file']
RESULTS_DIR = config['results_dir']
STUDY_NAME  = config['name']
END_DATE    = datetime.today().strftime('%Y-%m-%d')
PRICE_HISTORY_DAYS = 400
BACKFILL_DAYS      = 400
START_DATE         = (datetime.today() - timedelta(days=PRICE_HISTORY_DAYS)).strftime('%Y-%m-%d')
BACKFILL_START     = (datetime.today() - timedelta(days=BACKFILL_DAYS)).strftime('%Y-%m-%d')
# Data-quality guards — reject partial fetches instead of writing bad rows
MIN_FETCH_COVERAGE = 0.80   # min share of watchlist tickers with price data
MIN_UNIVERSE_RATIO = 0.90   # min row 'total' vs recent history median (partial
                            # fetches dip well below this; genuine watchlist
                            # drift does not — raise/lower if the universe
                            # legitimately changes size)

# ── Calculate breadth for a specific date ────────────────────────────────────
def calculate_breadth_for_date(prices, volumes, watchlist_df, as_of_date):
    sectors    = watchlist_df.set_index('ticker')['sector'].to_dict()
    industries = watchlist_df.set_index('ticker')['industry'].to_dict() if 'industry' in watchlist_df.columns else {}
    cap_bands  = watchlist_df.set_index('ticker')['cap_band'].to_dict()

    prices_asof  = prices[prices.index <= as_of_date]
    volumes_asof = volumes[volumes.index <= as_of_date]

    if len(prices_asof) < 2:
        return None

    results = []
    tickers = [t for t in prices_asof.columns if len(prices_asof[t].dropna()) >= 2]

    for ticker in tickers:
        tp = prices_asof[ticker].dropna()
        if len(tp) < 2:
            continue

        price   = tp.iloc[-1]
        ret_12m = (tp.iloc[-1] / tp.iloc[0]) - 1 if tp.iloc[0] != 0 else None

        # SMAs
        sma20  = tp.tail(20).mean() if len(tp) >= 20  else None
        sma50  = tp.tail(50).mean() if len(tp) >= 50  else None
        sma200 = tp.tail(200).mean() if len(tp) >= 200 else None

        pass_trend = 1 if sma200 is not None and price > sma200 else 0
        above_20   = 1 if sma20  is not None and price > sma20  else 0
        above_50   = 1 if sma50  is not None and price > sma50  else 0

        # Volume
        if ticker in volumes_asof.columns:
            tv          = volumes_asof[ticker].dropna()
            avg_vol_63  = tv.tail(63).mean() if len(tv) >= 1 else None
            current_vol = tv.iloc[-1] if len(tv) >= 1 else None
            rel_vol     = current_vol / avg_vol_63 if avg_vol_63 and avg_vol_63 > 0 else None
            vol_label   = 'HIGH' if rel_vol and rel_vol >= 1.5 else 'MED' if rel_vol and rel_vol >= 1.0 else 'LOW'
        else:
            vol_label = 'LOW'

        # Acc watch
        cap_band = cap_bands.get(ticker, 'small')
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

        # Volatility
        vol_63 = tp.pct_change().dropna().tail(63).std() * (252 ** 0.5) * 100 if len(tp) >= 63 else None

        # MQS
        daily_returns = tp.pct_change().dropna()
        persist_frac  = (daily_returns > 0).sum() / len(daily_returns) * 100 if len(daily_returns) > 0 else None
        mqs           = (ret_12m * 100 * persist_frac) / vol_63 if vol_63 and vol_63 > 0 and ret_12m is not None and persist_frac is not None else None

        # Sector peer RS
        sec       = sectors.get(ticker, 'Unknown')
        sec_peers = [t for t in tickers if sectors.get(t) == sec and t != ticker]
        sec_returns = [
            (prices_asof[t].dropna().iloc[-1] / prices_asof[t].dropna().iloc[0] - 1)
            for t in sec_peers
            if len(prices_asof[t].dropna()) >= 2 and prices_asof[t].dropna().iloc[0] != 0
        ]
        if ret_12m is not None and len(sec_returns) > 0:
            peer_rs_score = sum(1 for r in sec_returns if ret_12m > r) / len(sec_returns) * 100
        else:
            peer_rs_score = 50.0

        # Regime
        if peer_rs_score >= 75 and pass_trend == 1:
            regime_label = 'LEADER'
        elif peer_rs_score >= 50 and pass_trend == 1:
            regime_label = 'CONTENDER'
        elif peer_rs_score < 50 and pass_trend == 0:
            regime_label = 'WEAK'
        else:
            regime_label = 'LAGGARD'

        results.append({
            'ticker'      : ticker,
            'sector'      : sec,
            'industry'    : industries.get(ticker, ''),
            'cap_band'    : cap_band,
            'pass_trend'  : pass_trend,
            'vol_label'   : vol_label,
            'acc_watch'   : acc_watch,
            'regime_label': regime_label,
            'mqs'         : mqs,
            'above_20'    : above_20,
            'above_50'    : above_50,
        })

    return pd.DataFrame(results)

# ── Calculate breadth metrics from results ────────────────────────────────────
def calc_breadth_metrics(df, as_of_date):
    if df is None or len(df) == 0:
        return None

    total = len(df)
    row   = {'date': as_of_date, 'total': total}

    # ── Layer 1 — Full universe ───────────────────────────────────────────
    for label in ['LEADER', 'CONTENDER', 'LAGGARD', 'WEAK']:
        row[label.lower()] = len(df[df['regime_label'] == label])

    row['above_20']     = len(df[df['above_20']   == 1])
    row['above_50']     = len(df[df['above_50']   == 1])
    row['above_200']    = len(df[df['pass_trend'] == 1])
    row['high_vol']     = len(df[df['vol_label']  == 'HIGH'])
    row['acc_early']    = len(df[df['acc_watch']  == 'EARLY'])
    row['acc_progress'] = len(df[df['acc_watch']  == 'PROGRESS'])
    row['acc_shift']    = len(df[df['acc_watch']  == 'SHIFT'])

    for band in ['large', 'mid', 'small']:
        band_df = df[df['cap_band'] == band]
        row[f'{band}_total']    = len(band_df)
        row[f'{band}_leaders']  = len(band_df[band_df['regime_label'] == 'LEADER'])
        row[f'{band}_above200'] = len(band_df[band_df['pass_trend'] == 1])

    # Layer 1 sector breakdown
    for sector in df['sector'].unique():
        sec_df  = df[df['sector'] == sector]
        sec_key = str(sector).lower().replace(' ', '_').replace('/', '_')
        row[f'sec_{sec_key}_total']    = len(sec_df)
        row[f'sec_{sec_key}_leaders']  = len(sec_df[sec_df['regime_label'] == 'LEADER'])
        row[f'sec_{sec_key}_above20']  = len(sec_df[sec_df['above_20']   == 1])
        row[f'sec_{sec_key}_above50']  = len(sec_df[sec_df['above_50']   == 1])
        row[f'sec_{sec_key}_above200'] = len(sec_df[sec_df['pass_trend'] == 1])
        row[f'sec_{sec_key}_high_vol'] = len(sec_df[sec_df['vol_label']  == 'HIGH'])

    # Layer 1 industry breakdown
    industry_df = df[df['industry'].notna() & (df['industry'] != '')]
    for industry in industry_df['industry'].unique():
        ind_df  = industry_df[industry_df['industry'] == industry]
        ind_key = str(industry).lower().replace(' ', '_').replace('/', '_').replace('&', 'and')
        row[f'ind_{ind_key}_total']    = len(ind_df)
        row[f'ind_{ind_key}_leaders']  = len(ind_df[ind_df['regime_label'] == 'LEADER'])
        row[f'ind_{ind_key}_above200'] = len(ind_df[ind_df['pass_trend']  == 1])

    # ── Layer 2 — SP500/Nasdaq quality (has industry) ─────────────────────
    sp_df = df[df['industry'].notna() & (df['industry'] != '')]
    row['sp_total']     = len(sp_df)
    row['sp_leader']    = len(sp_df[sp_df['regime_label'] == 'LEADER'])
    row['sp_contender'] = len(sp_df[sp_df['regime_label'] == 'CONTENDER'])
    row['sp_laggard']   = len(sp_df[sp_df['regime_label'] == 'LAGGARD'])
    row['sp_weak']      = len(sp_df[sp_df['regime_label'] == 'WEAK'])
    row['sp_above_20']  = len(sp_df[sp_df['above_20']   == 1])
    row['sp_above_50']  = len(sp_df[sp_df['above_50']   == 1])
    row['sp_above_200'] = len(sp_df[sp_df['pass_trend'] == 1])
    row['sp_high_vol']  = len(sp_df[sp_df['vol_label']  == 'HIGH'])
    row['sp_acc_early'] = len(sp_df[sp_df['acc_watch']  == 'EARLY'])

    for band in ['large', 'mid', 'small']:
        band_df = sp_df[sp_df['cap_band'] == band]
        row[f'sp_{band}_total']    = len(band_df)
        row[f'sp_{band}_leaders']  = len(band_df[band_df['regime_label'] == 'LEADER'])
        row[f'sp_{band}_above200'] = len(band_df[band_df['pass_trend'] == 1])

    for sector in sp_df['sector'].unique():
        sec_df  = sp_df[sp_df['sector'] == sector]
        sec_key = str(sector).lower().replace(' ', '_').replace('/', '_')
        row[f'sp_sec_{sec_key}_total']    = len(sec_df)
        row[f'sp_sec_{sec_key}_leaders']  = len(sec_df[sec_df['regime_label'] == 'LEADER'])
        row[f'sp_sec_{sec_key}_above20']  = len(sec_df[sec_df['above_20']   == 1])
        row[f'sp_sec_{sec_key}_above50']  = len(sec_df[sec_df['above_50']   == 1])
        row[f'sp_sec_{sec_key}_above200'] = len(sec_df[sec_df['pass_trend'] == 1])
        row[f'sp_sec_{sec_key}_high_vol'] = len(sec_df[sec_df['vol_label']  == 'HIGH'])

        for industry in sec_df['industry'].unique():
            ind_df  = sec_df[sec_df['industry'] == industry]
            ind_key = str(industry).lower().replace(' ', '_').replace('/', '_').replace('&', 'and')
            row[f'sp_ind_{ind_key}_total']    = len(ind_df)
            row[f'sp_ind_{ind_key}_leaders']  = len(ind_df[ind_df['regime_label'] == 'LEADER'])
            row[f'sp_ind_{ind_key}_above200'] = len(ind_df[ind_df['pass_trend']  == 1])

    # ── Layer 3 — Russell proxy (no industry) ────────────────────────────
    rus_df = df[df['industry'].isna() | (df['industry'] == '')]
    row['rus_total']     = len(rus_df)
    row['rus_leader']    = len(rus_df[rus_df['regime_label'] == 'LEADER'])
    row['rus_contender'] = len(rus_df[rus_df['regime_label'] == 'CONTENDER'])
    row['rus_laggard']   = len(rus_df[rus_df['regime_label'] == 'LAGGARD'])
    row['rus_weak']      = len(rus_df[rus_df['regime_label'] == 'WEAK'])
    row['rus_above_20']  = len(rus_df[rus_df['above_20']   == 1])
    row['rus_above_50']  = len(rus_df[rus_df['above_50']   == 1])
    row['rus_above_200'] = len(rus_df[rus_df['pass_trend'] == 1])
    row['rus_high_vol']  = len(rus_df[rus_df['vol_label']  == 'HIGH'])
    row['rus_acc_early'] = len(rus_df[rus_df['acc_watch']  == 'EARLY'])

    for band in ['large', 'mid', 'small']:
        band_df = rus_df[rus_df['cap_band'] == band]
        row[f'rus_{band}_total']    = len(band_df)
        row[f'rus_{band}_leaders']  = len(band_df[band_df['regime_label'] == 'LEADER'])
        row[f'rus_{band}_above200'] = len(band_df[band_df['pass_trend'] == 1])

    for sector in rus_df['sector'].unique():
        sec_df  = rus_df[rus_df['sector'] == sector]
        sec_key = str(sector).lower().replace(' ', '_').replace('/', '_')
        row[f'rus_sec_{sec_key}_total']    = len(sec_df)
        row[f'rus_sec_{sec_key}_leaders']  = len(sec_df[sec_df['regime_label'] == 'LEADER'])
        row[f'rus_sec_{sec_key}_above20']  = len(sec_df[sec_df['above_20']   == 1])
        row[f'rus_sec_{sec_key}_above50']  = len(sec_df[sec_df['above_50']   == 1])
        row[f'rus_sec_{sec_key}_above200'] = len(sec_df[sec_df['pass_trend'] == 1])
        row[f'rus_sec_{sec_key}_high_vol'] = len(sec_df[sec_df['vol_label']  == 'HIGH'])

    return row

# ── Save breadth history ──────────────────────────────────────────────────────
def save_breadth_history(new_rows, results_dir, study_name):
    os.makedirs(results_dir, exist_ok=True)
    breadth_file = f"{results_dir}{study_name}_breadth_history.csv"

    if os.path.exists(breadth_file):
        history = pd.read_csv(breadth_file)
    else:
        history = pd.DataFrame()

    new_df  = pd.DataFrame(new_rows)

    # Guard — a partial price fetch (rate limit, dropped connection) yields rows
    # covering only a handful of tickers. Those rows read as a breadth collapse
    # on the charts, so drop anything far below the established universe size.
    if len(history) and 'total' in history.columns and 'total' in new_df.columns:
        baseline = pd.to_numeric(history['total'], errors='coerce').tail(60).median()
        if baseline and baseline > 0:
            undersized = pd.to_numeric(new_df['total'], errors='coerce') < baseline * MIN_UNIVERSE_RATIO
            for _, r in new_df[undersized].iterrows():
                print(f"  SKIPPED {r['date']} — only {int(r['total'])} tickers vs "
                      f"baseline {int(baseline)}; partial data fetch, not written")
            new_df = new_df[~undersized]

    if len(new_df) == 0:
        print("No valid rows to save — breadth history left unchanged.")
        return history

    history = pd.concat([history, new_df], ignore_index=True)
    history = history.drop_duplicates(subset=['date'], keep='last')
    history = history.sort_values('date').reset_index(drop=True)
    history.to_csv(breadth_file, index=False)
    print(f"Breadth history saved to {breadth_file}")
    return history

# ── Print and save breadth summary ───────────────────────────────────────────
def print_breadth_summary(history, results_dir, study_name):
    today     = history.iloc[-1]
    today_str = str(today['date'])

    def get_past(days):
        target = pd.Timestamp(today_str) - pd.Timedelta(days=days)
        past   = history[pd.to_datetime(history['date']) <= target]
        return past.iloc[-1] if len(past) > 0 else None

    d5  = get_past(7)
    d20 = get_past(28)
    d63 = get_past(91)

    def fmt(val):
        if val is None:
            return 'n/a'
        return f"+{int(val)}" if val > 0 else str(int(val))

    def delta(key, past):
        if past is None:
            return 'n/a'
        try:
            return fmt(today[key] - past[key])
        except:
            return 'n/a'

    lines = []

    # ── Layer 1 — Full Universe ───────────────────────────────────────────
    lines.append("═"*80)
    lines.append(f"  US MARKET BREADTH — {today_str}")
    lines.append("═"*80)

    lines.append("")
    lines.append("  LAYER 1 — FULL UNIVERSE (1557 tickers)")
    lines.append("─"*80)
    lines.append(f"  {'Metric':<25} {'Today':>8} {'D5':>8} {'D20':>8} {'D63':>8}")
    lines.append("─"*80)

    l1_metrics = [
        ('Total',         'total'),
        ('Leaders',       'leader'),
        ('Contenders',    'contender'),
        ('Laggards',      'laggard'),
        ('Weak',          'weak'),
        ('Above 20 SMA',  'above_20'),
        ('Above 50 SMA',  'above_50'),
        ('Above 200 SMA', 'above_200'),
        ('High Volume',   'high_vol'),
        ('Acc Early',     'acc_early'),
        ('Acc Progress',  'acc_progress'),
        ('Acc Shift',     'acc_shift'),
        ('Large Total',   'large_total'),
        ('Large Leaders', 'large_leaders'),
        ('Mid Total',     'mid_total'),
        ('Mid Leaders',   'mid_leaders'),
        ('Small Total',   'small_total'),
        ('Small Leaders', 'small_leaders'),
    ]

    for label, key in l1_metrics:
        try:
            val = int(today[key])
        except:
            val = 'n/a'
        lines.append(f"  {label:<25} {str(val):>8} {delta(key,d5):>8} {delta(key,d20):>8} {delta(key,d63):>8}")

    lines.append("")
    lines.append("  LAYER 1 SECTOR BREAKDOWN")
    lines.append("─"*80)
    lines.append(f"  {'Sector':<25} {'Lead':>6} {'dL5':>6} {'dL63':>6} {'Ab20':>6} {'dA20_5':>6} {'Ab50':>6} {'dA50_5':>6} {'Ab200':>6} {'dA200_5':>6} {'HVol':>6}")
    lines.append("─"*80)

    sector_cols = [c for c in history.columns if c.startswith('sec_') and c.endswith('_total')
                   and not c.startswith('sp_sec_') and not c.startswith('rus_sec_')]
    for col in sector_cols:
        sec_key  = col.replace('sec_', '').replace('_total', '')
        sec_name = sec_key.replace('_', ' ').title()[:24]
        try:
            leaders  = int(today[f'sec_{sec_key}_leaders'])
            above200 = int(today[f'sec_{sec_key}_above200'])
            high_vol = int(today[f'sec_{sec_key}_high_vol'])
            ab20     = int(today[f'sec_{sec_key}_above20'])
            ab50     = int(today[f'sec_{sec_key}_above50'])
            dl5      = delta(f'sec_{sec_key}_leaders',  d5)
            dl63     = delta(f'sec_{sec_key}_leaders',  d63)
            da5      = delta(f'sec_{sec_key}_above200', d5)
            da20_5   = delta(f'sec_{sec_key}_above20',  d5)
            da50_5   = delta(f'sec_{sec_key}_above50',  d5)
            lines.append(f"  {sec_name:<25} {leaders:>6} {dl5:>6} {dl63:>6} {ab20:>6} {da20_5:>6} {ab50:>6} {da50_5:>6} {above200:>6} {da5:>6} {high_vol:>6}")
        except:
            pass

    # ── Layer 2 — SP500/Nasdaq Quality ────────────────────────────────────
    lines.append("")
    lines.append("═"*80)
    lines.append("  LAYER 2 — SP500/NASDAQ QUALITY (~515 tickers with sector+industry)")
    lines.append("─"*80)
    lines.append(f"  {'Metric':<25} {'Today':>8} {'D5':>8} {'D20':>8} {'D63':>8}")
    lines.append("─"*80)

    l2_metrics = [
        ('Total',         'sp_total'),
        ('Leaders',       'sp_leader'),
        ('Contenders',    'sp_contender'),
        ('Laggards',      'sp_laggard'),
        ('Weak',          'sp_weak'),
        ('Above 20 SMA',  'sp_above_20'),
        ('Above 50 SMA',  'sp_above_50'),
        ('Above 200 SMA', 'sp_above_200'),
        ('High Volume',   'sp_high_vol'),
        ('Acc Early',     'sp_acc_early'),
        ('Large Leaders', 'sp_large_leaders'),
        ('Mid Leaders',   'sp_mid_leaders'),
        ('Small Leaders', 'sp_small_leaders'),
    ]

    for label, key in l2_metrics:
        try:
            val = int(today[key])
        except:
            val = 'n/a'
        lines.append(f"  {label:<25} {str(val):>8} {delta(key,d5):>8} {delta(key,d20):>8} {delta(key,d63):>8}")

    lines.append("")
    lines.append("  LAYER 2 SECTOR BREAKDOWN")
    lines.append("─"*80)
    lines.append(f"  {'Sector':<25} {'Lead':>6} {'dL5':>6} {'dL63':>6} {'Ab20':>6} {'dA20_5':>6} {'Ab50':>6} {'dA50_5':>6} {'Ab200':>6} {'dA200_5':>6} {'HVol':>6}")
    lines.append("─"*80)

    sp_sector_cols = [c for c in history.columns if c.startswith('sp_sec_') and c.endswith('_total')]
    for col in sp_sector_cols:
        sec_key  = col.replace('sp_sec_', '').replace('_total', '')
        sec_name = sec_key.replace('_', ' ').title()[:24]
        try:
            leaders  = int(today[f'sp_sec_{sec_key}_leaders'])
            above200 = int(today[f'sp_sec_{sec_key}_above200'])
            high_vol = int(today[f'sp_sec_{sec_key}_high_vol'])
            ab20     = int(today[f'sp_sec_{sec_key}_above20'])
            ab50     = int(today[f'sp_sec_{sec_key}_above50'])
            dl5      = delta(f'sp_sec_{sec_key}_leaders',  d5)
            dl63     = delta(f'sp_sec_{sec_key}_leaders',  d63)
            da5      = delta(f'sp_sec_{sec_key}_above200', d5)
            da20_5   = delta(f'sp_sec_{sec_key}_above20',  d5)
            da50_5   = delta(f'sp_sec_{sec_key}_above50',  d5)
            lines.append(f"  {sec_name:<25} {leaders:>6} {dl5:>6} {dl63:>6} {ab20:>6} {da20_5:>6} {ab50:>6} {da50_5:>6} {above200:>6} {da5:>6} {high_vol:>6}")
        except:
            pass

    # ── Layer 3 — Russell Proxy ───────────────────────────────────────────
    lines.append("")
    lines.append("═"*80)
    lines.append("  LAYER 3 — RUSSELL PROXY (~1042 tickers, no industry)")
    lines.append("─"*80)
    lines.append(f"  {'Metric':<25} {'Today':>8} {'D5':>8} {'D20':>8} {'D63':>8}")
    lines.append("─"*80)

    l3_metrics = [
        ('Total',         'rus_total'),
        ('Leaders',       'rus_leader'),
        ('Contenders',    'rus_contender'),
        ('Laggards',      'rus_laggard'),
        ('Weak',          'rus_weak'),
        ('Above 20 SMA',  'rus_above_20'),
        ('Above 50 SMA',  'rus_above_50'),
        ('Above 200 SMA', 'rus_above_200'),
        ('High Volume',   'rus_high_vol'),
        ('Acc Early',     'rus_acc_early'),
        ('Large Leaders', 'rus_large_leaders'),
        ('Mid Leaders',   'rus_mid_leaders'),
        ('Small Leaders', 'rus_small_leaders'),
    ]

    for label, key in l3_metrics:
        try:
            val = int(today[key])
        except:
            val = 'n/a'
        lines.append(f"  {label:<25} {str(val):>8} {delta(key,d5):>8} {delta(key,d20):>8} {delta(key,d63):>8}")

    lines.append("")
    lines.append("  LAYER 3 SECTOR BREAKDOWN")
    lines.append("─"*80)
    lines.append(f"  {'Sector':<25} {'Lead':>6} {'dL5':>6} {'dL63':>6} {'Ab20':>6} {'dA20_5':>6} {'Ab50':>6} {'dA50_5':>6} {'Ab200':>6} {'dA200_5':>6} {'HVol':>6}")
    lines.append("─"*80)

    rus_sector_cols = sorted([c for c in history.columns if c.startswith('rus_sec_') and c.endswith('_total')])
    for col in rus_sector_cols:
        sec_key  = col.replace('rus_sec_', '').replace('_total', '')
        sec_name = sec_key.replace('_', ' ').title()[:24]
        try:
            leaders  = int(today[f'rus_sec_{sec_key}_leaders'])
            above200 = int(today[f'rus_sec_{sec_key}_above200'])
            high_vol = int(today[f'rus_sec_{sec_key}_high_vol'])
            ab20     = int(today[f'rus_sec_{sec_key}_above20'])
            ab50     = int(today[f'rus_sec_{sec_key}_above50'])
            dl5      = delta(f'rus_sec_{sec_key}_leaders',  d5)
            dl63     = delta(f'rus_sec_{sec_key}_leaders',  d63)
            da5      = delta(f'rus_sec_{sec_key}_above200', d5)
            da20_5   = delta(f'rus_sec_{sec_key}_above20',  d5)
            da50_5   = delta(f'rus_sec_{sec_key}_above50',  d5)
            lines.append(f"  {sec_name:<25} {leaders:>6} {dl5:>6} {dl63:>6} {ab20:>6} {da20_5:>6} {ab50:>6} {da50_5:>6} {above200:>6} {da5:>6} {high_vol:>6}")
        except:
            pass

    lines.append("═"*80)

    output   = "\n".join(lines)
    print("\n" + output + "\n")
    txt_file = f"{results_dir}{today_str.replace('-','')}_breadth_summary.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"Breadth summary saved to {txt_file}")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    watchlist = load_watchlist(CSV_FILE)

    print("Fetching price data...")
    prices  = fetch_prices(watchlist, START_DATE, END_DATE)
    volumes = fetch_volumes(watchlist, START_DATE, END_DATE)

    # Abort on a partial fetch rather than writing a false breadth collapse
    fetched  = int(prices.notna().any().sum())
    expected = len(watchlist)
    if expected and fetched < expected * MIN_FETCH_COVERAGE:
        raise SystemExit(
            f"ABORT — only {fetched}/{expected} tickers returned price data "
            f"({fetched/expected:.0%}, need {MIN_FETCH_COVERAGE:.0%}). "
            f"Likely a rate limit or network problem. History left unchanged; "
            f"re-run in a few minutes."
        )
    print(f"Coverage: {fetched}/{expected} tickers ({fetched/expected:.0%})")

    # Load existing breadth history
    breadth_file = f"{RESULTS_DIR}{STUDY_NAME}_breadth_history.csv"
    if os.path.exists(breadth_file):
        history        = pd.read_csv(breadth_file)
        existing_dates = set(history['date'].astype(str).tolist())
    else:
        existing_dates = set()

    # Always reprocess last 2 dates to ensure accuracy
    sorted_dates = sorted(existing_dates)
    for d in sorted_dates[-2:]:
        existing_dates.discard(d)

    # Find missing days within backfill window
    all_trading_days = [str(d.date()) for d in prices.index]
    missing_days     = [d for d in all_trading_days if d not in existing_dates and d >= BACKFILL_START]

    if missing_days:
        print(f"Backfilling {len(missing_days)} missing trading days...")
        new_rows = []
        for i, day in enumerate(missing_days):
            print(f"  Processing {day} ({i+1}/{len(missing_days)})...")
            day_df = calculate_breadth_for_date(prices, volumes, watchlist, day)
            row    = calc_breadth_metrics(day_df, day)
            if row:
                new_rows.append(row)
        history = save_breadth_history(new_rows, RESULTS_DIR, STUDY_NAME)
    else:
        print("No missing trading days — breadth history is up to date.")
        history = pd.read_csv(breadth_file)

    print_breadth_summary(history, RESULTS_DIR, STUDY_NAME)