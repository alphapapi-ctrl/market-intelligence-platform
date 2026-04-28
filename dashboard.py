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
        'Seasonality'         : True,
        'Debt Markets'        : True,
        'AU Market'           : True,
        'US Market'           : True,
        'Commodities'         : True,
        'RRG Charts'          : True,
        'Drawdown Analysis'   : True,
        'Actionable & Exports': True,
        'DeMark Signals'      : True,
        'Run Scripts'         : True,
        'Rank Settings'       : True,
        'Settings'            : True,
    },
    'rank_settings': {

        'au_screener': {
            'min_market_cap'   : 2000000000,
            'min_vol_avg'      : 500000,
            'regime_filter'    : ['LEADER', 'CONTENDER'],
        },
        'us_screener': {
            'min_market_cap'   : 2000000000,
            'min_vol_avg'      : 500000,
            'regime_filter'    : ['LEADER', 'CONTENDER'],
        },
        'comm_screener': {
            'min_market_cap'   : 0,
            'min_vol_avg'      : 0,
            'regime_filter'    : ['LEADER', 'CONTENDER'],
        },
        'au_benchmark': {
            'ret_12m_weight': 0.4, 'persist_weight': 0.01, 'mqs_weight': 0.2,
            'trend_bonus': 1.0, 'lead_bonus': 1.0,
            'dd_weight_large': 0.4, 'dd_weight_mid': 0.3, 'dd_weight_small': 0.2, 'dd_weight_etf': 0.3,
            'vol_high': 1.1, 'vol_med': 1.0, 'vol_low': 0.9,
            'rs_trend_strong_up': 1.0, 'rs_trend_up': 0.5, 'rs_trend_flat': 0.0, 'rs_trend_down': -0.5, 'rs_trend_strong_down': -1.0,
        },
        'us_benchmark'  : {},
        'comm_benchmark': {},
    },
    'ai_prompts': {
        'au_breadth':    "You are a market breadth analyst for the Australian stock market (ASX).\nAnalyse these breadth readings and provide a concise 4-5 sentence assessment.\nFocus on: (1) overall market health and trend, (2) cap band divergences (large vs small),\n(3) key sector rotations, (4) what the breadth signals suggest about near-term direction.\nBe direct and specific — mention actual numbers.",
        'us_breadth':    "You are a market breadth analyst for the US stock market.\nAnalyse these breadth readings and provide a concise 4-5 sentence assessment.\nFocus on: (1) overall market health across all 3 layers, (2) divergences between layers,\n(3) key sector rotations in Layer 2, (4) what the breadth signals suggest about near-term direction.\nBe direct and specific — mention actual numbers.",
        'consumer_credit': "You are a macro credit analyst. Analyse these US consumer credit readings and provide a 3-4 sentence assessment focusing on: credit stress signals, delinquency trends, and what this means for consumer spending and equity markets.",
        'corporate_credit': "Analyse these US corporate credit readings in 3-4 sentences. Focus on HY spreads, investment grade conditions, and systemic risk signals.",
        'sovereign_credit': "Analyse US sovereign credit health in 3-4 sentences. Focus on yield curve shape, duration risk, and what rates signal about macro conditions.",
        'au_benchmark':  "You are a quantitative analyst. Analyse this AU market relative strength data and provide a 4-5 sentence assessment covering: top momentum leaders, laggards to avoid, sector rotation signals, and any regime changes visible in the data.",
        'us_benchmark':  "You are a quantitative analyst. Analyse this US market relative strength data and provide a 4-5 sentence assessment covering: top momentum leaders, laggards to avoid, sector rotation signals, and any regime changes visible in the data.",
        'comm_benchmark': "You are a commodity market analyst. Analyse this commodity relative strength data and provide a 4-5 sentence assessment covering: leading commodities, lagging groups, rotation signals, and what this implies for risk appetite.",
    },
    'ai_features': {
        'enabled'          : False,
        'provider'         : 'anthropic',
        'anthropic_api_key': '',
        'model'            : 'claude-sonnet-4-6',
    }
}


BM_DEFAULTS = {
    'ret_12m_weight': 0.4, 'persist_weight': 0.01, 'mqs_weight': 0.2,
    'trend_bonus': 1.0, 'lead_bonus': 1.0,
    'dd_weight_large': 0.4, 'dd_weight_mid': 0.3, 'dd_weight_small': 0.2, 'dd_weight_etf': 0.3,
    'vol_high': 1.1, 'vol_med': 1.0, 'vol_low': 0.9,
    'rs_trend_strong_up': 1.0, 'rs_trend_up': 0.5, 'rs_trend_flat': 0.0,
    'rs_trend_down': -0.5, 'rs_trend_strong_down': -1.0,
}
SC_DEFAULTS = {
    'ret_12m_weight': 0.4, 'persist_weight': 0.01, 'mqs_weight': 0.2, 'peer_rs_weight': 0.02,
    'dd_weight_large': 0.4, 'dd_weight_mid': 0.3, 'dd_weight_small': 0.2, 'dd_weight_etf': 0.3,
    'vol_high': 1.1, 'vol_med': 1.0, 'vol_low': 0.9,
    'rs_trend_strong_up': 1.0, 'rs_trend_up': 0.5, 'rs_trend_flat': 0.0,
    'rs_trend_down': -0.5, 'rs_trend_strong_down': -1.0,
    'regime_bonus_leader': 1.0, 'regime_bonus_contender': 0.5,
    'regime_bonus_laggard': 0.0, 'regime_bonus_weak': -0.5,
    'min_market_cap': 2000000000, 'min_vol_avg': 500000,
    'regime_filter': ['LEADER', 'CONTENDER'],
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
    ("Macro",                    "globe"),
    ("AU Market",                "flag"),
    ("US Market",                "flag"),
    ("Commodities",              "hammer"),
    ("Debt Markets",             "credit-card"),
    ("Seasonality",              "calendar3"),
    ("DeMark Signals",           "graph-up"),
    ("Relative Strength Charts", "broadcast"),
    ("Actionable & Exports",     "file-earmark-arrow-down"),
    ("Drawdown Analysis",        "graph-down"),
    ("Run Scripts",              "play-circle"),
    ("Rank Settings",            "sliders"),
    ("Settings",                 "gear"),
]

# Filter to enabled pages — Settings always shown
active_pages = [(name, icon) for name, icon in ALL_PAGES
                if page_config.get(name, True) or name in ('Rank Settings', 'Settings')]

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

    _mh1, _mh2, _mh3 = st.columns([900, 6000, 2000])
    with _mh2:
        st.title("🌍 Macro Dashboard")
    with _mh3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📊 Run Macro Report", key='top_macro_btn'):
            run_script(os.path.join(MACRO, 'macro_report.py'), MACRO)
            st.rerun()
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
        # Equities
        'SPX'    : ('^GSPC',   'S&P 500',        'equity'),
        'RSP'    : ('RSP',     'S&P EW (RSP)',    'equity'),
        'NDX'    : ('^NDX',    'Nasdaq 100',      'equity'),
        'IWM'    : ('IWM',     'Russell 2000',    'equity'),
        'XJO'    : ('^AXJO',   'ASX 200',         'equity'),
        # Global Indices
        'NKY'    : ('^N225',   'Nikkei 225',      'global'),
        'TSX'    : ('^GSPTSE', 'TSX (Canada)',     'global'),
        'FTSE'   : ('^FTSE',   'FTSE 100',        'global'),
        'DAX'    : ('^GDAXI',  'DAX',             'global'),
        'HSI'    : ('^HSI',    'Hang Seng',       'global'),
        'KOSPI'  : ('^KS11',   'South Korea (KOSPI)', 'global'),
        # FX
        'DXY'    : ('DX-Y.NYB','DXY',             'fx'),
        'AUDUSD' : ('AUDUSD=X','AUD/USD',         'fx'),
        'GBPUSD' : ('GBPUSD=X','GBP/USD',         'fx'),
        'EURUSD' : ('EURUSD=X','EUR/USD',         'fx'),
        'NZDUSD' : ('NZDUSD=X','NZD/USD',         'fx'),
        'JPYUSD' : ('JPY=X',   'JPY/USD',         'fx'),
        'CHFUSD' : ('CHF=X',   'CHF/USD',         'fx'),
        # Commodities
        'GSCI'   : ('^SPGSCI', 'GSCI Index',      'commodity'),
        'Gold'   : ('GC=F',    'Gold',            'commodity'),
        'Silver' : ('SI=F',    'Silver',          'commodity'),
        'Platinum': ('PL=F',   'Platinum',        'commodity'),
        'Palladium': ('PA=F',  'Palladium',       'commodity'),
        'Copper' : ('HG=F',    'Copper',          'commodity'),
        'Nickel' : ('^SPGSIK', 'Nickel (GSCI)',   'commodity'),
        'NatGas' : ('NG=F',    'Nat Gas',         'commodity'),
        'Oil'    : ('CL=F',    'Oil WTI',         'commodity'),
        # Rates
        'US10Y'  : ('^TNX',    'US 10Y',          'rates'),
        'US2Y'   : ('^IRX',    'US 2Y',           'rates'),
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
            ("Equities & Global", ['SPX','RSP','NDX','IWM','XJO',
                                   'NKY','TSX','FTSE','DAX','HSI','KOSPI']),
            ("Commodities",       ['GSCI','Gold','Silver','Platinum','Palladium',
                                   'Copper','Nickel','NatGas','Oil']),
            ("FX",                ['DXY','AUDUSD','GBPUSD','EURUSD','NZDUSD','JPYUSD','CHFUSD']),
        ]

        # 3-column table layout — Equities & Global | Commodities | FX
        _lc1, _lc2, _lc3 = st.columns(3)
        _live_cols = [_lc1, _lc2, _lc3]

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

    # ── HGX Housing Lead Indicator ───────────────────────────────────────────────
    try:
        from datetime import timedelta as _td_hgx
        import pandas as _pd_hgx
        # Use Ticker object to avoid MultiIndex issues with newer yfinance
        _hgx_tkr  = yf.Ticker('^HGX')
        _hgx_hist = _hgx_tkr.history(period='5y')
        if _hgx_hist.empty:
            raise ValueError("No HGX data returned")
        _hgx_data = _hgx_hist['Close'].dropna()
        if len(_hgx_data) > 20:
            _hgx_curr  = float(_hgx_data.iloc[-1])
            # Find the most recent local peak, then check drawdown from that peak
            # Use a rolling 252-day window to find recent peaks
            _cutoff    = _hgx_data.index[-1] - _td_hgx(days=18*30)
            _recent    = _hgx_data[_hgx_data.index >= _cutoff]
            _peak_idx  = _recent.idxmax()
            _peak_val  = float(_recent.max())
            _curr_dd   = (_hgx_curr - _peak_val) / _peak_val * 100
            _days_since = (_hgx_data.index[-1].tz_localize(None) - _peak_idx.tz_localize(None)).days

            # Also check if any point in last 18 months crossed -20% from a preceding high
            _cummax_full = _hgx_data.cummax()
            _dd_full     = (_hgx_data - _cummax_full) / _cummax_full * 100
            _recent_dd   = _dd_full[_dd_full.index >= _cutoff]
            _worst_recent = float(_recent_dd.min()) if len(_recent_dd) else 0
            _worst_idx   = _recent_dd.idxmin() if len(_recent_dd) else None

            if _worst_recent <= -20 and _worst_idx is not None:
                _trough_idx  = _worst_idx
                _trough_dd   = _worst_recent
                _trough_val  = float(_hgx_data.loc[_trough_idx])
                _peak_slice  = _hgx_data.loc[:_trough_idx]
                _peak_before = float(_peak_slice.max())
                _peak_date   = _peak_slice.idxmax().strftime('%d %b %Y')
                _trough_date = _trough_idx.strftime('%d %b %Y')
                _trough_dt   = _pd_hgx.Timestamp(_trough_idx).tz_localize(None)
                _reset_date  = (_trough_dt + _td_hgx(days=18*30)).strftime('%d %b %Y')
                st.markdown(f"""
<div style="background:rgba(255,180,0,0.10);border:1px solid rgba(255,180,0,0.5);
border-left:4px solid #f77f00;border-radius:8px;padding:12px 16px;margin-bottom:12px">
🏠 <b>HGX Housing Index — Caution Signal Active</b><br>
<span style="font-size:12px">
HGX fell <b style="color:#f77f00">{_trough_dd:.1f}%</b> from its high of
<b>{_peak_before:,.0f}</b> ({_peak_date}) to a trough of <b>{_trough_val:,.0f}</b> on <b>{_trough_date}</b>.
A ≥20% HGX drawdown has historically preceded broader economic weakness 6–18 months ahead.
Currently <b>{_hgx_curr:,.0f}</b>. Signal resets <b>{_reset_date}</b> (18 months from trough).
</span>
</div>
""", unsafe_allow_html=True)
        else:
            st.caption(f"HGX: insufficient data ({len(_hgx_data)} rows)")
    except Exception as _e_hgx:
        st.caption(f"HGX indicator error: {_e_hgx}")

    # ── Business Cycle + Macro Quad Banner ───────────────────────────────────────
    _pmi         = macro.get('pmi', 50)
    _cu_gold_63d = macro.get('cu_gold_chg_63d')
    _yc_vel      = macro.get('yc_roc_5d', 0)
    _growth_up   = _pmi >= 50
    if _cu_gold_63d is not None:
        _inflation_up = _cu_gold_63d > 0
    else:
        _inflation_up = _yc_vel > 0

    if _growth_up and _inflation_up:
        _quad=2; _quad_label="QUAD 2 — Inflationary Boom"; _quad_sub="Growth ↑ / Inflation ↑"
        _quad_favours="Commodities, Energy, Emerging Markets"; _quad_col="#c8860a"; _quad_bg="rgba(200,134,10,0.10)"
    elif _growth_up and not _inflation_up:
        _quad=4; _quad_label="QUAD 4 — Dis-inflationary Boom"; _quad_sub="Growth ↑ / Inflation ↓"
        _quad_favours="Stocks, Property, Long Duration"; _quad_col="#2a8a6e"; _quad_bg="rgba(42,138,110,0.10)"
    elif not _growth_up and _inflation_up:
        _quad=1; _quad_label="QUAD 1 — Stagflation"; _quad_sub="Growth ↓ / Inflation ↑"
        _quad_favours="Gold/Silver, Materials, Commodities, Cash"; _quad_col="#c45c0a"; _quad_bg="rgba(196,92,10,0.10)"
    else:
        _quad=3; _quad_label="QUAD 3 — Deflationary Bust"; _quad_sub="Growth ↓ / Inflation ↓"
        _quad_favours="Gold, Cash, Treasuries"; _quad_col="#c0392b"; _quad_bg="rgba(192,57,43,0.10)"

    # GDP from FRED
    @st.cache_data(ttl=43200)
    def _fetch_gdp_fred():
        try:
            import pandas_datareader.data as _web
            from datetime import datetime as _dt, timedelta as _td
            _df = _web.DataReader('A191RL1Q225SBEA','fred',_dt(2020,1,1),_dt.today()).dropna()
            if _df.empty: return None,None,None
            _last_date=_df.index[-1]; _last_val=float(_df.iloc[-1,0])
            _qtr_month=((_last_date.month-1)//3+1)*3
            _next_qtr_end=_dt(_last_date.year+(_last_date.month>9),((_qtr_month%12)+3 if _qtr_month<10 else 3),1)-_td(days=1)
            _next_release=_next_qtr_end+_td(days=30)
            return _last_val,_last_date.strftime('%d %b %Y'),_next_release.strftime('%d %b %Y')
        except: return None,None,None
    _gdp_val,_gdp_date,_gdp_next=_fetch_gdp_fred()
    if _gdp_val is None: _gdp_val=macro.get('gdp_growth'); _gdp_date=None; _gdp_next=None
    if _gdp_val is not None:
        _gdp_dir='↑ Expanding' if _gdp_val>0 else '↓ Contracting'
        _gdp_str=f"{_gdp_val:+.1f}% QoQ ann. ({_gdp_dir})"
        if _gdp_date: _gdp_str+=f" — last: {_gdp_date}"
        if _gdp_next: _gdp_str+=f" | next est. {_gdp_next}"
        if _gdp_val<0 and _growth_up: _gdp_str+=" ⚠ diverges from PMI"
    else: _gdp_str="Not yet available (quarterly)"

    # CPI from FRED
    @st.cache_data(ttl=43200)
    def _fetch_cpi_fred():
        try:
            import pandas_datareader.data as _web
            from datetime import datetime as _dt, timedelta as _td
            _df=_web.DataReader('CPIAUCSL','fred',_dt(2022,1,1),_dt.today()).dropna()
            if len(_df)<13: return None,None,None,None,None
            _last=float(_df.iloc[-1,0]); _prev_mo=float(_df.iloc[-2,0]); _prev_yr=float(_df.iloc[-13,0])
            _mom=round((_last/_prev_mo-1)*100,2); _yoy=round((_last/_prev_yr-1)*100,2)
            _last_date=_df.index[-1].strftime('%b %Y')
            _next_mo=(_df.index[-1].replace(day=1)+_td(days=45)).replace(day=15)
            return _mom,_yoy,_last_date,_next_mo.strftime('%d %b %Y'),_last
        except: return None,None,None,None,None
    _cpi_mom,_cpi_yoy,_cpi_date,_cpi_next,_cpi_idx=_fetch_cpi_fred()
    if _cpi_mom is not None:
        _inflation_up=_cpi_mom>0
        _cpi_str=f"CPI {_cpi_yoy:+.1f}% YoY | {_cpi_mom:+.2f}% MoM ({'↑ Rising' if _cpi_mom>0 else '↓ Falling'}) — {_cpi_date} | next ~{_cpi_next}"
    else: _cpi_str="CPI: not available"

    _pmi_str=f"PMI {_pmi:.1f} ({'↑ Expanding' if _growth_up else '↓ Contracting'})"
    _cu_str=(f"Cu/Gold 63d {_cu_gold_63d:+.1f}% ({'↑ Rising' if _inflation_up else '↓ Falling'})"
             if _cu_gold_63d is not None else f"YC Velocity {_yc_vel:+.2f}%")

    st.markdown(f"""
<div style="background:{_quad_bg};border:1px solid {_quad_col};border-left:5px solid {_quad_col};border-radius:8px;padding:12px 18px;margin-bottom:8px">
<div style="font-size:14px;font-weight:700;color:{_quad_col};margin-bottom:4px">📐 {_quad_label} <span style="font-weight:400;font-size:12px">({_quad_sub})</span></div>
<div style="display:flex;gap:24px;flex-wrap:wrap;font-size:12px">
  <div><b>Favours:</b> {_quad_favours}</div>
  <div><b>Growth — PMI:</b> {_pmi_str}</div>
  <div><b>Growth — GDP:</b> {_gdp_str}</div>
  <div><b>Inflation — CPI:</b> {_cpi_str}</div>
  <div><b>Inflation — Cu/Gold:</b> {_cu_str}</div>
</div></div>
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

    # ── Recession Warning Indicators ─────────────────────────────────────────────
    @st.cache_data(ttl=43200)
    def _fetch_recession_signals():
        try:
            import pandas_datareader.data as _web
            from datetime import datetime as _dt, timedelta as _td
            _start=_dt(2020,1,1); _today=_dt.today(); _sigs={}
            try:
                _u=_web.DataReader('UNRATE','fred',_start,_today).dropna()
                if len(_u)>=13:
                    _cur=float(_u.iloc[-1,0]); _min12=float(_u.iloc[-13:,0].min())
                    _sigs['unemp']={'value':_cur,'trough':_min12,'date':_u.index[-1].strftime('%b %Y'),'triggered':_cur>_min12+0.3}
            except: pass

            try:
                _hs=_web.DataReader('HOUST','fred',_start,_today).dropna()
                if len(_hs)>=13:
                    _cur=float(_hs.iloc[-1,0]); _pk=float(_hs.iloc[-13:,0].max())
                    _chg=round((_cur/_pk-1)*100,1)
                    _sigs['housing']={'value':round(_cur,0),'pct_from_peak':_chg,'date':_hs.index[-1].strftime('%b %Y'),'triggered':_chg<-15}
            except: pass
            return _sigs
        except: return {}

    _rec_sigs=_fetch_recession_signals()

    # Yield curve ratio
    _us10y=macro.get('us10y',0); _us2y=macro.get('us2y',0)
    _yc_ratio=round(_us10y/_us2y,4) if _us2y and _us2y>0 else None
    _yc_spread=macro.get('yield_curve',None)

    def _yc_ratio_check():
        if _yc_ratio is not None and _yc_ratio<1.25: return True
        if _yc_spread is not None and _yc_spread<0: return True
        return False
    def _yc_ratio_val():
        parts=[]
        if _yc_ratio:
            if _yc_ratio<1.0: _status=' 🔴 INVERTED'
            elif _yc_ratio<1.25: _status=' 🟠 below 1.25 — caution'
            else: _status=' 🔴 extreme — watch for acceleration'
            parts.append(f"Ratio: {_yc_ratio:.4f}{_status}")
        if _yc_spread is not None: parts.append(f"Spread: {_yc_spread:+.2f}%")
        return ' | '.join(parts) if parts else 'n/a'

    _unemp_val=macro.get('unemployment'); _unemp_sig=_rec_sigs.get('unemp',{})
    def _unemp_check():
        if _unemp_sig.get('triggered'): return True
        lbl=macro.get('unemp_label','').upper()
        return 'RISING' in lbl or 'TICKING UP' in lbl or 'INCREASING' in lbl
    def _unemp_val_fn():
        _uf=_unemp_sig.get('value'); _ut=_unemp_sig.get('trough')
        if _uf and _ut and _ut<_uf: return f"{_uf}% (+{_uf-_ut:.1f}pp from trough {_ut}%)"
        return f"{_unemp_val}% — {macro.get('unemp_label','')}" if _unemp_val else 'n/a'

    def _housing_check():
        if _rec_sigs.get('housing',{}).get('triggered'): return True
        try: return _trough_dd<=-20 and _days_since<=18*30
        except: return False
    def _housing_val_fn():
        parts=[]
        if 'housing' in _rec_sigs:
            _h=_rec_sigs['housing']; parts.append(f"Starts: {int(_h['value'])}K ({_h['pct_from_peak']:+.1f}% from peak)")
        try:
            if _trough_dd<=-20: parts.append(f"HGX: {_trough_dd:.1f}% drawdown (triggered)")
        except: pass
        return ' | '.join(parts) if parts else 'n/a'

    _RECESSION_INDICATORS=[
        {'key':'yield_curve','label':'📉 Yield Curve (US10Y/US02Y)','lead_time':'14–16 months',
         'check':_yc_ratio_check,'value_fn':_yc_ratio_val,
         'detail':'Ratio <1.25 = caution (orange), <1.0 = inverted (red). Above 1.25 = watch for acceleration.'},
        {'key':'unemp','label':'👷 Rising Unemployment','lead_time':'5–7 months',
         'check':_unemp_check,'value_fn':_unemp_val_fn,
         'detail':'Rising >0.3pp from cycle trough signals labour market softening'},

        {'key':'housing','label':'🏠 Housing Starts + HGX Decline','lead_time':'4–6 months',
         'check':_housing_check,'value_fn':_housing_val_fn,
         'detail':'Housing starts >15% below peak OR HGX ≥20% drawdown'},
        {'key':'hy_spread','label':'💳 HY Credit Spreads Widening','lead_time':'3–6 months',
         'check':lambda:macro.get('hy_spread',0)>4.0,
         'value_fn':lambda:f"{macro.get('hy_spread',0):.2f}% (warn >4%, stress >6%)",
         'detail':'HY spreads widening signals credit stress and risk-off'},
        {'key':'margin','label':'📈 Margin Debt Over-leverage','lead_time':'6–12 months',
         'check':lambda:macro.get('margin_m2',0)>1.4,
         'value_fn':lambda:f"Margin/M2: {macro.get('margin_m2',0):.4f} (extreme >1.4) | Accel: {macro.get('margin_acceleration',0):+.3f}%",
         'detail':'Margin/M2 ratio extreme — leveraged speculation at peak'},
    ]

    _active_triggers=[ind for ind in _RECESSION_INDICATORS if ind['check']()]
    _n_active=len(_active_triggers)

    if _n_active>=2:
        _rec_col='#e63946' if _n_active>=4 else '#f77f00'
        st.markdown(f"""<div style="background:rgba(230,57,70,0.08);border:1px solid {_rec_col};border-left:5px solid {_rec_col};border-radius:8px;padding:10px 16px;margin-bottom:8px">
<b>{'🔴' if _n_active>=4 else '🟠'} Recession Warning: {_n_active}/{len(_RECESSION_INDICATORS)} indicators triggered</b>
&nbsp;<span style="font-size:11px;color:#888">Score: {round(_n_active/len(_RECESSION_INDICATORS)*100)}%</span></div>""", unsafe_allow_html=True)

    with st.expander(f"🔍 Recession Warning Indicators — {_n_active}/{len(_RECESSION_INDICATORS)} active", expanded=False):
        for _ind in _RECESSION_INDICATORS:
            _triggered=_ind['check']()
            _val=_ind['value_fn']()
            _partial=(_ind['key']=='yield_curve' and _yc_ratio is not None and 1.0<=_yc_ratio<1.25)
            _dot='🔴' if (_triggered and not _partial) else '🟠' if _partial else '🟢'
            _status='TRIGGERED' if (_triggered and not _partial) else 'CAUTION' if _partial else 'Clear'
            _bdr='#e63946' if (_triggered and not _partial) else '#f77f00' if _partial else '#2dc653'
            _bg='230,57,70' if (_triggered and not _partial) else '247,127,0' if _partial else '45,198,83'
            _key_data=_rec_sigs.get(_ind['key'],{})
            _date_str=_key_data.get('date','') if _key_data else ''
            st.markdown(f"""<div style="border-left:3px solid {_bdr};padding:6px 12px;margin-bottom:6px;background:rgba({_bg},0.05);border-radius:0 6px 6px 0">
<div style="font-size:13px;font-weight:600">{_dot} {_ind['label']} <span style="font-size:11px;font-weight:400;color:#888;margin-left:8px">Lead time: {_ind['lead_time']} | {_date_str}</span> <span style="font-size:11px;font-weight:700;color:{_bdr};margin-left:8px">{_status}</span></div>
<div style="font-size:12px;color:#888;margin-top:2px">{_ind['detail']}</div>
<div style="font-size:12px;margin-top:2px"><b>Current:</b> {_val}</div></div>""", unsafe_allow_html=True)

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
        if _cpi_mom is not None:
            _cpi_good = _cpi_yoy < 3.0
            _ec_rows.append({'Indicator': f'CPI ({_cpi_date})',
                             'Value': f"{_cpi_yoy:+.1f}% YoY | {_cpi_mom:+.2f}% MoM",
                             'Signal': f"{'✓' if _cpi_good else '⚠'} {'Contained' if _cpi_good else 'Elevated'} — target 2%",
                             '_colour': '#2dc653' if _cpi_good else '#e63946'})

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
elif page == "Seasonality":
    import plotly.graph_objects as go
    import plotly.express as px
    st.title("📅 Seasonality")

    _sea_tab1, _sea_tab2, _sea_tab3 = st.tabs(["📊 Sectors", "🔍 Stocks", "🇺🇸 Presidential Cycle"])

    # ── Shared instruments ─────────────────────────────────────────────────────
    _INSTRUMENTS = {
        "AU Indices": {
            "All Ordinaries (^AORD)"  : "^AORD",
            "ASX 200 (^AXJO)"         : "^AXJO",
        },
        "AU Sectors": {
            "AU Energy (^AXEJ)"       : "^AXEJ",
            "AU Materials (^AXMJ)"    : "^AXMJ",
            "AU Financials (^AXFJ)"   : "^AXFJ",
            "AU Health (^AXHJ)"       : "^AXHJ",
            "AU Industrials (^AXIJ)"  : "^AXIJ",
            "AU Consumer Disc (^AXDJ)": "^AXDJ",
            "AU Consumer Staples (^AXSJ)": "^AXSJ",
            "AU Technology (^AXTJ)"   : "^AXTJ",
            "AU Utilities (^AXUJ)"    : "^AXUJ",
            "AU Real Estate (^AXPJ)"  : "^AXPJ",
            "AU Telecom (^AXNJ)"      : "^AXNJ",
        },
        "US Indices": {
            "S&P 500 (^GSPC)"         : "^GSPC",
            "Nasdaq 100 (^NDX)"       : "^NDX",
            "Russell 2000 (^RUT)"     : "^RUT",
            "Dow Jones (^DJI)"        : "^DJI",
        },
        "US Sectors": {
            "Technology (XLK)"        : "XLK",
            "Financials (XLF)"        : "XLF",
            "Healthcare (XLV)"        : "XLV",
            "Energy (XLE)"            : "XLE",
            "Industrials (XLI)"       : "XLI",
            "Consumer Disc (XLY)"     : "XLY",
            "Consumer Staples (XLP)"  : "XLP",
            "Materials (XLB)"         : "XLB",
            "Utilities (XLU)"         : "XLU",
            "Real Estate (XLRE)"      : "XLRE",
            "Communication (XLC)"     : "XLC",
        },
        "Commodities": {
            "GSCI Index (^SPGSCI)"    : "^SPGSCI",
            "Gold (GC=F)"             : "GC=F",
            "Silver (SI=F)"           : "SI=F",
            "Copper (HG=F)"           : "HG=F",
            "Oil WTI (CL=F)"          : "CL=F",
        },
    }

    # ── Tab 1: Seasonality Charts ───────────────────────────────────────────────
    with _sea_tab1:
        _sc1, _sc2, _sc3, _sc4 = st.columns([3, 2, 2, 2])
        _groups    = list(_INSTRUMENTS.keys())
        _grp_sel   = _sc1.selectbox("Asset class", _groups, key="sea_group")
        _inst_map  = _INSTRUMENTS[_grp_sel]
        _inst_sel  = _sc2.selectbox("Instrument", list(_inst_map.keys()), key="sea_inst")
        _ticker    = _inst_map[_inst_sel]
        _show_sea_avg = _sc4.toggle("Show average line", value=True, key="sea_show_avg")

        @st.cache_data(ttl=3600)
        def _fetch_sea(ticker):
            import yfinance as _yf
            df = _yf.download(ticker, start="1928-01-01", auto_adjust=True, progress=False)
            if df.empty: return None
            close = df["Close"].squeeze().dropna()
            close.index = pd.to_datetime(close.index).tz_localize(None)
            return close

        _sea_data = _fetch_sea(_ticker)
        if _sea_data is None or len(_sea_data) < 252:
            st.warning("Insufficient data for this instrument.")
        else:
            _min_yr = int(_sea_data.index.year.min())
            _max_yr = int(_sea_data.index.year.max())
            _yr_range = _sc3.slider("Year range", _min_yr, _max_yr,
                                     (_max_yr - 30, _max_yr), key="sea_yr")

            # All years in range
            _all_yrs_in_range = [y for y in range(_yr_range[0], _yr_range[1] + 1)
                                  if not _sea_data[_sea_data.index.year == y].empty]

            # Year filter multiselect — defaults to all
            _yr_excl = st.multiselect(
                "Exclude years", _all_yrs_in_range,
                default=[], key="sea_yr_excl",
                help="Select years to hide from the chart and tables"
            )
            _selected_yrs = [y for y in _all_yrs_in_range if y not in _yr_excl]

            _sea_filt = _sea_data[
                (_sea_data.index.year.isin(_selected_yrs))
            ]

            # Build per-year indexed series (Jan 1 = 100)
            _yearly = {}
            _monthly_rets = {}  # year -> {month -> pct}
            for _yr in _selected_yrs:
                _yd = _sea_filt[_sea_filt.index.year == _yr]
                if len(_yd) < 20: continue
                _base = float(_yd.iloc[0])
                if _base == 0: continue
                _indexed = (_yd / _base - 1) * 100
                # Reindex to day-of-year for alignment
                _doy = [d.timetuple().tm_yday for d in _indexed.index]
                _yearly[_yr] = (_doy, _indexed.values.tolist())
                # Monthly returns
                _mrets = {}
                for _mo in range(1, 13):
                    _md = _yd[_yd.index.month == _mo]
                    if len(_md) >= 2:
                        _mrets[_mo] = round((_md.iloc[-1] / _md.iloc[0] - 1) * 100, 2)
                    elif len(_md) == 1 and _mo > 1:
                        _prev = _yd[_yd.index.month == _mo - 1]
                        if len(_prev) > 0:
                            _mrets[_mo] = round((_md.iloc[-1] / _prev.iloc[-1] - 1) * 100, 2)
                _annual = round((_yd.iloc[-1] / _yd.iloc[0] - 1) * 100, 2)
                _monthly_rets[_yr] = {**_mrets, 0: _annual}  # 0 = annual
                
            if not _yearly:
                st.warning("No data in selected range.")
            else:
                # ── Spaghetti Chart ───────────────────────────────────────────
                _theme  = get_chart_theme()
                _avg_doy, _avg_vals = [], []
                _all_doys = sorted(set(d for doys, _ in _yearly.values() for d in doys))
                for _d in _all_doys:
                    _pts = []
                    for _yr, (_doys, _vals) in _yearly.items():
                        if _d in _doys:
                            _i = _doys.index(_d)
                            _pts.append(_vals[_i])
                    if _pts:
                        _avg_doy.append(_d)
                        _avg_vals.append(sum(_pts) / len(_pts))

                _fig_sea = go.Figure()
                _palette = px.colors.qualitative.Light24 + px.colors.qualitative.Pastel
                for _i, (_yr, (_doys, _vals)) in enumerate(_yearly.items()):
                    _fig_sea.add_trace(go.Scatter(
                        x=_doys, y=_vals,
                        mode='lines', name=str(_yr),
                        line=dict(width=1, color=_palette[_i % len(_palette)]),
                        opacity=0.45,
                        hovertemplate=f"<b>{_yr}</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                    ))
                # Average line — dotted, theme-aware
                if _show_sea_avg:
                    _avg_col = '#111111' if _get_theme_mode() == 'light' else '#ffffff'
                    _fig_sea.add_trace(go.Scatter(
                        x=_avg_doy, y=_avg_vals,
                        mode='lines', name='Average',
                        line=dict(width=2.5, color=_avg_col, dash='dot'),
                        hovertemplate="<b>Average</b><br>Day %{x}: %{y:.2f}%<extra></extra>"
                    ))
                _fig_sea.add_hline(y=0, line_dash="dash", line_color="rgba(128,128,128,0.4)", line_width=1)

                # X-axis ticks at month starts (approx day of year)
                _mo_days = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
                _mo_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                # Legend: sort by final value descending, cap at 40 entries
                _legend_order = []
                for _yr, (_doys, _vals) in _yearly.items():
                    _legend_order.append((_yr, _vals[-1]))
                _legend_order.sort(key=lambda x: x[1], reverse=True)
                _top40 = {y for y, _ in _legend_order[:40]}

                # Re-add traces with legend visibility controlled
                _fig_sea2 = go.Figure()
                for _tr in _fig_sea.data:
                    try:
                        _yr_int = int(_tr.name)
                        _show = _yr_int in _top40
                    except:
                        _show = True  # Average line always shown
                    _fig_sea2.add_trace(go.Scatter(
                        x=list(_tr.x), y=list(_tr.y),
                        mode=_tr.mode, name=_tr.name,
                        line=dict(width=_tr.line.width, color=_tr.line.color,
                                  dash=_tr.line.dash if _tr.line.dash else 'solid'),
                        opacity=_tr.opacity if _tr.opacity is not None else 1.0,
                        showlegend=_show,
                        hovertemplate=_tr.hovertemplate,
                    ))
                _fig_sea2.update_layout(
                    plot_bgcolor =_theme['plot_bgcolor'],
                    paper_bgcolor=_theme['paper_bgcolor'],
                    font=dict(color=_theme['font_color'], size=10),
                    xaxis=dict(
                        tickmode='array',
                        tickvals=[16,46,75,106,136,167,197,228,259,289,320,350],
                        ticktext=_mo_names,
                        gridcolor=_theme['gridcolor'],
                        zeroline=False,
                        range=[0, 366],
                        domain=[0, 0.99],
                        showline=False,
                        ticklabelposition='outside',
                    ),
                    yaxis=dict(
                        title="Return from Jan 1 (%)",
                        gridcolor=_theme['gridcolor'],
                        zeroline=False,
                        domain=[0, 1],
                    ),
                    title=dict(text=f"{_inst_sel} — Seasonal Returns ({_yr_range[0]}–{_yr_range[1]})",
                               font=dict(size=14)),
                    showlegend=True,
                    legend=dict(
                        orientation='v',
                        yanchor='top', y=1,
                        xanchor='left', x=1.03,
                        font=dict(size=9),
                        bgcolor='rgba(0,0,0,0)',
                        tracegroupgap=0,
                        itemwidth=30,
                        borderwidth=0,
                    ),
                    height=900,
                    margin=dict(l=10, r=120, t=60, b=40),
                )
                # Use columns to offset chart right — aligns Jan with Jan column in table below
                # Year col in table is ~8% width; spacer nudges chart to match
                _ch_spacer, _ch_plot = st.columns([0.03, 0.97])
                with _ch_plot:
                    st.plotly_chart(_fig_sea2, use_container_width=True)

                # ── Monthly Returns Heatmap ────────────────────────────────────
                st.markdown("#### Monthly Returns (%)")
                _MO_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
                             "Jul","Aug","Sep","Oct","Nov","Dec","Yearly"]
                _rows = []
                for _yr in sorted(_monthly_rets.keys(), reverse=True):
                    _row = {"Year": _yr}
                    for _mi, _mn in enumerate(_MO_NAMES[:12], 1):
                        _row[_mn] = _monthly_rets[_yr].get(_mi, None)
                    _row["Yearly"] = _monthly_rets[_yr].get(0, None)
                    _rows.append(_row)

                _df_heat = pd.DataFrame(_rows)

                # Summary rows
                _num_cols = _MO_NAMES
                _summ_rows = []
                def _best_fmt(c, df):
                    if c.empty: return None
                    idx = c.idxmax()
                    yr  = df.loc[idx, 'Year'] if idx in df.index else ''
                    return f"{round(c.max(),2)}% ({yr})"
                def _worst_fmt(c, df):
                    if c.empty: return None
                    idx = c.idxmin()
                    yr  = df.loc[idx, 'Year'] if idx in df.index else ''
                    return f"{round(c.min(),2)}% ({yr})"

                for _lbl, _fn in [
                    ("Average",   lambda c: round(c.mean(), 2)),
                    ("% Positive",lambda c: round((c > 0).sum() / c.count() * 100, 2)),
                    ("% Negative",lambda c: -round((c < 0).sum() / c.count() * 100, 2)),
                    ("Median",    lambda c: round(c.median(), 2)),
                    ("Best",      lambda c: _best_fmt(c, _df_heat)),
                    ("Worst",     lambda c: _worst_fmt(c, _df_heat)),
                ]:
                    _sr = {"Year": _lbl}
                    for _cn in _num_cols:
                        if _cn in _df_heat.columns:
                            _col = pd.to_numeric(_df_heat[_cn], errors='coerce').dropna()
                            _sr[_cn] = _fn(_col) if len(_col) > 0 else None
                        else:
                            _sr[_cn] = None
                    _summ_rows.append(_sr)

                # Style heatmap
                def _heat_style(val, col):
                    if col == "Year" or val is None: return ""
                    try:
                        v = float(val)
                        if v > 0:
                            intensity = min(int(abs(v) / 9 * 180), 200)
                            return f"background-color: rgba(45,198,83,{intensity/255:.2f}); color: #0a3d1a"
                        elif v < 0:
                            intensity = min(int(abs(v) / 9 * 180), 200)
                            return f"background-color: rgba(230,57,70,{intensity/255:.2f}); color: #3d0a0a"
                    except: pass
                    return ""

                def _apply_heat(df):
                    styles = df.copy().astype(str)
                    for col in styles.columns:
                        if col == "Year": continue
                        styles[col] = [_heat_style(v, col) for v in df[col]]
                    return styles

                # Format display
                _df_disp = _df_heat.copy()
                for _cn in _num_cols:
                    if _cn in _df_disp.columns:
                        _df_disp[_cn] = _df_disp[_cn].apply(
                            lambda x: f"{x:.2f}%" if pd.notna(x) else "")

                _styled = _df_disp.style.apply(
                    lambda col: [_heat_style(v, col.name) for v in _df_heat[col.name]
                                 if col.name in _df_heat.columns] if col.name != "Year"
                    else [""] * len(col), axis=0
                )
                st.dataframe(_df_disp.style.apply(
                    lambda col: [_heat_style(v, col.name)
                                 for v in (pd.to_numeric(_df_heat[col.name], errors="coerce")
                                           if col.name != "Year" else _df_heat[col.name])]
                    if col.name in _df_heat.columns else [""] * len(col), axis=0
                ), use_container_width=True, hide_index=True)

                # Summary table
                st.markdown("#### Summary")
                _df_summ = pd.DataFrame(_summ_rows)
                for _cn in _num_cols:
                    if _cn in _df_summ.columns:
                        _df_summ[_cn] = _df_summ[_cn].apply(
                            lambda x: x if isinstance(x, str) else
                            f"{x:.2f}%" if pd.notna(x) and x is not None else "—")
                def _summ_heat(v):
                    try:
                        n = float(str(v).replace("%","").replace("+",""))
                        if n > 0:
                            intensity = min(n / 9, 1.0)
                            return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:#0a3d1a"
                        elif n < 0:
                            intensity = min(abs(n) / 9, 1.0)
                            return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:#3d0a0a"
                    except: pass
                    return ""

                _num_summ_cols = [c for c in _df_summ.columns if c != "Year"]
                st.dataframe(
                    _df_summ.style.applymap(_summ_heat, subset=_num_summ_cols),
                    use_container_width=True, hide_index=True
                )

    # ── Tab 2: Presidential Cycle ───────────────────────────────────────────────

    # ── Sector mappings for stock comparison ──────────────────────────────────
    _SECTOR_MAP_US = {
        "Technology"             : ("Technology (XLK)",        "XLK"),
        "Financials"             : ("Financials (XLF)",        "XLF"),
        "Finance"                : ("Financials (XLF)",        "XLF"),
        "Health Care"            : ("Healthcare (XLV)",        "XLV"),
        "Healthcare"             : ("Healthcare (XLV)",        "XLV"),
        "Energy"                 : ("Energy (XLE)",            "XLE"),
        "Industrials"            : ("Industrials (XLI)",       "XLI"),
        "Consumer Discretionary" : ("Consumer Disc (XLY)",     "XLY"),
        "Consumer Cyclical"      : ("Consumer Disc (XLY)",     "XLY"),
        "Consumer Staples"       : ("Consumer Staples (XLP)",  "XLP"),
        "Consumer Defensive"     : ("Consumer Staples (XLP)",  "XLP"),
        "Materials"              : ("Materials (XLB)",         "XLB"),
        "Basic Materials"        : ("Materials (XLB)",         "XLB"),
        "Utilities"              : ("Utilities (XLU)",         "XLU"),
        "Real Estate"            : ("Real Estate (XLRE)",      "XLRE"),
        "Communication Services" : ("Communication (XLC)",     "XLC"),
        "Communication"          : ("Communication (XLC)",     "XLC"),
        "Information Technology" : ("Technology (XLK)",        "XLK"),
    }
    # AU sector map — covers both GICS parent sectors and common sub-sector labels
    _SECTOR_MAP_AU = {
        # Parent sectors
        "Materials"              : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Energy"                 : ("AU Energy (^AXEJ)",       "^AXEJ"),
        "Financials"             : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Finance"                : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Health Care"            : ("AU Health (^AXHJ)",       "^AXHJ"),
        "Healthcare"             : ("AU Health (^AXHJ)",       "^AXHJ"),
        "Industrials"            : ("AU Industrials (^AXIJ)",  "^AXIJ"),
        "Consumer Discretionary" : ("AU Cons Disc (^AXDJ)",    "^AXDJ"),
        "Consumer Cyclical"      : ("AU Cons Disc (^AXDJ)",    "^AXDJ"),
        "Consumer Staples"       : ("AU Cons Staples (^AXSJ)", "^AXSJ"),
        "Consumer Defensive"     : ("AU Cons Staples (^AXSJ)", "^AXSJ"),
        "Information Technology" : ("AU Technology (^AXTJ)",   "^AXTJ"),
        "Technology"             : ("AU Technology (^AXTJ)",   "^AXTJ"),
        "Technology services"    : ("AU Technology (^AXTJ)",   "^AXTJ"),
        "Utilities"              : ("AU Utilities (^AXUJ)",    "^AXUJ"),
        "Real Estate"            : ("AU Real Estate (^AXPJ)",  "^AXPJ"),
        "Communication Services" : ("AU Telecom (^AXNJ)",      "^AXNJ"),
        "Communication"          : ("AU Telecom (^AXNJ)",      "^AXNJ"),
        # Common AU sub-sector / industry labels from watchlist CSVs
        "Finance"                : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Banks"                  : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Insurance"              : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Diversified financials" : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Commercial banks"       : ("AU Financials (^AXFJ)",   "^AXFJ"),
        "Non-energy minerals"    : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Industrial minerals"    : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Precious metals"        : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Base metals"            : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Steel"                  : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Mining"                 : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Gold mining"            : ("AU Materials (^AXMJ)",    "^AXMJ"),
        "Energy minerals"        : ("AU Energy (^AXEJ)",       "^AXEJ"),
        "Oil & gas"              : ("AU Energy (^AXEJ)",       "^AXEJ"),
        "Coal"                   : ("AU Energy (^AXEJ)",       "^AXEJ"),
        "Electronic technology"  : ("AU Technology (^AXTJ)",   "^AXTJ"),
        "Packaged software"      : ("AU Technology (^AXTJ)",   "^AXTJ"),
        "Semiconductors"         : ("AU Technology (^AXTJ)",   "^AXTJ"),
        "Health technology"      : ("AU Health (^AXHJ)",       "^AXHJ"),
        "Health services"        : ("AU Health (^AXHJ)",       "^AXHJ"),
        "Pharmaceuticals"        : ("AU Health (^AXHJ)",       "^AXHJ"),
        "Biotechnology"          : ("AU Health (^AXHJ)",       "^AXHJ"),
        "Transportation"         : ("AU Industrials (^AXIJ)",  "^AXIJ"),
        "Producer manufacturing" : ("AU Industrials (^AXIJ)",  "^AXIJ"),
        "Retail trade"           : ("AU Cons Disc (^AXDJ)",    "^AXDJ"),
        "Restaurants"            : ("AU Cons Disc (^AXDJ)",    "^AXDJ"),
        "Hotels & entertainment" : ("AU Cons Disc (^AXDJ)",    "^AXDJ"),
        "Food & beverage"        : ("AU Cons Staples (^AXSJ)", "^AXSJ"),
        "Beverages"              : ("AU Cons Staples (^AXSJ)", "^AXSJ"),
        "Telecommunications"     : ("AU Telecom (^AXNJ)",      "^AXNJ"),
        "Real estate investment" : ("AU Real Estate (^AXPJ)",  "^AXPJ"),
        "Property trusts"        : ("AU Real Estate (^AXPJ)",  "^AXPJ"),
        "Electric utilities"     : ("AU Utilities (^AXUJ)",    "^AXUJ"),
        "Gas utilities"          : ("AU Utilities (^AXUJ)",    "^AXUJ"),
    }
    # Normalise: lowercase lookup for fuzzy matching
    def _resolve_sector(sector_val, industry_val, sector_map):
        """Try sector first, then industry, then case-insensitive partial match."""
        for val in [sector_val, industry_val]:
            if not val: continue
            if val in sector_map: return sector_map[val]
            # Case-insensitive exact
            _low = {k.lower(): v for k, v in sector_map.items()}
            if str(val).lower() in _low: return _low[str(val).lower()]
            # Partial match
            for k, v in sector_map.items():
                if k.lower() in str(val).lower() or str(val).lower() in k.lower():
                    return v
        return None

    # Friendly watchlist names — maps filename stem to display name
    _WL_FRIENDLY = {
        'au_total_market'           : 'ASX Stocks',
        'au_gold_miners'            : 'AU Gold Miners',
        'us_total_market'           : 'US Stocks',
        'all_major_commodities'     : 'Commodities',
        'uranium'                   : 'Uranium',
        'au_large_cap'              : 'ASX Large Cap',
        'us_large_cap'              : 'US Large Cap',
        'au_etfs'                   : 'AU ETFs',
        'us_etfs'                   : 'US ETFs',
    }
    def _wl_display(fname):
        stem = fname.replace('.csv','').lower()
        for k, v in _WL_FRIENDLY.items():
            if k in stem: return v
        return fname.replace('.csv','').replace('_',' ').title()

    with _sea_tab2:
        import plotly.graph_objects as go
        import plotly.express as px

        # ── Watchlist + ticker picker ─────────────────────────────────────────
        _st_c1, _st_c2, _st_c3 = st.columns([3, 3, 3])

        _wl_files       = sorted(glob.glob(os.path.join(STOCKS, 'watchlist', '*.csv')))
        _wl_basenames   = [os.path.basename(w) for w in _wl_files]
        _wl_display_names = [_wl_display(b) for b in _wl_basenames]
        _wl_disp_sel    = _st_c1.selectbox("Watchlist", _wl_display_names, key="stk_wl")
        _wl_idx         = _wl_display_names.index(_wl_disp_sel) if _wl_disp_sel in _wl_display_names else 0
        _wl_sel         = _wl_basenames[_wl_idx] if _wl_basenames else None
        _wl_path        = os.path.join(STOCKS, 'watchlist', _wl_sel) if _wl_sel else None

        _wl_tickers = []
        if _wl_path and os.path.exists(_wl_path):
            try:
                _wl_df = pd.read_csv(_wl_path)
                # Build display: "TICKER — Name" if name column exists
                if 'name' in _wl_df.columns and 'ticker' in _wl_df.columns:
                    _wl_tickers = [f"{r['ticker']} — {r['name']}" for _, r in _wl_df.iterrows()
                                   if r.get('benchmark') != 'benchmark']
                elif 'ticker' in _wl_df.columns:
                    _wl_tickers = _wl_df['ticker'].tolist()
            except: pass

        _stk_sel  = _st_c2.selectbox("Stock", _wl_tickers, key="stk_pick") if _wl_tickers else None
        _stk_ticker = _stk_sel.split(' — ')[0].strip() if _stk_sel else None

        # Detect AU vs US
        _is_au = _stk_ticker and _stk_ticker.endswith('.AX')

        # ── Sector comparison ─────────────────────────────────────────────────
        _cmp_mode = _st_c3.radio("Compare to", ["Auto sector", "Manual ticker", "None"],
                                  horizontal=True, key="stk_cmp_mode")
        _cmp_ticker = None
        _cmp_label  = None

        if _cmp_mode == "Manual ticker":
            _mc1, _mc2 = st.columns([2, 4])
            _cmp_manual = _mc1.text_input("Comparison ticker", placeholder="e.g. XLK or ^AXMJ",
                                           key="stk_cmp_manual")
            if _cmp_manual.strip():
                _cmp_ticker = _cmp_manual.strip().upper()
                _cmp_label  = _cmp_ticker

        elif _cmp_mode == "Auto sector" and _stk_ticker:
            # Try to get sector from watchlist
            _stk_sector = None
            if _wl_path and os.path.exists(_wl_path):
                try:
                    _wl_df2 = pd.read_csv(_wl_path)
                    _t_clean = _stk_ticker
                    _match = _wl_df2[_wl_df2['ticker'] == _t_clean]
                    if not _match.empty and 'sector' in _wl_df2.columns:
                        _stk_sector = _match.iloc[0]['sector']
                except: pass

            _sec_map = _SECTOR_MAP_AU if _is_au else _SECTOR_MAP_US
            # Get industry too for fuzzy matching
            _stk_industry = None
            if _wl_path and os.path.exists(_wl_path):
                try:
                    _wl_df3 = pd.read_csv(_wl_path)
                    _match3 = _wl_df3[_wl_df3['ticker'] == _stk_ticker]
                    if not _match3.empty and 'industry' in _wl_df3.columns:
                        _stk_industry = _match3.iloc[0]['industry']
                except: pass
            _resolved = _resolve_sector(_stk_sector, _stk_industry, _sec_map)
            if _resolved:
                _cmp_label, _cmp_ticker = _resolved
                st.caption(f"Auto-matched: **{_stk_sector}** / {_stk_industry or '—'} → {_cmp_label}")
            else:
                # Manual fallback picker
                _all_sec_labels = list(dict.fromkeys(_sec_map.values()))  # deduplicated
                _sec_pick = st.selectbox("Sector (auto-detect failed — pick manually)",
                                          [v[0] for v in _all_sec_labels], key="stk_sec_pick")
                _cmp_ticker = next((v[1] for v in _all_sec_labels if v[0] == _sec_pick), None)
                _cmp_label  = _sec_pick

        if not _stk_ticker:
            st.info("Select a watchlist and stock to view seasonality.")
        else:
            @st.cache_data(ttl=3600)
            def _fetch_stk(ticker):
                import yfinance as _yf
                df = _yf.download(ticker, start="1990-01-01", auto_adjust=True, progress=False)
                if df.empty: return None
                c = df["Close"].squeeze().dropna()
                c.index = pd.to_datetime(c.index).tz_localize(None)
                return c

            _stk_data = _fetch_stk(_stk_ticker)
            _cmp_data = _fetch_stk(_cmp_ticker) if _cmp_ticker else None

            if _stk_data is None or len(_stk_data) < 50:
                st.warning(f"No data found for {_stk_ticker}")
            else:
                _s_min = int(_stk_data.index.year.min())
                _s_max = int(_stk_data.index.year.max())

                _ss1, _ss2, _ss3 = st.columns([3, 3, 2])
                _s_range = _ss1.slider("Year range", _s_min, _s_max,
                                        (_s_max - min(15, _s_max - _s_min), _s_max),
                                        key="stk_yr")
                _s_excl  = _ss2.multiselect("Exclude years",
                                             list(range(_s_range[0], _s_range[1]+1)),
                                             default=[], key="stk_excl")
                _show_stk_avg = _ss3.toggle("Show average", value=True, key="stk_avg")

                _s_yrs = [y for y in range(_s_range[0], _s_range[1]+1) if y not in _s_excl]

                # ── Build per-year indexed series ─────────────────────────────
                _stk_yearly = {}
                _cmp_yearly = {}
                _ann_rets_stk = {}
                _ann_rets_cmp = {}

                for _yr in _s_yrs:
                    _yd = _stk_data[_stk_data.index.year == _yr]
                    if len(_yd) < 20: continue
                    _base = float(_yd.iloc[0])
                    if _base == 0: continue
                    _idx = (_yd / _base - 1) * 100
                    _doys = [d.timetuple().tm_yday for d in _idx.index]
                    _stk_yearly[_yr] = (_doys, _idx.values.tolist())
                    _ann_rets_stk[_yr] = round(float(_idx.iloc[-1]), 2)

                    if _cmp_data is not None:
                        _cd = _cmp_data[_cmp_data.index.year == _yr]
                        if len(_cd) >= 20:
                            _cb = float(_cd.iloc[0])
                            if _cb != 0:
                                _ci = (_cd / _cb - 1) * 100
                                _cdoys = [d.timetuple().tm_yday for d in _ci.index]
                                _cmp_yearly[_yr] = (_cdoys, _ci.values.tolist())
                                _ann_rets_cmp[_yr] = round(float(_ci.iloc[-1]), 2)

                # ── Average series ────────────────────────────────────────────
                def _build_avg(yearly):
                    _all_d = sorted(set(d for doys,_ in yearly.values() for d in doys))
                    _xs, _ys = [], []
                    for _d in _all_d:
                        _pts = [v for doys,vals in yearly.values()
                                for di,d in enumerate(doys) if d == _d
                                for v in [vals[di]]]
                        if _pts: _xs.append(_d); _ys.append(sum(_pts)/len(_pts))
                    return _xs, _ys

                _stk_avg_x, _stk_avg_y = _build_avg(_stk_yearly) if _stk_yearly else ([], [])
                _cmp_avg_x, _cmp_avg_y = _build_avg(_cmp_yearly) if _cmp_yearly else ([], [])

                # ── Spaghetti chart ───────────────────────────────────────────
                _theme   = get_chart_theme()
                _fig_stk = go.Figure()
                _palette = px.colors.qualitative.Light24

                for _i, (_yr, (_doys, _vals)) in enumerate(_stk_yearly.items()):
                    _fig_stk.add_trace(go.Scatter(
                        x=_doys, y=_vals, mode='lines',
                        name=str(_yr),
                        line=dict(width=1, color=_palette[_i % len(_palette)]),
                        opacity=0.4,
                        hovertemplate=f"<b>{_stk_ticker} {_yr}</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                    ))

                if _cmp_yearly:
                    for _yr, (_doys, _vals) in _cmp_yearly.items():
                        _fig_stk.add_trace(go.Scatter(
                            x=_doys, y=_vals, mode='lines',
                            name=f"{_cmp_label} {_yr}",
                            line=dict(width=1, color='rgba(255,180,0,0.3)'),
                            opacity=0.25, showlegend=False,
                            hovertemplate=f"<b>{_cmp_label} {_yr}</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                        ))
                    if _show_stk_avg and _cmp_avg_x:
                        _fig_stk.add_trace(go.Scatter(
                            x=_cmp_avg_x, y=_cmp_avg_y, mode='lines',
                            name=f"{_cmp_label} Avg",
                            line=dict(width=2.5, color='#f77f00', dash='dot'),
                            hovertemplate=f"<b>{_cmp_label} Avg</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                        ))

                if _show_stk_avg and _stk_avg_x:
                    _avg_col = '#111111' if _get_theme_mode() == 'light' else '#ffffff'
                    _fig_stk.add_trace(go.Scatter(
                        x=_stk_avg_x, y=_stk_avg_y, mode='lines',
                        name=f"{_stk_ticker} Avg",
                        line=dict(width=3, color=_avg_col, dash='dot'),
                        hovertemplate=f"<b>{_stk_ticker} Avg</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                    ))

                _fig_stk.add_hline(y=0, line_dash="dash",
                                    line_color="rgba(128,128,128,0.4)", line_width=1)
                _mo_mids  = [16,46,75,106,136,167,197,228,259,289,320,350]
                _mo_names = ["Jan","Feb","Mar","Apr","May","Jun",
                             "Jul","Aug","Sep","Oct","Nov","Dec"]
                _fig_stk.update_layout(
                    plot_bgcolor=_theme['plot_bgcolor'],
                    paper_bgcolor=_theme['paper_bgcolor'],
                    font=dict(color=_theme['font_color'], size=10),
                    xaxis=dict(tickmode='array', tickvals=_mo_mids, ticktext=_mo_names,
                               gridcolor=_theme['gridcolor'], zeroline=False,
                               range=[0,366], domain=[0, 0.99],
                               showline=False, ticklabelposition='outside'),
                    yaxis=dict(title="Return from Jan 1 (%)",
                               gridcolor=_theme['gridcolor'], zeroline=False),
                    title=dict(text=f"{_stk_ticker} Seasonal Returns ({_s_range[0]}–{_s_range[1]})"
                               + (f" vs {_cmp_label}" if _cmp_label else ""),
                               font=dict(size=14)),
                    height=700,
                    margin=dict(l=10, r=120, t=60, b=40),
                    legend=dict(
                        orientation='v',
                        yanchor='top', y=1,
                        xanchor='left', x=1.02,
                        font=dict(size=9),
                        bgcolor='rgba(0,0,0,0)',
                        tracegroupgap=0,
                        itemwidth=30,
                        borderwidth=0,
                    ),
                    showlegend=True,
                )
                _stk_spacer, _stk_plot = st.columns([0.03, 0.97])
                with _stk_plot:
                    st.plotly_chart(_fig_stk, use_container_width=True)

                # ── Correlation stats ─────────────────────────────────────────
                if _cmp_data is not None and _ann_rets_cmp:
                    st.markdown(f"#### {_stk_ticker} vs {_cmp_label} — Annual Return Correlation")

                    _common_yrs = sorted(set(_ann_rets_stk) & set(_ann_rets_cmp))
                    if len(_common_yrs) >= 5:
                        _xs_corr = [_ann_rets_cmp[y] for y in _common_yrs]
                        _ys_corr = [_ann_rets_stk[y] for y in _common_yrs]
                        _yr_labels = [str(y) for y in _common_yrs]

                        # Pearson correlation
                        import numpy as _np_corr
                        _corr = float(_np_corr.corrcoef(_xs_corr, _ys_corr)[0,1])

                        # Year-by-year rolling 3-yr correlation
                        _roll_corr = {}
                        for _i in range(2, len(_common_yrs)):
                            _w = _common_yrs[max(0,_i-2):_i+1]
                            _xw = [_ann_rets_cmp[y] for y in _w]
                            _yw = [_ann_rets_stk[y] for y in _w]
                            if len(_w) >= 3:
                                _rc = float(_np_corr.corrcoef(_xw, _yw)[0,1])
                                _roll_corr[_common_yrs[_i]] = _rc

                        # Correlation quality buckets
                        _strong = sum(1 for v in _roll_corr.values() if v >= 0.7)
                        _mod    = sum(1 for v in _roll_corr.values() if 0.3 <= v < 0.7)
                        _weak   = sum(1 for v in _roll_corr.values() if v < 0.3)
                        _n_roll = len(_roll_corr)

                        # ── Monthly returns heatmap (same as Sectors tab) ────────────
                        st.markdown("#### Monthly Returns (%)")
                        _MO_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
                                     "Jul","Aug","Sep","Oct","Nov","Dec","Yearly"]
                        _stk_mo_rows = []
                        for _yr in sorted(_ann_rets_stk.keys(), reverse=True):
                            _yd2 = _stk_data[_stk_data.index.year == _yr]
                            if len(_yd2) < 20: continue
                            _row = {"Year": _yr}
                            for _mi, _mn in enumerate(_MO_NAMES[:12], 1):
                                _md = _yd2[_yd2.index.month == _mi]
                                if len(_md) >= 2:
                                    _row[_mn] = round((_md.iloc[-1]/_md.iloc[0]-1)*100, 2)
                                else:
                                    _row[_mn] = None
                            _row["Yearly"] = _ann_rets_stk[_yr]
                            _stk_mo_rows.append(_row)

                        if _stk_mo_rows:
                            _df_stk_heat = pd.DataFrame(_stk_mo_rows)
                            def _stk_heat_style(val, col):
                                if col == "Year" or val is None: return ""
                                try:
                                    v = float(val)
                                    if v > 0:
                                        intensity = min(int(abs(v)/9*180), 200)
                                        return f"background-color:rgba(45,198,83,{intensity/255:.2f});color:#0a3d1a"
                                    elif v < 0:
                                        intensity = min(int(abs(v)/9*180), 200)
                                        return f"background-color:rgba(230,57,70,{intensity/255:.2f});color:#3d0a0a"
                                except: pass
                                return ""
                            _df_stk_disp = _df_stk_heat.copy()
                            for _cn in _MO_NAMES:
                                if _cn in _df_stk_disp.columns:
                                    _df_stk_disp[_cn] = _df_stk_disp[_cn].apply(
                                        lambda x: f"{x:.2f}%" if pd.notna(x) and x is not None else "")
                            st.dataframe(
                                _df_stk_disp.style.apply(
                                    lambda col: [_stk_heat_style(v, col.name)
                                                 for v in (pd.to_numeric(_df_stk_heat[col.name], errors="coerce")
                                                           if col.name != "Year" else _df_stk_heat[col.name])]
                                    if col.name in _df_stk_heat.columns else [""]*len(col), axis=0
                                ), use_container_width=True, hide_index=True
                            )

                            # Summary rows
                            _stk_summ = []
                            def _stk_best_fmt(c):
                                if c.empty: return None
                                idx = c.idxmax()
                                yr  = _df_stk_heat.loc[idx, 'Year'] if idx in _df_stk_heat.index else ''
                                return f"{round(c.max(),2)}% ({yr})"
                            def _stk_worst_fmt(c):
                                if c.empty: return None
                                idx = c.idxmin()
                                yr  = _df_stk_heat.loc[idx, 'Year'] if idx in _df_stk_heat.index else ''
                                return f"{round(c.min(),2)}% ({yr})"

                            for _lbl, _fn in [
                                ("Average",    lambda c: round(c.mean(), 2)),
                                ("% Positive", lambda c: round((c>0).sum()/c.count()*100, 2)),
                                ("% Negative", lambda c: -round((c<0).sum()/c.count()*100, 2)),
                                ("Median",     lambda c: round(c.median(), 2)),
                                ("Best",       lambda c: _stk_best_fmt(c)),
                                ("Worst",      lambda c: _stk_worst_fmt(c)),
                            ]:
                                _sr = {"Year": _lbl}
                                for _cn in _MO_NAMES:
                                    if _cn in _df_stk_heat.columns:
                                        _col = pd.to_numeric(_df_stk_heat[_cn], errors='coerce').dropna()
                                        _sr[_cn] = _fn(_col) if len(_col) > 0 else None
                                    else:
                                        _sr[_cn] = None
                                _stk_summ.append(_sr)
                            _df_stk_summ = pd.DataFrame(_stk_summ)
                            def _stk_summ_heat(v):
                                try:
                                    n = float(str(v).replace("%","").replace("+",""))
                                    if n > 0:
                                        intensity = min(n/9, 1.0)
                                        return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:#0a3d1a"
                                    elif n < 0:
                                        intensity = min(abs(n)/9, 1.0)
                                        return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:#3d0a0a"
                                except: pass
                                return ""
                            _stk_num_cols = [c for c in _df_stk_summ.columns if c != "Year"]
                            for _cn in _stk_num_cols:
                                _df_stk_summ[_cn] = _df_stk_summ[_cn].apply(
                                    lambda x: x if isinstance(x, str) else
                                    f"{x:.2f}%" if pd.notna(x) and x is not None else "—")
                            st.markdown("**Summary**")
                            st.dataframe(
                                _df_stk_summ.style.applymap(_stk_summ_heat, subset=_stk_num_cols),
                                use_container_width=True, hide_index=True
                            )

                        # ── Combined annual returns + correlation table ────────────────
                        # Summary metrics
                        _m1, _m2, _m3, _m4 = st.columns(4)
                        _m1.metric("Overall Correlation", f"{_corr:.2f}")
                        _m2.metric("Strong (≥0.7)", f"{_strong}/{_n_roll} yrs" if _n_roll else "—",
                                   f"{_strong/_n_roll*100:.0f}%" if _n_roll else None)
                        _m3.metric("Moderate (0.3–0.7)", f"{_mod}/{_n_roll} yrs" if _n_roll else "—",
                                   f"{_mod/_n_roll*100:.0f}%" if _n_roll else None)
                        _m4.metric("Weak (<0.3)", f"{_weak}/{_n_roll} yrs" if _n_roll else "—",
                                   f"{_weak/_n_roll*100:.0f}%" if _n_roll else None)

                        st.markdown("#### Annual Returns & Rolling Correlation")
                        _tbl_rows = []
                        for _yr in sorted(_common_yrs, reverse=True):
                            _sr = _ann_rets_stk.get(_yr)
                            _cr = _ann_rets_cmp.get(_yr)
                            _rc = _roll_corr.get(_yr)
                            _tbl_rows.append({
                                'Year'              : _yr,
                                f'{_stk_ticker} %'  : f"{'+' if _sr and _sr>=0 else ''}{_sr:.2f}%" if _sr is not None else '—',
                                f'{_cmp_label[:20]} %': f"{'+' if _cr and _cr>=0 else ''}{_cr:.2f}%" if _cr is not None else '—',
                                '3yr Corr'          : f"{_rc:.2f}" if _rc is not None else '—',
                            })
                        _df_tbl = pd.DataFrame(_tbl_rows)

                        def _tbl_heat(val, col):
                            if val == '—': return ''
                            try:
                                n = float(str(val).replace('%','').replace('+',''))
                                if '3yr Corr' in col:
                                    # Correlation: green=strong positive, red=negative
                                    if n >= 0.7:   return 'background-color:rgba(45,198,83,0.6);color:#0a3d1a;font-weight:bold'
                                    elif n >= 0.3:  return 'background-color:rgba(247,127,0,0.5);color:#3d2000;font-weight:bold'
                                    elif n >= 0:    return 'background-color:rgba(247,127,0,0.2);color:#3d2000'
                                    else:           return 'background-color:rgba(230,57,70,0.5);color:#3d0a0a;font-weight:bold'
                                else:
                                    # Return: green/red scaled to 9%
                                    if n > 0:
                                        intensity = min(n / 9, 1.0)
                                        return f'background-color:rgba(45,198,83,{intensity*0.7:.2f});color:#0a3d1a'
                                    elif n < 0:
                                        intensity = min(abs(n) / 9, 1.0)
                                        return f'background-color:rgba(230,57,70,{intensity*0.7:.2f});color:#3d0a0a'
                            except: pass
                            return ''

                        _heat_cols = [c for c in _df_tbl.columns if c != 'Year']
                        st.dataframe(
                            _df_tbl.style.apply(
                                lambda col: [_tbl_heat(v, col.name) for v in col]
                                if col.name in _heat_cols else ['']*len(col), axis=0
                            ),
                            use_container_width=True, hide_index=True
                        )

                        # Scatter plot — annual returns
                        _fig_scatter = go.Figure()
                        _sc_colors = ['#2dc653' if s*c > 0 else '#e63946'
                                      for s,c in zip(_ys_corr, _xs_corr)]
                        _fig_scatter.add_trace(go.Scatter(
                            x=_xs_corr, y=_ys_corr,
                            mode='markers+text',
                            text=_yr_labels,
                            textposition='top center',
                            textfont=dict(size=9),
                            marker=dict(size=10, color=_sc_colors, opacity=0.8,
                                        line=dict(width=1, color='rgba(0,0,0,0.3)')),
                            hovertemplate=(f"<b>%{{text}}</b><br>"
                                           f"{_cmp_label}: %{{x:.1f}}%<br>"
                                           f"{_stk_ticker}: %{{y:.1f}}%<extra></extra>"),
                        ))
                        # Trend line
                        _z = _np_corr.polyfit(_xs_corr, _ys_corr, 1)
                        _xr = [min(_xs_corr), max(_xs_corr)]
                        _yr_fit = [_z[0]*x + _z[1] for x in _xr]
                        _fig_scatter.add_trace(go.Scatter(
                            x=_xr, y=_yr_fit, mode='lines',
                            line=dict(dash='dash', color='rgba(128,128,128,0.6)', width=1.5),
                            showlegend=False,
                        ))
                        _fig_scatter.add_vline(x=0, line_dash="dot",
                                               line_color="rgba(128,128,128,0.4)")
                        _fig_scatter.add_hline(y=0, line_dash="dot",
                                               line_color="rgba(128,128,128,0.4)")
                        _fig_scatter.update_layout(
                            plot_bgcolor=_theme['plot_bgcolor'],
                            paper_bgcolor=_theme['paper_bgcolor'],
                            font=dict(color=_theme['font_color']),
                            xaxis=dict(title=f"{_cmp_label} Annual Return (%)",
                                       gridcolor=_theme['gridcolor'], zeroline=False),
                            yaxis=dict(title=f"{_stk_ticker} Annual Return (%)",
                                       gridcolor=_theme['gridcolor'], zeroline=False),
                            title=dict(text=f"Annual Return Scatter — r={_corr:.2f}",
                                       font=dict(size=13)),
                            height=450,
                            margin=dict(l=60, r=40, t=60, b=60),
                            showlegend=False,
                        )
                        st.plotly_chart(_fig_scatter, use_container_width=True)

                    else:
                        st.info("Need at least 5 years of overlapping data for correlation analysis.")


    with _sea_tab3:
        # Presidents from 1929 onwards (S&P data reliable from ~1928)
        _PRESIDENTS = [
            ("Hoover",     1929, 1933, "Republican"),
            ("Roosevelt",  1933, 1945, "Democrat"),
            ("Truman",     1945, 1953, "Democrat"),
            ("Eisenhower", 1953, 1961, "Republican"),
            ("Kennedy",    1961, 1963, "Democrat"),
            ("Johnson",    1963, 1969, "Democrat"),
            ("Nixon",      1969, 1974, "Republican"),
            ("Ford",       1974, 1977, "Republican"),
            ("Carter",     1977, 1981, "Democrat"),
            ("Reagan",     1981, 1989, "Republican"),
            ("Bush Sr",    1989, 1993, "Republican"),
            ("Clinton",    1993, 2001, "Democrat"),
            ("Bush Jr",    2001, 2009, "Republican"),
            ("Obama",      2009, 2017, "Democrat"),
            ("Trump",      2017, 2021, "Republican"),
            ("Biden",      2021, 2025, "Democrat"),
            ("Trump",      2025, 2029, "Republican"),
        ]

        _pc1, _pc2, _pc3 = st.columns([2, 2, 3])
        _yr_sel   = _pc1.radio("Presidential year", [1, 2, 3, 4, "All"],
                                horizontal=True, key="pres_yr",
                                help="Year 1 = inauguration year, Year 4 = final year of term. All = overlay all 4 years.")
        _party_sel = _pc2.multiselect("Party", ["Democrat", "Republican"],
                                       default=["Democrat", "Republican"], key="pres_party")
        _show_avg  = _pc3.toggle("Show average line", value=True, key="pres_avg")

        @st.cache_data(ttl=3600)
        def _fetch_spx():
            import yfinance as _yf
            df = _yf.download("^GSPC", start="1927-01-01", auto_adjust=True, progress=False)
            if df.empty: return None
            close = df["Close"].squeeze().dropna()
            close.index = pd.to_datetime(close.index).tz_localize(None)
            return close

        _spx = _fetch_spx()

        if _spx is None:
            st.warning("Could not load S&P 500 data.")
        else:
            _D_COL = "#4C8BF5"   # Democrat blue
            _R_COL = "#E8534A"   # Republican red
            _fig_pc = go.Figure()
            _avg_traces = {}  # party -> list of series

            _yr_nums = [1,2,3,4] if _yr_sel == "All" else [_yr_sel]

            for _name, _start, _end, _party in _PRESIDENTS:
                if _party not in _party_sel: continue
                for _yn in _yr_nums:
                    _term_yr = _start + (_yn - 1)
                    if _term_yr >= _end: continue

                    _yr_data = _spx[_spx.index.year == _term_yr]
                    if len(_yr_data) < 20: continue

                    _base = float(_yr_data.iloc[0])
                    if _base == 0: continue
                    _indexed = (_yr_data / _base - 1) * 100

                    _doys = [d.timetuple().tm_yday for d in _indexed.index]
                    _col  = _D_COL if _party == "Democrat" else _R_COL
                    _annual_ret = round(float(_indexed.iloc[-1]), 2)
                    _yr_suffix = f" Yr{_yn}" if _yr_sel == "All" else ""
                    _label = f"{_name}{_yr_suffix} ({_term_yr}) {'+' if _annual_ret >= 0 else ''}{_annual_ret:.1f}%"

                    _fig_pc.add_trace(go.Scatter(
                        x=_doys, y=_indexed.values.tolist(),
                        mode='lines', name=_label,
                        line=dict(width=1.5, color=_col),
                        opacity=0.5,
                        hovertemplate=f"<b>{_label}</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                    ))

                    if _party not in _avg_traces:
                        _avg_traces[_party] = {}
                    for _d, _v in zip(_doys, _indexed.values):
                        _avg_traces[_party].setdefault(_d, []).append(float(_v))

            # Average lines
            if _show_avg:
                for _party, _doy_vals in _avg_traces.items():
                    _col = _D_COL if _party == "Democrat" else _R_COL
                    _xs  = sorted(_doy_vals.keys())
                    _ys  = [sum(_doy_vals[d]) / len(_doy_vals[d]) for d in _xs]
                    _fig_pc.add_trace(go.Scatter(
                        x=_xs, y=_ys,
                        mode='lines',
                        name=f"{_party} Avg",
                        line=dict(width=3, color=_col, dash='dash'),
                        hovertemplate=f"<b>{_party} Average</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                    ))

            _fig_pc.add_hline(y=0, line_dash="dash",
                               line_color="rgba(128,128,128,0.4)", line_width=1)
            _mo_days  = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
            _mo_names = ["Jan","Feb","Mar","Apr","May","Jun",
                         "Jul","Aug","Sep","Oct","Nov","Dec"]
            _yr_label  = {1:"Inauguration Year (Yr 1)", 2:"Year 2",
                          3:"Year 3 (Mid-term)", 4:"Final Year (Yr 4)", "All":"All Years Overlay"}
            _theme = get_chart_theme()
            _fig_pc.update_layout(
                plot_bgcolor =_theme['plot_bgcolor'],
                paper_bgcolor=_theme['paper_bgcolor'],
                font=dict(color=_theme['font_color']),
                xaxis=dict(tickmode='array',
                           tickvals=[16,46,75,106,136,167,197,228,259,289,320,350],
                           ticktext=_mo_names,
                           gridcolor=_theme['gridcolor'], zeroline=False,
                           range=[0, 366], domain=[0, 0.99]),
                yaxis=dict(title="Return from Jan 1 (%)",
                           gridcolor=_theme['gridcolor'], zeroline=False),
                title=dict(text=f"S&P 500 — Presidential {_yr_label[_yr_sel]}",
                           font=dict(size=14)),
                height=500,
                margin=dict(l=10, r=60, t=60, b=40),
                legend=dict(
                    orientation='v',
                    yanchor='top', y=1,
                    xanchor='left', x=1,
                    font=dict(size=9),
                    bgcolor='rgba(0,0,0,0)',
                    tracegroupgap=0,
                    itemwidth=30,
                    borderwidth=0,
                ),
            )
            _pc_spacer, _pc_plot = st.columns([0.08, 0.885])
            with _pc_plot:
                st.plotly_chart(_fig_pc, use_container_width=True)


            # ── Monthly Returns Heatmap ───────────────────────────────────────
            st.markdown("#### Monthly Returns (%)")
            _MO_NAMES_PC = ["Jan","Feb","Mar","Apr","May","Jun",
                            "Jul","Aug","Sep","Oct","Nov","Dec","Yearly"]
            _pc_mo_rows = []
            _pc_yrs_to_show = []
            for _pname, _pstart, _pend, _pparty in _PRESIDENTS:
                if _pparty not in _party_sel: continue
                _ynums = [1,2,3,4] if _yr_sel == "All" else [_yr_sel]
                for _yn in _ynums:
                    _ty = _pstart + (_yn - 1)
                    if _ty >= _pend: continue
                    _yd = _spx[_spx.index.year == _ty]
                    if len(_yd) < 20: continue
                    _pc_yrs_to_show.append((_pname, _pparty, _yn, _ty, _yd))

            for _pname, _pparty, _yn, _ty, _yd in sorted(_pc_yrs_to_show, key=lambda x: x[3], reverse=True):
                _p_badge = '<span style="color:#4C8BF5">D</span>' if _pparty=="Democrat" else '<span style="color:#E8534A">R</span>'
                _row = {"President": f"{_pname} ({_ty}) {'D' if _pparty=='Democrat' else 'R'}"}
                for _mi, _mn in enumerate(_MO_NAMES_PC[:12], 1):
                    _md = _yd[_yd.index.month == _mi]
                    if len(_md) >= 2:
                        _row[_mn] = round((_md.iloc[-1]/_md.iloc[0]-1)*100, 2)
                    else:
                        _row[_mn] = None
                _row["Yearly"] = round((_yd.iloc[-1]/_yd.iloc[0]-1)*100, 2)
                _pc_mo_rows.append(_row)

            if _pc_mo_rows:
                _df_pc_heat = pd.DataFrame(_pc_mo_rows)

                def _pc_heat_style(val, col):
                    if col in ("President","Party") or val is None: return ""
                    try:
                        v = float(val)
                        if v > 0:
                            intensity = min(int(abs(v)/9*180), 200)
                            return f"background-color:rgba(45,198,83,{intensity/255:.2f});color:#0a3d1a"
                        elif v < 0:
                            intensity = min(int(abs(v)/9*180), 200)
                            return f"background-color:rgba(230,57,70,{intensity/255:.2f});color:#3d0a0a"
                    except: pass
                    return ""

                def _party_col(v):
                    if v == "Democrat": return "color:#4C8BF5"
                    if v == "Republican": return "color:#E8534A"
                    return ""

                _df_pc_disp = _df_pc_heat.copy()
                for _cn in _MO_NAMES_PC:
                    if _cn in _df_pc_disp.columns:
                        _df_pc_disp[_cn] = _df_pc_disp[_cn].apply(
                            lambda x: f"{x:.2f}%" if pd.notna(x) and x is not None else "")

                # Apply colour to R/D suffix in President column via styler
                def _pres_col_style(v):
                    if str(v).endswith(' D'): return 'color:#4C8BF5'
                    if str(v).endswith(' R'): return 'color:#E8534A'
                    return ''
                _df_pc_disp2 = _df_pc_disp.drop(columns=['Party'], errors='ignore')
                _df_pc_heat2 = _df_pc_heat.drop(columns=['Party'], errors='ignore')
                _pc_col_cfg = {"President": st.column_config.TextColumn(width="medium")}
                for _mn in _MO_NAMES_PC[:12]:
                    _pc_col_cfg[_mn] = st.column_config.TextColumn(width="small")
                _pc_col_cfg["Yearly"] = st.column_config.TextColumn(width="small")
                st.dataframe(
                    _df_pc_disp2.style
                        .apply(lambda col: [_pc_heat_style(v, col.name) for v in
                                            (pd.to_numeric(_df_pc_heat2[col.name], errors='coerce')
                                             if col.name in _MO_NAMES_PC else _df_pc_heat2[col.name])]
                               if col.name in _df_pc_heat2.columns else [""]*len(col), axis=0)
                        .applymap(_pres_col_style, subset=["President"]),
                    column_config=_pc_col_cfg,
                    use_container_width=True, hide_index=True
                )

                # Summary rows
                st.markdown("**Summary**")
                _pc_summ = []
                for _lbl, _fn in [
                    ("Average",    lambda c: round(c.mean(), 2)),
                    ("% Positive", lambda c: round((c>0).sum()/c.count()*100, 2)),
                    ("% Negative", lambda c: -round((c<0).sum()/c.count()*100, 2)),
                    ("Median",     lambda c: round(c.median(), 2)),
                    ("Best",       lambda c: f"{round(c.max(),2)}% ({_df_pc_heat.loc[c.idxmax(),'President'] if c.idxmax() in _df_pc_heat.index else ''})"),
                    ("Worst",      lambda c: f"{round(c.min(),2)}% ({_df_pc_heat.loc[c.idxmin(),'President'] if c.idxmin() in _df_pc_heat.index else ''})"),
                ]:
                    _sr = {"President": _lbl}
                    for _cn in _MO_NAMES_PC:
                        if _cn in _df_pc_heat.columns:
                            _col = pd.to_numeric(_df_pc_heat[_cn], errors='coerce').dropna()
                            _sr[_cn] = _fn(_col) if len(_col) > 0 else None
                        else:
                            _sr[_cn] = None
                    _pc_summ.append(_sr)
                _df_pc_summ = pd.DataFrame(_pc_summ)
                def _pc_summ_heat(v):
                    try:
                        n = float(str(v).replace("%","").replace("+",""))
                        if n > 0:
                            intensity = min(n/9, 1.0)
                            return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:#0a3d1a"
                        elif n < 0:
                            intensity = min(abs(n)/9, 1.0)
                            return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:#3d0a0a"
                    except: pass
                    return ""
                _pc_num_cols = [c for c in _df_pc_summ.columns if c not in ("President","Party")]
                for _cn in _pc_num_cols:
                    _df_pc_summ[_cn] = _df_pc_summ[_cn].apply(
                        lambda x: x if isinstance(x, str) else
                        f"{x:.2f}%" if pd.notna(x) and x is not None else "—")
                _pc_summ_col_cfg = {"President": st.column_config.TextColumn(width="medium")}
                for _mn in _MO_NAMES_PC[:12]:
                    _pc_summ_col_cfg[_mn] = st.column_config.TextColumn(width="small")
                _pc_summ_col_cfg["Yearly"] = st.column_config.TextColumn(width="small")
                st.dataframe(
                    _df_pc_summ.style
                        .applymap(_pc_summ_heat, subset=_pc_num_cols),
                    column_config=_pc_summ_col_cfg,
                    use_container_width=True, hide_index=True
                )

            # ── Summary table ─────────────────────────────────────────────────
            st.markdown("#### Presidential Year Returns")
            _summ_pc = []
            for _name, _start, _end, _party in _PRESIDENTS:
                _row = {"President": _name, "Party": _party, "Term": f"{_start}–{_end}"}
                for _y in [1, 2, 3, 4]:
                    _ty = _start + (_y - 1)
                    if _ty >= _end:
                        _row[f"Yr {_y}"] = "—"
                        continue
                    _yd = _spx[_spx.index.year == _ty]
                    if len(_yd) < 20:
                        _row[f"Yr {_y}"] = "—"
                        continue
                    _ret = round((_yd.iloc[-1] / _yd.iloc[0] - 1) * 100, 2)
                    _row[f"Yr {_y}"] = f"{'+' if _ret >= 0 else ''}{_ret:.2f}%"
                _summ_pc.append(_row)

            _df_pc = pd.DataFrame(_summ_pc)

            def _pc_style(v):
                if v in ("—", None): return ""
                try:
                    n = float(str(v).replace("%","").replace("+",""))
                    if n > 0: return f"color: #2dc653; font-weight: bold"
                    if n < 0: return f"color: #e63946; font-weight: bold"
                except: pass
                return ""

            def _party_style(v):
                if v == "Democrat":   return "color: #4C8BF5"
                if v == "Republican": return "color: #E8534A"
                return ""

            def _pc_heat(v):
                if v in ("—", None): return ""
                try:
                    n = float(str(v).replace("%","").replace("+",""))
                    if n > 0:
                        intensity = min(n / 9, 1.0)
                        return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:#0a3d1a;font-weight:bold"
                    elif n < 0:
                        intensity = min(abs(n) / 9, 1.0)
                        return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:#3d0a0a;font-weight:bold"
                except: pass
                return ""

            st.dataframe(
                _df_pc.style
                    .applymap(_pc_heat,    subset=["Yr 1","Yr 2","Yr 3","Yr 4"])
                    .applymap(_party_style, subset=["Party"]),
                use_container_width=True, hide_index=True
            )


elif page == "Debt Markets":
    import plotly.graph_objects as go
    import numpy as np
    import json
    import sys
    sys.path.insert(0, MACRO)

    _dh1, _dh2, _dh3, _dh4 = st.columns([900, 5000, 1500, 1500])
    with _dh2:
        st.title("💳 Debt Markets")
    with _dh3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Run Debt Data", key='top_debt_refresh'):
            run_script(os.path.join(MACRO, 'consumer_credit.py'), MACRO)
            st.rerun()
    with _dh4:
        st.markdown("<br>", unsafe_allow_html=True)
        _debt_file = os.path.join(MACRO, 'results', 'consumer_credit_report.txt')
        if os.path.exists(_debt_file):
            with open(_debt_file) as _f: _debt_txt = _f.read()
            st.download_button("⬇ Download Report", _debt_txt,
                               file_name="debt_markets_report.txt", key='top_debt_dl')
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
            _cc_prefix = load_settings().get('ai_prompts', {}).get('consumer_credit',
                DEFAULT_SETTINGS['ai_prompts']['consumer_credit'])
            prompt = f"""{_cc_prefix} 
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
            _corp_prefix = load_settings().get('ai_prompts', {}).get('corporate_credit',
                DEFAULT_SETTINGS['ai_prompts']['corporate_credit'])
            prompt = f"""{_corp_prefix}
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
            _sov_prefix = load_settings().get('ai_prompts', {}).get('sovereign_credit',
                DEFAULT_SETTINGS['ai_prompts']['sovereign_credit'])
            prompt = f"""{_sov_prefix}
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

        # ── Date-specific report download ─────────────────────────────────────
        rpt_file = os.path.join(credit_dir, f"{sel_date}_consumer_credit_report.txt")
        if os.path.exists(rpt_file):
            with open(rpt_file, 'r', encoding='utf-8') as f:
                rpt_txt = f.read()
            st.download_button(
                label     = f"⬇ Download {sel_date} Report",
                data      = rpt_txt,
                file_name = f"{sel_date}_consumer_credit_report.txt",
                mime      = 'text/plain'
            )

# ═══════════════════════════════════════════════════════════════════════════════
# AU MARKET PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "AU Market":
    _ph1, _ph2, _ph3, _ph4, _ph5, _ph6 = st.columns([900, 3500, 1200, 1400, 1400, 900])
    with _ph2:
        st.title("AU Total Market")
    with _ph3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🌐 Run Breadth", key='top_run_br_au'):
            run_script(os.path.join(STOCKS, 'au_total_market_breadth.py'), STOCKS)
            st.rerun()
    with _ph4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Run Benchmark", key='top_run_bm_au'):
            run_script(os.path.join(STOCKS, 'au_total_market_benchmark.py'), STOCKS)
            st.rerun()
    with _ph5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔍 Run Screener", key='top_run_sc_au'):
            run_script(os.path.join(STOCKS, 'au_total_market_screener.py'), STOCKS)
            st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["Breadth", "Zweig Thrust", "Benchmark", "Screener"])

    with tab1:
        st.subheader("AU Market Breadth")
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

            _au_br_prefix = load_settings().get('ai_prompts', {}).get('au_breadth',
                DEFAULT_SETTINGS['ai_prompts']['au_breadth'])
            prompt = f"""{_au_br_prefix}

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
                _au_bm_pfx = load_settings().get('ai_prompts', {}).get('au_benchmark', DEFAULT_SETTINGS['ai_prompts']['au_benchmark'])
                ai_prompt = _au_bm_pfx + '\n\n' + (build_benchmark_ai_prompt(df.reset_index(), 'AU Market', group_col='sector') or '')
                if ai_prompt.strip():
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
    _ph1, _ph2, _ph3, _ph4, _ph5, _ph6 = st.columns([900, 3500, 1200, 1400, 1400, 900])
    with _ph2:
        st.title("US Total Market")
    with _ph3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🌐 Run Breadth", key='top_run_br_us'):
            run_script(os.path.join(STOCKS, 'us_total_market_breadth.py'), STOCKS)
            st.rerun()
    with _ph4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Run Benchmark", key='top_run_bm_us'):
            run_script(os.path.join(STOCKS, 'us_total_market_benchmark.py'), STOCKS)
            st.rerun()
    with _ph5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔍 Run Screener", key='top_run_sc_us'):
            run_script(os.path.join(STOCKS, 'us_total_market_screener.py'), STOCKS)
            st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["Breadth", "Zweig Thrust", "Benchmark", "Screener"])

    with tab1:
        st.subheader("US Market Breadth")
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

            _us_br_prefix = load_settings().get('ai_prompts', {}).get('us_breadth',
                DEFAULT_SETTINGS['ai_prompts']['us_breadth'])
            prompt = f"""{_us_br_prefix}

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
                _us_bm_pfx = load_settings().get('ai_prompts', {}).get('us_benchmark', DEFAULT_SETTINGS['ai_prompts']['us_benchmark'])
                ai_prompt = _us_bm_pfx + '\n\n' + (build_benchmark_ai_prompt(df.reset_index(), 'US Market', group_col='sector') or '')
                if ai_prompt.strip():
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
    _ph1, _ph2, _ph3, _ph4, _ph5, _ph6 = st.columns([900, 3500, 1200, 1400, 1400, 900])
    with _ph2:
        st.title("⛏ All Major Commodities")
    with _ph3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🌐 Run Breadth", key='top_run_br_comm'):
            run_script(os.path.join(STOCKS, 'all_major_commodities_breadth.py'), STOCKS)
            st.rerun()
    with _ph4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Run Benchmark", key='top_run_bm_comm'):
            run_script(os.path.join(STOCKS, 'all_major_commodities_benchmark.py'), STOCKS)
            st.rerun()
    with _ph5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔍 Run Screener", key='top_run_sc_comm'):
            run_script(os.path.join(STOCKS, 'all_major_commodities_screener.py'), STOCKS)
            st.rerun()

    _main_tabs = st.tabs(["⛏ Commodities", "☢ Uranium", "🥇 AU Gold Miners"])

    with _main_tabs[0]:
        tab1, tab2, tab3 = st.tabs(["Breadth", "Benchmark", "Screener"])

    with tab1:
        st.subheader("Commodities Breadth")
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
                _cm_bm_pfx = load_settings().get('ai_prompts', {}).get('comm_benchmark', DEFAULT_SETTINGS['ai_prompts']['comm_benchmark'])
                ai_prompt = _cm_bm_pfx + '\n\n' + (build_benchmark_ai_prompt(df.reset_index(), 'Commodities', group_col='commodity') or '')
                if ai_prompt.strip():
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
    with _main_tabs[1]:
        _ph1, _ph2, _ph3, _ph4, _ph5 = st.columns([900, 4000, 1000, 2000, 900])
        with _ph2:
            st.title("☢ Uranium")
        with _ph4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Run Benchmark", key='top_run_bm_ura'):
                run_script(os.path.join(STOCKS, 'uranium_benchmark.py'), STOCKS)
                st.rerun()
        with _ph5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍 Run Screener", key='top_run_sc_ura'):
                run_script(os.path.join(STOCKS, 'uranium_screener.py'), STOCKS)
                st.rerun()

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

    with _main_tabs[2]:
        _ph1, _ph2, _ph3, _ph4, _ph5 = st.columns([900, 4000, 1000, 2000, 900])
        with _ph2:
            st.title("🥇 AU Gold Miners")
        with _ph4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Run Benchmark", key='top_run_bm_augm'):
                run_script(os.path.join(STOCKS, 'au_gold_miners_benchmark.py'), STOCKS)
                st.rerun()
        with _ph5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔍 Run Screener", key='top_run_sc_augm'):
                run_script(os.path.join(STOCKS, 'au_gold_miners_screener.py'), STOCKS)
                st.rerun()

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

elif page == "Relative Strength Charts":
    import plotly.graph_objects as go

    st.title("📡 Relative Rotation Graph")
    st.caption("RS-Ratio vs RS-Momentum — tails show last 63 trading days")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🇦🇺 AU vs XJO", "🇺🇸 US vs SPY/RSP", "📈 Dow 30 vs DJI",
        "🇦🇺 AU Breadth RRG", "🇺🇸 US Breadth RRG", "⛏ Comm Breadth RRG"
    ])

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
            # Dow 30
            'AAPL' : 'AAPL - Apple',
            'MSFT' : 'MSFT - Microsoft',
            'AMZN' : 'AMZN - Amazon',
            'NVDA' : 'NVDA - Nvidia',
            'HD'   : 'HD - Home Depot',
            'MCD'  : 'MCD - McDonald\'s',
            'NKE'  : 'NKE - Nike',
            'WMT'  : 'WMT - Walmart',
            'V'    : 'V - Visa',
            'GS'   : 'GS - Goldman Sachs',
            'JPM'  : 'JPM - JPMorgan',
            'AXP'  : 'AXP - Amex',
            'TRV'  : 'TRV - Travelers',
            'JNJ'  : 'JNJ - J&J',
            'UNH'  : 'UNH - UnitedHealth',
            'MRK'  : 'MRK - Merck',
            'AMGN' : 'AMGN - Amgen',
            'MMM'  : 'MMM - 3M',
            'HON'  : 'HON - Honeywell',
            'CAT'  : 'CAT - Caterpillar',
            'BA'   : 'BA - Boeing',
            'RTX'  : 'RTX - Raytheon',
            'IBM'  : 'IBM - IBM',
            'CRM'  : 'CRM - Salesforce',
            'INTC' : 'INTC - Intel',
            'CVX'  : 'CVX - Chevron',
            'KO'   : 'KO - Coca-Cola',
            'PG'   : 'PG - P&G',
            'DIS'  : 'DIS - Disney',
            'VZ'   : 'VZ - Verizon',
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
        _spy_rsp = st.toggle("Use RSP (equal-weight) benchmark", value=False, key='rrg_us_rsp',
                             help="SPY = cap-weighted S&P 500 | RSP = equal-weight S&P 500")
        if _spy_rsp:
            _us_hist_file = os.path.join(STOCKS, 'results', 'rrg', 'us_rrg_rsp_history.csv')
            _us_title     = 'US Sectors & ETFs vs RSP (Equal Weight)'
            _us_script    = 'rrg_us_rsp_data.py'
        else:
            _us_hist_file = os.path.join(STOCKS, 'results', 'rrg', 'us_rrg_history.csv')
            _us_title     = 'US Sectors & ETFs vs SPY'
            _us_script    = 'rrg_us_data.py'
        build_rrg(_us_hist_file, _us_title)
        if st.button("🔄 Update US RRG Data", key='rrg_us'):
            run_script(os.path.join(STOCKS, _us_script), STOCKS)
            st.rerun()

    with tab3:
        build_rrg(
            os.path.join(STOCKS, 'results', 'rrg', 'dow_rrg_history.csv'),
            'Dow 30 vs DJI'
        )
        if st.button("🔄 Update Dow RRG Data", key='rrg_dow'):
            run_script(os.path.join(STOCKS, 'rrg_dow_data.py'), STOCKS)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# BREADTH RRG PAGE
# ═══════════════════════════════════════════════════════════════════════════════
    with tab4:
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

    with tab5:
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

    with tab6:
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

    # ── Score weight settings ────────────────────────────────────────────────
    _dd_settings_file = os.path.join(BASE, 'drawdown_settings.json')

    def _load_dd_settings():
        if os.path.exists(_dd_settings_file):
            try:
                return json.load(open(_dd_settings_file))
            except: pass
        return {'rs_vs_bench': 0.4, 'peer_rs_score': 0.3, 'dd_vs_bench': 0.3}

    def _save_dd_settings(s):
        with open(_dd_settings_file, 'w') as f:
            json.dump(s, f, indent=2)

    _dd_s = _load_dd_settings()

    with st.expander("⚙️ Score Weights", expanded=False):
        st.caption("Weights are applied as-is — ensure they sum to a meaningful total. "
                   "DD vs Benchmark weight is applied as negative (penalises higher drawdown).")
        _wc1, _wc2, _wc3, _wc4 = st.columns([3, 3, 3, 2])
        _w_rs   = _wc1.number_input("RS vs Benchmark", min_value=0.0, max_value=2.0,
                                     value=float(_dd_s.get('rs_vs_bench', 0.4)),
                                     step=0.05, format="%.2f", key='dd_w_rs',
                                     help="Reward for outperforming the benchmark")
        _w_peer = _wc2.number_input("Peer RS Score",   min_value=0.0, max_value=2.0,
                                     value=float(_dd_s.get('peer_rs_score', 0.3)),
                                     step=0.05, format="%.2f", key='dd_w_peer',
                                     help="% of sector peers outperformed")
        _w_dd   = _wc3.number_input("DD vs Benchmark", min_value=0.0, max_value=2.0,
                                     value=float(_dd_s.get('dd_vs_bench', 0.3)),
                                     step=0.05, format="%.2f", key='dd_w_dd',
                                     help="Drawdown penalty vs benchmark (applied negative)")
        _wc4.markdown("<br>", unsafe_allow_html=True)
        if _wc4.button("💾 Save Weights", key='dd_save_weights'):
            _save_dd_settings({'rs_vs_bench': _w_rs, 'peer_rs_score': _w_peer, 'dd_vs_bench': _w_dd})
            st.success(f"Saved — RS:{_w_rs} | Peer:{_w_peer} | DD:{_w_dd}")
        st.markdown(f"**Current formula:** `score = RS×{_w_rs} + Peer×{_w_peer} - DD×{_w_dd}`")

    _dd_weights = {'rs_vs_bench': _w_rs, 'peer_rs_score': _w_peer, 'dd_vs_bench': _w_dd}

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
                    bench_override=bench_override,
                    weights=_dd_weights
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
    st.caption("Filtered actionable stocks grouped by market. Run scripts to generate files.")

    _act_screener_dir  = os.path.join(STOCKS, 'results', 'daily_actionable', 'screener')
    _act_benchmark_dir = os.path.join(STOCKS, 'results', 'daily_actionable', 'benchmark')
    actionable_dir = _act_screener_dir  # default for screener lookups

    _all_csv = (sorted(glob.glob(os.path.join(_act_screener_dir,  '*.csv')), reverse=True) +
                sorted(glob.glob(os.path.join(_act_benchmark_dir, '*.csv')), reverse=True))
    _all_txt = (sorted(glob.glob(os.path.join(_act_screener_dir,  '*.txt')), reverse=True) +
                sorted(glob.glob(os.path.join(_act_benchmark_dir, '*.txt')), reverse=True))

    if not _all_csv:
        st.info("No actionable files found — run scripts first")
    else:
        from collections import defaultdict
        by_date = defaultdict(dict)
        for f in _all_csv + _all_txt:
            n = os.path.basename(f); date = n[:8]
            by_date[date][n[9:]] = f

        dates    = sorted(by_date.keys(), reverse=True)
        sel_date = st.selectbox("Select date", dates, key="act_date")
        day_files = by_date[sel_date]

        # Load settings for display
        _as_file = os.path.join(BASE, 'actionable_settings.json')
        _act_cfg = {}
        if os.path.exists(_as_file):
            try: _act_cfg = json.load(open(_as_file))
            except: pass

        _AS_DISPLAY_DEFAULTS = {
            'au_market'  : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':[],'cap_bands':['large','mid','small']},
            'us_market'  : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':[],'cap_bands':['large','mid','small']},
            'commodities': {'min_score':0.0,'regimes':['LEADER','CONTENDER'],'vol':['HIGH','MED'],'acc_watch':[],'cap_bands':['large','mid','small','ETF']},
            'uranium'    : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':[],'cap_bands':['large','mid','small']},
            'au_gold'    : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':[],'cap_bands':['large','mid','small']},
        }
        def _settings_caption(cfg_key):
            _s = {**_AS_DISPLAY_DEFAULTS.get(cfg_key,{}), **_act_cfg.get(cfg_key,{})}
            parts = []
            if _s.get('regimes'):   parts.append(f"Regimes: **{', '.join(_s['regimes'])}**")
            if _s.get('vol'):       parts.append(f"Vol: **{', '.join(_s['vol'])}**")
            if _s.get('cap_bands'): parts.append(f"Cap: **{', '.join(_s['cap_bands'])}**")
            _aw = _s.get('acc_watch')
            if _aw and (isinstance(_aw,list) and len(_aw)>0 or isinstance(_aw,str) and _aw):
                parts.append(f"Acc watch: **{', '.join(_aw) if isinstance(_aw,list) else _aw}**")
            else:
                parts.append("Acc watch: **any**")
            parts.append(f"Min score: **{_s.get('min_score',0.0)}**")
            return "Filters — " + " | ".join(parts)

        def _show_section(label, csv_stem, tv_stem, is_hc, cfg_key, subdir="screener"):
            _dir     = _act_benchmark_dir if subdir == "benchmark" else _act_screener_dir
            csv_path = os.path.join(_dir, f"{sel_date}_{csv_stem}")
            tv_path  = os.path.join(_dir, f"{sel_date}_{tv_stem}")
            has_csv  = os.path.exists(csv_path)
            has_tv   = os.path.exists(tv_path)
            hc_badge = " 🔥" if is_hc else ""
            st.markdown(f"**{label}{hc_badge}**")
            # Always show settings caption if config exists
            _cap = _settings_caption(cfg_key)
            if _cap:
                st.caption(_cap)
            elif not _act_cfg:
                st.caption("⚙️ No filter settings saved — configure in Settings → Actionable Settings")
            if not has_csv and not has_tv:
                st.caption(f"No file found: {sel_date}_{csv_stem}")
                return
            _c1, _c2 = st.columns([4, 1])
            with _c2:
                if has_tv:
                    _tv = open(tv_path).read().strip()
                    st.metric("Tickers", len(_tv.split(',')) if _tv else 0)
                    st.download_button("⬇ TradingView", _tv, file_name=tv_stem,
                                       mime='text/plain', key=f"tv_{cfg_key}_{label}_{sel_date}")
                if has_csv:
                    st.download_button("⬇ CSV", open(csv_path, encoding='utf-8').read(),
                                       file_name=csv_stem, mime='text/csv',
                                       key=f"csv_{cfg_key}_{label}_{sel_date}")
            with _c1:
                if has_csv:
                    _df = load_csv(csv_path, index_col='rank')
                    if _df is not None and len(_df) > 0:
                        _bc = ['ticker','name','cap_band','close','vol_label','acc_watch','regime_label','score_final']
                        _ec = ['sector','commodity','type','rs_ratio','peer_rs_score','ret_6m','ret_12m','max_dd','rs_trend','delta_rank']
                        _sc = [c for c in _bc+_ec if c in _df.columns]
                        _df_fmt = _df[_sc].copy()
                        # Format columns
                        for _col in ['ret_6m','ret_12m','ret_24m','max_dd','persist_frac']:
                            if _col in _df_fmt.columns:
                                _df_fmt[_col] = pd.to_numeric(_df_fmt[_col], errors='coerce').apply(
                                    lambda x: f"{x:.0f}%" if pd.notna(x) else "")
                        for _col in ['score_final','peer_rs_score','rs_ratio','mqs']:
                            if _col in _df_fmt.columns:
                                _df_fmt[_col] = pd.to_numeric(_df_fmt[_col], errors='coerce').apply(
                                    lambda x: f"{x:.0f}" if pd.notna(x) else "")
                        if 'close' in _df_fmt.columns:
                            _df_fmt['close'] = pd.to_numeric(_df_fmt['close'], errors='coerce').apply(
                                lambda x: f"{x:.3f}" if pd.notna(x) else "")
                        st.dataframe(style_df(_df_fmt,'regime_label','delta_rank'),
                                     width='stretch', height=min(len(_df)*35+40,350))
                    else:
                        st.caption("No results")
            st.markdown("---")
        # Group definitions — stems verified from actual directory listing
        _GROUPS = [
            ("🇦🇺 AU Market", "au_market", [
                ("Benchmark",       "au_total_market_actionable.csv",                  "au_total_market_actionable_tvimport.txt",                  False, "benchmark"),
                ("Screener",        "au_total_market_actionable.csv",                  "au_total_market_actionable_tvimport.txt",                  False, "screener"),
                ("High Conviction", "au_total_market_actionable_highconv.csv",         "au_total_market_actionable_highconv_tvimport.txt",          True,  "screener"),
            ]),
            ("🇺🇸 US Market", "us_market", [
                ("Benchmark",       "us_benchmark_actionable.csv",                     "us_benchmark_actionable_tvimport.txt",                     False, "screener"),
                ("Screener",        "us_total_market_actionable.csv",                  "us_total_market_actionable_tvimport.txt",                  False, "screener"),
                ("High Conviction", "us_total_market_actionable_highconv.csv",         "us_total_market_actionable_highconv_tvimport.txt",          True,  "screener"),
            ]),
            ("⛏ Commodities", "commodities", [
                ("Benchmark",       "commodities_actionable.csv",                      "commodities_actionable_tvimport.txt",                      False, "screener"),
                ("Screener",        "commodities_screener_actionable.csv",             "commodities_screener_actionable_tvimport.txt",             False, "screener"),
                ("High Conviction", "all_major_commodities_actionable_highconv.csv",   "all_major_commodities_actionable_highconv_tvimport.txt",    True,  "screener"),
            ]),
            ("☢ Uranium", "uranium", [
                ("Benchmark",       "uranium_actionable.csv",                          "uranium_actionable_tvimport.txt",                          False, "screener"),
                ("Screener",        "uranium_screener_actionable.csv",                 "uranium_screener_actionable_tvimport.txt",                 False, "screener"),
                ("High Conviction", "uranium_screener_highconv.csv",                   "uranium_screener_highconv_tvimport.txt",                    True,  "screener"),
            ]),
            ("🥇 AU Gold", "au_gold", [
                ("Benchmark",       "au_gold_miners_actionable.csv",                   "au_gold_miners_actionable_tvimport.txt",                   False, "screener"),
                ("Screener",        "au_gold_miners_actionable.csv",                   "au_gold_miners_actionable_tvimport.txt",                   False, "screener"),
                ("High Conviction", "au_gold_miners_screener_highconv.csv",            "au_gold_miners_screener_highconv_tvimport.txt",             True,  "screener"),
            ]),
        ]

        _grp_tabs = st.tabs([g[0] for g in _GROUPS])
        for _gtab, (_glabel, _cfg_key, _studies) in zip(_grp_tabs, _GROUPS):
            with _gtab:
                for _slabel, _csv_stem, _tv_stem, _is_hc, _subdir in _studies:
                    _show_section(_slabel, _csv_stem, _tv_stem, _is_hc, _cfg_key, _subdir)


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
                ('rrg_us_rsp_data.py',            STOCKS),
                ('rrg_dow_data.py',               STOCKS),
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
elif page == "Rank Settings":
    st.title("🎛️ Rank Score Settings")
    st.caption("Adjust scoring parameters for each benchmark and screener. "
               "Save named profiles per tab. Load any saved profile. Reset to factory defaults at any time.")

    _rs_base = os.path.join(BASE, 'rank_profiles')
    os.makedirs(_rs_base, exist_ok=True)

    # ── Profile helpers ───────────────────────────────────────────────────────
    def _prof_dir(tab_key):
        d = os.path.join(_rs_base, tab_key)
        os.makedirs(d, exist_ok=True)
        return d

    def _list_profiles(tab_key):
        return sorted(f[:-5] for f in os.listdir(_prof_dir(tab_key)) if f.endswith('.json'))

    def _load_profile(tab_key, name):
        p = os.path.join(_prof_dir(tab_key), f"{name}.json")
        return json.load(open(p)) if os.path.exists(p) else {}

    def _save_profile(tab_key, name, settings):
        p = os.path.join(_prof_dir(tab_key), f"{name}.json")
        json.dump(settings, open(p,'w'), indent=2)

    def _active_settings(tab_key, defaults):
        """Load active settings: check rank_settings.json first, else defaults."""
        p = os.path.join(BASE, 'rank_settings.json')
        if os.path.exists(p):
            try:
                return {**defaults, **json.load(open(p)).get(tab_key, {})}
            except: pass
        return defaults.copy()

    def _save_active(tab_key, settings):
        p = os.path.join(BASE, 'rank_settings.json')
        try:    rs = json.load(open(p))
        except: rs = {}
        rs[tab_key] = settings
        json.dump(rs, open(p,'w'), indent=2)
        st.success(f"✓ Active settings saved to rank_settings.json")

    # ── Weight guidance ───────────────────────────────────────────────────────
    WEIGHT_GUIDE = """
<div style="background:rgba(255,180,0,0.08);border:1px solid rgba(255,180,0,0.3);
border-radius:6px;padding:8px 14px;font-size:11px;margin-bottom:12px;line-height:1.8">
<b>Weight guidance:</b> &nbsp;
<code>0.0</code> = disabled &nbsp;|&nbsp;
<code>0.01–0.1</code> = minor influence &nbsp;|&nbsp;
<code>0.2–0.3</code> = moderate &nbsp;|&nbsp;
<code>0.4–0.5</code> = standard weight &nbsp;|&nbsp;
<code>0.6–1.0</code> = high emphasis &nbsp;|&nbsp;
<code>>1.0</code> = dominant factor<br>
<b>Bonus values:</b> &nbsp;
<code>0.5</code> = small boost &nbsp;|&nbsp;
<code>1.0</code> = standard bonus &nbsp;|&nbsp;
<code>-0.5</code> = mild penalty &nbsp;|&nbsp;
<code>-1.0</code> = strong penalty<br>
<b>Vol multiplier:</b> &nbsp;
<code>1.0</code> = neutral &nbsp;|&nbsp;
<code>1.1</code> = 10%% boost for high volume &nbsp;|&nbsp;
<code>0.9</code> = 10%% penalty for low volume
</div>"""

    # ── Benchmark score widget ────────────────────────────────────────────────


    def _profile_bar(tab_key, cur, k):
        """Render profile load/save bar. Returns updated settings dict."""
        profiles = _list_profiles(tab_key)
        pb1, pb2, pb3, pb4 = st.columns([3, 2, 2, 1])
        sel = pb1.selectbox("Load profile", ["— current —"] + profiles, key=f"prof_sel_{k}")
        if sel != "— current —":
            loaded = _load_profile(tab_key, sel)
            if loaded:
                cur = {**cur, **loaded}
                st.session_state[f"prof_loaded_{k}"] = cur
        pname = pb2.text_input("Save as", placeholder="profile name", key=f"prof_name_{k}")
        if pb3.button("💾 Save profile", key=f"prof_save_{k}") and pname.strip():
            _save_profile(tab_key, pname.strip(), cur)
            st.success(f"Saved profile '{pname.strip()}'")
        if pb4.button("↩ Defaults", key=f"prof_def_{k}"):
            st.session_state[f"prof_loaded_{k}"] = None
            # Increment reset counter — widgets use it as key suffix to force re-render
            st.session_state[f"reset_ctr_{k}"] = st.session_state.get(f"reset_ctr_{k}", 0) + 1
            st.rerun()
        return cur

    def _bm_score_widgets(tab_key, script, defaults):
        cur = _active_settings(tab_key, defaults)
        # Apply any loaded profile from session state
        if st.session_state.get(f"prof_loaded_{tab_key}"):
            cur = {**cur, **st.session_state[f"prof_loaded_{tab_key}"]}
        st.markdown(unsafe_allow_html=True, body=WEIGHT_GUIDE)
        cur = _profile_bar(tab_key, cur, tab_key)
        _rk = st.session_state.get(f"reset_ctr_{tab_key}", 0)  # key suffix for reset
        def _w_tag(v):
            if v == 0: return "off"
            elif v <= 0.1: return "minor"
            elif v <= 0.3: return "moderate"
            elif v <= 0.5: return "standard"
            elif v <= 1.0: return "high"
            else: return "dominant"
        st.code(
            f"score = (ret_12m × {cur['ret_12m_weight']} [{_w_tag(cur['ret_12m_weight'])}])"
            f" + (persist × {cur['persist_weight']} [{_w_tag(cur['persist_weight'])}])"
            f" + (dd × -{cur['dd_weight_large']}..{cur['dd_weight_small']} [penalty])"
            f" + (mqs × {cur['mqs_weight']} [{_w_tag(cur['mqs_weight'])}])"
            f" + trend_bonus({cur['trend_bonus']}) + lead_bonus({cur['lead_bonus']})"
            f" + rs_trend_bonus  →  × vol_multiplier",
            language="python")
        st.markdown("#### Return & Quality")
        c1,c2,c3 = st.columns(3)
        v_ret  = c1.number_input("12m Return weight — standard 0.4", -2.0, 2.0, float(cur['ret_12m_weight']),  0.05, key=f"ret_{tab_key}_{_rk}", help="Primary momentum signal. 0.4 = standard. Higher = more return-chasing.")
        v_per  = c2.number_input("Persistence weight — standard 0.01", 0.0, 0.5, float(cur['persist_weight']),  0.005, format="%.3f", key=f"per_{tab_key}_{_rk}", help="% up-days. Small influence — keep low (0.01). Increase to reward consistency.")
        v_mqs  = c3.number_input("MQS weight — standard 0.2", -2.0, 2.0, float(cur['mqs_weight']),   0.05, key=f"mqs_{tab_key}_{_rk}", help="Momentum Quality Score. 0.2 = standard. Rewards clean rises with low volatility.")
        st.markdown("#### Drawdown Penalty (applied negative)")
        c1,c2,c3,c4 = st.columns(4)
        v_ddl = c1.number_input("Large cap — std 0.4", 0.0, 2.0, float(cur['dd_weight_large']),  0.05, key=f"ddl_{tab_key}_{_rk}", help="Higher = larger stocks penalised more for big drawdowns")
        v_ddm = c2.number_input("Mid cap — std 0.3",   0.0, 2.0, float(cur['dd_weight_mid']),    0.05, key=f"ddm_{tab_key}_{_rk}")
        v_dds = c3.number_input("Small cap — std 0.2", 0.0, 2.0, float(cur['dd_weight_small']),  0.05, key=f"dds_{tab_key}_{_rk}")
        v_dde = c4.number_input("ETF — std 0.3",       0.0, 2.0, float(cur['dd_weight_etf']),    0.05, key=f"dde_{tab_key}_{_rk}")
        st.markdown("#### Trend & Leadership Bonus")
        c1,c2 = st.columns(2)
        v_tb = c1.number_input("Trend bonus (above 200 SMA) — std 1.0", 0.0, 3.0, float(cur['trend_bonus']), 0.05, key=f"tb_{tab_key}_{_rk}", help="Added when price > 200 SMA. 1.0 = standard single-point bonus.")
        v_lb = c2.number_input("Lead bonus (RS ratio > 1.0) — std 1.0",  0.0, 3.0, float(cur['lead_bonus']),  0.05, key=f"lb_{tab_key}_{_rk}", help="Added when stock outperforms benchmark over 12m.")
        st.markdown("#### RS Trend Bonus")
        c1,c2,c3,c4,c5 = st.columns(5)
        v_rsu  = c1.number_input("Strong Up — std 1.0",   -2.0, 2.0, float(cur['rs_trend_strong_up']),    0.05, key=f"rsu_{tab_key}_{_rk}")
        v_ru   = c2.number_input("Up — std 0.5",          -2.0, 2.0, float(cur['rs_trend_up']),           0.05, key=f"ru_{tab_key}_{_rk}")
        v_rf   = c3.number_input("Flat — std 0.0",        -2.0, 2.0, float(cur['rs_trend_flat']),         0.05, key=f"rf_{tab_key}_{_rk}")
        v_rd   = c4.number_input("Down — std -0.5",       -2.0, 2.0, float(cur['rs_trend_down']),         0.05, key=f"rd_{tab_key}_{_rk}")
        v_rsd  = c5.number_input("Strong Down — std -1.0",-2.0, 2.0, float(cur['rs_trend_strong_down']),  0.05, key=f"rsd_{tab_key}_{_rk}")
        st.markdown("#### Volume Multiplier")
        c1,c2,c3 = st.columns(3)
        v_vh = c1.number_input("High vol — std 1.1 (+10%%)", 0.0, 3.0, float(cur['vol_high']), 0.05, key=f"vh_{tab_key}_{_rk}", help="Multiplies final score. 1.1 = 10%% boost for high volume days.")
        v_vm = c2.number_input("Med vol — std 1.0 (neutral)", 0.0, 3.0, float(cur['vol_med']),  0.05, key=f"vm_{tab_key}_{_rk}")
        v_vl = c3.number_input("Low vol — std 0.9 (-10%%)",  0.0, 3.0, float(cur['vol_low']),  0.05, key=f"vl_{tab_key}_{_rk}")
        new_s = {
            'ret_12m_weight': v_ret, 'persist_weight': v_per, 'mqs_weight': v_mqs,
            'trend_bonus': v_tb, 'lead_bonus': v_lb,
            'dd_weight_large': v_ddl, 'dd_weight_mid': v_ddm, 'dd_weight_small': v_dds, 'dd_weight_etf': v_dde,
            'vol_high': v_vh, 'vol_med': v_vm, 'vol_low': v_vl,
            'rs_trend_strong_up': v_rsu, 'rs_trend_up': v_ru, 'rs_trend_flat': v_rf,
            'rs_trend_down': v_rd, 'rs_trend_strong_down': v_rsd,
        }
        b1,b2 = st.columns([2,1])
        if b1.button("💾 Save as Active", type="primary", key=f"save_{tab_key}"):
            _save_active(tab_key, new_s)
        if b2.button("🔄 Save & Run", key=f"run_{tab_key}"):
            _save_active(tab_key, new_s)
            run_script(os.path.join(STOCKS, script), STOCKS)
            st.success("Done")
        return new_s

    def _sc_score_widgets(tab_key, bm_script, sc_script, defaults):
        cur = _active_settings(tab_key, defaults)
        if st.session_state.get(f"prof_loaded_{tab_key}"):
            cur = {**cur, **st.session_state[f"prof_loaded_{tab_key}"]}
        st.markdown(unsafe_allow_html=True, body=WEIGHT_GUIDE)
        cur = _profile_bar(tab_key, cur, tab_key)
        _rk = st.session_state.get(f"reset_ctr_{tab_key}", 0)  # key suffix for reset
        st.markdown("#### Score Weights")
        def _w_tag(v):
            if v == 0: return "off"
            elif v <= 0.1: return "minor"
            elif v <= 0.3: return "moderate"
            elif v <= 0.5: return "standard"
            elif v <= 1.0: return "high"
            else: return "dominant"
        st.code(
            f"score = (ret_12m × {cur['ret_12m_weight']} [{_w_tag(cur['ret_12m_weight'])}])"
            f" + (persist × {cur['persist_weight']} [{_w_tag(cur['persist_weight'])}])"
            f" + (dd × -w_dd [penalty])"
            f" + (mqs × {cur['mqs_weight']} [{_w_tag(cur['mqs_weight'])}])"
            f" + (peer_rs × {cur['peer_rs_weight']} [{_w_tag(cur['peer_rs_weight'])}])"
            f" + rs_trend_bonus + regime_bonus  →  × vol_multiplier",
            language="python")
        c1,c2,c3,c4 = st.columns(4)
        v_ret  = c1.number_input("12m Return — std 0.4",    -2.0, 2.0, float(cur['ret_12m_weight']),  0.05, key=f"ret_{tab_key}_{_rk}", help="Primary return signal. 0.4 standard.")
        v_per  = c2.number_input("Persistence — std 0.01",   0.0, 0.5, float(cur['persist_weight']),  0.005, format="%.3f", key=f"per_{tab_key}_{_rk}", help="Consistency of up-days. Keep small.")
        v_mqs  = c3.number_input("MQS — std 0.2",           -2.0, 2.0, float(cur['mqs_weight']),      0.05, key=f"mqs_{tab_key}_{_rk}", help="Quality score. Rewards clean trends.")
        v_prs  = c4.number_input("Peer RS — std 0.02",       0.0, 0.5, float(cur['peer_rs_weight']),  0.005, format="%.3f", key=f"prs_{tab_key}_{_rk}", help="% outperforming sector peers. Keep small — already 0-100 scale.")
        st.markdown("#### Drawdown Penalty")
        c1,c2,c3,c4 = st.columns(4)
        v_ddl = c1.number_input("Large — std 0.4", 0.0, 2.0, float(cur['dd_weight_large']),  0.05, key=f"ddl_{tab_key}_{_rk}")
        v_ddm = c2.number_input("Mid — std 0.3",   0.0, 2.0, float(cur['dd_weight_mid']),    0.05, key=f"ddm_{tab_key}_{_rk}")
        v_dds = c3.number_input("Small — std 0.2", 0.0, 2.0, float(cur['dd_weight_small']),  0.05, key=f"dds_{tab_key}_{_rk}")
        v_dde = c4.number_input("ETF — std 0.3",   0.0, 2.0, float(cur['dd_weight_etf']),    0.05, key=f"dde_{tab_key}_{_rk}")
        st.markdown("#### RS Trend Bonus")
        c1,c2,c3,c4,c5 = st.columns(5)
        v_rsu = c1.number_input("Strong Up — std 1.0",   -2.0, 2.0, float(cur['rs_trend_strong_up']),   0.05, key=f"rsu_{tab_key}_{_rk}")
        v_ru  = c2.number_input("Up — std 0.5",          -2.0, 2.0, float(cur['rs_trend_up']),          0.05, key=f"ru_{tab_key}_{_rk}")
        v_rf  = c3.number_input("Flat — std 0.0",        -2.0, 2.0, float(cur['rs_trend_flat']),        0.05, key=f"rf_{tab_key}_{_rk}")
        v_rd  = c4.number_input("Down — std -0.5",       -2.0, 2.0, float(cur['rs_trend_down']),        0.05, key=f"rd_{tab_key}_{_rk}")
        v_rsd = c5.number_input("Strong Down — std -1.0",-2.0, 2.0, float(cur['rs_trend_strong_down']), 0.05, key=f"rsd_{tab_key}_{_rk}")
        st.markdown("#### Regime Bonus")
        c1,c2,c3,c4 = st.columns(4)
        v_rl  = c1.number_input("Leader — std 1.0",    -2.0, 2.0, float(cur['regime_bonus_leader']),    0.05, key=f"rl_{tab_key}_{_rk}", help="Top peer RS + above trend. 1.0 = strong boost.")
        v_rc  = c2.number_input("Contender — std 0.5", -2.0, 2.0, float(cur['regime_bonus_contender']), 0.05, key=f"rc_{tab_key}_{_rk}")
        v_rlag= c3.number_input("Laggard — std 0.0",   -2.0, 2.0, float(cur['regime_bonus_laggard']),   0.05, key=f"rlag_{tab_key}_{_rk}")
        v_rw  = c4.number_input("Weak — std -0.5",     -2.0, 2.0, float(cur['regime_bonus_weak']),      0.05, key=f"rw_{tab_key}_{_rk}", help="Below trend + low peer RS. -0.5 = penalty.")
        st.markdown("#### Volume Multiplier")
        c1,c2,c3 = st.columns(3)
        v_vh = c1.number_input("High — std 1.1", 0.0, 3.0, float(cur['vol_high']), 0.05, key=f"vh_{tab_key}_{_rk}")
        v_vm = c2.number_input("Med — std 1.0",  0.0, 3.0, float(cur['vol_med']),  0.05, key=f"vm_{tab_key}_{_rk}")
        v_vl = c3.number_input("Low — std 0.9",  0.0, 3.0, float(cur['vol_low']),  0.05, key=f"vl_{tab_key}_{_rk}")
        st.divider()
        st.markdown("#### Filter Parameters")
        fc1, fc2 = st.columns(2)
        v_cap = fc1.number_input("Min market cap ($)", 0, 100_000_000_000,
                                  int(cur.get('min_market_cap', 0)), 10_000_000, key=f"cap_{tab_key}_{_rk}")
        v_vol = fc2.number_input("Min avg daily volume ($)", 0, 100_000_000,
                                  int(cur.get('min_vol_avg', 0)), 10_000, key=f"vol_{tab_key}_{_rk}")
        _valid_regimes = ['LEADER','CONTENDER','LAGGARD','WEAK']
        _reg_default = [r for r in cur.get('regime_filter', ['LEADER','CONTENDER']) if r in _valid_regimes] or ['LEADER','CONTENDER']
        v_reg = st.multiselect("Allowed regimes", _valid_regimes,
                                default=_reg_default, key=f"reg_{tab_key}_{_rk}")
        new_s = {
            'ret_12m_weight': v_ret, 'persist_weight': v_per, 'mqs_weight': v_mqs, 'peer_rs_weight': v_prs,
            'dd_weight_large': v_ddl, 'dd_weight_mid': v_ddm, 'dd_weight_small': v_dds, 'dd_weight_etf': v_dde,
            'vol_high': v_vh, 'vol_med': v_vm, 'vol_low': v_vl,
            'rs_trend_strong_up': v_rsu, 'rs_trend_up': v_ru, 'rs_trend_flat': v_rf,
            'rs_trend_down': v_rd, 'rs_trend_strong_down': v_rsd,
            'regime_bonus_leader': v_rl, 'regime_bonus_contender': v_rc,
            'regime_bonus_laggard': v_rlag, 'regime_bonus_weak': v_rw,
            'min_market_cap': v_cap, 'min_vol_avg': v_vol, 'regime_filter': v_reg,
        }
        b1,b2,b3 = st.columns([2,2,1])
        if b1.button("💾 Save as Active", type="primary", key=f"save_{tab_key}"):
            _save_active(tab_key, new_s)
        if b2.button("🔄 Save & Run Screener", key=f"run_sc_{tab_key}"):
            _save_active(tab_key, new_s)
            run_script(os.path.join(STOCKS, sc_script), STOCKS)
            st.success("Screener done")
        if b3.button("📊 Run Benchmark", key=f"run_bm_{tab_key}"):
            run_script(os.path.join(STOCKS, bm_script), STOCKS)
            st.success("Benchmark done")
        return new_s

    # ── Tabs ──────────────────────────────────────────────────────────────────
    _rs_tabs = st.tabs([
        "🇦🇺 AU Benchmark", "🇺🇸 US Benchmark", "🪨 Comm Benchmark",
        "🔍 AU Screener",   "🔍 US Screener",   "🔍 Comm Screener",
    ])
    with _rs_tabs[0]: _bm_score_widgets('au_benchmark',   'au_total_market_benchmark.py',       BM_DEFAULTS)
    with _rs_tabs[1]: _bm_score_widgets('us_benchmark',   'us_total_market_benchmark.py',       BM_DEFAULTS)
    with _rs_tabs[2]: _bm_score_widgets('comm_benchmark', 'all_major_commodities_benchmark.py', BM_DEFAULTS)
    with _rs_tabs[3]: _sc_score_widgets('au_screener',   'au_total_market_benchmark.py',   'au_total_market_screener.py',       SC_DEFAULTS)
    with _rs_tabs[4]: _sc_score_widgets('us_screener',   'us_total_market_benchmark.py',   'us_total_market_screener.py',       SC_DEFAULTS)
    with _rs_tabs[5]: _sc_score_widgets('comm_screener', 'all_major_commodities_benchmark.py', 'all_major_commodities_screener.py', SC_DEFAULTS)

elif page == "Settings":
    st.title("⚙ Settings")
    _settings_tabs = st.tabs(["⚙ General Settings", "⚙️ Actionable Settings", "🤖 AI Settings"])

    # ── General Settings ──────────────────────────────────────────────────────
    with _settings_tabs[0]:
        st.subheader("⚙ Dashboard Settings")
        st.caption("Changes take effect after saving and reloading the page")

        current = load_settings()

        # ── Pages ─────────────────────────────────────────────────────────────
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

        # ── AI Features ───────────────────────────────────────────────────────
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

        # ── Save / Reset ──────────────────────────────────────────────────────
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

        # ── Display Settings ──────────────────────────────────────────────────
        st.divider()
        st.subheader("Display")

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

        # ── Network Access ────────────────────────────────────────────────────
        st.divider()
        st.subheader("Network Access")
        st.caption(
            "Controls which network interfaces Streamlit listens on. "
            "Restart Streamlit after changing. Uses .streamlit/config.toml."
        )

        _net_cfg_file = os.path.join(BASE, '.streamlit', 'config.toml')
        _net_current  = '0.0.0.0'
        if os.path.isfile(_net_cfg_file):
            import re as _re_net
            _nc_txt = open(_net_cfg_file).read()
            _nm = _re_net.search(r'address\s*=\s*"([^"]*)"', _nc_txt)
            if _nm: _net_current = _nm.group(1)

        _net_options = {
            'Localhost only (127.0.0.1)'          : '127.0.0.1',
            'Local network only (LAN/Tailscale)'  : '0.0.0.0',
            'Custom address'                       : 'custom',
        }
        _net_labels   = list(_net_options.keys())
        _net_vals     = list(_net_options.values())
        _net_idx      = _net_vals.index(_net_current) if _net_current in _net_vals else 2

        _net_sel = st.radio("Listen on", _net_labels, index=_net_idx,
                             key='net_mode',
                             help="Localhost only = most secure, only your machine. "
                                  "Local network = accessible from other devices on LAN or via Tailscale. "
                                  "Custom = specify exact IP.")

        _custom_addr = ''
        if _net_sel == 'Custom address':
            _custom_addr = st.text_input("IP address", value=_net_current
                                          if _net_current not in ('127.0.0.1','0.0.0.0') else '',
                                          placeholder="e.g. 192.168.1.100", key='net_custom_addr')

        _net_addr = _net_options.get(_net_sel, _custom_addr or '0.0.0.0')
        if _net_sel == 'Custom address':
            _net_addr = _custom_addr or '0.0.0.0'

        _port_current = 8501
        if os.path.isfile(_net_cfg_file):
            _pm = _re_net.search(r'port\s*=\s*(\d+)', open(_net_cfg_file).read())
            if _pm: _port_current = int(_pm.group(1))

        _port = st.number_input("Port", min_value=1024, max_value=65535,
                                 value=_port_current, step=1, key='net_port')

        st.info(
            f"Current: {_net_current}:{_port_current} — "
            f"If seeing your public/NAT IP in the Streamlit banner, switch to Localhost only "
            f"(http://localhost:{_port_current}) or Local network with Tailscale.",
            icon="🌐"
        )

        if st.button("💾 Apply Network Settings", type="primary", key='net_apply'):
            import re as _re_net2
            if os.path.isfile(_net_cfg_file):
                _nc = open(_net_cfg_file).read()
            else:
                _nc = '[server]\n'

            if 'address' in _nc:
                _nc = _re_net2.sub(r'address\s*=\s*"[^"]*"', f'address = "{_net_addr}"', _nc)
            else:
                _nc = _nc.rstrip() + '\n' + f'address = "{_net_addr}"\n'

            if _re_net2.search(r'port\s*=\s*\d+', _nc):
                _nc = _re_net2.sub(r'port\s*=\s*\d+', f'port = {_port}', _nc)
            else:
                _nc = _nc.rstrip() + '\n' + f'port = {_port}\n'

            os.makedirs(os.path.dirname(_net_cfg_file), exist_ok=True)
            with open(_net_cfg_file, 'w') as _f: _f.write(_nc)
            st.success(f"Network settings saved — restart Streamlit to apply (address={_net_addr}, port={_port})")

    # ── Actionable Settings ───────────────────────────────────────────────────
    with _settings_tabs[1]:
        st.subheader("⚙️ Actionable Report Settings")
        st.caption("Configure filters for actionable export files. Saved to actionable_settings.json.")
        _as_file = os.path.join(BASE, 'actionable_settings.json')
        _AS_DEFAULTS = {
            'au_market'  : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':False,'cap_bands':['large','mid','small']},
            'us_market'  : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':False,'cap_bands':['large','mid','small']},
            'commodities': {'min_score':0.0,'regimes':['LEADER','CONTENDER'],'vol':['HIGH','MED'],'acc_watch':False,'cap_bands':['large','mid','small','ETF']},
            'uranium'    : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':False,'cap_bands':['large','mid','small']},
            'au_gold'    : {'min_score':0.0,'regimes':['LEADER','CONTENDER','TREND+LEAD'],'vol':['HIGH','MED'],'acc_watch':False,'cap_bands':['large','mid','small']},
        }
        def _load_as():
            if os.path.exists(_as_file):
                try: return {k:{**_AS_DEFAULTS[k],**json.load(open(_as_file)).get(k,{})} for k in _AS_DEFAULTS}
                except: pass
            return {k:dict(v) for k,v in _AS_DEFAULTS.items()}
        def _save_as(s):
            with open(_as_file,'w') as _f: json.dump(s,_f,indent=2)
            st.success("Saved to actionable_settings.json")
        _as=_load_as()
        _as_tabs=st.tabs(["🇦🇺 AU Market","🇺🇸 US Market","⛏ Commodities","☢ Uranium","🥇 AU Gold"])
        for _k,_t in zip(['au_market','us_market','commodities','uranium','au_gold'],_as_tabs):
            with _t:
                _s=_as[_k]
                st.markdown("#### Filter Parameters")
                st.caption("Settings saved here are displayed under each table on the Actionable & Exports page.")
                _c1,_c2=st.columns(2)
                _ms =_c1.number_input("Min score_final",-5.0,10.0,float(_s['min_score']),0.1,key=f"as_ms_{_k}")
                _acc_opts = ['EARLY','PROGRESS','SHIFT','-']
                _acc_def  = _s['acc_watch'] if isinstance(_s['acc_watch'],list) else (['EARLY','PROGRESS','SHIFT'] if _s['acc_watch'] else [])
                _acc=_c2.multiselect("Acc watch filter",_acc_opts,default=_acc_def,key=f"as_acc_{_k}",help="Leave empty = no filter. Select values to only show stocks with those acc_watch values.")
                _reg=st.multiselect("Allowed regimes",['LEADER','CONTENDER','LAGGARD','WEAK','TREND+LEAD','TREND_ONLY'],default=_s['regimes'],key=f"as_reg_{_k}")
                _vol=st.multiselect("Volume filter",['HIGH','MED','LOW'],default=_s['vol'],key=f"as_vol_{_k}")
                _cap=st.multiselect("Cap bands",['large','mid','small','ETF'],default=_s['cap_bands'],key=f"as_cap_{_k}")
                st.markdown("")
                if st.button("💾 Save",type="primary",key=f"as_save_{_k}"):
                    _as[_k]={'min_score':_ms,'acc_watch':_acc,'regimes':_reg,'vol':_vol,'cap_bands':_cap}
                    _save_as(_as)

    # ── AI Settings ───────────────────────────────────────────────────────────
    with _settings_tabs[2]:
        st.subheader("🤖 AI Settings")

        _ai_s    = load_settings()
        _ai_feat = _ai_s.get('ai_features', {})
        _ai_prmp = _ai_s.get('ai_prompts', DEFAULT_SETTINGS.get('ai_prompts', {}))

        def _save_ai_settings(feat, prompts):
            s = load_settings()
            s['ai_features'] = feat
            s['ai_prompts']  = prompts
            save_settings(s)

        _ai_tabs = st.tabs([
            "⚙️ General",
            "🇦🇺 AU Breadth",
            "🇺🇸 US Breadth",
            "💳 Debt Markets",
            "📊 AU Benchmark",
            "📊 US Benchmark",
            "🪨 Commodities",
        ])

        with _ai_tabs[0]:
            _ai_enabled = st.toggle("Enable AI Assessments", value=_ai_feat.get('enabled', False))
            st.markdown("#### Active Provider")
            _provider = st.radio("Active provider", options=["anthropic", "openai"],
                                  index=0 if _ai_feat.get('provider', 'anthropic') == 'anthropic' else 1,
                                  horizontal=True,
                                  format_func=lambda x: "🟣 Claude (Anthropic)" if x == "anthropic" else "🟢 ChatGPT (OpenAI)",
                                  help="Select which API to use for all AI assessments",
                                  label_visibility="collapsed")

            st.divider()
            st.markdown("#### 🟣 Claude API")
            _claude_key = st.text_input("Anthropic API Key", value=_ai_feat.get('anthropic_api_key', ''),
                                         type="password", help="sk-ant-...")
            _claude_models = ['claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5-20251001']
            _claude_model  = st.selectbox("Claude Model",
                                           options=_claude_models,
                                           index=_claude_models.index(_ai_feat.get('model', 'claude-sonnet-4-6'))
                                           if _ai_feat.get('model', 'claude-sonnet-4-6') in _claude_models else 0)

            st.divider()
            st.markdown("#### 🟢 ChatGPT API")
            _openai_key   = st.text_input("OpenAI API Key", value=_ai_feat.get('openai_api_key', ''),
                                           type="password", help="sk-...")
            _openai_model = st.selectbox("OpenAI Model",
                                          options=['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
                                          index=['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'].index(
                                              _ai_feat.get('openai_model', 'gpt-4o')))

            st.markdown("")
            if st.button("💾 Save General Settings", type="primary", key='ai_save_general'):
                _new_feat = {
                    'enabled'          : _ai_enabled,
                    'provider'         : _provider,
                    'anthropic_api_key': _claude_key,
                    'model'            : _claude_model,
                    'openai_api_key'   : _openai_key,
                    'openai_model'     : _openai_model,
                }
                _save_ai_settings(_new_feat, _ai_prmp)
                st.success(f"Saved — using {'Claude' if _provider == 'anthropic' else 'ChatGPT'}")

        _prompt_defs = [
            ('au_breadth',       'AU Breadth', '🇦🇺 AU Breadth', _ai_tabs[1]),
            ('us_breadth',       'US Breadth', '🇺🇸 US Breadth', _ai_tabs[2]),
            ('consumer_credit',  'Debt Markets — Consumer Credit', '💳 Consumer', _ai_tabs[3]),
            ('au_benchmark',     'AU Benchmark', '📊 AU Benchmark', _ai_tabs[4]),
            ('us_benchmark',     'US Benchmark', '📊 US Benchmark', _ai_tabs[5]),
            ('comm_benchmark',   'Commodities Benchmark', '🪨 Commodities', _ai_tabs[6]),
        ]

        for _pk, _plabel, _ptab_label, _ptab in _prompt_defs:
            with _ptab:
                st.markdown(f"#### {_plabel} Prompt")
                st.caption("Edit the system instruction sent to the AI. The live market data is appended automatically.")
                _default_prompt = DEFAULT_SETTINGS.get('ai_prompts', {}).get(_pk, '')
                _current_prompt = _ai_prmp.get(_pk, _default_prompt)
                _new_prompt = st.text_area(
                    "Prompt", value=_current_prompt,
                    height=200, key=f"ai_prompt_{_pk}",
                    label_visibility="collapsed"
                )
                _pc1, _pc2 = st.columns([1, 4])
                if _pc1.button("💾 Save", key=f"ai_save_{_pk}", type="primary"):
                    _ai_prmp[_pk] = _new_prompt
                    _save_ai_settings(_ai_feat, _ai_prmp)
                    st.success("Prompt saved")
                if _pc2.button("↩ Reset to default", key=f"ai_reset_{_pk}"):
                    _ai_prmp[_pk] = _default_prompt
                    _save_ai_settings(_ai_feat, _ai_prmp)
                    st.success("Reset to default")
                    st.rerun()