import pandas as pd
import numpy as np
import yfinance as yf
import os
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
BASE         = os.path.dirname(os.path.abspath(__file__))
WATCHLIST    = os.path.join(BASE, 'watchlist', 'us_all_watchlist.csv')
RESULTS_DIR  = os.path.join(BASE, 'results', 'demark')
DAYS_HISTORY       = 200   # daily
DAYS_HISTORY_WEEKLY = 500  # weekly — need ~70+ weekly bars for countdown

# ── DeMark Calculations ───────────────────────────────────────────────────────
def calc_td_setup(close):
    """Calculate TD Setup — 9 consecutive closes vs close 4 bars prior"""
    n        = len(close)
    setup    = np.zeros(n, dtype=int)  # positive = buy bars, negative = sell bars
    buy_seq  = 0
    sell_seq = 0

    for i in range(4, n):
        if close.iloc[i] < close.iloc[i-4]:
            buy_seq  += 1
            sell_seq  = 0
        elif close.iloc[i] > close.iloc[i-4]:
            sell_seq += 1
            buy_seq   = 0
        else:
            buy_seq   = 0
            sell_seq  = 0
        setup[i] = buy_seq if buy_seq > 0 else -sell_seq

    return pd.Series(setup, index=close.index)

def calc_td_countdown(close, setup):
    """Calculate TD Countdown 13 — simplified version using close vs close 2 bars prior"""
    n            = len(close)
    countdown    = np.zeros(n, dtype=int)
    buy_count    = 0
    sell_count   = 0
    in_buy_cd    = False
    in_sell_cd   = False

    for i in range(2, n):
        # Start buy countdown after completed buy setup (setup == 9)
        if setup.iloc[i] == 9:
            in_buy_cd  = True
            buy_count  = 0
        # Start sell countdown after completed sell setup (setup == -9)
        if setup.iloc[i] == -9:
            in_sell_cd  = True
            sell_count  = 0

        # Cancel countdown if opposing setup completes
        if setup.iloc[i] == 9 and in_sell_cd:
            in_sell_cd = False
            sell_count = 0
        if setup.iloc[i] == -9 and in_buy_cd:
            in_buy_cd = False
            buy_count = 0

        if in_buy_cd and close.iloc[i] < close.iloc[i-2]:
            buy_count += 1
            if buy_count >= 13:
                countdown[i] = 13
                in_buy_cd    = False
                buy_count    = 0
            else:
                countdown[i] = buy_count

        if in_sell_cd and close.iloc[i] > close.iloc[i-2]:
            sell_count += 1
            if sell_count >= 13:
                countdown[i] = -13
                in_sell_cd   = False
                sell_count   = 0
            else:
                countdown[i] = -sell_count

    return pd.Series(countdown, index=close.index)

def check_signals(close):
    """Return signal dict for a price series"""
    if len(close) < 50:
        return None

    setup    = calc_td_setup(close)
    countdown= calc_td_countdown(close, setup)

    last_setup     = setup.iloc[-1]
    last_countdown = countdown.iloc[-1]

    signals = {
        'setup9_buy'    : last_setup == 9,
        'setup9_sell'   : last_setup == -9,
        'countdown13_buy' : last_countdown == 13,
        'countdown13_sell': last_countdown == -13,
        'setup_val'     : int(last_setup),
        'countdown_val' : int(last_countdown),
    }
    return signals

# [with]
def run_scan(market_cap_min=0, market_cap_max=None, end_date=None):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    if end_date is None:
        end_date = datetime.today().strftime('%Y-%m-%d')

    today      = datetime.strptime(end_date, '%Y-%m-%d').strftime('%Y%m%d')
    start_date        = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=DAYS_HISTORY)).strftime('%Y-%m-%d')
    start_date_weekly = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=DAYS_HISTORY_WEEKLY)).strftime('%Y-%m-%d')

    # Load watchlist
    wl = pd.read_csv(WATCHLIST)
    wl.columns = wl.columns.str.strip()
    wl['ticker'] = wl['ticker'].str.strip()

    # Filter benchmark row
    wl = wl[wl['benchmark'] != 'benchmark'].copy()

    # Filter by market cap
    wl['market_cap'] = pd.to_numeric(wl['market_cap'], errors='coerce')
    if market_cap_min > 0:
        wl = wl[wl['market_cap'] >= market_cap_min]
    if market_cap_max:
        wl = wl[wl['market_cap'] <= market_cap_max]

    tickers = wl['ticker'].tolist()
    print(f"Scanning {len(tickers)} tickers...")

    try:
        raw_daily = yf.download(tickers, start=start_date, end=end_date,
                                auto_adjust=True, progress=True)
        raw_weekly_raw = yf.download(tickers, start=start_date_weekly, end=end_date,
                                     auto_adjust=True, progress=False)

        # Handle MultiIndex
        if isinstance(raw_daily.columns, pd.MultiIndex):
            close_daily = raw_daily['Close']
        else:
            close_daily = raw_daily

        if isinstance(raw_weekly_raw.columns, pd.MultiIndex):
            close_weekly_daily = raw_weekly_raw['Close']
        else:
            close_weekly_daily = raw_weekly_raw

        if isinstance(close_daily.columns, pd.MultiIndex):
            close_daily.columns = close_daily.columns.get_level_values(-1)
        if isinstance(close_weekly_daily.columns, pd.MultiIndex):
            close_weekly_daily.columns = close_weekly_daily.columns.get_level_values(-1)

        close_weekly = close_weekly_daily.resample('W-FRI').last().dropna(how='all')

        print(f"Daily shape: {close_daily.shape}")
        print(f"Weekly shape: {close_weekly.shape}")

    except Exception as e:
        print(f"Download error: {e}")
        return None, None

    # Build ticker info lookup
    ticker_info = wl.set_index('ticker')[['name','sector','cap_band','market_cap']].to_dict('index')

    results = []

    for ticker in tickers:
        if ticker not in close_daily.columns:
            continue

        daily_close  = close_daily[ticker].dropna()
        weekly_close = close_weekly[ticker].dropna() if ticker in close_weekly.columns else pd.Series(dtype=float)
        
        if len(weekly_close) < 15:
            print(f"{ticker}: insufficient weekly bars ({len(weekly_close)})")
            weekly_sig = None
        else:
            weekly_sig = check_signals(weekly_close)
        
        daily_sig    = check_signals(daily_close)  if len(daily_close)  >= 50 else None
        weekly_sig   = check_signals(weekly_close) if len(weekly_close) >= 15 else None  # reduce from 20

        if daily_sig is None and weekly_sig is None:
            continue

        info    = ticker_info.get(ticker, {})
        mkt_cap = info.get('market_cap', None)

        row = {
            'ticker'            : ticker,
            'name'              : info.get('name', ''),
            'sector'            : info.get('sector', ''),
            'cap_band'          : info.get('cap_band', ''),
            'market_cap'        : mkt_cap,
            'market_cap_b'      : round(mkt_cap / 1e9, 2) if pd.notna(mkt_cap) and mkt_cap else None,
        }

        if daily_sig:
            row.update({
                'd_setup'          : daily_sig['setup_val'],
                'd_countdown'      : daily_sig['countdown_val'],
                'd_setup9_buy'     : daily_sig['setup9_buy'],
                'd_setup9_sell'    : daily_sig['setup9_sell'],
                'd_cd13_buy'       : daily_sig['countdown13_buy'],
                'd_cd13_sell'      : daily_sig['countdown13_sell'],
            })
        else:
            row.update({'d_setup': 0, 'd_countdown': 0, 'd_setup9_buy': False,
                        'd_setup9_sell': False, 'd_cd13_buy': False, 'd_cd13_sell': False})

        if weekly_sig:
            row.update({
                'w_setup'          : weekly_sig['setup_val'],
                'w_countdown'      : weekly_sig['countdown_val'],
                'w_setup9_buy'     : weekly_sig['setup9_buy'],
                'w_setup9_sell'    : weekly_sig['setup9_sell'],
                'w_cd13_buy'       : weekly_sig['countdown13_buy'],
                'w_cd13_sell'      : weekly_sig['countdown13_sell'],
            })
        else:
            row.update({'w_setup': 0, 'w_countdown': 0, 'w_setup9_buy': False,
                        'w_setup9_sell': False, 'w_cd13_buy': False, 'w_cd13_sell': False})

        results.append(row)

    df = pd.DataFrame(results)
    if df.empty:
        print("No results")
        return None, None

    # Save CSV
    csv_file = os.path.join(RESULTS_DIR, f"{today}_demark.csv")
    df.to_csv(csv_file, index=False)
    print(f"Saved: {csv_file}")

    # Build report
    def ticker_list(mask):
        return ','.join(sorted(df[mask]['ticker'].tolist()))

    report = f"""{'═'*70}
  DEMARK SIGNAL REPORT — {datetime.today().strftime('%d %b %Y')}
  Universe: {len(df)} stocks scanned
{'═'*70}

DM9 Top Daily:
{ticker_list(df['d_setup9_sell'])}

DM9 Bottom Daily:
{ticker_list(df['d_setup9_buy'])}

DM9 Top Weekly:
{ticker_list(df['w_setup9_sell'])}

DM9 Bottom Weekly:
{ticker_list(df['w_setup9_buy'])}

DM13 Top Daily:
{ticker_list(df['d_cd13_sell'])}

DM13 Bottom Daily:
{ticker_list(df['d_cd13_buy'])}

DM13 Top Weekly:
{ticker_list(df['w_cd13_sell'])}

DM13 Bottom Weekly:
{ticker_list(df['w_cd13_buy'])}

{'═'*70}
"""

    report_file = os.path.join(RESULTS_DIR, f"{today}_demark_report.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Report: {report_file}")
    print(report)

    return df, report

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run_scan()