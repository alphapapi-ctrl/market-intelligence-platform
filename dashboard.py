import streamlit as st
import pandas as pd
import os
import subprocess
from datetime import datetime, timedelta
import glob
from streamlit_option_menu import option_menu
import json

# ── Theme helpers ─────────────────────────────────────────────────────────────
import re as _re

def _get_theme_mode():
    """Read .streamlit/config.toml and return 'light' or 'dark'.
    Falls back to dashboard_settings.json theme key, then 'light' as default."""
    cfg_file = os.path.join(BASE, '.streamlit', 'config.toml')
    if os.path.isfile(cfg_file):
        try:
            text = open(cfg_file).read()
            m = _re.search(r'base\s*=\s*"([^"]*)"', text)
            if m:
                return m.group(1).lower()
        except:
            pass
    try:
        s = json.load(open(SETTINGS_FILE))
        return s.get('theme', 'light')
    except:
        pass
    return 'light'

def get_chart_theme():
    """Return plotly colour dict matching current theme."""
    mode = _get_theme_mode()
    if mode == 'light':
        return {
            'plot_bgcolor' : 'rgba(245,245,248,1)',
            'paper_bgcolor': 'rgba(245,245,248,1)',
            'gridcolor'    : 'rgba(0,0,0,0.08)',
            'font_color'   : '#1a1a1a',
        }
    return {
        'plot_bgcolor' : 'rgba(15,15,25,1)',
        'paper_bgcolor': 'rgba(15,15,25,1)',
        'gridcolor'    : 'rgba(255,255,255,0.05)',
        'font_color'   : 'white',
    }

def _write_streamlit_config(theme_dict):
    """Write .streamlit/config.toml with given theme."""
    cfg_dir = os.path.join(BASE, '.streamlit')
    os.makedirs(cfg_dir, exist_ok=True)
    lines = ['[theme]\n']
    for k, v in theme_dict.items():
        lines.append(f'{k} = "{v}"\n')
    with open(os.path.join(cfg_dir, 'config.toml'), 'w') as f:
        f.writelines(lines)

THEMES = {
    'Dark': {
        'base'                    : 'dark',
        'primaryColor'            : '#1a3a5c',
        'backgroundColor'         : '#0e1117',
        'secondaryBackgroundColor': '#1a1f2e',
        'textColor'               : '#fafafa',
        'font'                    : 'sans serif',
    },
    'Light': {
        'base'                    : 'light',
        'primaryColor'            : '#1a3a5c',
        'backgroundColor'         : '#ffffff',
        'secondaryBackgroundColor': '#f0f2f6',
        'textColor'               : '#1a1a1a',
        'font'                    : 'sans serif',
    },
}


# ── Config ────────────────────────────────────────────────────────────────────
BASE    = os.path.dirname(os.path.abspath(__file__))
MACRO   = os.path.join(BASE, 'macro')
STOCKS  = os.path.join(BASE, 'stocks')
PYTHON  = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')

st.set_page_config(
    page_title   = "Market Intelligence",
    page_icon    = "📊",
    layout       = "wide",
    initial_sidebar_state = "collapsed"
)

STATUS_COLOURS = {
    'FIRED'    : 'background-color: rgba(0,180,0,0.25); color: #2dc653; font-weight: bold',
    'WATCHING' : 'background-color: rgba(255,180,0,0.20); color: #f77f00; font-weight: bold',
    'STRONG'   : 'background-color: rgba(0,120,255,0.20); color: #4da6ff; font-weight: bold',
    'OVERSOLD' : 'background-color: rgba(180,0,0,0.20); color: #e63946; font-weight: bold',
    'INACTIVE' : '',
}

st.markdown("""
    <style>
    thead tr th { color: #1a1a2e !important; font-weight: 600 !important; }
    [data-testid="stDataFrame"] th { color: #1a1a2e !important; font-weight: 600 !important; }
    .info-card {
        background: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
        font-size: 13px;
        color: inherit;
        line-height: 1.7;
    }
    .macro-card {
        background: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }
    .macro-label  { color: #888; font-size: 10px; }
    .macro-value  { font-size: 15px; font-weight: bold; }
    .macro-signal { font-size: 10px; }
    </style>
""", unsafe_allow_html=True)

# ── Page Settings  ────────────────────────────────────────────────────────────────────
SETTINGS_FILE = os.path.join(BASE, 'dashboard_settings.json')

DEFAULT_SETTINGS = {
    'theme': 'light',
    'pages': {
        'Macro'               : True,
        'Debt Markets'        : True,
        'AU Market'           : True,
        'US Market'           : True,
        'Commodities'         : True,
        'Uranium'             : True,
        'AU Gold Miners'      : True,
        'RRG Charts'          : True,
        'Breadth RRG'         : True,
        'Drawdown Analysis'   : True,
        'Actionable & Exports': True,
        'DeMark Signals'      : True,
        'Run Scripts'         : True,
        'Settings'            : True,
    },
    'ai_features': {
        'enabled'          : False,
        'anthropic_api_key': '',
        'model'            : 'claude-sonnet-4-6',
    }
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                merged['pages'].update(saved.get('pages', {}))
                merged['ai_features'].update(saved.get('ai_features', {}))
                if 'theme' in saved:
                    merged['theme'] = saved['theme']
                return merged
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ── Horizontal top menu ───────────────────────────────────────────────────────
settings    = load_settings()
page_config = settings['pages']

ALL_PAGES = [
    ("Macro",                "globe"),
    ("Debt Markets",          "credit-card"),
    ("AU Market",            "flag"),
    ("US Market",            "flag"),
    ("Commodities",          "hammer"),
    ("Uranium",              "radioactive"),
    ("AU Gold Miners",       "star"),
    ("RRG Charts",           "broadcast"),
    ("Breadth RRG",          "grid-3x3"),
    ("Drawdown Analysis",    "graph-down"),
    ("Actionable & Exports", "file-earmark-arrow-down"),
    ("DeMark Signals",       "graph-up"),
    ("Run Scripts",          "play-circle"),
    ("Settings",             "gear"),
]

# Filter to enabled pages — Settings always shown
active_pages = [(name, icon) for name, icon in ALL_PAGES
                if page_config.get(name, True) or name == 'Settings']

page = option_menu(
    menu_title  = None,
    options     = [p[0] for p in active_pages],
    icons       = [p[1] for p in active_pages],
    default_index = 0,
    orientation = "horizontal",
    styles      = {
        "container"        : {"padding": "0!important", "background-color": "#2c3e50"},
        "icon"             : {"color": "#b0bec5", "font-size": "13px"},
        "nav-link"         : {"font-size": "12px", "text-align": "center", "margin": "0px",
                              "color": "#ecf0f1", "--hover-color": "#34495e"},
        "nav-link-selected": {"background-color": "#1a3a5c", "color": "white"},
    }
)

# ── Updated timestamp ─────────────────────────────────────────────────────────
st.caption(f"Market Intelligence — {datetime.now().strftime('%d %b %Y %H:%M')}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def format_screener_df(df, cols):
    formatted = df[cols].copy()
    for col in ['close','rs_ratio']:
        if col in formatted.columns:
            formatted[col] = pd.to_numeric(
                formatted[col].astype(str).str.replace(',',''), errors='coerce'
            ).round(2)
    for col in ['peer_rs_score']:
        if col in formatted.columns:
            formatted[col] = pd.to_numeric(formatted[col], errors='coerce').round(0).astype('Int64')
    for col in ['ret_6m','ret_12m','max_dd']:
        if col in formatted.columns:
            formatted[col] = pd.to_numeric(
                formatted[col].astype(str).str.replace('%',''), errors='coerce'
            ).round(0).apply(lambda x: f"{int(x)}%" if pd.notna(x) else '')
    for col in ['score_final']:
        if col in formatted.columns:
            formatted[col] = pd.to_numeric(formatted[col], errors='coerce').round(0).astype('Int64')
    return formatted

def load_csv(path, **kwargs):
    try:
        if os.path.exists(path):
            return pd.read_csv(path, **kwargs)
    except Exception as e:
        st.error(f"Error loading {path}: {e}")
    return None

def load_txt(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    except:
        pass
    return None

def latest_file(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None

def file_age(path):
    if os.path.exists(path):
        modified = datetime.fromtimestamp(os.path.getmtime(path))
        diff     = datetime.now() - modified
        hours    = int(diff.total_seconds() // 3600)
        mins     = int((diff.total_seconds() % 3600) // 60)
        if hours > 0:
            return f"{hours}h {mins}m ago"
        return f"{mins}m ago"
    return "not found"

def run_script(script_path, cwd):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    with st.spinner(f"Running {os.path.basename(script_path)}..."):
        result = subprocess.run(
            [PYTHON, script_path],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
    if result.returncode == 0:
        st.success("✓ Completed successfully")
    else:
        st.error(f"✗ Failed\n{result.stderr[-500:]}")
    return result.returncode == 0

def colour_regime(val):
    colours = {
        'TREND+LEAD' : 'background-color: #1a472a; color: white',
        'LEADER'     : 'background-color: #1a472a; color: white',
        'TREND_ONLY' : 'background-color: #2d5a27; color: white',
        'CONTENDER'  : 'background-color: #2d5a27; color: white',
        'LAGGARD'    : 'background-color: #5a4000; color: white',
        'WEAK'       : 'background-color: #5a0000; color: white',
    }
    return colours.get(str(val), '')

def colour_delta(val):
    try:
        v = float(val)
        if v > 0:   return 'color: #00cc44'
        if v < 0:   return 'color: #ff4444'
    except:
        pass
    return ''

def style_df(df, regime_col=None, delta_col=None):
    styler = df.style
    if regime_col and regime_col in df.columns:
        styler = styler.map(colour_regime, subset=[regime_col])
    if delta_col and delta_col in df.columns:
        styler = styler.map(colour_delta, subset=[delta_col])
    return styler

#── Drawdown Tool helpers  ─────────────────────────────────────────────────────
def format_drawdown_df(df, cols):
    formatted = df[cols].copy()
    pct_cols  = ['ret_period','bench_ret','rs_vs_bench','max_dd_period',
                 'dd_vs_bench','peer_rs_score','current_dd']
    num_cols  = ['score']
    for col in pct_cols:
        if col in formatted.columns:
            formatted[col] = formatted[col].apply(
                lambda x: f"{x:+.0f}%" if pd.notna(x) else '')
    for col in num_cols:
        if col in formatted.columns:
            formatted[col] = formatted[col].apply(
                lambda x: f"{x:.1f}" if pd.notna(x) else '')
    return formatted

# ── Breadth table helpers ─────────────────────────────────────────────────────
def get_past_row(history, today_str, days):
    target = pd.Timestamp(today_str) - pd.Timedelta(days=days)
    past   = history[pd.to_datetime(history['date']) <= target]
    return past.iloc[-1] if len(past) > 0 else None

def delta_val(today_row, past_row, key):
    try:
        d = int(today_row[key]) - int(past_row[key])
        return f"+{d}" if d > 0 else str(d)
    except:
        return 'n/a'

def build_breadth_table(history, metrics, label=''):
    if history is None or len(history) == 0:
        return None

    today     = history.iloc[-1]
    today_str = str(today['date'])
    d5        = get_past_row(history, today_str, 7)
    d20       = get_past_row(history, today_str, 28)
    d63       = get_past_row(history, today_str, 91)

    def pct(num, denom):
        try:
            return round(int(num) / int(denom) * 100, 1) if int(denom) > 0 else 0
        except:
            return 0

    def delta(key, past):
        try:
            d = int(today[key]) - int(past[key])
            return f"+{d}" if d > 0 else str(d)
        except:
            return 'n/a'

    total = int(today['total']) if 'total' in today.index else 1

    # Columns that should show as % of total
    pct_keys = pct_keys = ['above_20','above_50','above_200',
                'sp_above_20','sp_above_50','sp_above_200',
                'rus_above_20','rus_above_50','rus_above_200',
                'large_above20','large_above50','large_above200',
                'mid_above20','mid_above50','mid_above200',
                'small_above20','small_above50','small_above200']

    rows = []
    for display_name, key in metrics:
        try:
            val = int(today[key])
        except:
            continue

        if key in pct_keys:
            today_val = f"{pct(val, total)}%"
        else:
            today_val = str(val)

        rows.append({
            'Metric' : display_name,
            'Today'  : today_val,
            'D5'     : delta(key, d5)  if d5  is not None else 'n/a',
            'D20'    : delta(key, d20) if d20 is not None else 'n/a',
            'D63'    : delta(key, d63) if d63 is not None else 'n/a',
        })
    return pd.DataFrame(rows)

def sector_breadth_caption():
    st.markdown("""
        <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#888;
                    margin-bottom:6px;padding:6px 4px">
            <span><b style="color:#ccc">Total</b> — stocks in sector</span>
            <span><b style="color:#ccc">Leaders</b> — LEADER/CONTENDER regime count</span>
            <span><b style="color:#ccc">dL5/dL63</b> — change in leaders over 5/63 days</span>
            <span><b style="color:#ccc">Ab20%</b> — % of sector above 20 SMA</span>
            <span><b style="color:#ccc">Ab50%</b> — % of sector above 50 SMA</span>
            <span><b style="color:#ccc">Ab200%</b> — % of sector above 200 SMA</span>
            <span><b style="color:#ccc">HVol</b> — stocks with HIGH relative volume</span>
        </div>
    """, unsafe_allow_html=True)

def build_sector_table(history, sector_keys, prefix='sec'):
    if history is None or len(history) == 0:
        return None

    today     = history.iloc[-1]
    today_str = str(today['date'])
    d1        = get_past_row(history, today_str, 1)   # add 1-day lookback
    d5        = get_past_row(history, today_str, 7)
    d63       = get_past_row(history, today_str, 91)

    def pct(num, denom):
        try:
            return round(int(num) / int(denom) * 100, 1) if int(denom) > 0 else 0
        except:
            return 0

    def delta(key, past):
        try:
            d = int(today[key]) - int(past[key])
            return f"+{d}" if d > 0 else str(d)
        except:
            return 'n/a'

    def ab_cell(above, total, above_key, total_key):
        """Return pct value with 1-day arrow and delta"""
        try:
            today_pct = pct(above, total)
            if d1 is not None:
                prev_pct  = pct(int(d1[above_key]), int(d1[total_key]))
                diff      = round(today_pct - prev_pct, 1)
                if diff > 0:
                    arrow = '▲'
                    sign  = '+'
                elif diff < 0:
                    arrow = '▼'
                    sign  = ''
                else:
                    arrow = '→'
                    sign  = ''
                return f"{today_pct}% {arrow}{sign}{diff}%"
            return f"{today_pct}%"
        except:
            return f"{pct(above, total)}%"

    rows = []
    for sec_key in sector_keys:
        try:
            total_key  = f'{prefix}_{sec_key}_total'
            above20_key= f'{prefix}_{sec_key}_above20'
            above50_key= f'{prefix}_{sec_key}_above50'
            above200_key=f'{prefix}_{sec_key}_above200'
            hvol_key   = f'{prefix}_{sec_key}_high_vol'

            total   = int(today[total_key])
            leaders = int(today[f'{prefix}_{sec_key}_leaders'])
            above20 = int(today.get(above20_key, 0))
            above50 = int(today.get(above50_key, 0))
            above200= int(today[above200_key])
            high_vol= int(today.get(hvol_key, 0))

            rows.append({
                'Sector'  : sec_key.replace('_', ' ').replace('-', ' ').title(),
                'Total'   : total,
                'Leaders' : leaders,
                'dL5'     : delta(f'{prefix}_{sec_key}_leaders', d5)  if d5  is not None else 'n/a',
                'dL63'    : delta(f'{prefix}_{sec_key}_leaders', d63) if d63 is not None else 'n/a',
                'Ab20%'   : ab_cell(above20,  total, above20_key,  total_key),
                'Ab50%'   : ab_cell(above50,  total, above50_key,  total_key),
                'Ab200%'  : ab_cell(above200, total, above200_key, total_key),
                'HVol'    : high_vol,
            })
        except:
            continue

    return pd.DataFrame(rows) if rows else None

def style_breadth(df, pct_cols=None, delta_cols=None):
    # Convert all columns to object type to prevent pyarrow type inference issues
    df = df.copy().astype(object)

    def colour_delta(val):
        try:
            v = int(str(val).replace('+',''))
            if v > 0:  return 'background-color: rgba(0,180,0,0.12); color: #00cc44'
            if v < 0:  return 'background-color: rgba(180,0,0,0.12); color: #ff4444'
        except:
            pass
        return ''

    def colour_ab_pct(val):
        try:
            v = float(str(val).split('%')[0].split(' ')[0].replace('+','').replace('▲','').replace('▼','').strip())
            if v >= 70: return 'background-color: rgba(0,180,0,0.15)'
            if v >= 40: return 'background-color: rgba(255,180,0,0.15)'
            if v >= 20: return 'background-color: rgba(180,0,0,0.15)'
            return 'background-color: rgba(148,0,211,0.15)'
        except:
            pass
        return ''

    styler = df.style
    if delta_cols:
        for col in delta_cols:
            if col in df.columns:
                styler = styler.map(colour_delta, subset=[col])

    ab_cols = [c for c in df.columns if c.startswith('Ab') and '%' in c]
    for col in ab_cols:
        if col in df.columns:
            styler = styler.map(colour_ab_pct, subset=[col])

    return styler

# ── Zweig Breadth Thrust ──────────────────────────────────────────────────────

def build_benchmark_ai_prompt(df, market_label, group_col='sector'):
    """Build AI prompt from benchmark DataFrame for rotation analysis."""
    if df is None or len(df) == 0:
        return None
    try:
        total    = len(df)
        leaders  = len(df[df['regime_label'].isin(['TREND+LEAD','LEADER'])])
        trend    = len(df[df['regime_label'].isin(['TREND_ONLY','CONTENDER'])])
        weak     = len(df[df['regime_label'] == 'WEAK'])
        strong_up = len(df[df.get('rs_trend', pd.Series()).isin(['STRONG_UP'])]) if 'rs_trend' in df.columns else 0

        # Top 10 movers by score
        score_col = 'score_final' if 'score_final' in df.columns else None
        if score_col:
            top10 = df.head(10)[['ticker','name', group_col, 'regime_label','rs_trend']].values.tolist() if group_col in df.columns else df.head(10)[['ticker','name','regime_label','rs_trend']].values.tolist()
            top10_str = ', '.join([f"{r[0]} ({r[2] if len(r)>2 else ''}/{r[-1]})" for r in top10])
        else:
            top10_str = 'n/a'

        # Delta rank movers — biggest climbers
        if 'delta_rank' in df.columns:
            df_copy = df.copy()
            df_copy['delta_rank_num'] = pd.to_numeric(df_copy['delta_rank'].astype(str).str.replace('+',''), errors='coerce')
            if 'rs_ratio' in df_copy.columns:
                df_copy['rs_ratio_num'] = pd.to_numeric(df_copy['rs_ratio'], errors='coerce')
                climbers_pool = df_copy[df_copy['rs_ratio_num'] > 0.8]
                fallers_pool  = df_copy[df_copy['rs_ratio_num'] < 1.2]
            else:
                climbers_pool = fallers_pool = df_copy
            climbers = climbers_pool.nlargest(5, 'delta_rank_num')[['ticker', group_col if group_col in df_copy.columns else 'ticker', 'delta_rank']].values.tolist()
            fallers  = fallers_pool.nsmallest(5, 'delta_rank_num')[['ticker', group_col if group_col in df_copy.columns else 'ticker', 'delta_rank']].values.tolist()
            climbers_str = ', '.join([f"{r[0]} {r[2]}" for r in climbers])
            fallers_str  = ', '.join([f"{r[0]} {r[2]}" for r in fallers])
        else:
            climbers_str = fallers_str = 'n/a'

        # Sector/commodity rotation
        if group_col in df.columns:
            grp = df.groupby(group_col).agg(
                total   = ('regime_label', 'count'),
                leaders = ('regime_label', lambda x: x.isin(['TREND+LEAD','LEADER']).sum()),
            ).reset_index()
            grp['pct'] = (grp['leaders'] / grp['total'] * 100).round(1)
            grp = grp.sort_values('pct', ascending=False)
            top_grp = grp.head(3)[[group_col,'leaders','total','pct']].values.tolist()
            bot_grp = grp.tail(3)[[group_col,'leaders','total','pct']].values.tolist()
            top_grp_str = ', '.join([f"{r[0]} ({r[1]}/{r[2]}, {r[3]}%)" for r in top_grp])
            bot_grp_str = ', '.join([f"{r[0]} ({r[1]}/{r[2]}, {r[3]}%)" for r in bot_grp])
        else:
            top_grp_str = bot_grp_str = 'n/a'

        prompt = f"""You are a quantitative equity analyst specialising in relative strength rotation.
Analyse this {market_label} benchmark ranking data and provide a 5-6 sentence assessment covering:
(1) Overall market regime health, (2) Sector/group rotation — which are leading and lagging,
(3) Notable individual movers — both climbers and fallers in rank,
(4) Accumulation watch signals if any (stocks below SMAs with improving momentum),
(5) Key risks or divergences worth monitoring.
Be specific — name tickers and sectors. Avoid generic commentary.

Universe: {total} stocks | Leaders/Trend+Lead: {leaders} ({round(leaders/total*100,1)}%) | Trend Only: {trend} | Weak: {weak} ({round(weak/total*100,1)}%) | Strong RS Up: {strong_up}
Top 10 by score: {top10_str}
Biggest rank climbers (5d): {climbers_str}
Biggest rank fallers (5d): {fallers_str}
Leading {group_col}s: {top_grp_str}
Lagging {group_col}s: {bot_grp_str}"""
        return prompt
    except Exception as e:
        return None

def calc_zweig_thrust(advancing_series, declining_series, lookback=252):
    """
    Calculate Zweig Breadth Thrust from advancing and declining issue counts.
    Returns dict with current status, EMA history, and historical signal dates.
    
    advancing_series: pd.Series of advancing issue counts indexed by date
    declining_series: pd.Series of declining issue counts indexed by date
    lookback: number of days of history to use
    """
    import pandas as pd
    import numpy as np

    if advancing_series is None or declining_series is None:
        return None
    if len(advancing_series) < 15 or len(declining_series) < 15:
        return None

    # Align and calculate ratio
    df = pd.DataFrame({
        'adv': advancing_series,
        'dec': declining_series,
    }).dropna()

    if len(df) < 15:
        return None

    df = df.tail(lookback)
    df['total'] = df['adv'] + df['dec']
    df['ratio'] = df.apply(
        lambda r: r['adv'] / r['total'] if r['total'] > 0 else 0.5, axis=1
    )

    # 10-day EMA
    df['ema10'] = df['ratio'].ewm(span=10, adjust=False).mean()

    # Find historical signal firings
    # Signal: EMA goes from <=0.40 to >=0.615 within 10 trading days
    signal_dates = []
    ema_vals     = df['ema10'].values
    dates        = df.index.tolist()
    n            = len(ema_vals)

    for i in range(10, n):
        window      = ema_vals[max(0, i-10):i+1]
        window_min  = min(window)
        current_ema = ema_vals[i]
        if window_min <= 0.40 and current_ema >= 0.615:
            # Check not already captured (avoid duplicates within 10 days)
            if not signal_dates or (dates[i] - signal_dates[-1]).days > 10:
                signal_dates.append(dates[i])

    # Current status
    current_ema  = float(df['ema10'].iloc[-1])
    window_10d   = df['ema10'].tail(10)
    window_min   = float(window_10d.min())
    window_max   = float(window_10d.max())

    if current_ema >= 0.615 and window_min <= 0.40:
        status = 'FIRED'
    elif current_ema >= 0.615:
        status = 'STRONG'
    elif window_min <= 0.40 and current_ema > 0.40:
        status = 'WATCHING'
    elif current_ema <= 0.40:
        status = 'OVERSOLD'
    else:
        status = 'INACTIVE'

    return {
        'current_ema'   : round(current_ema, 4),
        'window_min'    : round(window_min, 4),
        'window_max'    : round(window_max, 4),
        'status'        : status,
        'signal_dates'  : signal_dates,
        'ema_series'    : df['ema10'],
        'ratio_series'  : df['ratio'],
        'df'            : df,
    }


def render_zweig_section(history_df, prefix, label, show_sector=True):
    import plotly.graph_objects as go
    import pandas as pd

    # Always work on a clean copy with date as index
    history_df = history_df.copy()

    if 'date' not in history_df.columns:
        history_df = history_df.reset_index()
        if 'date' not in history_df.columns and 'index' in history_df.columns:
            history_df = history_df.rename(columns={'index': 'date'})

    if 'date' not in history_df.columns:
        first_col = history_df.columns[0]
        try:
            history_df = history_df.rename(columns={first_col: 'date'})
        except:
            st.warning("Could not parse date column for Zweig calculation")
            return

    history_df['date'] = pd.to_datetime(history_df['date'])
    history_df = history_df.set_index('date').sort_index()

    st.markdown("### 📡 Zweig Breadth Thrust")
    st.markdown("""
        <div class="info-card">
            The Zweig Breadth Thrust fires when the 10-day EMA of advancing issues /
            (advancing + declining) moves from below 0.40 to above 0.615 within
            10 trading days. Historically one of the most reliable bull market
            confirmation signals — fires rarely (~15 times since 1945) but has
            preceded significant gains every time.
            <b>WATCHING</b> = setup building (EMA crossed below 0.40 recently).
            <b>FIRED</b> = signal active. <b>STRONG</b> = above threshold but no
            prior oversold setup.
        </div>
    """, unsafe_allow_html=True)

# ── Market-wide internal breadth ──────────────────────────────────────────
    st.markdown("**Internal Breadth Version**")

    if history_df is not None and 'leader' in history_df.columns:
        adv_int = history_df['leader'].astype(float)

        if 'weak' in history_df.columns:
            dec_int = (history_df['laggard'] + history_df['weak']).astype(float)
        else:
            dec_int = history_df['laggard'].astype(float)

        result = calc_zweig_thrust(adv_int, dec_int)

        if result:
            _render_zweig_card(result, f"{label} Internal", key_suffix=f"{prefix}_internal")
            _render_zweig_chart(result, f"{label} Internal Breadth Thrust — EMA10")
            _render_zweig_history(result)
        else:
            st.warning("Insufficient breadth history for Zweig calculation")
    else:
        st.warning("No breadth history available")



    # ── Per sector table ──────────────────────────────────────────────────────
    if show_sector and history_df is not None:
        st.markdown("**Per Sector Zweig Status**")

        # Find all sector keys
        total_cols  = [c for c in history_df.columns if c.startswith(f'{prefix}_') and c.endswith('_total')]
        sector_keys = [c.replace(f'{prefix}_','').replace('_total','') for c in total_cols
                       if 'nan' not in c and 'index' not in c]

        sector_rows = []
        for sec_key in sector_keys:
            leader_col = f'{prefix}_{sec_key}_leaders'
            laggard_col= f'{prefix}_{sec_key}_laggard'
            weak_col   = f'{prefix}_{sec_key}_weak'
            total_col  = f'{prefix}_{sec_key}_total'

            if leader_col not in history_df.columns:
                continue

            try:
                adv_s = history_df[leader_col].astype(float)
                # Use total - leaders as declining proxy if no laggard/weak columns
                if laggard_col in history_df.columns and weak_col in history_df.columns:
                    dec_s = (history_df[laggard_col] + history_df[weak_col]).astype(float)
                elif total_col in history_df.columns:
                    dec_s = (history_df[total_col].astype(float) - adv_s).clip(lower=0)
                else:
                    continue

                res = calc_zweig_thrust(adv_s, dec_s, lookback=252)
                if res is None:
                    continue

                last_signal = res['signal_dates'][-1].strftime('%Y-%m-%d') if res['signal_dates'] else 'Never'
                sector_rows.append({
                    'Sector'      : sec_key.replace('_',' ').title(),
                    'EMA10'       : round(res['current_ema'], 4),
                    '10d Low'     : round(res['window_min'], 4),
                    '10d High'    : round(res['window_max'], 4),
                    'Status'      : res['status'],
                    'Last Signal' : last_signal,
                    'Signals'     : len(res['signal_dates']),
                })
            except Exception as e:
                continue

        if sector_rows:
            df_sec = pd.DataFrame(sector_rows).sort_values('EMA10', ascending=False)
            
            # Ensure all numeric columns are plain Python floats
            for col in ['EMA10', '10d Low', '10d High']:
                df_sec[col] = df_sec[col].astype(float)
            df_sec['Signals'] = df_sec['Signals'].astype(int)

            def style_status(val):
                return STATUS_COLOURS.get(val, '')

            def style_ema(val):
                try:
                    v = float(val)
                    if v >= 0.615: return 'color: #2dc653'
                    if v <= 0.40:  return 'color: #e63946'
                    return 'color: #f77f00'
                except:
                    return ''

            st.dataframe(
                df_sec.style
                    .map(style_status, subset=['Status'])
                    .map(style_ema, subset=['EMA10', '10d Low', '10d High'])
                    .format({'EMA10': '{:.4f}', '10d Low': '{:.4f}', '10d High': '{:.4f}'}),
                width='stretch', hide_index=True,
                height=min(len(df_sec) * 35 + 40, 600)
            )


def _render_zweig_card(result, label, key_suffix=''):
    """Render status card for a Zweig result"""
    STATUS_CONFIG = {
        'FIRED'   : ('#2dc653', '🚀', 'Signal FIRED — high conviction bull signal'),
        'WATCHING': ('#f77f00', '👀', 'Setup building — EMA crossed below 0.40, watch for thrust'),
        'STRONG'  : ('#00b4d8', '💪', 'Above threshold but no prior oversold setup'),
        'OVERSOLD': ('#e63946', '⚠',  'Market oversold — potential setup building'),
        'INACTIVE': ('#888888', '—',  'No active setup'),
    }
    colour, icon, desc = STATUS_CONFIG.get(result['status'], ('#888', '—', ''))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
            <div class="macro-card" style="border-left:4px solid {colour}">
                <div class="macro-label">{label} — Status</div>
                <div style="color:{colour};font-size:20px;font-weight:bold">{icon} {result['status']}</div>
                <div style="font-size:10px;color:#aaa">{desc}</div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div class="macro-card">
                <div class="macro-label">Current EMA10</div>
                <div style="font-size:20px;font-weight:bold;color:{colour}">{result['current_ema']:.4f}</div>
                <div style="font-size:10px;color:#aaa">Threshold: 0.615</div>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
            <div class="macro-card">
                <div class="macro-label">10-Day Range</div>
                <div style="font-size:16px;font-weight:bold">
                    {result['window_min']:.4f} → {result['window_max']:.4f}
                </div>
                <div style="font-size:10px;color:#aaa">Low → High (need ≤0.40 then ≥0.615)</div>
            </div>
        """, unsafe_allow_html=True)
    with col4:
        signals = result['signal_dates']
        st.markdown(f"""
            <div class="macro-card">
                <div class="macro-label">Historical Signals</div>
                <div style="font-size:20px;font-weight:bold">{len(signals)}</div>
                <div style="font-size:10px;color:#aaa">in available history</div>
            </div>
        """, unsafe_allow_html=True)


def _render_zweig_chart(result, title):
    """Render EMA chart for Zweig result"""
    import plotly.graph_objects as go

    ema_s   = result['ema_series'].tail(126)
    ratio_s = result['ratio_series'].tail(126)

    fig = go.Figure()

    # Raw ratio
    fig.add_trace(go.Scatter(
        x=ema_s.index.astype(str).tolist(),
        y=ratio_s.values.tolist(),
        mode='lines',
        line=dict(color='rgba(100,150,255,0.3)', width=1),
        name='Daily Ratio',
    ))

    # EMA line
    fig.add_trace(go.Scatter(
        x=ema_s.index.astype(str).tolist(),
        y=ema_s.values.tolist(),
        mode='lines',
        line=dict(color='#00b4d8', width=2),
        name='EMA10',
    ))

    # Signal threshold lines
    fig.add_hline(y=0.615, line_dash='dash', line_color='#2dc653',
                  annotation_text='0.615 — Thrust threshold',
                  annotation_position='right')
    fig.add_hline(y=0.40, line_dash='dash', line_color='#e63946',
                  annotation_text='0.40 — Oversold threshold',
                  annotation_position='right')

    # Mark signal firing dates
    for sig_date in result['signal_dates']:
        if sig_date >= ema_s.index[0]:
            fig.add_vline(
                x=str(sig_date)[:10],
                line_dash='dot',
                line_color='#2dc653',
                opacity=0.6,
            )

    fig.update_layout(
        title       = title,
        height      = 280,
        plot_bgcolor= get_chart_theme()['plot_bgcolor'],
        paper_bgcolor= get_chart_theme()['paper_bgcolor'],
        font        = dict(color=get_chart_theme()['font_color']),
        xaxis       = dict(gridcolor=get_chart_theme()['gridcolor']),
        yaxis       = dict(gridcolor=get_chart_theme()['gridcolor'],
                           range=[0, 1]),
        showlegend  = True,
        legend      = dict(font=dict(size=10)),
        margin      = dict(l=50, r=120, t=40, b=30),
    )
    st.plotly_chart(fig, width='stretch')


def _render_zweig_history(result):
    """Render historical signal dates"""
    signals = result['signal_dates']
    if not signals:
        st.caption("No historical signals found in available data")
        return

    with st.expander(f"📅 Historical signal dates ({len(signals)} total)"):
        import pandas as pd
        rows = []
        for i, sig_date in enumerate(reversed(signals[-20:])):
            rows.append({
                '#'   : len(signals) - i,
                'Date': sig_date.strftime('%Y-%m-%d'),
                'Day' : sig_date.strftime('%A'),
            })
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MACRO PAGE
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Macro":
    import yfinance as yf
    import plotly.graph_objects as go

    st.title("🌍 Macro Dashboard")
    st.markdown("""
        <style>
        .macro-card {
            background: var(--background-color, rgba(0,0,0,0.04));
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 8px;
        }
        .macro-label { color: #888; font-size: 10px; }
        .macro-value { color: inherit; font-size: 15px; font-weight: bold; }
        .macro-signal { font-size: 10px; }
        </style>
    """, unsafe_allow_html=True)

    # ── Parse macro report txt ────────────────────────────────────────────────
    report_file = latest_file(os.path.join(MACRO, 'results', '*_macro_report.txt'))

    def parse_macro_report(path):
        """Extract key values from macro report txt"""
        if not path or not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()

        import re
        d = {}

        # VIX
        m = re.search(r'VIX:\s*([\d.]+)', text)
        if m: d['vix'] = float(m.group(1))
        m = re.search(r'VVIX:\s*([\d.]+)', text)
        if m: d['vvix'] = float(m.group(1))
        m = re.search(r'VIX/VVIX:\s*([\d.]+)', text)
        if m: d['vix_vvix'] = float(m.group(1))
        m = re.search(r'REGIME:\s*(.+)', text)
        if m: d['regime'] = m.group(1).strip()

        # Change alerts
        alerts = re.findall(r'→\s+(WATCH|ALERT)\s+(.+?)(?:\n|$)', text)
        d['alerts'] = alerts

        # Focus instruments
        asx_focus  = re.findall(r'ASX:.*?(?=US:|$)', text, re.DOTALL)
        us_focus   = re.findall(r'US:.*?(?=Ratios:|$)', text, re.DOTALL)
        d['focus_raw'] = text[text.find("TODAY'S FOCUS"):text.find("ECONOMIC REGIME")] if "TODAY'S FOCUS" in text else ''

        # Economic
        m = re.search(r'Unemployment:\s*([\d.]+)%.*?→\s*(.+)', text)
        if m: d['unemployment'] = float(m.group(1)); d['unemp_label'] = m.group(2).strip()
        m = re.search(r'PMI Mfg:\s*([\d.]+).*?✓\s*(.+?)(?:\n|$)', text)
        if m: d['pmi'] = float(m.group(1)); d['pmi_label'] = m.group(2).strip()
        m = re.search(r'Non-Farm Pay:\s*([\d,]+)', text)
        if m: d['nfp'] = m.group(1).strip()
        m = re.search(r'Consumer Sent:\s*([\d.]+).*?(?:⚠|✓)\s*(.+?)(?:\n|$)', text)
        if m: d['consumer_sent'] = float(m.group(1)); d['sent_label'] = m.group(2).strip()

        # Consumer cycle
        m = re.search(r'XLY/XLP ratio:\s*([\d.]+)\s+[▲▼]\s*([\d.]+)%\s+5d.*?(⚠|→|✓)\s*(.+?)(?:\n|$)', text)
        if m: d['xly_xlp'] = float(m.group(1)); d['xly_xlp_5d'] = m.group(2); d['xly_xlp_label'] = m.group(4).strip()
        m = re.search(r'RSPD/RSPS ratio:\s*([\d.]+)\s+[▲▼]\s*([\d.]+)%\s+5d.*?(⚠|→|✓)\s*(.+?)(?:\n|$)', text)
        if m: d['rspd_rsps'] = float(m.group(1)); d['rspd_rsps_label'] = m.group(4).strip()
        m = re.search(r'Sector Groups Risk On/Off ratio:\s*([\d.]+).*?(⚠|→|✓)\s*(.+?)(?:\n|$)', text)
        if m: d['sector_ratio'] = float(m.group(1)); d['sector_ratio_label'] = m.group(3).strip()

        # Valuation
        m = re.search(r'SPX/M2 ratio:\s*([\d.]+)', text)
        if m: d['spx_m2'] = float(m.group(1))
        m = re.search(r'Margin/M2 ratio:\s*([\d.]+)', text)
        if m: d['margin_m2'] = float(m.group(1))
        m = re.search(r'Buffett Indicator:\s*([\d.]+)%', text)
        if m: d['buffett'] = float(m.group(1))
        m = re.search(r'Shiller CAPE:\s*([\d.]+)', text)
        if m: d['cape'] = float(m.group(1))

        # Cycles
        cycles = {}
        cycle_blocks = re.findall(
            r'([\d/\-]+ YEAR [^\n]+|[A-Z/]+ CYCLE[^\n]*)\n.*?Phase:\s*(.+?)\n.*?Years in:\s*([\d.]+)',
            text, re.DOTALL
        )
        for name, phase, years in cycle_blocks:
            cycles[name.strip()] = {'phase': phase.strip(), 'years': float(years)}

        # Business cycle
        m = re.search(r'BUSINESS/ECONOMIC CYCLE.*?Phase:\s*(.+?)\s*\(signal score:\s*(\d+)\)', text, re.DOTALL)
        if m: d['biz_cycle'] = m.group(1).strip(); d['biz_score'] = int(m.group(2))

        # Fed cycle
        m = re.search(r'FED QT/QE CYCLE.*?Phase:\s*(.+?)\n', text, re.DOTALL)
        if m: d['fed_cycle'] = m.group(1).strip()

        # Presidential
        m = re.search(r'SPX return since Nov 2024\s+([\d.]+)%\s+([\d.]+)%', text)
        if m: d['pres_ret'] = float(m.group(1)); d['pres_hist'] = float(m.group(2))
        m = re.search(r'Current DD from cycle high\s+([-\d.]+)%', text)
        if m: d['pres_dd'] = float(m.group(1))
        m = re.search(r'Day\s+(\d+)', text)
        if m: d['pres_day'] = int(m.group(1))

        # Rates
        m = re.search(r'US10Y:\s*([\d.]+)', text)
        if m: d['us10y'] = float(m.group(1))
        m = re.search(r'US2Y:\s*([\d.]+)', text)
        if m: d['us2y'] = float(m.group(1))
        m = re.search(r'AU10Y:\s*([\d.]+)', text)
        if m: d['au10y'] = float(m.group(1))
        m = re.search(r'Yield Curve:\s*([\d.]+)', text)
        if m: d['yield_curve'] = float(m.group(1))
        m = re.search(r'HY Spread:\s*([\d.]+)', text)
        if m: d['hy_spread'] = float(m.group(1))
        m = re.search(r'Fed Funds:\s*([\d.]+)', text)
        if m: d['fed_funds'] = float(m.group(1))
        m = re.search(r'Fed Balance Sheet:\s*\$([\d.]+)T', text)
        if m: d['fed_bs'] = float(m.group(1))

        # Copper/Gold ratio
        m = re.search(r'Cu/Gold ratio:\s*([\d.]+)\s+[▲▼]\s*([\d.]+)%\s+5d\s+[▲▼]\s*([\d.]+)%\s+63d\s+(.*?)(?:\n|$)', text)
        if m:
            d['cu_gold_ratio']   = float(m.group(1))
            d['cu_gold_chg_5d']  = float(m.group(2))
            d['cu_gold_chg_63d'] = float(m.group(3))
            d['cu_gold_status']  = m.group(4).strip()

        # Yield curve velocity
        m = re.search(r'Yield Curve Velocity:\s+([-\d.]+)%\s+5d\s+([-\d.]+)%\s+21d\s+(.*?)(?:\n|$)', text)
        if m:
            d['yc_roc_5d']    = float(m.group(1))
            d['yc_roc_21d']   = float(m.group(2))
            d['yc_vel_status']= m.group(3).strip()

        # Margin debt acceleration
        m = re.search(r'Margin Debt Accel:\s+([+\-\d.]+)%\s+(.*?)(?:\n|$)', text)
        if m:
            d['margin_acceleration'] = float(m.group(1))
            d['margin_accel_status'] = m.group(2).strip()

        # A/D line divergence
        m = re.search(r'A/D Line:\s+(?:⚠|✓|→)\s+(.*?)(?:\n|$)', text)
        if m:
            d['ad_divergence'] = m.group(1).strip()

        return d

    macro = parse_macro_report(report_file)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — LIVE MARKET READINGS
    # ══════════════════════════════════════════════════════════════════════════
    st.subheader("📡 Live Market Readings")

    LIVE_TICKERS = {
        'SPX'    : ('^GSPC',  'S&P 500',     'equity'),
        'NDX'    : ('^NDX',   'Nasdaq 100',   'equity'),
        'IWM'    : ('IWM',    'Russell 2000', 'equity'),
        'XJO'    : ('^AXJO',  'ASX 200',      'equity'),
        'VIX'    : ('^VIX',   'VIX',          'risk'),
        'DXY'    : ('DX-Y.NYB','DXY',         'fx'),
        'AUDUSD' : ('AUDUSD=X','AUDUSD',      'fx'),
        'Gold'   : ('GC=F',   'Gold',         'commodity'),
        'Silver' : ('SI=F',   'Silver',       'commodity'),
        'Copper' : ('HG=F',   'Copper',       'commodity'),
        'Oil'    : ('CL=F',   'Oil WTI',      'commodity'),
        'US10Y'  : ('^TNX',   'US 10Y',       'rates'),
        'US2Y'   : ('^IRX',   'US 2Y',        'rates'),
    }

    @st.cache_data(ttl=300)
    def fetch_live_prices():
        results = {}
        tickers = [v[0] for v in LIVE_TICKERS.values()]
        try:
            raw = yf.download(tickers, period='10d', auto_adjust=True, progress=False)
            closes = raw['Close']
            for key, (ticker, label, group) in LIVE_TICKERS.items():
                if ticker in closes.columns:
                    series = closes[ticker].dropna()
                    if len(series) >= 2:
                        price   = float(series.iloc[-1])
                        prev_5d = float(series.iloc[-6]) if len(series) >= 6 else float(series.iloc[0])
                        chg_5d  = round((price / prev_5d - 1) * 100, 2)
                        prev_1d = float(series.iloc[-2])
                        chg_1d  = round((price / prev_1d - 1) * 100, 2)
                        results[key] = {'label': label, 'price': price,
                                        'chg_1d': chg_1d, 'chg_5d': chg_5d, 'group': group}
        except Exception as e:
            st.warning(f"Could not fetch live prices: {e}")
        return results

    with st.spinner("Fetching live prices..."):
        live = fetch_live_prices()

    if live:
        def metric_colour(val):
            if val > 0:   return "#2dc653"
            elif val < 0: return "#e63946"
            return "#888888"

        def arrow(val):
            return "▲" if val > 0 else "▼" if val < 0 else "→"

        # Group display
        groups = [
            ("Equities",    ['SPX','NDX','IWM','XJO']),
            ("Risk & FX",   ['VIX','DXY','AUDUSD']),
            ("Commodities", ['Gold','Silver','Copper','Oil']),
            ("Rates", ['US10Y','US2Y']),
        ]

        # 4-column table layout — one column per group
        _lc1, _lc2, _lc3, _lc4 = st.columns(4)
        _live_cols = [_lc1, _lc2, _lc3, _lc4]

        for gi, (group_name, keys) in enumerate(groups):
            grp_rows = []
            for key in keys:
                if key not in live: continue
                d = live[key]; price = d['price']; c1d = d['chg_1d']; c5d = d['chg_5d']
                if price > 1000:   fmt = f"{price:,.2f}"
                elif price > 10:   fmt = f"{price:.2f}"
                elif price > 1:    fmt = f"{price:.4f}"
                else:              fmt = f"{price:.5f}"
                grp_rows.append({'Name': d['label'], 'Price': fmt, '1D %': c1d, '5D %': c5d})
            if grp_rows:
                import pandas as _pd7
                df_grp = _pd7.DataFrame(grp_rows)
                def _live_style(row):
                    styles = ['', '']
                    for col_idx, col_key in [(2, '1D %'), (3, '5D %')]:
                        try:
                            v = float(row.iloc[col_idx])
                            styles.append('color:#2dc653' if v > 0 else 'color:#e63946' if v < 0 else '')
                        except: styles.append('')
                    return styles
                with _live_cols[gi % 4]:
                    st.markdown(f"**{group_name}**")
                    st.dataframe(
                        df_grp.style.apply(_live_style, axis=1)
                            .format({'1D %': '{:+.2f}%', '5D %': '{:+.2f}%'}),
                        use_container_width=True, hide_index=True
                    )

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — REGIME & ALERTS
    # ══════════════════════════════════════════════════════════════════════════
    st.subheader("⚠ Regime, Alerts & Indicators")

    if report_file:
        report_date = os.path.basename(report_file)[:8]
        st.caption(f"From macro report: {report_date} — last updated {file_age(report_file)}")

    # VIX Regime banner
    regime     = macro.get('regime', 'UNKNOWN')
    vix_val    = macro.get('vix', 0)
    vvix_val   = macro.get('vvix', 0)
    vix_vvix   = macro.get('vix_vvix', 0)

    regime_colours = {
        'RISK ON'   : '#1a472a',
        'CAUTIOUS'  : '#5a4000',
        'RISK OFF'  : '#5a1a00',
        'PANIC'     : '#5a0000',
        'COMPLACENCY WARNING': '#2d4a00',
    }
    regime_colour = regime_colours.get(regime, '#333333')

    st.markdown(f"""
        <div style="background:{regime_colour};border-radius:8px;padding:16px;
                    text-align:center;margin-bottom:12px;border:1px solid rgba(255,255,255,0.15)">
            <div style="color:white;font-size:22px;font-weight:bold">{regime}</div>
            <div style="color:rgba(255,255,255,0.7);font-size:13px;margin-top:4px">
                VIX: {vix_val} &nbsp;|&nbsp; VVIX: {vvix_val} &nbsp;|&nbsp; VIX/VVIX: {vix_vvix:.4f}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Change alerts
    alerts = macro.get('alerts', [])
    if alerts:
        st.markdown("**Change Alerts**")
        for alert_type, alert_text in alerts:
            colour = '#e63946' if alert_type == 'ALERT' else '#f77f00'
            st.markdown(f"""
                <div class="macro-card" style="border-left:3px solid {colour}">
                    <span style="color:{colour};font-weight:bold">{alert_type}</span>
                    &nbsp; {alert_text}
                </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("No change alerts since last run")

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    _ms1, col1, col2, col3, col4, _ms2 = st.columns([600, 2500, 2500, 2500, 2500, 600])

    with col1:
        st.markdown("**Economic Regime**")
        unemp = macro.get('unemployment', None)
        pmi   = macro.get('pmi', None)
        nfp   = macro.get('nfp', '')
        sent  = macro.get('consumer_sent', None)

        def indicator_row(label, value, signal_text, good=True):
            colour = '#2dc653' if good else '#e63946'
            icon   = '✓' if good else '⚠'
            _ec_rows.append({'Indicator': label, 'Value': str(value), 'Signal': f"{icon} {signal_text}", '_colour': colour})
        _ec_rows = []

        if unemp: indicator_row("Unemployment", f"{unemp}%",
            macro.get('unemp_label',''), good=unemp < 4.5)
        if pmi:   indicator_row("PMI Mfg", f"{pmi}",
            macro.get('pmi_label',''), good=pmi >= 50)
        if nfp:   indicator_row("Non-Farm Payrolls", nfp, "", good=True)
        if sent:  indicator_row("Consumer Sentiment", f"{sent}",
            macro.get('sent_label',''), good=sent > 70)

        # Copper/Gold ratio
        cu_gold = macro.get('cu_gold_ratio')
        if cu_gold:
            cu_5d  = macro.get('cu_gold_chg_5d')
            cu_63d = macro.get('cu_gold_chg_63d')
            if cu_63d is not None:
                if cu_63d > 5:
                    cu_st  = '✓ RISING — industrial demand expanding'
                    colour = '#2dc653'
                elif cu_63d < -5:
                    cu_st  = '⚠ FALLING — industrial demand contracting'
                    colour = '#e63946'
                else:
                    cu_st  = '→ FLAT — neutral growth signal'
                    colour = '#f77f00'
            else:
                cu_st  = ''
                colour = '#888'
            _ec_rows.append({'Indicator':'Cu/Gold Ratio','Value':f"{cu_gold:.6f}  5d:{f'{cu_5d:+.2f}%' if cu_5d is not None else 'n/a'} 63d:{f'{cu_63d:+.2f}%' if cu_63d is not None else 'n/a'}", 'Signal':cu_st,'_colour':colour})
        if _ec_rows:
            import pandas as _pd3
            _ec_df = _pd3.DataFrame(_ec_rows)[['Indicator','Value','Signal']]
            def _ec_style(row):
                return ['','',f"color:{_ec_rows[row.name]['_colour']}"]
            st.dataframe(_ec_df.style.apply(_ec_style,axis=1),use_container_width=True,hide_index=True)

    with col2:
        st.markdown("**Consumer Cycle**")
        xly = macro.get('xly_xlp', None)
        rsp = macro.get('rspd_rsps', None)
        sec = macro.get('sector_ratio', None)

        _cc_rows = []
        if xly:
            lbl = macro.get('xly_xlp_label',''); good = 'RISK OFF' not in lbl; colour = '#2dc653' if good else '#e63946'
            _cc_rows.append({'Indicator':'XLY/XLP Ratio','Value':str(xly),'Signal':lbl[:60],'_c':colour})
        if rsp:
            lbl = macro.get('rspd_rsps_label',''); good = 'RISK OFF' not in lbl; colour = '#2dc653' if good else '#e63946'
            _cc_rows.append({'Indicator':'RSPD/RSPS Ratio','Value':str(rsp),'Signal':lbl[:60],'_c':colour})
        if sec:
            lbl = macro.get('sector_ratio_label',''); good = 'NEUTRAL' in lbl or 'RISK ON' in lbl; colour = '#2dc653' if good else '#f77f00'
            _cc_rows.append({'Indicator':'Sector Risk On/Off','Value':str(sec),'Signal':lbl[:60],'_c':colour})
            ad_div = macro.get('ad_divergence')
        if ad_div:
            good = 'BULLISH' in ad_div; colour = '#2dc653' if good else '#e63946' if 'BEARISH' in ad_div else '#f77f00'
            _cc_rows.append({'Indicator':'A/D Divergence','Value':'','Signal':ad_div[:60],'_c':colour})
        if _cc_rows:
            import pandas as _pd4
            _cc_df = _pd4.DataFrame(_cc_rows)[['Indicator','Value','Signal']]
            def _cc_style(row): return ['','',f"color:{_cc_rows[row.name]['_c']}"]
            st.dataframe(_cc_df.style.apply(_cc_style,axis=1),use_container_width=True,hide_index=True)

    with col3:
        st.markdown("**Valuation**")
        vals = [
            ("SPX/M2",        macro.get('spx_m2'),   0.25, "Extreme above 0.25"),
            ("Margin/M2",     macro.get('margin_m2'),1.4,  "Extreme above 1.4"),
            ("Margin Accel %", macro.get('margin_acceleration'), 0.5, "Accelerating — leverage building"),
            ("Buffett Ind %", macro.get('buffett'),  150,  "Extreme above 150%"),
            ("Shiller CAPE",  macro.get('cape'),     30,   "Extreme above 30"),
        ]
        _val_rows = []
        for lbl, val, threshold, warning in vals:
            if val is None: continue
            extreme = val > threshold; colour = '#e63946' if extreme else '#2dc653'; icon = '⚠' if extreme else '✓'
            _val_rows.append({'Indicator':lbl,'Value':str(val),'Signal':f"{icon} {warning if extreme else 'Normal range'}", '_c':colour})
        if _val_rows:
            import pandas as _pd5
            _val_df = _pd5.DataFrame(_val_rows)[['Indicator','Value','Signal']]
            def _val_style(row): return ['','',f"color:{_val_rows[row.name]['_c']}"]
            st.dataframe(_val_df.style.apply(_val_style,axis=1),use_container_width=True,hide_index=True)

    with col4:
        st.markdown("**Credit & Rates**")
        credit_items = [
            ("Fed Funds",         macro.get('fed_funds'),   "%"),
            ("US 10Y",            macro.get('us10y'),       "%"),
            ("US 2Y",             macro.get('us2y'),        "%"),
            ("AU 10Y",            macro.get('au10y'),       "%"),
            ("Yield Curve",       macro.get('yield_curve'), "%"),
            ("Yield Curve 5d Vel", macro.get('yc_roc_5d'),  "%"),
            ("HY Spread",         macro.get('hy_spread'),   "%"),
            ("Fed Balance Sheet", macro.get('fed_bs'),      "T"),
        ]
        _cr_rows = []
        for lbl, val, suffix in credit_items:
            if val is None: continue
            if lbl == "Yield Curve": colour = '#2dc653' if val > 0 else '#e63946'; signal = '✓ Uninverted' if val > 0 else '⚠ Inverted'
            elif lbl == "HY Spread": colour = '#2dc653' if val < 4 else '#f77f00' if val < 6 else '#e63946'; signal = 'Contained' if val < 4 else 'Widening' if val < 6 else 'Stress'
            else: colour = '#888888'; signal = ''
            _cr_rows.append({'Indicator':lbl,'Value':f"{val}{suffix}",'Signal':signal,'_c':colour})
        if _cr_rows:
            import pandas as _pd6
            _cr_df = _pd6.DataFrame(_cr_rows)[['Indicator','Value','Signal']]
            def _cr_style(row): return ['','',f"color:{_cr_rows[row.name]['_c']}"]
            st.dataframe(_cr_df.style.apply(_cr_style,axis=1),use_container_width=True,hide_index=True)

    # Focus instruments expander
    focus_raw = macro.get('focus_raw', '')
    if focus_raw:
        with st.expander("Today's Focus Instruments"):
            import re
            # Parse sections and items from raw text
            sections = {}
            current  = None
            for line in focus_raw.splitlines():
                line = line.strip()
                if not line or 'FOCUS' in line.upper():
                    continue
                # Section header — ends with colon
                if line.endswith(':'):
                    current = line.rstrip(':').strip()
                    sections[current] = []
                elif line.startswith('•') and current:
                    item = line.lstrip('•').strip()
                    sections[current].append(item)

            if sections:
                # Build flat list of (section, item) pairs
                rows = []
                for section, items in sections.items():
                    for item in items:
                        rows.append({'Group': section, 'Instrument': item.split('—')[0].strip(),
                                     'Note': item.split('—')[1].strip() if '—' in item else ''})

                if rows:
                    df_focus = pd.DataFrame(rows)
                    # Split into 3 columns by group
                    groups   = list(sections.keys())
                    n_cols   = min(len(groups), 3)
                    grp_cols = st.columns(n_cols)
                    for i, group in enumerate(groups[:n_cols]):
                        with grp_cols[i % n_cols]:
                            st.markdown(f"**{group}**")
                            grp_df = df_focus[df_focus['Group'] == group][['Instrument','Note']]
                            st.dataframe(grp_df, width='stretch',
                                         hide_index=True,
                                         height=min(len(grp_df) * 35 + 40, 400))
            else:
                st.code(focus_raw, language=None)

    if st.button("🔄 Run Macro Report", key='macro_run'):
        run_script(os.path.join(MACRO, 'macro_report.py'), MACRO)
        st.rerun()

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — MACRO CYCLE POSITIONING
    # ══════════════════════════════════════════════════════════════════════════
    st.subheader("🔄 Macro Cycle Positioning")

    # Business and Fed cycles as status cards
    biz_col, fed_col, pres_col = st.columns(3)

    with biz_col:
        biz   = macro.get('biz_cycle', 'UNKNOWN')
        score = macro.get('biz_score', 0)
        biz_colours = {
            'EARLY EXPANSION': '#2dc653', 'MID EXPANSION': '#80b918',
            'LATE EXPANSION': '#f77f00',  'LATE CYCLE': '#e63946',
            'EARLY CONTRACTION': '#c1121f','RECESSION': '#9b0000',
            'EARLY RECOVERY': '#2dc653',
        }
        colour = biz_colours.get(biz, '#888888')
        st.markdown(f"""
            <div class="macro-card" style="border-left:4px solid {colour};text-align:center;padding:16px">
                <div class="macro-label">BUSINESS CYCLE</div>
                <div style="color:{colour};font-size:20px;font-weight:bold;margin:6px 0">{biz}</div>
                <div class="macro-label">Signal score: {score}/10</div>
            </div>
        """, unsafe_allow_html=True)

    with fed_col:
        fed  = macro.get('fed_cycle', 'UNKNOWN')
        fed_colours = {
            'QT': '#e63946', 'QT SLOWING': '#f77f00',
            'QT SLOWING — PRE PIVOT': '#f77f00',
            'PRE PIVOT': '#fcbf49', 'QE': '#2dc653',
            'FULL EASING': '#2dc653',
        }
        colour = next((v for k, v in fed_colours.items() if k in fed), '#888888')
        st.markdown(f"""
            <div class="macro-card" style="border-left:4px solid {colour};text-align:center;padding:16px">
                <div class="macro-label">FED CYCLE</div>
                <div style="color:{colour};font-size:16px;font-weight:bold;margin:6px 0">{fed}</div>
                <div class="macro-label">Funds: {macro.get('fed_funds','')}% &nbsp;|&nbsp; BS: ${macro.get('fed_bs','')}T</div>
            </div>
        """, unsafe_allow_html=True)

    with pres_col:
        p_ret  = macro.get('pres_ret', 0)
        p_hist = macro.get('pres_hist', 0)
        p_dd   = macro.get('pres_dd', 0)
        p_day  = macro.get('pres_day', 0)
        ahead  = p_ret - p_hist
        colour = '#2dc653' if ahead > 0 else '#e63946'
        st.markdown(f"""
            <div class="macro-card" style="border-left:4px solid {colour};text-align:center;padding:16px">
                <div class="macro-label">PRESIDENTIAL CYCLE — DAY {p_day}</div>
                <div style="color:{colour};font-size:20px;font-weight:bold;margin:6px 0">{p_ret:+.1f}%</div>
                <div class="macro-label">vs hist avg {p_hist:.1f}% &nbsp;
                    <span style="color:{colour}">({ahead:+.1f}%)</span></div>
                <div style="color:#e63946;font-size:11px;margin-top:4px">DD from high: {p_dd:.1f}%</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSUMER CREDIT PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Debt Markets":
    import plotly.graph_objects as go
    import numpy as np
    import json
    import sys
    sys.path.insert(0, MACRO)

    st.title("💳 Debt Markets")
    st.markdown("""
        <div class="info-card">
            Tracks the health of consumer, corporate and sovereign credit markets using
            Federal Reserve (FRED) data. Most series are updated quarterly — signals here
            are slow-moving but highly reliable leading indicators of economic stress.
            <b>Rate of change</b> is more important than the level — accelerating
            delinquencies signal deteriorating credit conditions before they appear in
            employment or GDP data. Alerts feed into the Macro page change alerts.
        </div>
    """, unsafe_allow_html=True)

    # ── Load latest snapshot ──────────────────────────────────────────────────
    credit_dir   = os.path.join(MACRO, 'results', 'consumer_credit')
    json_files   = sorted(glob.glob(os.path.join(credit_dir, '*_consumer_credit.json')),
                          reverse=True)

    if not json_files:
        st.warning("No consumer credit data found — run the script first")
        if st.button("▶ Run Debt Markets Report", type="primary"):
            run_script(os.path.join(MACRO, 'consumer_credit.py'), MACRO)
            st.rerun()
    else:
        # Date selector
        dates      = [os.path.basename(f)[:8] for f in json_files][:30]
        sel_date   = st.selectbox("Report date", dates, index=0)
        json_file  = os.path.join(credit_dir, f"{sel_date}_consumer_credit.json")

        with open(json_file, 'r') as f:
            snap = json.load(f)

        credit_data = snap.get('credit_data', {})
        pe_data     = snap.get('pe_data', {})
        alerts      = snap.get('alerts', [])

        report_date = datetime.strptime(sel_date, '%Y%m%d').strftime('%d %b %Y')
        st.caption(f"Report date: {report_date}")

        # ── Alerts banner ─────────────────────────────────────────────────────
        if alerts:
            st.markdown("**⚠ Active Alerts**")
            for alert in alerts:
                colour = '#e63946' if alert['type'] == 'ALERT' else '#f77f00'
                st.markdown(f"""
                    <div class="macro-card" style="border-left:3px solid {colour}">
                        <span style="color:{colour};font-weight:bold">{alert['type']}</span>
                        &nbsp; {alert['message']}
                    </div>
                """, unsafe_allow_html=True)
            st.divider()

        # ── Helper: indicator card ────────────────────────────────────────────
        def credit_card(key, description, context, thresholds_text):
            if key not in credit_data:
                return
            d       = credit_data[key]
            val     = d['current']
            roc     = d.get('roc', 0) or 0
            roc_3m  = d.get('roc_3m', 0) or 0
            level   = d.get('alert_level', 'OK')
            arrow   = '▲' if roc > 0 else '▼' if roc < 0 else '→'
            colours = {'ALERT': '#e63946', 'WARN': '#f77f00', 'OK': '#2dc653'}
            colour  = colours.get(level, '#888')
            icon    = '⚠' if level == 'ALERT' else '!' if level == 'WARN' else '✓'

            st.markdown(f"""
                <div class="macro-card" style="border-left:4px solid {colour}">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <div>
                            <div class="macro-label">{d['label']}</div>
                            <div style="font-size:22px;font-weight:bold;color:{colour}">
                                {val:.2f}{'%' if key != 'consumer_credit' else 'B'}
                            </div>
                            <div style="font-size:11px;color:#888">
                                {arrow} {roc:+.3f} qoq &nbsp;|&nbsp; 3m: {roc_3m:+.3f}
                            </div>
                        </div>
                        <div style="text-align:right">
                            <div style="color:{colour};font-size:18px">{icon} {level}</div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            with st.expander("ℹ What this means"):
                st.markdown(f"""
                    <div style="font-size:12px;color:#aaa;line-height:1.7">
                        <b style="color:#ccc">What it measures:</b> {description}<br><br>
                        <b style="color:#ccc">Current context:</b> {context}<br><br>
                        <b style="color:#ccc">Thresholds:</b> {thresholds_text}
                    </div>
                """, unsafe_allow_html=True)

        # ── Helper: history chart ─────────────────────────────────────────────
        def credit_chart(key, title, recession_shade=True):
            if key not in credit_data:
                return
            history = credit_data[key].get('history', {})
            if not history:
                return
            dates_h = list(history.keys())
            values  = list(history.values())
            suffix  = 'B' if key == 'consumer_credit' else '%'

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates_h, y=values,
                mode='lines+markers',
                line=dict(color='#00b4d8', width=2),
                marker=dict(size=5),
                name=title,
                hovertemplate=f"%{{x}}: %{{y:.2f}}{suffix}<extra></extra>"
            ))

            # Trend line
            if len(values) >= 4:
                x_num   = list(range(len(values)))
                n       = len(x_num)
                sum_x   = sum(x_num)
                sum_y   = sum(values)
                sum_xy  = sum(x * y for x, y in zip(x_num, values))
                sum_x2  = sum(x * x for x in x_num)
                slope   = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
                intercept = (sum_y - slope * sum_x) / n
                trend   = [slope * x + intercept for x in x_num]
                t_colour= '#e63946' if slope > 0 else '#2dc653'
                fig.add_trace(go.Scatter(
                    x=dates_h, y=trend,
                    mode='lines',
                    line=dict(color=t_colour, width=1, dash='dash'),
                    name='Trend', opacity=0.6
                ))

            fig.update_layout(
                title       = title,
                height      = 250,
                plot_bgcolor= get_chart_theme()['plot_bgcolor'],
                paper_bgcolor= get_chart_theme()['paper_bgcolor'],
                font        = dict(color=get_chart_theme()['font_color']),
                xaxis       = dict(gridcolor=get_chart_theme()['gridcolor']),
                yaxis       = dict(gridcolor=get_chart_theme()['gridcolor'],
                                   ticksuffix=suffix),
                showlegend  = False,
                margin      = dict(l=50,r=20,t=40,b=30),
            )
            st.plotly_chart(fig, width='stretch')

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 1 — CONSUMER CREDIT
        # ══════════════════════════════════════════════════════════════════════
        st.subheader("💳 Consumer Credit Markets")
        st.markdown("""
            <div class="info-card">
                Consumer credit delinquency rates measure the percentage of loans
                30+ days past due. Rising delinquencies signal financial stress among
                households — typically 2-4 quarters ahead of broader economic weakness.
                Credit card and auto loans are the canary in the coal mine as they
                reflect lower income household stress first. Mortgage delinquencies
                rising confirms the stress is spreading to middle income households.
            </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            credit_card('cc_delinquency',
                'Percentage of credit card balances 30+ days past due.',
                'Rising above 3% signals consumer stress. Above 4% is crisis territory last seen in 2009-2010.',
                'WARN >2.5% | ALERT >3.5%')
            credit_chart('cc_delinquency', 'Credit Card Delinquency Rate')

            credit_card('auto_delinquency',
                'Percentage of auto loan balances 30+ days past due.',
                'Auto loans are often the first to default — consumers prioritise housing and food. Rising auto defaults lead credit card defaults by 1-2 quarters.',
                'WARN >1.5% | ALERT >2.5%')
            credit_chart('auto_delinquency', 'Auto Loan Delinquency Rate')

        with c2:
            credit_card('cc_chargeoff',
                'Percentage of credit card debt written off as uncollectable.',
                'Charge-offs lag delinquencies by 1-2 quarters. Charge-off rate rising above delinquency rate signals banks are accelerating write-downs.',
                'WARN >3.0% | ALERT >4.5%')
            credit_chart('cc_chargeoff', 'Credit Card Charge-Off Rate')

            credit_card('mortgage_delinquency',
                'Percentage of mortgage balances 30+ days past due.',
                'Mortgage delinquencies rising above 2% historically precede housing market stress by 2-3 quarters. Currently near historic lows.',
                'WARN >1.5% | ALERT >2.5%')
            credit_chart('mortgage_delinquency', 'Mortgage Delinquency Rate')

        credit_card('consumer_credit',
            'Total outstanding consumer credit in billions — credit cards, auto loans, student loans (excludes mortgages).',
            'Decelerating growth signals consumers are tapped out. Contraction (negative QoQ) is recessionary.',
            'Monitor rate of change — deceleration is the key signal')
        credit_chart('consumer_credit', 'Total Consumer Credit Outstanding ($B)')

        # Load AI settings and render assessment
        ai_settings = load_settings()
        if ai_settings.get('ai_features', {}).get('enabled', False):
            import sys
            import importlib
            if MACRO not in sys.path:
                sys.path.insert(0, MACRO)
            importlib.invalidate_caches()
            from ai_assessment import render_ai_assessment
            cc  = credit_data.get('cc_delinquency', {})
            aut = credit_data.get('auto_delinquency', {})
            mor = credit_data.get('mortgage_delinquency', {})
            cho = credit_data.get('cc_chargeoff', {})
            prompt = f"""You are a macro credit analyst. Analyse these US consumer credit readings 
and provide a 4-5 sentence assessment. Focus on acceleration/deceleration trends, 
what the combined picture suggests about consumer financial health, and what 
to watch over the next 1-2 quarters. Be direct and quantitative.

Credit card delinquency: {cc.get('current','n/a')}% (qoq change: {cc.get('roc','n/a')}, 3m: {cc.get('roc_3m','n/a')})
Auto loan delinquency: {aut.get('current','n/a')}% (qoq: {aut.get('roc','n/a')})
Mortgage delinquency: {mor.get('current','n/a')}% (qoq: {mor.get('roc','n/a')})
Charge-off rate: {cho.get('current','n/a')}% (qoq: {cho.get('roc','n/a')})"""
            render_ai_assessment(prompt, ai_settings, 'consumer_credit_assessment')

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 2 — CORPORATE CREDIT
        # ══════════════════════════════════════════════════════════════════════
        st.subheader("🏢 Corporate Credit")
        st.markdown("""
            <div class="info-card">
                Corporate credit spreads measure the premium investors demand over
                risk-free rates to hold corporate debt. Widening spreads signal
                deteriorating credit conditions and reduced risk appetite — often
                leading equity market stress by 4-8 weeks. HY spreads above 600bps
                historically coincide with recession. The leveraged loan market
                (BKLN) reflects the health of PE-backed companies.
            </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            credit_card('hy_spread',
                'Option-adjusted spread of US high yield bonds over US Treasuries.',
                'Below 300bps = risk on. 300-500bps = caution. Above 500bps = stress. Above 800bps = crisis.',
                'WARN >4.0% | ALERT >6.0%')
            credit_chart('hy_spread', 'High Yield Spread')

        with c2:
            credit_card('ig_spread',
                'Option-adjusted spread of US investment grade bonds over US Treasuries.',
                'IG spreads widen after HY — when IG starts widening it confirms stress is spreading beyond junk. Above 2% is historically recessionary.',
                'WARN >1.5% | ALERT >2.5%')
            credit_chart('ig_spread', 'Investment Grade Spread')

        # BKLN from PE data
        if 'BKLN' in pe_data:
            bkln    = pe_data['BKLN']
            colour  = '#2dc653' if bkln.get('ret_1m') and bkln['ret_1m'] > 0 else '#e63946'
            ret_1m  = f"{bkln['ret_1m']:+.1f}%" if bkln.get('ret_1m')  is not None else 'n/a'
            ret_3m  = f"{bkln['ret_3m']:+.1f}%" if bkln.get('ret_3m')  is not None else 'n/a'
            ret_12m = f"{bkln['ret_12m']:+.1f}%" if bkln.get('ret_12m') is not None else 'n/a'
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">Leveraged Loan ETF (BKLN) — PE credit proxy</div>
                    <div style="font-size:18px;font-weight:bold">${bkln['price']}</div>
                    <div style="font-size:11px;color:#888">
                        1m: <span style="color:{colour}">{ret_1m}</span>
                        &nbsp;|&nbsp; 3m: {ret_3m}
                        &nbsp;|&nbsp; 12m: {ret_12m}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        if ai_settings.get('ai_features', {}).get('enabled', False):
            hy  = credit_data.get('hy_spread', {})
            ig  = credit_data.get('ig_spread', {})
            bkln_d = pe_data.get('BKLN', {})
            prompt = f"""Analyse these US corporate credit readings in 3-4 sentences.
Focus on what the spread levels and trend suggest about corporate credit conditions
and risk appetite. Note any divergences between HY, IG and leveraged loans.

HY spread: {hy.get('current','n/a')}% (qoq: {hy.get('roc','n/a')})
IG spread: {ig.get('current','n/a')}% (qoq: {ig.get('roc','n/a')})
BKLN 1m return: {bkln_d.get('ret_1m','n/a')}%"""
            render_ai_assessment(prompt, ai_settings, 'corporate_credit_assessment')

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 3 — SOVEREIGN CREDIT
        # ══════════════════════════════════════════════════════════════════════
        st.subheader("🏛 Sovereign Credit")
        st.markdown("""
            <div class="info-card">
                Sovereign credit health reflects the US government's fiscal position.
                Rising debt/GDP and deficit spending are structural headwinds for
                long-term bond yields and the dollar. The critical threshold is
                when interest payments as a percentage of revenue become unsustainable —
                historically above 20% triggers bond market vigilante activity.
            </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            credit_card('debt_gdp',
                'Total federal debt as a percentage of GDP.',
                'US debt/GDP has risen from 35% in 2007 to 122%+ today. Above 130% historically associated with currency crises in smaller economies — the US reserve currency status provides buffer but is not unlimited.',
                'WARN >110% | ALERT >130%')
            credit_chart('debt_gdp', 'Federal Debt % GDP')

        with c2:
            credit_card('deficit_gdp',
                'Annual federal budget deficit as a percentage of GDP. Negative = deficit.',
                'Deficit above 5% of GDP during non-recession periods is historically unusual and inflationary. Running deficits this large during low unemployment is highly unusual.',
                'Monitor trend — sustained deficits above 5% GDP are unsustainable')
            credit_chart('deficit_gdp', 'Federal Deficit % GDP')

        if ai_settings.get('ai_features', {}).get('enabled', False):
            dbt = credit_data.get('debt_gdp', {})
            dfc = credit_data.get('deficit_gdp', {})
            prompt = f"""Analyse US sovereign credit health in 3-4 sentences.
Focus on trajectory, sustainability and key risks over the next 12 months.
Note what bond markets are likely pricing in given these readings.

Federal debt/GDP: {dbt.get('current','n/a')}% (qoq change: {dbt.get('roc','n/a')})
Federal deficit/GDP: {dfc.get('current','n/a')}% (qoq: {dfc.get('roc','n/a')})"""
            render_ai_assessment(prompt, ai_settings, 'sovereign_credit_assessment')

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 4 — PRIVATE EQUITY & BDC
        # ══════════════════════════════════════════════════════════════════════
        st.subheader("🏦 Private Equity & BDC")
        st.markdown("""
            <div class="info-card">
                Private equity firms and Business Development Companies (BDCs) are
                sensitive leading indicators of credit market health. BDCs lend
                directly to middle-market companies — their stock performance and
                dividend sustainability reflect the health of PE-backed credit.
                PE firm stock prices reflect deal flow, exit activity and credit
                availability. Deterioration here often leads public market stress
                by 2-4 months.
            </div>
        """, unsafe_allow_html=True)

        pe_rows = []
        for ticker, d in pe_data.items():
            if ticker == 'BKLN':
                continue
            pe_rows.append({
                'Ticker'  : ticker,
                'Name'    : d['name'],
                'Price'   : f"${d['price']:.2f}" if d.get('price') is not None else 'n/a',
                '1M %'    : f"{d['ret_1m']:+.1f}%" if d.get('ret_1m') is not None else 'n/a',
                '3M %'    : f"{d['ret_3m']:+.1f}%" if d.get('ret_3m') is not None else 'n/a',
                '12M %'   : f"{d['ret_12m']:+.1f}%" if d.get('ret_12m') is not None else 'n/a',
            })

        if pe_rows:
            df_pe = pd.DataFrame(pe_rows)

            def colour_ret(val):
                try:
                    v = float(str(val).replace('%','').replace('+',''))
                    if v > 0: return 'color: #2dc653'
                    if v < 0: return 'color: #e63946'
                except: pass
                return ''

            st.dataframe(
                df_pe.style.map(colour_ret, subset=['1M %','3M %','12M %']),
                width='stretch', hide_index=True
            )

        if ai_settings.get('ai_features', {}).get('enabled', False):
            pe_summary = ', '.join([
                f"{t}: 1m {d['ret_1m']:+.1f}% 3m {d['ret_3m']:+.1f}%"
                for t, d in pe_data.items() if d.get('ret_1m')
            ])
            prompt = f"""Analyse the private equity and BDC sector performance in 3 sentences.
Focus on what the collective performance signals about credit availability,
deal flow and middle-market corporate health.

PE and BDC returns: {pe_summary}"""
            render_ai_assessment(prompt, ai_settings, 'pe_assessment')

        st.divider()

        # ── Run script button ─────────────────────────────────────────────────
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh Data", type="primary"):
                run_script(os.path.join(MACRO, 'consumer_credit.py'), MACRO)
                st.rerun()
        with col2:
            rpt_file = os.path.join(credit_dir,
                                    f"{sel_date}_consumer_credit_report.txt")
            if os.path.exists(rpt_file):
                with open(rpt_file, 'r', encoding='utf-8') as f:
                    rpt_txt = f.read()
                st.download_button(
                    label     = "⬇ Download Report",
                    data      = rpt_txt,
                    file_name = f"{sel_date}_consumer_credit_report.txt",
                    mime      = 'text/plain'
                )

# ═══════════════════════════════════════════════════════════════════════════════
# AU MARKET PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "AU Market":
    st.title("AU Total Market")

    tab1, tab2, tab3, tab4 = st.tabs(["Breadth", "Zweig Thrust", "Benchmark", "Screener"])

    with tab1:
        _th1,_th2,_th3,_th4,_th5=st.columns([900,4000,1000,2000,900])
        with _th2:
            st.subheader("AU Market Breadth")
        with _th4:
            st.markdown('<br>',unsafe_allow_html=True)
            if st.button("🔄 Run AU Breadth",key='au_breadth'):
                run_script(os.path.join(STOCKS,'au_total_market_breadth.py'),STOCKS)
                st.rerun()
        _hc1, _hc2, _hc3 = st.columns([900, 10000, 900])
        with _hc2:
            st.markdown("""
                <div class="info-card">
                    Tracks daily market internals across the full ASX universe. 
                    <b style="color:#ccc">Overall</b> shows aggregate counts and SMA participation as % of total universe with D5/D20/D63 deltas. 
                    <b style="color:#ccc">By Cap Band</b> shows leader and SMA breadth broken down by large/mid/small cap. 
                    <b style="color:#ccc">Sector Breadth</b> shows per-sector leader counts and SMA participation — useful for identifying sector rotation early.
                    <br><span style="color:#666;font-size:16px">💡 Download the breadth history CSV for AI analysis — upload to an AI assistant to identify trends, divergences and rotation signals across the full history.</span>
                </div>
            """, unsafe_allow_html=True)

        history_file = os.path.join(STOCKS, 'results', 'breadth', 'au_total_market', 'au_total_market_breadth_history.csv')
        history = load_csv(history_file)

        if history is not None:
            today_str = str(history.iloc[-1]['date'])
            _dc1, _dc2, _dc3 = st.columns([900, 10000, 900])
            with _dc2:
                st.caption(f"Latest: {today_str} — {file_age(history_file)}")

        # ── AI Assessment ─────────────────────────────────────────────────
        ai_settings = load_settings()
        if history is not None and ai_settings.get('ai_features', {}).get('enabled', False):
            import importlib
            if MACRO not in __import__('sys').path:
                __import__('sys').path.insert(0, MACRO)
            importlib.invalidate_caches()
            from ai_assessment import render_ai_assessment

            today = history.iloc[-1]
            total = int(today.get('total', 0))
            leaders = int(today.get('leader', 0))
            contenders = int(today.get('contender', 0))
            laggards = int(today.get('laggard', 0))
            weak = int(today.get('weak', 0))
            ab20 = round(int(today.get('above_20', 0)) / total * 100, 1) if total > 0 else 0
            ab50 = round(int(today.get('above_50', 0)) / total * 100, 1) if total > 0 else 0
            ab200 = round(int(today.get('above_200', 0)) / total * 100, 1) if total > 0 else 0
            large_l = int(today.get('large_leaders', 0))
            mid_l   = int(today.get('mid_leaders', 0))
            small_l = int(today.get('small_leaders', 0))

            # Sector summary — top 3 and bottom 3 by leaders
            sec_summary = ''
            df_sector = locals().get('df_sector', None)
            if df_sector is not None and len(df_sector) > 0:
                top3 = df_sector.nlargest(3, 'Leaders')[['Sector','Leaders','Ab200%']].values.tolist()
                bot3 = df_sector.nsmallest(3, 'Leaders')[['Sector','Leaders','Ab200%']].values.tolist()
                sec_summary = (
                    'Top sectors (leaders): ' +
                    ', '.join([f"{r[0]} ({r[1]})" for r in top3]) +
                    '. Bottom sectors: ' +
                    ', '.join([f"{r[0]} ({r[1]})" for r in bot3])
                )

            # D5 deltas
            d5_row = get_past_row(history, str(today['date']), 7)
            d5_leaders = int(today.get('leader', 0)) - int(d5_row.get('leader', 0)) if d5_row is not None else 0
            d5_ab200   = round(ab200 - (int(d5_row.get('above_200', 0)) / int(d5_row.get('total', total)) * 100), 1) if d5_row is not None else 0

            prompt = f"""You are a market breadth analyst for the Australian stock market (ASX).
Analyse these breadth readings and provide a concise 4-5 sentence assessment.
Focus on: (1) overall market health and trend, (2) cap band divergences (large vs small),
(3) key sector rotations, (4) what the breadth signals suggest about near-term direction.
Be direct and specific — mention actual numbers.

Date: {today['date']}
Universe: {total} stocks
Leaders: {leaders} ({round(leaders/total*100,1)}%) | Contenders: {contenders} | Laggards: {laggards} | Weak: {weak} ({round(weak/total*100,1)}%)
Above 20 SMA: {ab20}% | Above 50 SMA: {ab50}% | Above 200 SMA: {ab200}%
5-day change — Leaders: {d5_leaders:+d} | Above 200 SMA: {d5_ab200:+.1f}%
Cap band leaders — Large: {large_l} | Mid: {mid_l} | Small: {small_l}
{sec_summary}"""

            _aic1, _aic2, _aic3 = st.columns([900, 10000, 900])
            with _aic2:
                render_ai_assessment(prompt, ai_settings, 'au_breadth_summary')

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Overall**")
            overall_metrics = [
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
            ]
            df_overall = build_breadth_table(history, overall_metrics)
            if df_overall is not None:
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(
                        style_breadth(df_overall, delta_cols=['D5','D20','D63']),
                        width='stretch', hide_index=True, height=460
                    )

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**By Cap Band**")
            cap_metrics = [
                ('Large Leaders',  'large_leaders'),
                ('Large Ab20',     'large_above20'),
                ('Large Ab50',     'large_above50'),
                ('Large Ab200',    'large_above200'),
                ('Mid Leaders',    'mid_leaders'),
                ('Mid Ab20',       'mid_above20'),
                ('Mid Ab50',       'mid_above50'),
                ('Mid Ab200',      'mid_above200'),
                ('Small Leaders',  'small_leaders'),
                ('Small Ab20',     'small_above20'),
                ('Small Ab50',     'small_above50'),
                ('Small Ab200',    'small_above200'),
            ]
            df_cap = build_breadth_table(history, cap_metrics)
            if df_cap is not None:
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(
                        style_breadth(df_cap, delta_cols=['D5','D20','D63']),
                        width='stretch', hide_index=True, height=370
                    )

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Sector Breadth**")
            sec_cols  = [c for c in history.columns if c.startswith('sec_') and c.endswith('_total')
                         and not c.startswith('sp_sec_') and not c.startswith('rus_sec_')]
            sec_keys  = [c.replace('sec_','').replace('_total','') for c in sec_cols
                         if 'nan' not in c and 'index' not in c]
            df_sector = build_sector_table(history, sec_keys, prefix='sec')
            if df_sector is not None:
                _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                sector_breadth_caption()
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(
                        style_breadth(df_sector, delta_cols=['dL5','dL63']),
                        width='stretch', hide_index=True, height=600
                    )

        else:
            st.warning("No breadth history found")


    with tab2:
        st.subheader("Zweig Breadth Thrust")
        history_file = os.path.join(STOCKS, 'results', 'breadth', 'au_total_market',
                                    'au_total_market_breadth_history.csv')
        zweig_history = load_csv(history_file)
        if zweig_history is not None:
            render_zweig_section(zweig_history, 'sec', 'AU Market', show_sector=True)
        else:
            st.warning("No breadth history found — run AU breadth script first")

    with tab3:
        st.subheader("Benchmark vs VAS.AX")
        st.markdown("""
            <div class="info-card">
                Ranks all ASX stocks by relative strength versus the <b style="color:#ccc">VAS.AX</b> benchmark (Vanguard Australian Shares ETF).
                <b style="color:#ccc">RS Ratio</b> &gt; 1.0 means outperforming the benchmark over 12 months.
                <b style="color:#ccc">Regime</b>: TREND+LEAD = outperforming AND above 200 SMA — highest quality. TREND_ONLY = above 200 SMA but lagging benchmark. WEAK = below 200 SMA.
                <b style="color:#ccc">Acc Watch</b>: accumulation signal for large/mid caps — EARLY (below all SMAs), PROGRESS (crossed 20 SMA), SHIFT (crossed 50 SMA).
                <b style="color:#ccc">Score</b> combines 12M return, persistence, drawdown, MQS, RS trend and regime bonus.
            </div>
        """, unsafe_allow_html=True)
        bm_file = os.path.join(STOCKS, 'results', 'benchmark', 'au_total_market', 'au_total_market_latest_formatted.csv')
        df = load_csv(bm_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(bm_file)} — {len(df)} stocks")
            # ── AI Rotation Assessment ────────────────────────────────────────
            ai_settings = load_settings()
            if ai_settings.get('ai_features', {}).get('enabled', False):
                import importlib
                if MACRO not in __import__('sys').path:
                    __import__('sys').path.insert(0, MACRO)
                importlib.invalidate_caches()
                from ai_assessment import render_ai_assessment
                ai_prompt = build_benchmark_ai_prompt(df.reset_index(), 'AU Market', group_col='sector')
                if ai_prompt:
                    render_ai_assessment(ai_prompt, ai_settings, 'au_bm_rotation')
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'rs_ratio','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            col1, col2, col3 = st.columns(3)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['TREND+LEAD','TREND_ONLY','WEAK'],
                    default=['TREND+LEAD','TREND_ONLY'],
                    key='au_bm_regime')
            with col2:
                sector_filter = st.multiselect("Filter sector",
                    sorted(df['sector'].dropna().unique().tolist()),
                    key='au_bm_sector')
            with col3:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='au_bm_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run AU Benchmark", key='au_bm'):
            run_script(os.path.join(STOCKS, 'au_total_market_benchmark.py'), STOCKS)
            st.rerun()

    with tab4:
        st.subheader("Sector Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks stocks by relative strength versus their <b style="color:#ccc">sector peers</b> rather than the overall market benchmark.
                <b style="color:#ccc">Peer RS Score</b> is a percentile rank (0–100) — 90 means outperforming 90% of stocks in the same sector over 12 months.
                <b style="color:#ccc">Regime</b>: LEADER = top 25% of peers AND above 200 SMA. CONTENDER = top 50% AND above 200 SMA. LAGGARD = below median peers. WEAK = below median AND below 200 SMA.
                Use this alongside the Benchmark tab — a stock ranking highly on both is leading its sector AND the broader market.
            </div>
        """, unsafe_allow_html=True)
        sc_file = os.path.join(STOCKS, 'results', 'screener', 'au_total_market', 'au_total_market_latest_formatted.csv')
        df = load_csv(sc_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            
            col1, col2, col3 = st.columns(3)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['LEADER','CONTENDER','LAGGARD','WEAK'],
                    default=['LEADER','CONTENDER'],
                    key='au_sc_regime')
            with col2:
                sector_filter = st.multiselect("Filter sector",
                    sorted(df['sector'].dropna().unique().tolist()),
                    key='au_sc_sector')
            with col3:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='au_sc_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No screener results found")
        if st.button("🔄 Run AU Screener", key='au_sc'):
            run_script(os.path.join(STOCKS, 'au_total_market_screener.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# US MARKET PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "US Market":
    st.title("US Total Market")

    tab1, tab2, tab3, tab4 = st.tabs(["Breadth", "Zweig Thrust", "Benchmark", "Screener"])

    with tab1:
        _th1,_th2,_th3,_th4,_th5=st.columns([900,4000,1000,2000,900])
        with _th2:
            st.subheader("US Market Breadth")
        with _th4:
            st.markdown('<br>',unsafe_allow_html=True)
            if st.button("🔄 Run US Breadth",key='us_breadth'):
                run_script(os.path.join(STOCKS,'us_total_market_breadth.py'),STOCKS)
                st.rerun()
        _hc1, _hc2, _hc3 = st.columns([900, 10000, 900])
        with _hc2:
            st.markdown("""
                <div class="info-card">
                    Three-layer breadth analysis of the US market.
                    <b style="color:#ccc">Layer 1</b>: full universe of 1,500+ US stocks.
                    <b style="color:#ccc">Layer 2</b>: S&P 500/Nasdaq quality subset (~515 stocks) — higher quality names with sector data.
                    <b style="color:#ccc">Layer 3</b>: Russell 2000 proxy (~1,000 smaller stocks) — leading indicator for risk appetite.
                    Divergence between layers is a key signal — e.g. Layer 2 breadth holding while Layer 3 deteriorates signals large cap defensiveness.
                    <br><span style="color:#666;font-size:16px">💡 Download the breadth history CSV for AI analysis — upload to identify trend divergences, rotation signals and breadth thrust patterns across the full history.</span>
                </div>
            """, unsafe_allow_html=True)

        history_file = os.path.join(STOCKS, 'results', 'breadth', 'us_total_market', 'us_total_market_breadth_history.csv')
        history = load_csv(history_file)

        if history is not None:
            today_str = str(history.iloc[-1]['date'])
            _dc1, _dc2, _dc3 = st.columns([900, 10000, 900])
            with _dc2:
                st.caption(f"Latest: {today_str} — {file_age(history_file)}")

        # ── AI Assessment ─────────────────────────────────────────────────
        ai_settings = load_settings()
        if history is not None and ai_settings.get('ai_features', {}).get('enabled', False):
            import importlib
            if MACRO not in __import__('sys').path:
                __import__('sys').path.insert(0, MACRO)
            importlib.invalidate_caches()
            from ai_assessment import render_ai_assessment

            today = history.iloc[-1]
            total   = int(today.get('total', 0))
            leaders = int(today.get('leader', 0))
            weak    = int(today.get('weak', 0))
            ab20    = round(int(today.get('above_20', 0)) / total * 100, 1) if total > 0 else 0
            ab50    = round(int(today.get('above_50', 0)) / total * 100, 1) if total > 0 else 0
            ab200   = round(int(today.get('above_200', 0)) / total * 100, 1) if total > 0 else 0

            # Layer 2 (SP500 quality)
            sp_total   = int(today.get('sp_total', 0))
            sp_leaders = int(today.get('sp_leader', 0))
            sp_ab200   = round(int(today.get('sp_above_200', 0)) / sp_total * 100, 1) if sp_total > 0 else 0

            # Layer 3 (Russell)
            rus_total   = int(today.get('rus_total', 0))
            rus_leaders = int(today.get('rus_leader', 0))
            rus_ab200   = round(int(today.get('rus_above_200', 0)) / rus_total * 100, 1) if rus_total > 0 else 0

            # Cap band
            large_l = int(today.get('large_leaders', 0))
            mid_l   = int(today.get('mid_leaders', 0))
            small_l = int(today.get('small_leaders', 0))

            # D5 deltas
            d5_row = get_past_row(history, str(today['date']), 7)
            d5_leaders = leaders - int(d5_row.get('leader', 0)) if d5_row is not None else 0
            d5_ab200   = round(ab200 - (int(d5_row.get('above_200', 0)) / int(d5_row.get('total', total)) * 100), 1) if d5_row is not None else 0
            d5_sp_ab200  = round(sp_ab200  - (int(d5_row.get('sp_above_200', 0))  / int(d5_row.get('sp_total', sp_total or 1)) * 100), 1) if d5_row is not None else 0
            d5_rus_ab200 = round(rus_ab200 - (int(d5_row.get('rus_above_200', 0)) / int(d5_row.get('rus_total', rus_total or 1)) * 100), 1) if d5_row is not None else 0

            # Zweig status
            zweig_status = ''
            try:
                adv = history['leader'].astype(float)
                dec = history['laggard'].astype(float)
                zr  = calc_zweig_thrust(adv, dec)
                if zr:
                    zweig_status = f"Zweig EMA10: {zr['current_ema']:.4f} — Status: {zr['status']}"
            except:
                pass

            # SP sector summary
            sec_summary = ''
            df_sp_sec = locals().get('df_sp_sec', None)
            if df_sp_sec is not None and len(df_sp_sec) > 0:
                top3 = df_sp_sec.nlargest(3, 'Leaders')[['Sector','Leaders','Ab200%']].values.tolist()
                bot3 = df_sp_sec.nsmallest(3, 'Leaders')[['Sector','Leaders','Ab200%']].values.tolist()
                sec_summary = (
                    'SP500 top sectors: ' +
                    ', '.join([f"{r[0]} ({r[1]})" for r in top3]) +
                    '. Bottom: ' +
                    ', '.join([f"{r[0]} ({r[1]})" for r in bot3])
                )

            prompt = f"""You are a market breadth analyst for the US stock market.
Analyse these three-layer breadth readings and provide a 5-6 sentence assessment.
Focus on: (1) overall market health trend, (2) divergence between large cap quality (Layer 2)
and small cap risk appetite (Layer 3), (3) cap band leadership, (4) sector rotation signals,
(5) what the Zweig Breadth Thrust status implies about near-term momentum.
Be direct — reference specific numbers and note any concerning divergences.

Date: {today['date']}
Layer 1 (Full universe {total} stocks): Leaders {leaders} ({round(leaders/total*100,1)}%) | Weak {weak} ({round(weak/total*100,1)}%) | Ab200: {ab200}% ({d5_ab200:+.1f}% 5d)
Layer 2 (SP500 quality {sp_total} stocks): Leaders {sp_leaders} ({round(sp_leaders/sp_total*100,1) if sp_total else 0}%) | Ab200: {sp_ab200}% ({d5_sp_ab200:+.1f}% 5d)
Layer 3 (Russell proxy {rus_total} stocks): Leaders {rus_leaders} ({round(rus_leaders/rus_total*100,1) if rus_total else 0}%) | Ab200: {rus_ab200}% ({d5_rus_ab200:+.1f}% 5d)
Cap band leaders — Large: {large_l} | Mid: {mid_l} | Small: {small_l}
5-day overall change — Leaders: {d5_leaders:+d}
{zweig_status}
{sec_summary}"""

            _aic1, _aic2, _aic3 = st.columns([900, 10000, 900])
            with _aic2:
                render_ai_assessment(prompt, ai_settings, 'us_breadth_summary')

            overall_metrics = [
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

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Layer 1 — Full Universe**")
            df_l1 = build_breadth_table(history, overall_metrics)
            if df_l1 is not None:
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_l1, delta_cols=['D5','D20','D63']),
                                 width='stretch', hide_index=True, height=680)

            sec_cols = [c for c in history.columns if c.startswith('sec_') and c.endswith('_total')
                        and not c.startswith('sp_sec_') and not c.startswith('rus_sec_')]
            sec_keys = [c.replace('sec_','').replace('_total','') for c in sec_cols
                        if 'nan' not in c and 'index' not in c]
            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Layer 1 Sector Breadth**")
            df_sec = build_sector_table(history, sec_keys, prefix='sec')
            if df_sec is not None:
                _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                sector_breadth_caption()
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_sec, delta_cols=['dL5','dL63']),
                                 width='stretch', hide_index=True, height=500)

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Layer 2 — SP500/Nasdaq Quality**")
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
            df_l2 = build_breadth_table(history, l2_metrics)
            if df_l2 is not None:
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_l2, delta_cols=['D5','D20','D63']),
                                 width='stretch', hide_index=True, height=520)

            sp_sec_cols = [c for c in history.columns if c.startswith('sp_sec_') and c.endswith('_total')]
            sp_sec_keys = [c.replace('sp_sec_','').replace('_total','') for c in sp_sec_cols
                           if 'nan' not in c and 'index' not in c]
            if sp_sec_keys:
                _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Layer 2 Sector Breadth**")
                df_sp_sec = build_sector_table(history, sp_sec_keys, prefix='sp_sec')
                if df_sp_sec is not None:
                    _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
                    with _lbc2:
                        sector_breadth_caption()
                    _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                    with _bc2:
                        st.dataframe(style_breadth(df_sp_sec, delta_cols=['dL5','dL63']),
                                     width='stretch', hide_index=True, height=500)

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Layer 3 — Russell Proxy**")
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
            df_l3 = build_breadth_table(history, l3_metrics)
            if df_l3 is not None:
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_l3, delta_cols=['D5','D20','D63']),
                                 width='stretch', hide_index=True, height=520)

            rus_sec_cols = [c for c in history.columns if c.startswith('rus_sec_') and c.endswith('_total')]
            rus_sec_keys = [c.replace('rus_sec_','').replace('_total','') for c in rus_sec_cols
                            if 'nan' not in c and 'index' not in c]
            if rus_sec_keys:
                _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Layer 3 Sector Breadth**")
                df_rus_sec = build_sector_table(history, rus_sec_keys, prefix='rus_sec')
                if df_rus_sec is not None:
                    _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
                    with _lbc2:
                        sector_breadth_caption()
                    _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                    with _bc2:
                        st.dataframe(style_breadth(df_rus_sec, delta_cols=['dL5','dL63']),
                                     width='stretch', hide_index=True, height=500)
        else:
            st.warning("No breadth history found")


    with tab2:
        st.subheader("Zweig Breadth Thrust")
        history_file = os.path.join(STOCKS, 'results', 'breadth', 'us_total_market', 'us_total_market_breadth_history.csv')
        history = load_csv(history_file)
        if history is not None:
            render_zweig_section(history, 'sp_sec', 'US Market', show_sector=True)
        else:
            st.warning("No breadth history found — run US breadth script first")

    with tab3:
        st.subheader("Benchmark vs SPY")
        st.markdown("""
            <div class="info-card">
                Ranks US stocks by relative strength versus <b style="color:#ccc">SPY</b> (S&P 500 ETF).
                Same regime and scoring methodology as AU Benchmark. 
                <b style="color:#ccc">Acc Watch</b> signals are particularly useful in the US market — large/mid cap institutional accumulation below key SMAs often precedes significant moves.
                Filter by sector to identify which industries are producing the most leaders relative to the broader market.
            </div>
        """, unsafe_allow_html=True)
        bm_file = os.path.join(STOCKS, 'results', 'benchmark', 'us_total_markets', 'us_total_market_latest_formatted.csv')
        df = load_csv(bm_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(bm_file)} — {len(df)} stocks")
            # ── AI Rotation Assessment ────────────────────────────────────────
            ai_settings = load_settings()
            if ai_settings.get('ai_features', {}).get('enabled', False):
                import importlib
                if MACRO not in __import__('sys').path:
                    __import__('sys').path.insert(0, MACRO)
                importlib.invalidate_caches()
                from ai_assessment import render_ai_assessment
                ai_prompt = build_benchmark_ai_prompt(df.reset_index(), 'US Market', group_col='sector')
                if ai_prompt:
                    render_ai_assessment(ai_prompt, ai_settings, 'us_bm_rotation')
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'rs_ratio','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns

            col1, col2, col3 = st.columns(3)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['TREND+LEAD','TREND_ONLY','WEAK'],
                    default=['TREND+LEAD','TREND_ONLY'],
                    key='us_bm_regime')
            with col2:
                sector_filter = st.multiselect("Filter sector",
                    sorted(df['sector'].dropna().unique().tolist()),
                    key='us_bm_sector')
            with col3:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='us_bm_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run US Benchmark", key='us_bm'):
            run_script(os.path.join(STOCKS, 'us_total_market_benchmark.py'), STOCKS)
            st.rerun()

    with tab4:
        st.subheader("Sector Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks US stocks by relative strength versus their <b style="color:#ccc">sector peers</b>.
                With 1,500+ stocks the peer group is large — a Peer RS Score above 90 means genuinely exceptional relative performance within the sector.
                Cross-reference with the RRG Charts page to confirm sector-level momentum before drilling into individual names.
            </div>
        """, unsafe_allow_html=True)
        sc_file = os.path.join(STOCKS, 'results', 'screener', 'us_total_market', 'us_total_market_latest_formatted.csv')
        df = load_csv(sc_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
           
            col1, col2, col3 = st.columns(3)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['LEADER','CONTENDER','LAGGARD','WEAK'],
                    default=['LEADER','CONTENDER'],
                    key='us_sc_regime')
            with col2:
                sector_filter = st.multiselect("Filter sector",
                    sorted(df['sector'].dropna().unique().tolist()),
                    key='us_sc_sector')
            with col3:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='us_sc_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No screener results found")
        if st.button("🔄 Run US Screener", key='us_sc'):
            run_script(os.path.join(STOCKS, 'us_total_market_screener.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# COMMODITIES PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Commodities":
    st.title("⛏ All Major Commodities")

    tab1, tab2, tab3 = st.tabs(["Breadth", "Benchmark", "Screener"])

    with tab1:
        _th1,_th2,_th3,_th4,_th5=st.columns([900,4000,1000,2000,900])
        with _th2:
            st.subheader("Commodities Breadth")
        with _th4:
            st.markdown('<br>',unsafe_allow_html=True)
            if st.button("🔄 Run Commodities Breadth",key='comm_breadth'):
                run_script(os.path.join(STOCKS,'all_major_commodities_breadth.py'),STOCKS)
                st.rerun()
        _hc1, _hc2, _hc3 = st.columns([900, 10000, 900])
        with _hc2:
            st.markdown("""
                <div class="info-card">
                    Breadth analysis across 390 tickers covering gold, silver, copper, uranium, lithium, platinum and palladium.
                    <b style="color:#ccc">By Commodity</b> shows leader counts and SMA participation per metal — useful for identifying which commodity groups are leading.
                    <b style="color:#ccc">Junior vs Senior Rotation</b> shows large/mid/small cap breakdown within each commodity — junior miners leading seniors is a classic early cycle signal.
                    <b style="color:#ccc">By Type</b> shows producers vs explorers vs ETFs — explorer breadth expanding signals speculative risk appetite returning.
                    <br><span style="color:#666;font-size:16px">💡 Download the breadth history CSV for AI analysis — commodity breadth history is particularly useful for identifying cycle turning points.</span>
                </div>
            """, unsafe_allow_html=True)

        history_file = os.path.join(STOCKS, 'results', 'breadth', 'all_major_commodities', 'all_major_commodities_breadth_history.csv')
        history = load_csv(history_file)

        if history is not None:
            today_str = str(history.iloc[-1]['date'])
            _dc1, _dc2, _dc3 = st.columns([900, 10000, 900])
            with _dc2:
                st.caption(f"Latest: {today_str} — {file_age(history_file)}")

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Overall**")
            overall_metrics = [
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
                ('Large Leaders', 'large_leaders'),
                ('Mid Leaders',   'mid_leaders'),
                ('Small Leaders', 'small_leaders'),
            ]
            df_overall = build_breadth_table(history, overall_metrics)
            if df_overall is not None:
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_overall, delta_cols=['D5','D20','D63']),
                                 width='stretch', hide_index=True, height=520)

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**By Commodity**")
            comm_cols = [c for c in history.columns if c.startswith('comm_') and c.endswith('_total')
                         and c.count('_') == 2]
            comm_keys = [c.replace('comm_','').replace('_total','') for c in comm_cols
                         if c.count('_') == 2 and 'unknown' not in c.lower()]

            today     = history.iloc[-1]
            today_str = str(today['date'])
            d5        = get_past_row(history, today_str, 7)
            d63       = get_past_row(history, today_str, 91)

            comm_rows = []
            for ck in comm_keys:
                try:
                    comm_total = int(today[f'comm_{ck}_total'])
                    comm_rows.append({
                        'Commodity' : ck.title(),
                        'Total'     : comm_total,
                        'Leaders'   : int(today[f'comm_{ck}_leaders']),
                        'dL5'       : delta_val(today, d5,  f'comm_{ck}_leaders')  if d5  is not None else 'n/a',
                        'dL63'      : delta_val(today, d63, f'comm_{ck}_leaders')  if d63 is not None else 'n/a',
                        'Ab20%'     : f"{round(int(today[f'comm_{ck}_above20'])  / comm_total * 100, 1)}%" if comm_total > 0 else '0%',
                        'Ab50%'     : f"{round(int(today[f'comm_{ck}_above50'])  / comm_total * 100, 1)}%" if comm_total > 0 else '0%',
                        'Ab200%'    : f"{round(int(today[f'comm_{ck}_above200']) / comm_total * 100, 1)}%" if comm_total > 0 else '0%',
                        'HVol'      : int(today[f'comm_{ck}_high_vol']),
                        'AccEarly'  : int(today[f'comm_{ck}_acc_early']),
                    })
                except:
                    continue
            if comm_rows:
                df_comm = pd.DataFrame(comm_rows)
                _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
                with _lbc2:
                    sector_breadth_caption()
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_comm, delta_cols=['dL5','dL63']),
                                 width='stretch', hide_index=True)

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**Junior vs Senior Rotation**")
            jr_rows = []
            for ck in comm_keys:
                for band in ['large', 'mid', 'small']:
                    try:
                        jr_rows.append({
                            'Commodity/Band' : f"{ck.title()} {band}",
                            'Total'          : int(today[f'comm_{ck}_{band}_total']),
                            'Leaders'        : int(today[f'comm_{ck}_{band}_leaders']),
                            'Ab200'          : int(today[f'comm_{ck}_{band}_above200']),
                            'dL5'            : delta_val(today, d5,  f'comm_{ck}_{band}_leaders') if d5  is not None else 'n/a',
                            'dL63'           : delta_val(today, d63, f'comm_{ck}_{band}_leaders') if d63 is not None else 'n/a',
                        })
                    except:
                        continue
            if jr_rows:
                df_jr = pd.DataFrame(jr_rows)
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_jr, delta_cols=['dL5','dL63']),
                                 width='stretch', hide_index=True)

            _lbc1, _lbc2, _lbc3 = st.columns([900, 10000, 900])
            with _lbc2:
                st.markdown("**By Type**")
            type_cols = [c for c in history.columns if c.startswith('type_') and c.endswith('_total')]
            type_keys = [c.replace('type_','').replace('_total','') for c in type_cols]
            type_rows = []
            for tk in type_keys:
                try:
                    type_rows.append({
                        'Type'    : tk.replace('_', ' ').title(),
                        'Total'   : int(today[f'type_{tk}_total']),
                        'Leaders' : int(today[f'type_{tk}_leaders']),
                        'Ab200'   : int(today[f'type_{tk}_above200']),
                        'dL5'     : delta_val(today, d5,  f'type_{tk}_leaders') if d5  is not None else 'n/a',
                        'dL63'    : delta_val(today, d63, f'type_{tk}_leaders') if d63 is not None else 'n/a',
                    })
                except:
                    continue
            if type_rows:
                df_type = pd.DataFrame(type_rows)
                _bc1, _bc2, _bc3 = st.columns([900, 10000, 900])
                with _bc2:
                    st.dataframe(style_breadth(df_type, delta_cols=['dL5','dL63']),
                                 width='stretch', hide_index=True)
        else:
            st.warning("No breadth history found")


    with tab2:
        st.subheader("Benchmark vs ETF")
        st.markdown("""
            <div class="info-card">
                Ranks commodity stocks by relative strength versus their <b style="color:#ccc">commodity ETF benchmark</b> 
                (GDX for gold, SIL for silver, COPX for copper, URA for uranium, LIT for lithium).
                Filter by commodity to see rankings within a single metal. Filter by type to compare producers vs explorers vs ETFs.
                A stock ranked highly here is outperforming not just its peers but the overall commodity ETF — the strongest names in the strongest commodities.
            </div>
        """, unsafe_allow_html=True)
        bm_file = os.path.join(STOCKS, 'results', 'benchmark', 'all_major_commodities', 'all_major_commodities_latest_formatted.csv')
        df = load_csv(bm_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(bm_file)} — {len(df)} stocks")
            # ── AI Rotation Assessment ────────────────────────────────────────
            ai_settings = load_settings()
            if ai_settings.get('ai_features', {}).get('enabled', False):
                import importlib
                if MACRO not in __import__('sys').path:
                    __import__('sys').path.insert(0, MACRO)
                importlib.invalidate_caches()
                from ai_assessment import render_ai_assessment
                ai_prompt = build_benchmark_ai_prompt(df.reset_index(), 'Commodities', group_col='commodity')
                if ai_prompt:
                    render_ai_assessment(ai_prompt, ai_settings, 'comm_bm_rotation')
            cols = ['delta_rank','ticker','name','commodity','type','cap_band','close',
                    'rs_ratio','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['TREND+LEAD','TREND_ONLY','WEAK'],
                    default=['TREND+LEAD','TREND_ONLY'],
                    key='comm_bm_regime')
            with col2:
                comm_filter = st.multiselect("Filter commodity",
                    sorted(df['commodity'].dropna().unique().tolist()),
                    key='comm_bm_comm')
            with col3:
                type_filter = st.multiselect("Filter type",
                    sorted(df['type'].dropna().unique().tolist()),
                    key='comm_bm_type')
            with col4:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='comm_bm_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if comm_filter:
                df = df[df['commodity'].isin(comm_filter)]
            if type_filter:
                df = df[df['type'].isin(type_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run Commodities Benchmark", key='comm_bm'):
            run_script(os.path.join(STOCKS, 'all_major_commodities_benchmark.py'), STOCKS)
            st.rerun()

    with tab3:
        st.subheader("Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks commodity stocks by relative strength versus <b style="color:#ccc">commodity peers</b> — gold stocks vs gold stocks, copper vs copper etc.
                Use the commodity filter to focus on a single metal and find the intra-commodity leaders.
                Combined with the Benchmark tab — a stock leading both its commodity peers AND the commodity ETF is the highest conviction name in that metal.
            </div>
        """, unsafe_allow_html=True)

        sc_file = os.path.join(STOCKS, 'results', 'screener', 'all_major_commodities', 'all_major_commodities_latest_formatted.csv')
        df = load_csv(sc_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','commodity','type','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['LEADER','CONTENDER','LAGGARD','WEAK'],
                    default=['LEADER','CONTENDER'],
                    key='comm_sc_regime')
            with col2:
                comm_filter = st.multiselect("Filter commodity",
                    sorted(df['commodity'].dropna().unique().tolist()),
                    key='comm_sc_comm')
            with col3:
                type_filter = st.multiselect("Filter type",
                    sorted(df['type'].dropna().unique().tolist()),
                    key='comm_sc_type')
            with col4:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='comm_sc_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if comm_filter:
                df = df[df['commodity'].isin(comm_filter)]
            if type_filter:
                df = df[df['type'].isin(type_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No screener results found")
        if st.button("🔄 Run Commodities Screener", key='comm_sc'):
            run_script(os.path.join(STOCKS, 'all_major_commodities_screener.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# URANIUM PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Uranium":
    st.title("☢ Uranium")

    tab1, tab2 = st.tabs(["Benchmark", "Screener"])

    with tab1:
        st.subheader("Benchmark vs URA")
        st.markdown("""
            <div class="info-card">
                Ranks 47 uranium stocks versus <b style="color:#ccc">URA</b> (Global X Uranium ETF).
                Universe includes uranium miners, explorers, nuclear construction and nuclear power companies.
                RS Ratio &gt; 1.0 means outperforming the uranium ETF — identifies names capturing more upside than the sector average.
            </div>
        """, unsafe_allow_html=True)

        bm_file = os.path.join(STOCKS, 'results', 'benchmark', 'uranium', 'uranium_latest_formatted.csv')
        df = load_csv(bm_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(bm_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'rs_ratio','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            
            col1, col2 = st.columns(2)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['TREND+LEAD','TREND_ONLY','WEAK'],
                    default=['TREND+LEAD','TREND_ONLY'],
                    key='ura_bm_regime')
            with col2:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='ura_bm_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run Uranium Benchmark", key='ura_bm'):
            run_script(os.path.join(STOCKS, 'uranium_benchmark.py'), STOCKS)
            st.rerun()

    with tab2:
        st.subheader("Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks uranium stocks by relative strength versus <b style="color:#ccc">uranium peers</b>.
                With only 47 stocks the peer group is tight — a Peer RS Score of 80+ puts a stock in the top 20% of the uranium universe.
                Cross-reference with the Benchmark tab — leaders on both are the highest quality uranium names.
            </div>
        """, unsafe_allow_html=True)

        sc_file = os.path.join(STOCKS, 'results', 'screener', 'uranium', 'uranium_latest_formatted.csv')
        df = load_csv(sc_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            
            col1, col2 = st.columns(2)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['LEADER','CONTENDER','LAGGARD','WEAK'],
                    default=['LEADER','CONTENDER'],
                    key='ura_sc_regime')
            with col2:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='ura_sc_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No screener results found")
        if st.button("🔄 Run Uranium Screener", key='ura_sc'):
            run_script(os.path.join(STOCKS, 'uranium_screener.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# AU GOLD MINERS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "AU Gold Miners":
    st.title("🥇 AU Gold Miners")

    tab1, tab2 = st.tabs(["Benchmark", "Screener"])

    with tab1:
        st.subheader("Benchmark vs GDX")
        st.markdown("""
            <div class="info-card">
                Ranks 154 ASX gold mining stocks versus <b style="color:#ccc">GDX</b> (VanEck Gold Miners ETF).
                GDX is a global benchmark — ASX stocks ranked highly here are outperforming not just local peers but the best gold miners globally.
                Includes producers, developers, explorers and royalty companies.
            </div>
        """, unsafe_allow_html=True)
        bm_file = os.path.join(STOCKS, 'results', 'benchmark', 'au_gold_miners', 'au_gold_miners_latest_formatted.csv')
        df = load_csv(bm_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(bm_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'rs_ratio','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            
            col1, col2 = st.columns(2)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['TREND+LEAD','TREND_ONLY','WEAK'],
                    default=['TREND+LEAD','TREND_ONLY'],
                    key='gold_bm_regime')
            with col2:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='gold_bm_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run AU Gold Benchmark", key='gold_bm'):
            run_script(os.path.join(STOCKS, 'au_gold_miners_benchmark.py'), STOCKS)
            st.rerun()

    with tab2:
        st.subheader("Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks ASX gold stocks by relative strength versus <b style="color:#ccc">ASX gold mining peers</b>.
                With 154 stocks the peer group is broad enough to be meaningful — a Peer RS Score above 85 puts a stock in the top 15% of ASX gold miners.
                Use alongside the Benchmark tab and the Commodities page gold filter for a complete picture of gold stock leadership.
            </div>
        """, unsafe_allow_html=True)
        sc_file = os.path.join(STOCKS, 'results', 'screener', 'au_gold_miners', 'au_gold_miners_latest_formatted.csv')
        df = load_csv(sc_file, index_col='rank')
        if df is not None:
            st.caption(f"Last updated: {file_age(sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            # Format numeric columns
            
            col1, col2 = st.columns(2)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['LEADER','CONTENDER','LAGGARD','WEAK'],
                    default=['LEADER','CONTENDER'],
                    key='gold_sc_regime')
            with col2:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='gold_sc_acc')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600)
        else:
            st.warning("No screener results found")
        if st.button("🔄 Run AU Gold Screener", key='gold_sc'):
            run_script(os.path.join(STOCKS, 'au_gold_miners_screener.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# RRG PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "RRG Charts":
    import plotly.graph_objects as go

    st.title("📡 Relative Rotation Graph")
    st.caption("RS-Ratio vs RS-Momentum — tails show last 63 trading days")

    tab1, tab2 = st.tabs(["🇦🇺 AU vs XJO", "🇺🇸 US vs SPY"])

    def build_rrg(history_file, title):
        history = load_csv(history_file)
        if history is None or len(history) == 0:
            st.warning(f"No RRG data found — run data collection script first")
            return

        history['date'] = pd.to_datetime(history['date'])
        latest_date     = history['date'].max()
        st.caption(f"Latest: {latest_date.strftime('%d %b %Y')} — {file_age(history_file)}")

        # Controls
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            tail_range = st.slider(
                "Tail range (trading days)",
                min_value=1, max_value=252, value=(1, 20),
                key=f"tail_{title}",
                help="Left = recent end of tail  |  Right = oldest end. Tail always ends at most recent date."
            )
            tail_to, tail_from = tail_range[0], tail_range[1]
        with col2:
            groups      = sorted(history['group'].unique().tolist())
            sel_groups  = st.multiselect("Filter groups", groups, default=groups, key=f"grp_{title}")
        with col3:
            show_labels = st.toggle("Show labels", value=True, key=f"lbl_{title}")
            smooth_span = st.slider("Smoothing (EWM span)", 1, 20, 20, key=f"span_{title}")
        with col4:
            all_tickers = sorted(history['ticker'].unique().tolist())
            sel_tickers = st.multiselect("Filter tickers", all_tickers, default=[],
                                          key=f"tick_{title}", placeholder="All tickers")

        # Filter by date window and group/ticker
        cutoff_from = latest_date - pd.Timedelta(days=int(tail_from * 1.5))
        cutoff_to   = latest_date - pd.Timedelta(days=max(0, tail_to - 1))
        df      = history[(history['date'] >= cutoff_from) & (history['date'] <= cutoff_to + pd.Timedelta(days=2))].copy()
        # Cap to tail_from rows per ticker
        df      = df.groupby('ticker', group_keys=False).apply(lambda x: x.sort_values('date').tail(tail_from))
        df      = df[df['group'].isin(sel_groups)]
        if sel_tickers:
            df = df[df['ticker'].isin(sel_tickers)]
        tickers = df['ticker'].unique()
        tail_days = tail_from

        # Colour palette — distinct per ticker
        _rrg_light = _get_theme_mode() == 'light'
        COLOURS = [
            '#00b4d8','#90e0ef','#48cae4',
            '#f77f00','#fcbf49','#eae2b7',
            '#2dc653','#80b918','#aacc00',
            '#e63946','#ff6b6b','#ffadad',
            '#9b5de5','#c77dff','#e0aaff',
            '#f15bb5','#fee440','#00bbf9',
            '#06d6a0','#118ab2','#ffd166',
            '#ef476f','#b7e4c7','#40916c',
        ] if not _rrg_light else [
            '#0077a8','#005f87','#0096c7',
            '#c96a00','#a85500','#8b6914',
            '#1a8a3a','#4a7c00','#2d6a00',
            '#c0152a','#d93d3d','#a01020',
            '#6a20c8','#8b00cc','#5c0fa8',
            '#c4006a','#b8970a','#0088cc',
            '#007a60','#005f8a','#a07800',
            '#c42050','#1a6640','#004d30',
        ]

        # Assign colour per ticker
        ticker_colours = {}
        for i, ticker in enumerate(sorted(tickers)):
            ticker_colours[ticker] = COLOURS[i % len(COLOURS)]

        # Short display labels
        display_labels = {
            # AU sectors
            '^AXEJ': 'XEJ - Energy',
            '^AXFJ': 'XFJ - Financials',
            '^AXIJ': 'XIJ - IT',
            '^AXTJ': 'XTJ - Telecom',
            '^AXUJ': 'XUJ - Utilities',
            '^AXMJ': 'XMJ - Materials',
            '^AXDJ': 'XDJ - Cons Disc',
            '^AXHJ': 'XHJ - Healthcare',
            '^AXSJ': 'XSJ - Cons Staples',
            '^AXNJ': 'XNJ - Industrials',
            # US sectors
            'XLE'  : 'XLE - Energy',
            'XLK'  : 'XLK - Technology',
            'XLY'  : 'XLY - Cons Disc',
            'XLF'  : 'XLF - Financials',
            'XLI'  : 'XLI - Industrials',
            'XLB'  : 'XLB - Materials',
            'XLU'  : 'XLU - Utilities',
            'XLP'  : 'XLP - Cons Staples',
            'XLV'  : 'XLV - Healthcare',
            'XLC'  : 'XLC - Comm Services',
            'XLRE' : 'XLRE - Real Estate',
            'KRE'  : 'KRE - Reg Banks',
            # Housing
            'ITB'  : 'ITB - Homebuilders',
            '^HGX' : 'HGX - Housing Index',
            # Thematic
            'SMH'  : 'SMH - Semis',
            'BOTZ' : 'BOTZ - Robotics/AI',
            'IGV'  : 'IGV - Software',
            'IBB'  : 'IBB - Biotech',
            # Commodities
            'GDX'  : 'GDX - Gold Miners',
            'GDXJ' : 'GDXJ - Jr Gold',
            'URA'  : 'URA - Uranium',
            'LIT'  : 'LIT - Lithium',
            'COPX' : 'COPX - Copper',
            'SIL'  : 'SIL - Silver',
            'SILJ' : 'SILJ - Jr Silver',
            'OIH'  : 'OIH - Oil Services',
            'XOP'  : 'XOP - Oil E&P',
            'PBW'  : 'PBW - Clean Energy',
            'TAN'  : 'TAN - Solar',
            'JETS' : 'JETS - Airlines',
            'MOO'  : 'MOO - Agribusiness',
            'PHO'  : 'PHO - Water',
            'FDN'  : 'FDN - Internet',
            'URNM' : 'URNM - Uranium Miners',
            'REMX' : 'REMX - Rare Earth',
        }

        fig = go.Figure()

        # Quadrant backgrounds
        fig.add_shape(type='rect', x0=100, y0=100, x1=165, y1=155,
                      fillcolor='rgba(0,180,0,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=50,  y0=100, x1=100, y1=155,
                      fillcolor='rgba(100,100,255,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=50,  y0=50,  x1=100, y1=100,
                      fillcolor='rgba(255,50,50,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=100, y0=50,  x1=165, y1=100,
                      fillcolor='rgba(255,180,0,0.06)', line_width=0, layer='below')

        # Quadrant labels
        _qt_color = 'rgba(0,0,0,0.45)' if _get_theme_mode()=='light' else 'rgba(255,255,255,0.25)'
        for text, x, y in [
            ('LEADING',    132, 133),
            ('WEAKENING',  132, 67),
            ('LAGGING',    68,  67),
            ('IMPROVING',  68,  133),
        ]:
            fig.add_annotation(x=x, y=y, text=f"<b>{text}</b>", showarrow=False,
                               font=dict(size=13, color=_qt_color),
                               xanchor='center')

        # Centre lines
        _cl_color = 'rgba(0,0,0,0.25)' if _get_theme_mode()=='light' else 'rgba(255,255,255,0.2)'
        fig.add_hline(y=100, line_width=1, line_dash='dash', line_color=_cl_color)
        fig.add_vline(x=100, line_width=1, line_dash='dash', line_color=_cl_color)

        # Track current positions for legend sorting
        current_positions = {}

        # Plot each ticker
        for ticker in tickers:
            tdf    = df[df['ticker'] == ticker].sort_values('date').tail(tail_from)
            if len(tdf) == 0:
                continue
            if len(tdf) < 2:
                continue

            colour  = ticker_colours[ticker]
            label   = display_labels.get(ticker, ticker)
            # Smooth RS values using EWM
            tdf = tdf.copy()
            tdf['rs_ratio_smooth']    = tdf['rs_ratio'].ewm(span=smooth_span, adjust=False).mean()
            tdf['rs_momentum_smooth'] = tdf['rs_momentum'].ewm(span=smooth_span, adjust=False).mean()

            x_vals = tdf['rs_ratio_smooth'].tolist()
            y_vals = tdf['rs_momentum_smooth'].tolist()

            current_positions[ticker] = (x_vals[-1], y_vals[-1], label, colour)

            # Tail segments with fading opacity
            n = len(x_vals)
            for j in range(1, n):
                opacity = 0.15 + 0.7 * (j / n)
                fig.add_trace(go.Scatter(
                    x=[x_vals[j-1], x_vals[j]],
                    y=[y_vals[j-1], y_vals[j]],
                    mode='lines',
                    line=dict(color=colour, width=2),
                    opacity=opacity,
                    showlegend=False,
                    hoverinfo='skip',
                ))

            # Current dot + label
            fig.add_trace(go.Scatter(
                x=[x_vals[-1]], y=[y_vals[-1]],
                mode='markers+text',
                marker=dict(size=12, color=colour,
                            line=dict(color='white', width=1.5)),
                text=[label],
                textposition='top right',
                textfont=dict(size=11, color=colour),
                name=label,
                showlegend=False,
                hovertemplate=f"<b>{label}</b><br>RS-Ratio: %{{x:.2f}}<br>RS-Momentum: %{{y:.2f}}<extra></extra>",
            ))

        # ── Sort for legend and PNG export ────────────────────────────────────
        def get_quadrant(x, y):
            if x >= 100 and y >= 100: return ('1_LEADING',   '🟢')
            if x >= 100 and y <  100: return ('2_WEAKENING', '🟡')
            if x <  100 and y >= 100: return ('3_IMPROVING', '🔵')
            return                           ('4_LAGGING',   '🔴')

        _quad_order = {'1_LEADING': 0, '3_IMPROVING': 1, '2_WEAKENING': 2, '4_LAGGING': 3}
        sorted_tickers = sorted(
            current_positions.items(),
            key=lambda item: (_quad_order.get(get_quadrant(item[1][0], item[1][1])[0], 9), -item[1][0])
        )

        # Build title with date range info
        _dates_in_view = sorted(df['date'].unique())
        _date_from_str = pd.to_datetime(_dates_in_view[0]).strftime('%d %b %Y')  if _dates_in_view else ''
        _date_to_str   = pd.to_datetime(_dates_in_view[-1]).strftime('%d %b %Y') if _dates_in_view else ''
        _n_days        = len(_dates_in_view)
        _chart_title   = f"{title}  ·  {_n_days} trading days  ({_date_from_str} → {_date_to_str})"

        fig.update_layout(
            title        = dict(text=_chart_title, font=dict(size=14, color=get_chart_theme()['font_color'])),
            xaxis_title  = 'RS-Ratio',
            yaxis_title  = 'RS-Momentum',
            height       = 800,
            plot_bgcolor = get_chart_theme()['plot_bgcolor'],
            paper_bgcolor= get_chart_theme()['paper_bgcolor'],
            font         = dict(color=get_chart_theme()['font_color']),
            xaxis        = dict(range=[50,165], gridcolor=get_chart_theme()['gridcolor'],
                                tickfont=dict(size=10), title_font=dict(size=11)),
            yaxis        = dict(range=[50,155], gridcolor=get_chart_theme()['gridcolor'],
                                tickfont=dict(size=10), title_font=dict(size=11)),
            showlegend   = False,
            margin       = dict(r=40, l=60, t=60, b=60),
        )

        _sp1, _mid, _sp2 = st.columns([800, 10000, 800])
        with _mid:
            st.plotly_chart(fig, use_container_width=True)

        # ── Streamlit legend below chart ──────────────────────────────────────
        quad_groups = {'4_LAGGING': [], '2_WEAKENING': [], '3_IMPROVING': [], '1_LEADING': []}
        quad_labels = {
            '4_LAGGING'  : ('🔴 LAGGING',    '#e63946'),
            '2_WEAKENING': ('🟡 WEAKENING',  '#f77f00'),
            '3_IMPROVING': ('🔵 IMPROVING',  '#00b4d8'),
            '1_LEADING'  : ('🟢 LEADING',   '#2dc653'),
        }
        for ticker, (x, y, label, colour) in sorted_tickers:
            quad = get_quadrant(x, y)[0]
            quad_groups[quad].append((label, colour))

        _ls1, _lc1, _lc2, _lc3, _lc4, _ls2 = st.columns([2900, 600, 600, 600, 600, 2900])
        _leg_cols = [_lc1, _lc2, _lc3, _lc4]
        for i, (quad_key, items) in enumerate(quad_groups.items()):
            qname, qcolour = quad_labels[quad_key]
            with _leg_cols[i]:
                st.markdown(f"<div style='color:{qcolour};font-weight:bold;font-size:13px;margin-bottom:6px'>{qname}</div>",
                            unsafe_allow_html=True)
                for label, colour in items:
                    st.markdown(f"<div style='font-size:12px;margin-bottom:3px'>"
                                f"<span style='color:{colour}'>●</span> {label}</div>",
                                unsafe_allow_html=True)

        # ── PNG export with embedded legend ───────────────────────────────────
        fig_export = go.Figure(fig)
        # Build two-column legend for PNG export
        _png_quad_order = {'4_LAGGING': 0, '2_WEAKENING': 1, '3_IMPROVING': 2, '1_LEADING': 3}
        sorted_tickers_png = sorted(
            sorted_tickers,
            key=lambda item: (_png_quad_order.get(get_quadrant(item[1][0], item[1][1])[0], 9), -item[1][0])
        )

        lh = 0.032; ann_color = '#111111' if _get_theme_mode()=='light' else '#ffffff'
        col1_x, col2_x = 1.02, 1.175; col1_items, col2_items = [], []
        _left_quads = {'4_LAGGING', '2_WEAKENING'}; last_quad = None
        for ticker, (x, y, label, colour) in sorted_tickers_png:
            quad, icon = get_quadrant(x, y); qname = quad.split('_')[1]
            cur_list = col1_items if quad in _left_quads else col2_items
            if quad != last_quad:
                cur_list.append(('header', f"<b>{icon} {qname}</b>", ann_color)); last_quad = quad
            cur_list.append(('ticker', f"● {label}  {x:.1f}/{y:.1f}", colour))

        # Place col1
        y_pos = 1.0
        for kind, text, colour in col1_items:
            fig_export.add_annotation(
                x=col1_x, y=y_pos, xref='paper', yref='paper',
                text=text, showarrow=False, xanchor='left',
                font=dict(size=11 if kind=='header' else 10, color=colour),
            )
            y_pos -= lh * 0.7 if kind == 'header' else lh

        # Place col2
        y_pos = 1.0
        for kind, text, colour in col2_items:
            fig_export.add_annotation(
                x=col2_x, y=y_pos, xref='paper', yref='paper',
                text=text, showarrow=False, xanchor='left',
                font=dict(size=11 if kind=='header' else 10, color=colour),
            )
            y_pos -= lh * 0.7 if kind == 'header' else lh

        fig_export.update_layout(
            margin=dict(r=600, l=60, t=80, b=60),
            font=dict(color='#1a1a1a' if _get_theme_mode()=='light' else 'white'),
        )

        img_bytes = fig_export.to_image(format='png', width=2400, height=1000, scale=2)
        st.download_button(
            label     = f"⬇ Download PNG ({tail_days}d tail)",
            data      = img_bytes,
            file_name = f"rrg_{title.replace(' ','_').replace('/','_')}_{tail_to}to{tail_from}d_{datetime.today().strftime('%Y%m%d')}.png",
            mime      = 'image/png',
            key       = f"dl_rrg_{title}"
        )

    with tab1:
        build_rrg(
            os.path.join(STOCKS, 'results', 'rrg', 'au_rrg_history.csv'),
            'AU Sectors & ETFs vs XJO'
        )
        if st.button("🔄 Update AU RRG Data", key='rrg_au'):
            run_script(os.path.join(STOCKS, 'rrg_au_data.py'), STOCKS)
            st.rerun()

    with tab2:
        build_rrg(
            os.path.join(STOCKS, 'results', 'rrg', 'us_rrg_history.csv'),
            'US Sectors & ETFs vs SPY'
        )
        if st.button("🔄 Update US RRG Data", key='rrg_us'):
            run_script(os.path.join(STOCKS, 'rrg_us_data.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# BREADTH RRG PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Breadth RRG":
    import plotly.graph_objects as go

    st.title("📊 Breadth Rotation Graph")
    st.markdown("""
        <div class="info-card">
            Plots sector breadth participation using an RRG-style chart. 
            <b>X axis</b> — normalised % of stocks above SMA (breadth strength vs universe average).
            <b>Y axis</b> — rate of change of that breadth score over 21 days (breadth momentum).
            Reading top-right to bottom-left follows the same rotation cycle as a standard RRG.
            Three charts per universe show early (Ab20), intermediate (Ab50) and established (Ab200) trend participation — 
            sectors leading on Ab20 but lagging on Ab200 are early rotation candidates.
        </div>
    """, unsafe_allow_html=True)

    def build_breadth_rrg(history, sector_keys, prefix, sma_col, title, tail_days, smooth_span):
        """Build one breadth RRG chart for a given SMA level"""
        if history is None or len(history) == 0:
            st.warning("No breadth history found")
            return

        history = history.copy()
        history['date'] = pd.to_datetime(history['date'])
        history = history.sort_values('date')

        # Calculate % above SMA per sector per day
        breadth_data = {}
        for sec_key in sector_keys:
            total_col = f'{prefix}_{sec_key}_total'
            above_col = f'{prefix}_{sec_key}_{sma_col}'
            if total_col not in history.columns or above_col not in history.columns:
                continue
            series = history.set_index('date').apply(
                lambda row: round(row[above_col] / row[total_col] * 100, 2)
                if row[total_col] > 0 else 0, axis=1
            )
            if series.std() > 0:
                breadth_data[sec_key] = series

        if not breadth_data:
            st.warning(f"No breadth data for {sma_col}")
            return

        df_breadth = pd.DataFrame(breadth_data)
        df_breadth = df_breadth.tail(tail_days + 63)  # enough history for momentum calc

        # Normalise to universe average each day (like RRG normalisation)
        universe_avg = df_breadth.mean(axis=1)

        # RS-Ratio equivalent: sector breadth relative to universe average, normalised to 100
        rs_ratio_df = df_breadth.apply(lambda col: (col / universe_avg) * 100)

        # Apply EWM smoothing
        rs_ratio_smooth = rs_ratio_df.ewm(span=smooth_span, adjust=False).mean()

        # RS-Momentum: rate of change of RS-Ratio over 21 days, normalised to 100
        rs_mom_df = rs_ratio_smooth / rs_ratio_smooth.shift(21) * 100
        rs_mom_smooth = rs_mom_df.ewm(span=smooth_span, adjust=False).mean()

        # Trim to tail length
        rs_ratio_tail = rs_ratio_smooth.tail(tail_days)
        rs_mom_tail   = rs_mom_smooth.tail(tail_days)

        # Colour palette
        _brrg_light = _get_theme_mode() == 'light'
        COLOURS = [
            '#00b4d8','#f77f00','#2dc653','#e63946','#9b5de5',
            '#f15bb5','#fee440','#06d6a0','#118ab2','#ffd166',
            '#ef476f','#b7e4c7','#40916c','#fcbf49','#eae2b7',
        ] if not _brrg_light else [
            '#0077a8','#c96a00','#1a8a3a','#c0152a','#6a20c8',
            '#c4006a','#b8970a','#007a60','#005f8a','#a07800',
            '#c42050','#1a6640','#004d30','#a85500','#8b6914',
        ]

        # Short labels
        SECTOR_LABELS = {
            'energy_minerals'             : 'Energy Min',
            'finance'                     : 'Finance',
            'technology_services'         : 'Tech Svcs',
            'electronic_technology'       : 'Elec Tech',
            'communications'              : 'Comms',
            'utilities'                   : 'Utilities',
            'non_energy_minerals'         : 'Non-E Min',
            'process_industries'          : 'Process Ind',
            'consumer_services'           : 'Cons Svcs',
            'consumer_durables'           : 'Cons Dur',
            'consumer_non_durables'       : 'Cons NonDur',
            'retail_trade'                : 'Retail',
            'health_technology'           : 'Health Tech',
            'health_services'             : 'Health Svcs',
            'industrial_services'         : 'Ind Svcs',
            'commercial_services'         : 'Comm Svcs',
            'distribution_services'       : 'Distrib',
            'transportation'              : 'Transport',
            'producer_manufacturing'      : 'Producer Mfg',
            'energy'                      : 'Energy',
            'information_technology'      : 'Info Tech',
            'consumer_discretionary'      : 'Cons Disc',
            'financials'                  : 'Financials',
            'industrials'                 : 'Industrials',
            'materials'                   : 'Materials',
            'consumer_staples'            : 'Cons Staples',
            'health_care'                 : 'Health Care',
            'communication_services'      : 'Comm Svcs',
            'real_estate'                 : 'Real Estate',
            'gold'                        : 'Gold',
            'silver'                      : 'Silver',
            'copper'                      : 'Copper',
            'uranium'                     : 'Uranium',
            'lithium'                     : 'Lithium',
            'platinum'                    : 'Platinum',
            'palladium'                   : 'Palladium',
        }

        fig = go.Figure()
        
        # Centre lines
        fig.add_hline(y=100, line_width=1, line_dash='dash',
                      line_color='rgba(128,128,128,0.3)')
        fig.add_vline(x=100, line_width=1, line_dash='dash',
                      line_color='rgba(128,128,128,0.3)')

        current_positions = {}

        for i, sec_key in enumerate(breadth_data.keys()):
            if sec_key not in rs_ratio_tail.columns:
                continue

            colour = COLOURS[i % len(COLOURS)]
            label  = SECTOR_LABELS.get(sec_key, sec_key.replace('_',' ').title())

            x_vals = rs_ratio_tail[sec_key].dropna().tolist()
            y_vals = rs_mom_tail[sec_key].dropna().tolist()

            if len(x_vals) < 2:
                continue

            # Align lengths
            min_len = min(len(x_vals), len(y_vals))
            x_vals  = x_vals[-min_len:]
            y_vals  = y_vals[-min_len:]

            current_positions[sec_key] = (x_vals[-1], y_vals[-1], label, colour)

            # Tail with fading opacity
            n = len(x_vals)
            for j in range(1, n):
                opacity = 0.15 + 0.75 * (j / n)
                fig.add_trace(go.Scatter(
                    x=[x_vals[j-1], x_vals[j]],
                    y=[y_vals[j-1], y_vals[j]],
                    mode='lines',
                    line=dict(color=colour, width=2),
                    opacity=opacity,
                    showlegend=False,
                    hoverinfo='skip',
                ))

            # Current dot + label
            fig.add_trace(go.Scatter(
                x=[x_vals[-1]], y=[y_vals[-1]],
                mode='markers+text',
                marker=dict(size=12, color=colour,
                            line=dict(color='white', width=1.5)),
                text=[label],
                textposition='top right',  # change from top center
                textfont=dict(size=11, color=colour),  # increase from 9
                name=label,
                showlegend=False,
                hovertemplate=f"<b>{label}</b><br>Breadth RS: %{{x:.1f}}<br>Momentum: %{{y:.1f}}<extra></extra>",
            ))

        # ── Sort for legend and PNG export ────────────────────────────────────
        def get_quadrant(x, y):
            if x >= 100 and y >= 100: return ('1_LEADING',   '🟢')
            if x >= 100 and y <  100: return ('2_WEAKENING', '🟡')
            if x <  100 and y >= 100: return ('3_IMPROVING', '🔵')
            return                           ('4_LAGGING',   '🔴')

        _quad_order = {'1_LEADING': 0, '3_IMPROVING': 1, '2_WEAKENING': 2, '4_LAGGING': 3}
        sorted_tickers = sorted(
            current_positions.items(),
            key=lambda item: (_quad_order.get(get_quadrant(item[1][0], item[1][1])[0], 9), -item[1][0])
        )

        # Calculate dynamic axis ranges
        all_x = [pos[0] for pos in current_positions.values()]
        all_y = [pos[1] for pos in current_positions.values()]
        x_pad = max((max(all_x) - min(all_x)) * 0.15, 10)
        y_pad = max((max(all_y) - min(all_y)) * 0.15, 10)
        x_min = min(min(all_x) - x_pad, 60)
        x_max = max(max(all_x) + x_pad, 140)
        y_min = min(min(all_y) - y_pad, 60)
        y_max = max(max(all_y) + y_pad, 140)

        # Quadrant backgrounds
        fig.add_shape(type='rect', x0=100, y0=100, x1=x_max, y1=y_max,
                      fillcolor='rgba(0,180,0,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=x_min, y0=100, x1=100, y1=y_max,
                      fillcolor='rgba(100,100,255,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=x_min, y0=y_min, x1=100, y1=100,
                      fillcolor='rgba(255,50,50,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=100, y0=y_min, x1=x_max, y1=100,
                      fillcolor='rgba(255,180,0,0.06)', line_width=0, layer='below')

        # Quadrant labels
        for text, x, y in [
            ('LEADING',   x_max * 0.97, y_max * 0.97),
            ('WEAKENING', x_max * 0.97, y_min * 1.03),
            ('LAGGING',   x_min * 1.03, y_min * 1.03),
            ('IMPROVING', x_min * 1.03, y_max * 0.97),
        ]:
            fig.add_annotation(x=x, y=y, text=text, showarrow=False,
                               font=dict(size=11, color='rgba(150,150,150,0.4)'),
                               xanchor='center')

        fig.update_layout(
            title        = dict(text=title, font=dict(size=14)),
            height       = 1000,
            plot_bgcolor = get_chart_theme()['plot_bgcolor'],
            paper_bgcolor= get_chart_theme()['paper_bgcolor'],
            font         = dict(color=get_chart_theme()['font_color']),
            xaxis        = dict(range=[x_min, x_max], gridcolor=get_chart_theme()['gridcolor'],
                                title='Breadth Strength (vs universe avg)', title_font=dict(size=10)),
            yaxis        = dict(range=[y_min, y_max], gridcolor=get_chart_theme()['gridcolor'],
                                title='Breadth Momentum (21d ROC)', title_font=dict(size=10)),
            showlegend   = False,
            margin       = dict(r=40, l=60, t=50, b=50),
        )

        _sp1, _mid, _sp2 = st.columns([800, 10000, 800])
        with _mid:
            st.plotly_chart(fig, use_container_width=True)

        # ── Streamlit legend below chart ──────────────────────────────────────
        quad_groups = {'4_LAGGING': [], '2_WEAKENING': [], '3_IMPROVING': [], '1_LEADING': []}
        quad_labels = {
            '4_LAGGING'  : ('🔴 LAGGING',    '#e63946'),
            '2_WEAKENING': ('🟡 WEAKENING',  '#f77f00'),
            '3_IMPROVING': ('🔵 IMPROVING',  '#00b4d8'),
            '1_LEADING'  : ('🟢 LEADING',   '#2dc653'),
        }
        for sec_key, (x, y, label, colour) in sorted_tickers:
            quad = get_quadrant(x, y)[0]
            quad_groups[quad].append((label, colour))

        _ls1, _lc1, _lc2, _lc3, _lc4, _ls2 = st.columns([2900, 600, 600, 600, 600, 2900])
        _leg_cols = [_lc1, _lc2, _lc3, _lc4]
        for i, (quad_key, items) in enumerate(quad_groups.items()):
            qname, qcolour = quad_labels[quad_key]
            with _leg_cols[i]:
                st.markdown(f"<div style='color:{qcolour};font-weight:bold;font-size:13px;margin-bottom:6px'>{qname}</div>",
                            unsafe_allow_html=True)
                for label, colour in items:
                    st.markdown(f"<div style='font-size:12px;margin-bottom:3px'>"
                                f"<span style='color:{colour}'>●</span> {label}</div>",
                                unsafe_allow_html=True)

    # ── Controls ──────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        tail_days   = st.slider("Tail length (trading days)", 10, 63, 10, key='brrg_tail')
    with col2:
        smooth_span = st.slider("Smoothing (EWM span)", 1, 20, 20, key='brrg_smooth')

    tab_au, tab_us, tab_comm = st.tabs(["🇦🇺 AU Sectors", "🇺🇸 US Sectors", "⛏ Commodities"])

    # ── AU ─────────────────────────────────────────────────────────────────────
    with tab_au:
        au_hist_file = os.path.join(STOCKS, 'results', 'breadth', 'au_total_market',
                                    'au_total_market_breadth_history.csv')
        au_hist = load_csv(au_hist_file)
        if au_hist is not None:
            sec_cols = [c for c in au_hist.columns if c.startswith('sec_') and c.endswith('_total')
                        and not c.startswith('sp_') and not c.startswith('rus_')]
            sec_keys = [c.replace('sec_','').replace('_total','') for c in sec_cols
                        if 'nan' not in c and 'index' not in c]

            st.caption(f"Latest: {au_hist.iloc[-1]['date']} — {file_age(au_hist_file)}")

            sma_choice = st.radio("SMA Level", ["Above 20", "Above 50", "Above 200"],
                                   horizontal=True, key='brrg_au_sma')
            sma_col_map = {"Above 20": "above20", "Above 50": "above50", "Above 200": "above200"}
            sma_col = sma_col_map[sma_choice]

            build_breadth_rrg(au_hist, sec_keys, 'sec', sma_col,
                              f'AU Sector Breadth — {sma_choice} SMA', tail_days, smooth_span)
        else:
            st.warning("No AU breadth history found — run AU breadth script first")

    # ── US ─────────────────────────────────────────────────────────────────────
    with tab_us:
        us_hist_file = os.path.join(STOCKS, 'results', 'breadth', 'us_total_market',
                                    'us_total_market_breadth_history.csv')
        us_hist = load_csv(us_hist_file)
        if us_hist is not None:
            sp_cols = [c for c in us_hist.columns if c.startswith('sp_sec_') and c.endswith('_total')]
            sp_keys = [c.replace('sp_sec_','').replace('_total','') for c in sp_cols
                       if 'nan' not in c and 'index' not in c]

            st.caption(f"Latest: {us_hist.iloc[-1]['date']} — {file_age(us_hist_file)}")

            sma_choice = st.radio("SMA Level", ["Above 20", "Above 50", "Above 200"],
                                   horizontal=True, key='brrg_us_sma')
            sma_col_map = {"Above 20": "above20", "Above 50": "above50", "Above 200": "above200"}
            sma_col = sma_col_map[sma_choice]

            build_breadth_rrg(us_hist, sp_keys, 'sp_sec', sma_col,
                              f'US Sector Breadth — {sma_choice} SMA', tail_days, smooth_span)
        else:
            st.warning("No US breadth history found — run US breadth script first")

    # ── Commodities ────────────────────────────────────────────────────────────
    with tab_comm:
        comm_hist_file = os.path.join(STOCKS, 'results', 'breadth', 'all_major_commodities',
                                      'all_major_commodities_breadth_history.csv')
        comm_hist = load_csv(comm_hist_file)
        if comm_hist is not None:
            comm_cols = [c for c in comm_hist.columns if c.startswith('comm_') and c.endswith('_total')
                         and c.count('_') == 2]
            comm_keys = [c.replace('comm_','').replace('_total','') for c in comm_cols]

            st.caption(f"Latest: {comm_hist.iloc[-1]['date']} — {file_age(comm_hist_file)}")

            sma_choice = st.radio("SMA Level", ["Above 20", "Above 50", "Above 200"],
                                   horizontal=True, key='brrg_comm_sma')
            sma_col_map = {"Above 20": "above20", "Above 50": "above50", "Above 200": "above200"}
            sma_col = sma_col_map[sma_choice]

            build_breadth_rrg(comm_hist, comm_keys, 'comm', sma_col,
                              f'Commodity Breadth — {sma_choice} SMA', tail_days, smooth_span)
        else:
            st.warning("No commodities breadth history found — run commodities breadth script first")

# ═══════════════════════════════════════════════════════════════════════════════
# DRAWDOWN ANALYSIS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Drawdown Analysis":
    import sys
    sys.path.insert(0, STOCKS)
    from drawdown_analysis import calculate_period, save_period

    st.title("📉 Drawdown Analysis")

    # ── Inputs ────────────────────────────────────────────────────────────────
    st.subheader("Setup")
    st.markdown("""
        <div style="background:rgba(255,255,255,0.04);border-radius:8px;padding:14px 16px;
                    margin-bottom:16px;border:1px solid rgba(255,255,255,0.08)">
            <div style="color:white;font-size:13px;font-weight:bold;margin-bottom:8px">
                How to use this tool
            </div>
            <div style="color:#aaa;font-size:14px;line-height:1.7">
                The Drawdown Analysis tool measures how individual stocks performed during a specific 
                market event or pullback period — relative to their benchmark and sector peers.<br><br>
                <b style="color:#ccc">1. Select a watchlist</b> — choose the universe to analyse 
                (AU market, US market, commodities etc).<br>
                <b style="color:#ccc">2. Filter (optional)</b> — narrow to a specific sector or 
                commodity. The benchmark automatically switches to the relevant sector ETF 
                (e.g. gold → GDX, energy → XLE).<br>
                <b style="color:#ccc">3. Set analysis periods</b> — enter a start date for each 
                period. The tool measures performance from that date to today.<br>
                <b style="color:#ccc">4. Run analysis</b> — results show the top 20 strongest and 
                bottom 10 weakest stocks vs the benchmark for each period.<br>
                <b style="color:#ccc">5. Cross-period comparison</b> — if using multiple periods, 
                stocks consistently improving or declining across periods are highlighted.<br><br>
                <div style="color:#aaa;font-size:14px;border-top:1px solid rgba(255,255,255,0.08);
                            padding-top:8px;margin-top:4px">
                    <b style="color:#ccc">Scoring:</b> &nbsp;
                    RS vs Benchmark × 0.4 &nbsp;+&nbsp; Peer RS Score × 0.3 &nbsp;+&nbsp; 
                    DD vs Benchmark × 0.3<br>
                    <b style="color:#ccc">Suggested lookbacks:</b> &nbsp;
                    5 days (weekly move) &nbsp;|&nbsp; 
                    21 days (monthly) &nbsp;|&nbsp; 
                    63 days (quarterly) &nbsp;|&nbsp; 
                    126 days (6 month cycle) &nbsp;|&nbsp;
                    Use a specific event date (e.g. market peak, Fed announcement)
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        watchlists     = sorted(glob.glob(os.path.join(STOCKS, 'watchlist', '*.csv')))
        wl_names       = [os.path.basename(w) for w in watchlists]
        wl_selected    = st.selectbox("Watchlist", wl_names)
        watchlist_path = os.path.join(STOCKS, 'watchlist', wl_selected)

    with col2:
        study_name = st.text_input("Study name", value=wl_selected.replace('.csv',''))

    # Load watchlist preview for filter options
    wl_preview = load_csv(watchlist_path)
    filter_col = None
    filter_val = None

    if wl_preview is not None:
        col3, col4 = st.columns(2)
        with col3:
            if 'sector' in wl_preview.columns:
                sectors     = sorted(wl_preview['sector'].dropna().unique().tolist())
                sector_opts = ['All sectors'] + sectors
                sel_sector  = st.selectbox("Filter by sector", sector_opts)
                if sel_sector != 'All sectors':
                    filter_col = 'sector'
                    filter_val = sel_sector
        with col4:
            if 'commodity' in wl_preview.columns:
                commodities   = sorted(wl_preview['commodity'].dropna().unique().tolist())
                comm_opts     = ['All commodities'] + commodities
                sel_commodity = st.selectbox("Filter by commodity", comm_opts)
                if sel_commodity != 'All commodities':
                    filter_col = 'commodity'
                    filter_val = sel_commodity

    n_periods = st.radio("Number of periods", [1, 2, 3], horizontal=True)

    periods = []
    cols    = st.columns(n_periods)
    for i in range(n_periods):
        with cols[i]:
            st.markdown(f"**Period {i+1}**")
            date_val = st.date_input(
                f"Start date",
                value=datetime.today() - timedelta(days=91),
                max_value=datetime.today() - timedelta(days=1),
                key=f"date_{i}"
            )
            label = st.text_input(
                f"Label",
                value=f"period_{i+1}",
                key=f"label_{i}"
            )
            periods.append({
                'date' : date_val.strftime('%Y-%m-%d'),
                'label': label.lower().replace(' ','_')
            })

    # ── Run analysis ──────────────────────────────────────────────────────────
    if st.button("▶ Run Drawdown Analysis", type="primary"):
        from data_fetch.benchmark.data_fetch_generic import load_watchlist, fetch_prices, fetch_volumes

        earliest        = min(p['date'] for p in periods)
        fetch_start_200 = (datetime.today() - timedelta(days=400)).strftime('%Y-%m-%d')
        end_date        = datetime.today().strftime('%Y-%m-%d')

        with st.spinner("Loading watchlist and fetching prices..."):
            os.chdir(STOCKS)
            watchlist = load_watchlist(watchlist_path)

            # Apply sector/commodity filter
            if filter_col and filter_val:
                bench_rows  = watchlist[watchlist['benchmark'] == 'benchmark']
                filter_rows = watchlist[watchlist[filter_col] == filter_val]
                watchlist   = pd.concat([bench_rows, filter_rows]).drop_duplicates()
                st.info(f"Filtered to {filter_col}: {filter_val} — {len(filter_rows)} stocks")

            prices  = fetch_prices(watchlist, fetch_start_200, end_date)
            volumes = fetch_volumes(watchlist, fetch_start_200, end_date)

        # Determine sector/commodity benchmark override
        bench_override = None
        if filter_col and filter_val:
            from drawdown_analysis import get_sector_benchmark
            bench_override = get_sector_benchmark(filter_col, filter_val)
            if bench_override:
                st.info(f"Using sector benchmark: {bench_override} for {filter_val}")
            else:
                st.info(f"No sector ETF mapping found for {filter_val} — using watchlist benchmark")

        # Build results folder
        period_labels = '_'.join([p['label'] for p in periods])
        results_dir   = os.path.join(STOCKS, 'results', 'drawdown_analysis',
                                     f"{study_name}_{period_labels}") + os.sep
        os.makedirs(results_dir, exist_ok=True)

        all_periods_data = []
        for p in periods:
            with st.spinner(f"Analysing period: {p['label']} from {p['date']}..."):
                result = calculate_period(
                    prices, volumes, watchlist,
                    p['date'], p['label'],
                    bench_override=bench_override
                )
                if result is None:
                    st.warning(f"Insufficient data for period {p['label']} from {p['date']}")
                    continue
                df, bench_ret, bench_dd = result
                save_period(df, bench_ret, bench_dd, results_dir, study_name, p['label'], p['date'])
                all_periods_data.append((df, bench_ret, bench_dd, p['label'], p['date']))

        st.session_state['drawdown_results'] = all_periods_data
        st.session_state['drawdown_study']   = study_name
        st.success(f"Analysis complete — {len(all_periods_data)} periods processed")

    # ── Display results ───────────────────────────────────────────────────────
    if 'drawdown_results' in st.session_state:
        all_periods_data = st.session_state['drawdown_results']
        study_name       = st.session_state['drawdown_study']

        for df, bench_ret, bench_dd, label, start_date in all_periods_data:
            st.divider()
            st.subheader(f"Period: {label.upper()} — from {start_date}")
            st.caption(f"Benchmark return: {bench_ret:+.2f}%   Benchmark max DD: {bench_dd:.2f}%   Trading days: {df['trading_days'].iloc[0]}")

            col1, col2 = st.columns(2)

            def colour_rs(val):
                try:
                    v = float(str(val).replace('%',''))
                    if v > 0: return 'background-color: rgba(0,180,0,0.12)'
                    if v < 0: return 'background-color: rgba(180,0,0,0.12)'
                except: pass
                return ''

            cols_show = ['ticker','name','ret_period','bench_ret','rs_vs_bench',
                         'max_dd_period','dd_vs_bench','peer_rs_score','rs_trend',
                         'acc_watch','score']
            cols_show = [c for c in cols_show if c in df.columns]

            with col1:
                st.markdown("**Top 20 — strongest vs benchmark**")
                st.dataframe(
                    format_drawdown_df(df, cols_show).head(20).style.map(colour_rs, subset=['rs_vs_bench','dd_vs_bench']),
                    width='stretch',
                    hide_index=False,
                    height=500
                )

            with col2:
                st.markdown("**Bottom 10 — weakest vs benchmark**")
                st.dataframe(
                    format_drawdown_df(df, cols_show).tail(10).style.map(colour_rs, subset=['rs_vs_bench','dd_vs_bench']),
                    width='stretch',
                    hide_index=False,
                    height=280
                )

        # Cross period comparison
        if len(all_periods_data) > 1:
            st.divider()
            st.subheader("Cross Period Rank Comparison")

            period_dfs = {}
            for df, _, _, label, _ in all_periods_data:
                period_dfs[label] = df.reset_index()[['rank','ticker','name','score']].rename(
                    columns={'rank': f'rank_{label}', 'score': f'score_{label}'}
                )

            first_label = all_periods_data[0][3]
            merged      = period_dfs[first_label]
            for _, _, _, label, _ in all_periods_data[1:]:
                merged = merged.merge(
                    period_dfs[label][['ticker', f'rank_{label}', f'score_{label}']],
                    on='ticker', how='outer'
                )

            rank_cols = [f'rank_{df[3]}' for df in all_periods_data]
            merged['trend'] = merged.apply(
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

            def colour_trend(val):
                if val == 'IMPROVING': return 'background-color: rgba(0,180,0,0.12)'
                if val == 'DECLINING': return 'background-color: rgba(180,0,0,0.12)'
                return ''

            st.dataframe(
                merged.head(30).style.map(colour_trend, subset=['trend']),
                width='stretch',
                hide_index=True,
                height=600
            )

# ── Previous studies ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("Previous Studies")

    study_dirs  = glob.glob(os.path.join(STOCKS, 'results', 'drawdown_analysis', '*'))
    study_dirs  = [d for d in study_dirs if os.path.isdir(d)]
    study_names = [os.path.basename(d) for d in study_dirs]

    # ── Download ──────────────────────────────────────────────────────────────
    if study_dirs:
        dl_col1, dl_col2 = st.columns([3, 1])
        with dl_col1:
            dl_selected = st.selectbox("Download study files",
                                       ['-- select --'] + study_names,
                                       key='dl_study')
        with dl_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if dl_selected != '-- select --':
                dl_dir       = os.path.join(STOCKS, 'results', 'drawdown_analysis', dl_selected)
                dl_csv_files = glob.glob(os.path.join(dl_dir, '*_drawdown.csv'))
                if dl_csv_files:
                    import io, zipfile
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for f in dl_csv_files:
                            zf.write(f, os.path.basename(f))
                        summary = glob.glob(os.path.join(dl_dir, '*_drawdown_summary.txt'))
                        if summary:
                            zf.write(summary[-1], os.path.basename(summary[-1]))
                    zip_buffer.seek(0)
                    st.download_button(
                        label     = "⬇ Download Study",
                        data      = zip_buffer,
                        file_name = f"{dl_selected}.zip",
                        mime      = 'application/zip',
                        key       = 'dl_study_btn'
                    )

    # ── View previous study ───────────────────────────────────────────────────
    if study_dirs:
        selected = st.selectbox("Load previous study", ['-- select --'] + study_names)
        if selected != '-- select --':
            study_dir = os.path.join(STOCKS, 'results', 'drawdown_analysis', selected)
            csv_files = glob.glob(os.path.join(study_dir, '*_drawdown.csv'))
            for f in sorted(csv_files):
                label = os.path.basename(f).replace('.csv','')
                with st.expander(label, expanded=True):
                    df = load_csv(f, index_col='rank')
                    if df is not None:
                        cols_show = ['ticker','name','ret_period','bench_ret',
                                     'rs_vs_bench','max_dd_period','dd_vs_bench',
                                     'peer_rs_score','rs_trend','acc_watch','score']
                        cols_show = [c for c in cols_show if c in df.columns]

                        def colour_rs(val):
                            try:
                                v = float(str(val).replace('%','').replace('+',''))
                                if v > 0: return 'background-color: rgba(0,180,0,0.12)'
                                if v < 0: return 'background-color: rgba(180,0,0,0.12)'
                            except:
                                pass
                            return ''

                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Top 20**")
                            st.dataframe(
                                format_drawdown_df(df, cols_show).head(20).style.map(colour_rs, subset=['rs_vs_bench','dd_vs_bench']),
                                width='stretch', hide_index=False, height=500
                            )
                        with col2:
                            st.markdown("**Bottom 10**")
                            st.dataframe(
                                format_drawdown_df(df, cols_show).tail(10).style.map(colour_rs, subset=['rs_vs_bench','dd_vs_bench']),
                                width='stretch', hide_index=False, height=280
                            )
    else:
        st.info("No previous studies found")

# ═══════════════════════════════════════════════════════════════════════════════
# ACTIONABLE & TRADINGVIEW EXPORTS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Actionable & Exports":
    st.title("📋 Actionable & TradingView Exports")
    st.caption("Filtered actionable stocks with TradingView import files")

    actionable_dir = os.path.join(STOCKS, 'results', 'daily_actionable', 'screener')

    # Find all dated CSV actionable files
    csv_files = sorted(glob.glob(os.path.join(actionable_dir, '*.csv')), reverse=True)
    tv_files  = sorted(glob.glob(os.path.join(actionable_dir, '*.txt')), reverse=True)

    if not csv_files:
        st.info("No actionable files found — run scripts first")
    else:
        # Get available dates
        from collections import defaultdict
        by_date = defaultdict(dict)

        for f in csv_files:
            name  = os.path.basename(f)
            date  = name[:8]
            label = name[9:] \
                .replace('_actionable_highconv.csv', '_highconv') \
                .replace('_actionable.csv', '') \
                .replace('_screener_highconv.csv', '_screener_highconv') \
                .replace('_screener_actionable.csv', '_screener') \
                .replace('_highconv.csv', '_highconv') \
                .replace('.csv', '') \
                .replace('_', ' ').title()
            by_date[date][f'csv_{label}'] = f

        for f in tv_files:
            name  = os.path.basename(f)
            date  = name[:8]
            label = name[9:] \
                .replace('_actionable_highconv_tvimport.txt', '_highconv') \
                .replace('_actionable_tvimport.txt', '') \
                .replace('_screener_highconv_tvimport.txt', '_screener_highconv') \
                .replace('_screener_tvimport.txt', '_screener') \
                .replace('_tvimport.txt', '') \
                .replace('_', ' ').title()
            by_date[date][f'tv_{label}'] = f

        dates = sorted(by_date.keys(), reverse=True)
        selected_date = st.selectbox("Select date", dates)
        files = by_date[selected_date]
        
        st.divider()

        STUDY_DESCRIPTIONS = {
            'Au Total Market'              : 'AU Market — vs VAS.AX benchmark',
            'Au Total Market Highconv'     : 'AU Market — HIGH vol + acc_watch signal (above 200 SMA)',
            'Us Total Market'              : 'US Market — vs SPY benchmark (peer RS score)',
            'Us Total Market Highconv'     : 'US Market — HIGH vol + acc_watch signal (above 200 SMA)',
            'Us Benchmark'                 : 'US Market — vs SPY benchmark (RS ratio)',
            'Us Benchmark Highconv'        : 'US Market Benchmark — HIGH vol + acc_watch (above 200 SMA)',
            'All Major Commodities'        : 'Commodities — vs commodity ETF benchmark (RS ratio)',
            'All Major Commodities Highconv': 'Commodities — HIGH vol + acc_watch signal (above 200 SMA)',
            'Commodities Screener'         : 'Commodities — vs commodity peers (peer RS score)',
            'Commodities Screener Highconv': 'Commodities — HIGH vol + acc_watch signal (above 200 SMA)',
            'Uranium'                      : 'Uranium — vs URA benchmark (RS ratio)',
            'Uranium Screener'             : 'Uranium — vs uranium peers (peer RS score)',
            'Uranium Screener Highconv'    : 'Uranium — HIGH vol + acc_watch signal (above 200 SMA)',
            'Au Gold Miners Screener'      : 'AU Gold — vs gold miner peers (peer RS score)',
            'Au Gold Miners Screener Highconv': 'AU Gold — HIGH vol + acc_watch signal (above 200 SMA)',
        }

        # Group by study — match csv + tv pairs
        studies = sorted(set(
            k.replace('csv_','').replace('tv_','')
            for k in files.keys()
        ))

        for study in studies:
            csv_path = files.get(f'csv_{study}')
            tv_path  = files.get(f'tv_{study}')

            # skip if neither exists
            if not csv_path and not tv_path:
                continue

            desc = STUDY_DESCRIPTIONS.get(study, '')
            st.subheader(study)
            if desc:
                st.caption(desc)
            col1, col2 = st.columns([3, 1])

            with col2:
                if tv_path:
                    content = load_txt(tv_path)
                    tickers = content.strip() if content else ''
                    count   = len(tickers.split(',')) if tickers else 0
                    st.metric("Tickers", count)
                    st.download_button(
                        label     = "⬇ TradingView Import",
                        data      = tickers,
                        file_name = os.path.basename(tv_path),
                        mime      = 'text/plain',
                        key       = f"tv_{study}"
                    )
                if csv_path:
                    csv_content = open(csv_path, encoding='utf-8').read()
                    st.download_button(
                        label     = "⬇ Download CSV",
                        data      = csv_content,
                        file_name = os.path.basename(csv_path),
                        mime      = 'text/csv',
                        key       = f"csv_{study}"
                    )

            with col1:
                if csv_path:
                    df = load_csv(csv_path, index_col='rank')
                    if df is not None and len(df) > 0:
                        base_cols  = ['ticker', 'name', 'cap_band', 'close',
                                      'vol_label', 'acc_watch', 'regime_label', 'score_final']
                        extra_cols = ['sector', 'commodity', 'type',
                                      'rs_ratio', 'peer_rs_score', 'ret_6m', 'ret_12m',
                                      'max_dd', 'rs_trend', 'delta_rank']
                        show_cols  = [c for c in base_cols + extra_cols if c in df.columns]
                        st.dataframe(
                            style_df(df[show_cols], 'regime_label', 'delta_rank'),
                            width='stretch',
                            height=300
                        )
                else:
                    st.info("No CSV available for this study — TradingView import only")

            st.divider()

# RUN SCRIPTS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Run Scripts":
    st.title("🚀 Run Scripts")
    st.caption("Scripts run synchronously — page will wait until complete")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Macro")
        if st.button("Run Macro Report"):
            run_script(os.path.join(MACRO, 'macro_report.py'), MACRO)

        st.subheader("Debt Markets")
        if st.button("Run Debt Markets Report"):
            run_script(os.path.join(MACRO, 'consumer_credit.py'), MACRO)

        st.subheader("AU Market")
        if st.button("Run AU Screener"):
            run_script(os.path.join(STOCKS, 'au_total_market_screener.py'), STOCKS)
        if st.button("Run AU Benchmark"):
            run_script(os.path.join(STOCKS, 'au_total_market_benchmark.py'), STOCKS)
        if st.button("Run AU Breadth"):
            run_script(os.path.join(STOCKS, 'au_total_market_breadth.py'), STOCKS)

        st.subheader("US Market")
        if st.button("Run US Screener"):
            run_script(os.path.join(STOCKS, 'us_total_market_screener.py'), STOCKS)
        if st.button("Run US Benchmark"):
            run_script(os.path.join(STOCKS, 'us_total_market_benchmark.py'), STOCKS)
        if st.button("Run US Breadth"):
            run_script(os.path.join(STOCKS, 'us_total_market_breadth.py'), STOCKS)

    with col2:
        st.subheader("Commodities")
        if st.button("Run Commodities Screener"):
            run_script(os.path.join(STOCKS, 'all_major_commodities_screener.py'), STOCKS)
        if st.button("Run Commodities Benchmark"):
            run_script(os.path.join(STOCKS, 'all_major_commodities_benchmark.py'), STOCKS)
        if st.button("Run Commodities Breadth"):
            run_script(os.path.join(STOCKS, 'all_major_commodities_breadth.py'), STOCKS)

        st.subheader("Uranium")
        if st.button("Run Uranium Benchmark"):
            run_script(os.path.join(STOCKS, 'uranium_benchmark.py'), STOCKS)
        if st.button("Run Uranium Screener"):
            run_script(os.path.join(STOCKS, 'uranium_screener.py'), STOCKS)

        st.subheader("AU Gold Miners")
        if st.button("Run AU Gold Benchmark"):
            run_script(os.path.join(STOCKS, 'au_gold_miners_benchmark.py'), STOCKS)
        if st.button("Run AU Gold Screener"):
            run_script(os.path.join(STOCKS, 'au_gold_miners_screener.py'), STOCKS)

        st.subheader("Batch Runs")
        if st.button("🔄 Run ALL — Full daily run", type="primary"):
            for script in [
                ('macro_report.py', MACRO),
                ('au_total_market_screener.py', STOCKS),
                ('au_total_market_benchmark.py', STOCKS),
                ('au_total_market_breadth.py', STOCKS),
                ('us_total_market_screener.py', STOCKS),
                ('us_total_market_benchmark.py', STOCKS),
                ('us_total_market_breadth.py', STOCKS),
                ('all_major_commodities_screener.py', STOCKS),
                ('all_major_commodities_benchmark.py', STOCKS),
                ('all_major_commodities_breadth.py', STOCKS),
                ('uranium_benchmark.py', STOCKS),
                ('uranium_screener.py', STOCKS),
                ('au_gold_miners_benchmark.py', STOCKS),
                ('au_gold_miners_screener.py', STOCKS),
            ]:
                run_script(os.path.join(script[1], script[0]), script[1])

        if st.button("🇦🇺 Run ALL AU Market", type="secondary"):
            for script in [
                ('au_total_market_screener.py',   STOCKS),
                ('au_total_market_benchmark.py',  STOCKS),
                ('au_total_market_breadth.py',    STOCKS),
                ('au_gold_miners_benchmark.py',   STOCKS),
                ('au_gold_miners_screener.py',    STOCKS),
                ('rrg_au_data.py',                STOCKS),
            ]:
                run_script(os.path.join(script[1], script[0]), script[1])

        if st.button("🇺🇸 Run ALL US Market", type="secondary"):
            for script in [
                ('us_total_market_screener.py',   STOCKS),
                ('us_total_market_benchmark.py',  STOCKS),
                ('us_total_market_breadth.py',    STOCKS),
                ('uranium_benchmark.py',          STOCKS),
                ('uranium_screener.py',           STOCKS),
                ('rrg_us_data.py',                STOCKS),
            ]:
                run_script(os.path.join(script[1], script[0]), script[1])

        st.subheader("Utilities — Market Cap Update")
        st.caption("Run monthly to keep cap bands current")
        if st.button("Fetch Market Caps — AU"):
            run_script(os.path.join(BASE, 'utilities', 'fetch_market_caps_au.py'), os.path.join(BASE, 'utilities'))
        if st.button("Fetch Market Caps — US"):
            run_script(os.path.join(BASE, 'utilities', 'fetch_market_caps_us.py'), os.path.join(BASE, 'utilities'))
        if st.button("Fetch Market Caps — Commodities"):
            run_script(os.path.join(BASE, 'utilities', 'fetch_market_caps_commodities.py'), os.path.join(BASE, 'utilities'))
        if st.button("Fetch Market Caps — Uranium"):
            run_script(os.path.join(BASE, 'utilities', 'fetch_market_caps_uranium.py'), os.path.join(BASE, 'utilities'))
        if st.button("Fetch Market Caps — AU Gold"):
            run_script(os.path.join(BASE, 'utilities', 'fetch_market_caps_au_gold.py'), os.path.join(BASE, 'utilities'))
        if st.button("📈 Run DeMark Scan"):
            import sys
            sys.path.insert(0, STOCKS)
            from demark_scan import run_scan
            with st.spinner("Running DeMark scan..."):
                run_scan()

# ═══════════════════════════════════════════════════════════════════════════════
# DEMARK SIGNALS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "DeMark Signals":
    st.title("📈 DeMark Signal Scanner")
    st.markdown("""
        <div class="info-card">
            Scans the US market for TD Setup 9 and TD Countdown 13 signals on daily and weekly timeframes.
            <b>DM9 Top</b> — sell setup exhaustion (9 consecutive closes above close 4 bars prior) — potential reversal down.
            <b>DM9 Bottom</b> — buy setup exhaustion — potential reversal up.
            <b>DM13</b> — countdown exhaustion, higher conviction signal than setup alone.
            Signals are not directional certainties — they indicate exhaustion of the current move and increased probability of reversal.
        </div>
    """, unsafe_allow_html=True)

    demark_dir = os.path.join(STOCKS, 'results', 'demark')

    # ── Controls ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        cap_min = st.slider("Min Market Cap ($B)", 0.0, 10.0, 0.0, 0.5,
                             help="0 = no minimum filter")
    with col2:
        cap_max_enabled = st.toggle("Apply upper cap limit", value=False)
    with col3:
        if cap_max_enabled:
            cap_max = st.slider("Max Market Cap ($B)", 0.5, 100.0, 5.0, 0.5)
        else:
            st.caption("No upper limit applied")
            cap_max = None
    with col4:
        scan_date = st.date_input("Scan as of date", value=datetime.today(),
                                   max_value=datetime.today())
        run_btn = st.button("▶ Run DeMark Scan", type="primary")

    if run_btn:
        with st.spinner("Fetching prices and scanning signals — this may take 5-10 minutes..."):
            import sys
            sys.path.insert(0, STOCKS)
            from demark_scan import run_scan
            cap_min_val = int(cap_min * 1e9) if cap_min > 0 else 0
            cap_max_val = int(cap_max * 1e9) if cap_max_enabled and cap_max else None
            df_scan, report = run_scan(
                market_cap_min = cap_min_val,
                market_cap_max = cap_max_val,
                end_date       = scan_date.strftime('%Y-%m-%d')
            )
        if df_scan is not None:
            st.success(f"✓ Scan complete — {len(df_scan)} stocks analysed")
            st.rerun()

    # ── Date selector ─────────────────────────────────────────────────────────
    report_files = sorted(glob.glob(os.path.join(demark_dir, '*_demark.csv')), reverse=True)

    if not report_files:
        st.info("No scan results found — run the scanner above")
    else:
        dates     = [os.path.basename(f)[:8] for f in report_files][:10]
        sel_date  = st.selectbox("Select scan date", dates)
        csv_file  = os.path.join(demark_dir, f"{sel_date}_demark.csv")
        txt_file  = os.path.join(demark_dir, f"{sel_date}_demark_report.txt")

        df = load_csv(csv_file)

        if df is not None and len(df) > 0:
            # Apply market cap filter to display
            df['market_cap'] = pd.to_numeric(df['market_cap'], errors='coerce')
            df_filtered = df.copy()
            if cap_min > 0:
                df_filtered = df_filtered[df_filtered['market_cap'] >= cap_min * 1e9]
            if cap_max_enabled and cap_max:
                df_filtered = df_filtered[df_filtered['market_cap'] <= cap_max * 1e9]
            
            cap_max_label = f"${cap_max:.1f}B" if cap_max_enabled and cap_max else "no limit"
            st.caption(f"Showing {len(df_filtered)} stocks | Market cap ${cap_min:.1f}B — {cap_max_label}")

            # ── Signal groups ──────────────────────────────────────────────────
            SIGNAL_GROUPS = [
                ('DM9 Top Daily',      'd_setup9_sell',  'DM9 Top Daily',      '#e63946'),
                ('DM9 Bottom Daily',   'd_setup9_buy',   'DM9 Bottom Daily',   '#2dc653'),
                ('DM9 Top Weekly',     'w_setup9_sell',  'DM9 Top Weekly',     '#e63946'),
                ('DM9 Bottom Weekly',  'w_setup9_buy',   'DM9 Bottom Weekly',  '#2dc653'),
                ('DM13 Top Daily',     'd_cd13_sell',    'DM13 Top Daily',     '#c1121f'),
                ('DM13 Bottom Daily',  'd_cd13_buy',     'DM13 Bottom Daily',  '#00b050'),
                ('DM13 Top Weekly',    'w_cd13_sell',    'DM13 Top Weekly',    '#c1121f'),
                ('DM13 Bottom Weekly', 'w_cd13_buy',     'DM13 Bottom Weekly', '#00b050'),
            ]

            # Text report
            with st.expander("📄 Text Report", expanded=False):
                report_txt = load_txt(txt_file)
                if report_txt:
                    st.code(report_txt, language=None)

            st.divider()

            # Display each signal group
            for group_name, col_flag, label, colour in SIGNAL_GROUPS:
                if col_flag not in df_filtered.columns:
                    continue
                mask    = df_filtered[col_flag] == True
                grp_df  = df_filtered[mask].copy()

                if len(grp_df) == 0:
                    continue

                tickers_str = ','.join(sorted(grp_df['ticker'].tolist()))

                st.markdown(f"""
                    <div style="color:{colour};font-weight:bold;font-size:14px;
                                margin-bottom:4px;font-family:monospace">
                        {label}:
                    </div>
                    <div style="font-size:13px;color:#ccc;margin-bottom:8px;
                                font-family:monospace;word-break:break-all">
                        {tickers_str}
                    </div>
                """, unsafe_allow_html=True)

                c1, c2 = st.columns([3, 1])
                with c2:
                    st.download_button(
                        label     = "⬇ TV Import",
                        data      = tickers_str,
                        file_name = f"{sel_date}_{group_name.replace(' ','_').lower()}_tvimport.txt",
                        mime      = 'text/plain',
                        key       = f"tv_{group_name}"
                    )
                    st.caption(f"{len(grp_df)} tickers")

                with c1:
                    show_cols = ['ticker','name','sector','cap_band','market_cap_b']
                    show_cols = [c for c in show_cols if c in grp_df.columns]
                    st.dataframe(
                        grp_df[show_cols].sort_values('ticker'),
                        width='stretch',
                        hide_index=True,
                        height=min(len(grp_df) * 35 + 40, 300)
                    )

                st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Settings":
    st.title("⚙ Dashboard Settings")
    st.caption("Changes take effect after saving and reloading the page")

    current = load_settings()

    # ── Pages ─────────────────────────────────────────────────────────────────
    st.subheader("Pages")
    st.markdown("Toggle pages on or off. Settings is always visible.")

    updated_pages = {}
    cols = st.columns(3)
    for i, (name, icon) in enumerate(ALL_PAGES):
        if name == 'Settings':
            continue
        with cols[i % 3]:
            updated_pages[name] = st.toggle(
                name,
                value=current['pages'].get(name, True),
                key=f"setting_{name}"
            )

    # ── AI Features ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("AI Features")
    st.caption("Requires an Anthropic API key — get one free at console.anthropic.com")

    ai_enabled = st.toggle(
        "Enable AI assessments",
        value=current.get('ai_features', {}).get('enabled', False),
        key='setting_ai_enabled'
    )
    if ai_enabled:
        api_key = st.text_input(
            "Anthropic API Key",
            value=current.get('ai_features', {}).get('anthropic_api_key', ''),
            type="password",
            key='setting_api_key',
            help="Stored locally in dashboard_settings.json — never pushed to GitHub"
        )
        model = st.selectbox(
            "Model",
            ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
            index=0,
            key='setting_model'
        )
    else:
        api_key = current.get('ai_features', {}).get('anthropic_api_key', '')
        model   = current.get('ai_features', {}).get('model', 'claude-sonnet-4-6')

    # ── Save / Reset ──────────────────────────────────────────────────────────
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save & Reload", type="primary"):
            current['pages']       = updated_pages
            current['ai_features'] = {
                'enabled'          : ai_enabled,
                'anthropic_api_key': api_key,
                'model'            : model,
            }
            save_settings(current)
            st.success("Settings saved")
            st.rerun()
    with col2:
        if st.button("Reset to defaults", type="secondary"):
            save_settings(DEFAULT_SETTINGS)
            st.success("Reset to defaults")
            st.rerun()

    # ── Display Settings ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("Display")

    # Theme
    st.markdown("**Theme**")
    st.caption("Sets chart backgrounds and colours. Restart may be required for full effect.")

    cfg_file = os.path.join(BASE, '.streamlit', 'config.toml')
    current_base = 'dark'
    if os.path.isfile(cfg_file):
        import re as _re2
        txt = open(cfg_file).read()
        m = _re2.search(r'base\s*=\s*"([^"]*)"', txt)
        if m: current_base = m.group(1).lower()

    theme_names  = list(THEMES.keys())
    theme_idx    = 1 if current_base == 'light' else 0
    selected_theme = st.radio("Theme", theme_names, horizontal=True,
                               index=theme_idx, key='disp_theme')

    if selected_theme == 'Custom':
        pass  # reserved for future custom picker

    tc1, tc2 = st.columns(2)
    with tc1:
        if st.button(f"Apply {selected_theme} Theme", type="primary", key='apply_theme'):
            _write_streamlit_config(THEMES[selected_theme])
            _s = load_settings()
            _s['theme'] = selected_theme.lower()
            save_settings(_s)
            st.success(f"{selected_theme} theme applied — reload the page to see effect")
            st.rerun()
    with tc2:
        st.caption("After applying, use the Streamlit menu (top right ☰) to also toggle the app theme if needed.")

    # Font size
    st.markdown("**Text Size**")
    st.caption("Applies immediately — no reload needed.")
    font_size = st.radio("Text size",
                          ["Normal", "Large (+2px)", "Extra Large (+4px)"],
                          horizontal=True, key="st_font_size")
    _size_map = {"Normal": 0, "Large (+2px)": 2, "Extra Large (+4px)": 4}
    _delta = _size_map.get(font_size, 0)
    if _delta > 0:
        st.markdown(f"""<style>
        html, body, [class*="css"] {{ font-size: calc(1rem + {_delta}px) !important; }}
        .stMarkdown p, .stMarkdown li, .stCaption, label {{
            font-size: calc(1rem + {_delta}px) !important;
        }}
        h1 {{ font-size: calc(2rem   + {_delta}px) !important; }}
        h2 {{ font-size: calc(1.5rem + {_delta}px) !important; }}
        h3 {{ font-size: calc(1.25rem + {_delta}px) !important; }}
        </style>""", unsafe_allow_html=True)

    with st.expander("Current config.toml"):
        if os.path.isfile(cfg_file):
            st.code(open(cfg_file).read(), language="toml")
        else:
            st.caption("No config.toml yet — created on first Apply.")