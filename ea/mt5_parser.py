import pandas as pd
import re
from io import StringIO

def parse_mt5_report(file_bytes):
    """Parse MT5 HTML trade history report into a DataFrame"""
    # Try UTF-16 first then fallbacks
    for enc in ['utf-16', 'utf-8', 'latin-1', 'cp1252']:
        try:
            text = file_bytes.decode(enc)
            break
        except:
            continue

    rows      = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
    trades    = []
    in_trades = False

    # Column map based on MT5 export format
    COLS = ['open_time','position','symbol','type','comment','volume',
            'open_price','sl','tp','close_time','close_price',
            'commission','swap','profit']

    for row in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip().replace('\xa0','') for c in cells]
        cells = [re.sub(r'\s+', ' ', c).strip() for c in cells]

        # Detect start of trade data
        if cells and cells[0] == 'Time' and len(cells) >= 13:
            in_trades = True
            continue

        if not in_trades:
            continue

        # Stop at summary section
        if cells and any(kw in cells[0] for kw in ['Total Net Profit','Results','Balance','Equity']):
            break

        # Valid trade row — must have open time, position, symbol, type
        if len(cells) >= 14 and re.match(r'\d{4}\.\d{2}\.\d{2}', cells[0]):
            # Skip orders — they have 'placed', 'cancelled', 'expired' as last meaningful cell
            last_cells = [c.lower() for c in cells if c]
            if any(s in last_cells for s in ['placed', 'cancelled', 'expired', 'partial']):
                continue
            # Must have a valid close time in column 9
            if len(cells) < 10 or not re.match(r'\d{4}\.\d{2}\.\d{2}', cells[9]):
                continue
            # Volume field (col 5) for orders contains '0.28 / 0' format — skip these
            if '/' in str(cells[5]):
                continue
            try:
                trade = dict(zip(COLS, cells[:14]))
                trades.append(trade)
            except:
                continue

    if not trades:
        return None

    df = pd.DataFrame(trades)

    # Clean and type convert
    df['open_time']   = pd.to_datetime(df['open_time'],  format='%Y.%m.%d %H:%M:%S', errors='coerce')
    df['close_time']  = pd.to_datetime(df['close_time'], format='%Y.%m.%d %H:%M:%S', errors='coerce')
    df['open_date']   = df['open_time'].dt.date
    df['close_date']  = df['close_time'].dt.date
    df['day_of_week'] = df['open_time'].dt.day_name()
    df['hour']        = df['open_time'].dt.hour
    df['duration_min']= ((df['close_time'] - df['open_time']).dt.total_seconds() / 60).round(1)

    for col in ['volume','open_price','close_price','sl','tp','commission','swap','profit']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(' ','').str.replace(',',''), errors='coerce')

    df['net_profit']  = df['profit'] + df['commission'] + df['swap']
    df['win']         = df['net_profit'] > 0
    df['type']        = df['type'].str.lower()

    # Extract strategy name from comment
    df['strategy'] = df['comment'].apply(extract_strategy)

    return df

def extract_strategy(comment):
    """Extract base strategy name from comment field"""
    if not comment or comment == '':
        return 'Manual'
    # Strip trailing _SYMBOL_N pattern if present
    # e.g. "The Gold Reaper_XAUUSD_6" -> "The Gold Reaper"
    parts = str(comment).split('_')
    # If last part is a number, remove it
    while parts and re.match(r'^\d+$', parts[-1]):
        parts.pop()
    # If last part looks like a symbol (all caps, 3-8 chars), remove it
    if parts and re.match(r'^[A-Z]{3,8}(\.a)?$', parts[-1]):
        parts.pop()
    return '_'.join(parts) if parts else comment

def calc_stats(df):
    """Calculate comprehensive trading statistics for a DataFrame of trades"""
    if df is None or len(df) == 0:
        return {}

    total       = len(df)
    wins        = df[df['win'] == True]
    losses      = df[df['win'] == False]
    win_rate    = round(len(wins) / total * 100, 1) if total > 0 else 0
    gross_profit= round(wins['net_profit'].sum(), 2)
    gross_loss  = round(losses['net_profit'].sum(), 2)
    net_profit  = round(df['net_profit'].sum(), 2)
    profit_factor= round(abs(gross_profit / gross_loss), 2) if gross_loss != 0 else float('inf')
    avg_win     = round(wins['net_profit'].mean(), 2) if len(wins) > 0 else 0
    avg_loss    = round(losses['net_profit'].mean(), 2) if len(losses) > 0 else 0
    rr_ratio    = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else float('inf')
    expectancy  = round((win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss), 2)

    # Consecutive wins/losses
    results          = df.sort_values('close_time')['win'].tolist()
    max_consec_wins  = max_consecutive(results, True)
    max_consec_losses= max_consecutive(results, False)
    avg_consec_wins  = avg_consecutive(results, True)
    avg_consec_losses= avg_consecutive(results, False)

    # Max drawdown on equity curve
    cumulative = df.sort_values('close_time')['net_profit'].cumsum()
    rolling_max= cumulative.cummax()
    drawdown   = cumulative - rolling_max
    max_dd     = round(drawdown.min(), 2)

    # Duration
    avg_duration = round(df['duration_min'].mean(), 1) if 'duration_min' in df.columns else 0
    avg_win_dur  = round(wins['duration_min'].mean(), 1) if len(wins) > 0 else 0
    avg_loss_dur = round(losses['duration_min'].mean(), 1) if len(losses) > 0 else 0

    # Best / worst
    best_trade  = round(df['net_profit'].max(), 2)
    worst_trade = round(df['net_profit'].min(), 2)

    return {
        'total_trades'      : total,
        'win_rate'          : win_rate,
        'net_profit'        : net_profit,
        'gross_profit'      : gross_profit,
        'gross_loss'        : gross_loss,
        'profit_factor'     : profit_factor,
        'avg_win'           : avg_win,
        'avg_loss'          : avg_loss,
        'rr_ratio'          : rr_ratio,
        'expectancy'        : expectancy,
        'max_consec_wins'   : max_consec_wins,
        'max_consec_losses' : max_consec_losses,
        'avg_consec_wins'   : avg_consec_wins,
        'avg_consec_losses' : avg_consec_losses,
        'max_drawdown'      : max_dd,
        'best_trade'        : best_trade,
        'worst_trade'       : worst_trade,
        'avg_duration_min'  : avg_duration,
        'avg_win_duration'  : avg_win_dur,
        'avg_loss_duration' : avg_loss_dur,
        'long_trades'       : len(df[df['type'] == 'buy']),
        'short_trades'      : len(df[df['type'] == 'sell']),
        'long_win_rate'     : round(len(df[(df['type']=='buy') & df['win']]) / len(df[df['type']=='buy']) * 100, 1) if len(df[df['type']=='buy']) > 0 else 0,
        'short_win_rate'    : round(len(df[(df['type']=='sell') & df['win']]) / len(df[df['type']=='sell']) * 100, 1) if len(df[df['type']=='sell']) > 0 else 0,
    }

def max_consecutive(results, target):
    max_c = cur_c = 0
    for r in results:
        if r == target:
            cur_c += 1
            max_c  = max(max_c, cur_c)
        else:
            cur_c  = 0
    return max_c

def avg_consecutive(results, target):
    runs = []
    cur  = 0
    for r in results:
        if r == target:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    return round(sum(runs) / len(runs), 1) if runs else 0