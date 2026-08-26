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
ETF     = os.path.join(BASE, 'etf')
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

# Theme-aware UI text: silver-grey in dark mode, near-black in light mode.
# Fixes primaryColor (#1a3a5c) text being unreadable on the dark background
# (active tab labels, slider thumb values) and hardcoded dark table headers.
_UI_TEXT = '#d5d9de' if _get_theme_mode() == 'dark' else '#111111'

st.markdown(f"""
    <style>
    thead tr th {{ color: {_UI_TEXT} !important; font-weight: 600 !important; }}
    [data-testid="stDataFrame"] th {{ color: {_UI_TEXT} !important; font-weight: 600 !important; }}
    .stTabs [data-baseweb="tab"] p {{ color: {_UI_TEXT} !important; }}
    .stTabs [data-baseweb="tab"][aria-selected="true"] p {{ font-weight: 700 !important; }}
    [data-testid="stSliderThumbValue"] {{ color: {_UI_TEXT} !important; }}
    [data-testid="stSliderThumbValue"] p {{ color: {_UI_TEXT} !important; }}
    .info-card {{
        background: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
        font-size: 13px;
        color: inherit;
        line-height: 1.7;
    }}
    .macro-card {{
        background: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }}
    .macro-label  {{ color: #888; font-size: 10px; }}
    .macro-value  {{ font-size: 15px; font-weight: bold; }}
    .macro-signal {{ font-size: 10px; }}
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
        'Screeners & Exports': True,
        'DeMark Signals'      : True,
        'Fundamental Analysis': True,
        'Sentiment'           : True,
        'Run Scripts'         : True,
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
            'rsi_div_bull': 1.0, 'rsi_div_hid_bull': 0.5, 'rsi_div_bear': -1.0, 'rsi_div_hid_bear': -0.5,
            'obv_conv_up': 0.5, 'obv_bull_div': 1.0, 'obv_accum': 0.5,
            'obv_conv_down': -0.5, 'obv_bear_div': -1.0, 'obv_distrib': -0.5,
        },
        'us_benchmark'  : {},
        'comm_benchmark': {},
    },
    'ai_prompts': {
        'au_breadth':    "You are a market breadth analyst for the Australian stock market (ASX).\nAnalyse these breadth readings and provide a concise 4-5 sentence assessment.\nFocus on: (1) overall market health and trend, (2) cap band divergences (large vs small),\n(3) key sector rotations, (4) what the breadth signals suggest about near-term direction.\nBe direct and specific — mention actual numbers.",
        'us_breadth':    "You are a market breadth analyst for the US stock market.\nAnalyse these breadth readings and provide a concise 4-5 sentence assessment.\nFocus on: (1) overall market health across all 3 layers, (2) divergences between layers,\n(3) key sector rotations in Layer 2, (4) what the breadth signals suggest about near-term direction.\nBe direct and specific — mention actual numbers.",
        'consumer_credit': "You are a macro credit analyst. Analyse these US consumer credit readings and provide a 3-4 sentence assessment focusing on: credit stress signals, delinquency trends, and what this means for consumer spending and equity markets.",
        'au_credit': "You are a macro credit analyst covering Australia. Analyse these Australian debt market readings from RBA statistical tables. Note Australia has no free arrears series — household stress is read through leverage ratios and credit growth composition. Australian household debt-to-income is among the highest in the developed world.",
        'hhdc_flows': "You are a macro credit analyst specialising in the NY Fed Household Debt and Credit report. Analyse these transition rates into delinquency and origination quality data. These are FLOW measures (share of current balances newly going delinquent each quarter, all lenders) which lead bank-reported stock delinquency rates by 1-2 quarters. Note the student loan series is distorted by the 2020-2024 payment moratorium.",
        'corporate_credit': "Analyse these US corporate credit readings in 3-4 sentences. Focus on HY spreads, investment grade conditions, and systemic risk signals.",
        'sovereign_credit': "Analyse US sovereign credit health in 3-4 sentences. Focus on yield curve shape, duration risk, and what rates signal about macro conditions.",
        'au_benchmark':  "You are a quantitative analyst. Analyse this AU market relative strength data and provide a 4-5 sentence assessment covering: top momentum leaders, laggards to avoid, sector rotation signals, and any regime changes visible in the data.",
        'us_benchmark':  "You are a quantitative analyst. Analyse this US market relative strength data and provide a 4-5 sentence assessment covering: top momentum leaders, laggards to avoid, sector rotation signals, and any regime changes visible in the data.",
        'comm_benchmark': "You are a commodity market analyst. Analyse this commodity relative strength data and provide a 4-5 sentence assessment covering: leading commodities, lagging groups, rotation signals, and what this implies for risk appetite.",
        'sea_sectors':   "You are a market seasonality analyst. Analyse the monthly seasonal data provided and give a 4-5 sentence assessment. Highlight: (1) the 2-3 strongest months by average return and % positive, (2) the 2-3 weakest months to be cautious of, (3) how the current presidential year compares to the historical average for the same year-in-term, (4) any notable seasonal edge or caution for the current month. Be specific with numbers.",
        'sea_stocks':    "You are a market seasonality analyst. Analyse the monthly seasonal data for this stock/ETF and give a 4-5 sentence assessment. Highlight: (1) the 2-3 strongest months by average return and % positive, (2) the 2-3 weakest months, (3) how the current presidential year-in-term affects this instrument's seasonality, (4) any strong correlation with the benchmark if provided. Be specific with numbers.",
        'sea_presidential': "You are a market seasonality analyst specialising in presidential cycle analysis. Analyse the monthly data for this presidential year pattern and give a 4-5 sentence assessment. Highlight: (1) which months show the strongest edge vs the full-history average, (2) typical drawdown risk for this year-in-term, (3) current YTD performance vs historical expectation, (4) any cautionary or favourable seasonal signals for the months ahead.",
    },
    'ai_features': {
        'enabled'          : False,
        'provider'         : 'anthropic',
        'anthropic_api_key': '',
        'model'            : 'claude-sonnet-4-6',
        'openai_api_key'   : '',
        'openai_model'     : 'gpt-4o',
        'ollama_url'       : 'http://localhost:11434',
        'ollama_model'     : 'llama3.1:8b',
    },
    'fa_features': {
        'provider'      : 'ollama',
        'ollama_url'    : 'http://localhost:11434',
        'lmstudio_url'  : 'http://localhost:1234',
        'openai_url'    : 'https://api.openai.com',
        'openai_api_key': '',
        'model'         : 'llama3.1:8b',
    },
    'burry_screener': {
        'max_market_cap'   : 300_000_000,
        'max_pe'           : 15.0,
        'max_pb'           : 1.5,
        'max_ps'           : 1.0,
        'max_debt_equity'  : 50.0,
        'min_current_ratio': 1.5,
        'min_roe'          : 0.0,
        'max_shares'       : 100_000_000,
        'markets'          : ['us'],
    },
}


BM_DEFAULTS = {
    'ret_12m_weight': 0.4, 'persist_weight': 0.01, 'mqs_weight': 0.2,
    'trend_bonus': 1.0, 'lead_bonus': 1.0,
    'dd_weight_large': 0.4, 'dd_weight_mid': 0.3, 'dd_weight_small': 0.2, 'dd_weight_etf': 0.3,
    'vol_high': 1.1, 'vol_med': 1.0, 'vol_low': 0.9,
    'rs_trend_strong_up': 1.0, 'rs_trend_up': 0.5, 'rs_trend_flat': 0.0,
    'rs_trend_down': -0.5, 'rs_trend_strong_down': -1.0,
    'rsi_div_bull': 1.0, 'rsi_div_hid_bull': 0.5, 'rsi_div_bear': -1.0, 'rsi_div_hid_bear': -0.5,
    'obv_conv_up': 0.5, 'obv_bull_div': 1.0, 'obv_accum': 0.5,
    'obv_conv_down': -0.5, 'obv_bear_div': -1.0, 'obv_distrib': -0.5,
}
SC_DEFAULTS = {
    'ret_12m_weight': 0.4, 'persist_weight': 0.01, 'mqs_weight': 0.2, 'peer_rs_weight': 0.02,
    'dd_weight_large': 0.4, 'dd_weight_mid': 0.3, 'dd_weight_small': 0.2, 'dd_weight_etf': 0.3,
    'vol_high': 1.1, 'vol_med': 1.0, 'vol_low': 0.9,
    'rs_trend_strong_up': 1.0, 'rs_trend_up': 0.5, 'rs_trend_flat': 0.0,
    'rs_trend_down': -0.5, 'rs_trend_strong_down': -1.0,
    'regime_bonus_leader': 1.0, 'regime_bonus_contender': 0.5,
    'regime_bonus_laggard': 0.0, 'regime_bonus_weak': -0.5,
    'rsi_div_bull': 1.0, 'rsi_div_hid_bull': 0.5, 'rsi_div_bear': -1.0, 'rsi_div_hid_bear': -0.5,
    'obv_conv_up': 0.5, 'obv_bull_div': 1.0, 'obv_accum': 0.5,
    'obv_conv_down': -0.5, 'obv_bear_div': -1.0, 'obv_distrib': -0.5,
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
                if 'fa_features' not in merged:
                    merged['fa_features'] = DEFAULT_SETTINGS.get('fa_features', {}).copy()
                merged['fa_features'].update(saved.get('fa_features', {}))
                if 'burry_screener' not in merged:
                    merged['burry_screener'] = DEFAULT_SETTINGS.get('burry_screener', {}).copy()
                merged['burry_screener'].update(saved.get('burry_screener', {}))
                if 'theme' in saved:
                    merged['theme'] = saved['theme']
                return merged
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

MODELS_FILE = os.path.join(BASE, 'models.json')

def load_models():
    """Load model registry from models.json."""
    if os.path.exists(MODELS_FILE):
        try:
            with open(MODELS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'ollama': [], 'openai': [], 'lmstudio': []}

@st.cache_data(ttl=60, show_spinner=False)
def _list_ollama_models(url):
    """Query a running Ollama instance for installed models (like `ollama list`).
    Returns a models.json-style list, or None if Ollama is unreachable."""
    import requests as _requests
    try:
        r = _requests.get(f"{url.rstrip('/')}/api/tags", timeout=3)
        r.raise_for_status()
        out = []
        for m in r.json().get('models', []):
            caps = m.get('capabilities', [])
            if caps and 'completion' not in caps:
                continue  # skip embedding-only models
            out.append({
                'id'    : m['name'],
                'name'  : m['name'],
                'params': m.get('details', {}).get('parameter_size', ''),
                'notes' : 'installed',
            })
        return sorted(out, key=lambda m: m['id'])
    except Exception:
        return None

def get_model_options(provider, ollama_url=None):
    """Return (ids, display_labels, models) for a provider.
    For ollama the list comes live from the running instance (`ollama list`);
    models.json is only the fallback when Ollama is unreachable."""
    models = None
    if provider == 'ollama':
        models = _list_ollama_models(ollama_url or 'http://localhost:11434')
    if models is None:
        models = load_models().get(provider, [])
    ids = [m['id'] for m in models]
    labels = [f"{m['name']} ({m.get('params', m['id'])})" if m.get('params') else m['name'] for m in models]
    return ids, labels, models

# ── Horizontal top menu ───────────────────────────────────────────────────────
settings    = load_settings()
page_config = settings['pages']

# Nav groups: (group label, icon, [pages within group])
# Single-page groups map straight to their page; multi-page groups show a sub-nav.
NAV_GROUPS = [
    ("Macro",              "globe",                   ["Macro"]),
    ("AU Market",          "flag",                    ["AU Market"]),
    ("US Market",          "flag",                    ["US Market"]),
    ("Commodities",        "hammer",                  ["Commodities"]),
    ("Debt Markets",       "credit-card",             ["Debt Markets"]),
    ("Analysis",           "graph-up",                ["Relative Strength Charts", "Drawdown Analysis",
                                                       "DeMark Signals", "Seasonality", "Fundamental Analysis"]),
    ("Sentiment",          "speedometer2",            ["Sentiment"]),
    ("ETF Income",         "cash-stack",              ["ETF Income"]),
    ("Screeners & Exports","file-earmark-arrow-down", ["Screeners & Exports"]),
    ("Run Scripts",        "play-circle",             ["Run Scripts"]),
    ("Settings",           "gear",                    ["Settings"]),
]

# Kept for the Settings page-visibility toggles
ALL_PAGES = [(g[0], g[1]) for g in NAV_GROUPS]

# Filter to enabled groups — Settings always shown
active_groups = [g for g in NAV_GROUPS
                 if page_config.get(g[0], True) or g[0] == 'Settings']

nav_sel = option_menu(
    menu_title  = None,
    options     = [g[0] for g in active_groups],
    icons       = [g[1] for g in active_groups],
    default_index = 0,
    orientation = "horizontal",
    key         = "main_nav_menu",
    styles      = {
        "container"        : {"padding": "0!important", "background-color": "#2c3e50"},
        "icon"             : {"color": "#b0bec5", "font-size": "13px"},
        "nav-link"         : {"font-size": "12px", "text-align": "center", "margin": "0px",
                              "color": "#ecf0f1", "--hover-color": "#34495e"},
        "nav-link-selected": {"background-color": "#1a3a5c", "color": "white"},
    }
)

# Resolve group to page — multi-page groups get a sub-nav
_sel_group = next((g for g in active_groups if g[0] == nav_sel), active_groups[0])
if len(_sel_group[2]) == 1:
    page = _sel_group[2][0]
else:
    _sub_icons = {
        "Relative Strength Charts": "broadcast",
        "Drawdown Analysis"       : "graph-down",
        "DeMark Signals"          : "activity",
        "Seasonality"             : "calendar3",
        "Fundamental Analysis"    : "bank",
        "Settings"                : "gear",
        "Run Scripts"             : "play-circle",
    }
    page = option_menu(
        menu_title  = None,
        options     = _sel_group[2],
        icons       = [_sub_icons.get(p, "dot") for p in _sel_group[2]],
        default_index = 0,
        orientation = "horizontal",
        key         = f"sub_nav_{_sel_group[0].replace(' ', '_')}",
        styles      = {
            "container"        : {"padding": "0!important", "background-color": "#22303e"},
            "icon"             : {"color": "#8fa3b0", "font-size": "12px"},
            "nav-link"         : {"font-size": "11px", "text-align": "center", "margin": "0px",
                                  "color": "#b0bec5", "--hover-color": "#2c3e50"},
            "nav-link-selected": {"background-color": "#144066", "color": "white"},
        }
    )

# ── Updated timestamp ─────────────────────────────────────────────────────────
st.caption(f"Market Intelligence — {datetime.now().strftime('%d %b %Y %H:%M')}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def format_screener_df(df, cols):
    formatted = df[cols].copy()
    if 'close' in formatted.columns:
        formatted['close'] = pd.to_numeric(
            formatted['close'].astype(str).str.replace(',',''), errors='coerce'
        ).round(3)
    if 'rs_ratio' in formatted.columns:
        formatted['rs_ratio'] = pd.to_numeric(
            formatted['rs_ratio'].astype(str).str.replace(',',''), errors='coerce'
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


def macro_setup_notice(what, launcher_keys, button=None):
    """Explainer shown where a macro/credit report has not been generated yet (fresh clone):
    names the gitignored config file if it is missing, then the button / launcher command."""
    try:
        from macro._config_check import config_problem
        problem = config_problem()
    except Exception:
        problem = None
    parts = [f"**No {what} stored yet.**"]
    if problem:
        parts.append(f"⚠ {problem}. Copy `macro/config_template.py` to `macro/config.py` and put a FRED API key in it "
                     "(free at fred.stlouisfed.org/docs/api/api_key.html). The file is gitignored, so it has to be "
                     "created on each machine.")
    how = f"click **{button}**" if button else "run it"
    parts.append(f"To generate it, {how} (or from the repo folder: `python launcher.py {launcher_keys}`). "
                 "`python launcher.py A` is the full daily run — macro report + market data — for a scheduled task.")
    st.info("\n\n".join(parts))


# ── marketdb: SQLite data layer (replaces the CSV result trees under stocks/results) ──
import sys as _sys
if BASE not in _sys.path:
    _sys.path.insert(0, BASE)
from marketdb import db as mdb, results as MR, universe as MU, prices as MP


def marketdb_ready():
    """Show a setup banner (with a Run-bootstrap button) when the store has no data. Returns
    True when the store is usable."""
    try:
        if not mdb.is_empty():
            return True
    except Exception as e:
        st.error(f"marketdb unavailable: {e}")
        return False
    st.warning("**marketdb has no data yet** — the database is not in git and is built once per machine. "
               "Run `python -m marketdb.bootstrap` from a terminal (≈15 min: universe, 3 years of prices, "
               "all studies), or copy `data/market.db` from a machine that already has it, then reload.")
    if st.button("▶ Run bootstrap now (≈15 min, page will wait)", key=f"bootstrap_{page}"):
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        with st.spinner("Bootstrapping marketdb — seeding universe, back-filling prices, running studies…"):
            result = subprocess.run([PYTHON, '-m', 'marketdb.bootstrap'], cwd=BASE, env=env,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            st.success("✓ Bootstrap complete — reloading")
            st.rerun()
        else:
            st.error("✗ Bootstrap failed: " + (result.stderr or result.stdout)[-2000:])
    return False


def run_marketdb(*args, label=None, module='marketdb.run_daily'):
    """Run `python -m <module> <args>` (default marketdb.run_daily) from BASE — same UX as run_script()."""
    if not marketdb_ready():
        return False
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    with st.spinner(label or f"Running {module} {' '.join(args)}..."):
        result = subprocess.run([PYTHON, '-m', module, *args], cwd=BASE, env=env,
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode == 0:
        st.success("✓ Completed successfully")
        with st.expander("Run log"):
            st.code(result.stdout[-8000:])
    else:
        st.error(f"✗ Failed\n{(result.stderr or result.stdout)[-1500:]}")
    return result.returncode == 0


def db_age(kind, universe=None):
    """'3h 12m ago' for the latest successful marketdb run of a study (or 'fetch')."""
    try:
        sql = "SELECT MAX(finished) FROM runs WHERE kind=? AND status IN ('ok','partial')"
        params = [kind]
        if universe:
            sql += " AND universe=?"
            params.append(universe)
        ts = mdb.scalar(sql, params)
        if not ts:
            return "not run yet"
        diff = datetime.now() - datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        hours = int(diff.total_seconds() // 3600)
        mins = int((diff.total_seconds() % 3600) // 60)
        return f"{hours}h {mins}m ago" if hours else f"{mins}m ago"
    except Exception:
        return "unknown"


def db_universe_members(universe, con=None):
    """Member frame for a universe key (ticker, name, sector, industry, cap_band, benchmark...)."""
    try:
        return MU.members(universe, con)
    except Exception as e:
        st.error(f"marketdb: {e}")
        return None


UNIVERSE_LABELS = {k: v['name'] for k, v in MU.config()['universes'].items()}


def store_close(ticker, start, max_lag_days=400):
    """Adjusted-close Series from the price store if it holds history back to ~`start`
    (deep-history tickers such as ^GSPC, ^AORD, sector ETFs); otherwise None so the
    caller falls back to yfinance. Naive DatetimeIndex."""
    try:
        first = mdb.scalar("SELECT first_date FROM fetch_log WHERE ticker=? AND status='ok'", (ticker,))
        if not first:
            return None
        if (pd.Timestamp(first) - pd.Timestamp(start)).days > max_lag_days:
            return None
        m = MP.get_prices([ticker], start, None)
        c = m[ticker].dropna() if ticker in m.columns else None
        return c if c is not None and len(c) else None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def _pres_cycle_stats():
    try:
        import yfinance as _yf
        import numpy as _np2
        from datetime import datetime as _dt
        _spx = store_close('^GSPC', '1927-01-01')
        if _spx is None:
            _spx = _yf.download('^GSPC', start='1927-01-01', auto_adjust=True, progress=False)['Close'].squeeze().dropna()
            _spx.index = pd.to_datetime(_spx.index).tz_localize(None)
        if len(_spx) < 1000:
            return {}          # partial/empty download — show nothing rather than zeros
        _PRESIDENTS = [
            ("Hoover",1929,1933,"R"),("Roosevelt",1933,1945,"D"),("Truman",1945,1953,"D"),
            ("Eisenhower",1953,1961,"R"),("Kennedy",1961,1963,"D"),("Johnson",1963,1969,"D"),
            ("Nixon",1969,1974,"R"),("Ford",1974,1977,"R"),("Carter",1977,1981,"D"),
            ("Reagan",1981,1989,"R"),("Bush Sr",1989,1993,"R"),("Clinton",1993,2001,"D"),
            ("Bush Jr",2001,2009,"R"),("Obama",2009,2017,"D"),("Trump",2017,2021,"R"),
            ("Biden",2021,2025,"D"),("Trump",2025,2029,"R"),
        ]
        _now   = _dt.now()
        _curr  = next(((n,s,e,p) for n,s,e,p in _PRESIDENTS if s<=_now.year<e), None)
        if not _curr: return {}
        _nm,_s,_e,_p = _curr
        _yit  = _now.year - _s + 1
        _ytdd = _spx[_spx.index.year==_now.year]
        _ytdr = round((_ytdd.iloc[-1]/_ytdd.iloc[0]-1)*100,2) if len(_ytdd)>1 else 0
        _yrets,_ydds,_mrets = [],[],[]
        for _hn,_hs,_he,_hp in _PRESIDENTS[:-1]:
            _hy = _hs+(_yit-1)
            if _hy>=_he: continue
            _yd = _spx[_spx.index.year==_hy]
            if len(_yd)<20: continue
            _yrets.append(round((_yd.iloc[-1]/_yd.iloc[0]-1)*100,2))
            _ydds.append(round(float(((_yd-_yd.expanding().max())/_yd.expanding().max()*100).min()),2))
            _md = _yd[_yd.index.month==_now.month]
            if len(_md)>=2: _mrets.append(round((_md.iloc[-1]/_md.iloc[0]-1)*100,2))
        _n = len(_yrets)
        return {
            'president':_nm,'party':_p,'term_start':_s,'yr_in_term':_yit,'ytd_ret':_ytdr,
            'hist_avg':round(_np2.mean(_yrets),2) if _yrets else 0,
            'hist_med':round(_np2.median(_yrets),2) if _yrets else 0,
            'hist_pos':round(sum(r>0 for r in _yrets)/_n*100,1) if _n else 0,
            'avg_dd':round(_np2.mean(_ydds),2) if _ydds else 0,
            'worst_dd':round(min(_ydds),2) if _ydds else 0,
            'n_dds':len([d for d in _ydds if d<-10]),
            'mo_avg':round(_np2.mean(_mrets),2) if _mrets else 0,
            'mo_pos':round(sum(r>0 for r in _mrets)/len(_mrets)*100,1) if _mrets else 0,
            'curr_mo':_now.strftime('%B'),'n_yrs':_n,
        }
    except: return {}


def db_memo(key, ttl_hours, fn):
    """Persistent memo for slow external lookups (FRED etc.): reuse the stored result while it is
    younger than ttl_hours, otherwise call fn() and store it. Survives Streamlit restarts, unlike
    st.cache_data. Empty / all-None results are returned but never stored, so failures retry."""
    try:
        row = mdb.connect().execute("SELECT payload, created FROM reports WHERE kind='memo' AND date=?", (key,)).fetchone()
        if row and row[0] and (datetime.now() - datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S')) < timedelta(hours=ttl_hours):
            return json.loads(row[0])
    except Exception:
        pass
    val = fn()
    empty = val is None or val == {} or (isinstance(val, (tuple, list)) and all(v is None for v in val))
    if not empty:
        try:
            MR.save_report('memo', key, payload=val)
        except Exception:
            pass
    return val


def store_ohlc(ticker, start):
    """Unadjusted OHLC frame from the store when its history reaches back to `start`."""
    try:
        first = mdb.scalar("SELECT first_date FROM fetch_log WHERE ticker=? AND status='ok'", (ticker,))
        if not first or (pd.Timestamp(first) - pd.Timestamp(start)).days > 400:
            return None
        df = MP.get_ohlc(ticker, start, None)
        return df[['Open', 'High', 'Low', 'Close']].dropna() if df is not None and len(df) else None
    except Exception:
        return None

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

DIVERGENCE_COLOURS = {
    # RSI divergence (pivot based)          OBV vs price (21-bar direction)
    'BULL'     : 'color: #00cc44; font-weight: 600',   'BULL_DIV' : 'color: #00cc44; font-weight: 600',
    'HID_BULL' : 'color: #00cc44',                     'ACCUM'    : 'color: #00cc44',
    'CONV_UP'  : 'color: #7fbf7f',
    'BEAR'     : 'color: #ff4444; font-weight: 600',   'BEAR_DIV' : 'color: #ff4444; font-weight: 600',
    'HID_BEAR' : 'color: #ff4444',                     'DISTRIB'  : 'color: #ff4444',
    'CONV_DOWN': 'color: #c97a7a',
}

def colour_divergence(val):
    return DIVERGENCE_COLOURS.get(str(val), 'color: #777777')

DIVERGENCE_COLUMN_CONFIG = {
    # explicit format needed: with a Styler, unformatted number columns display
    # pandas' 6-decimal default instead of the underlying rounded value
    'close': st.column_config.NumberColumn('close', format='%.3f'),
    'rsi_div': st.column_config.TextColumn('rsi_div', help=(
        "RSI(14) divergence at the last two RSI pivots (5 bars each side, newer pivot confirmed "
        "within 20 bars). BULL: price lower low, RSI higher low. BEAR: price higher high, RSI lower high. "
        "HID_BULL / HID_BEAR: hidden (trend-continuation) divergence. Void once price closes through the pivot.")),
    'obv_div': st.column_config.TextColumn('obv_div', help=(
        "Price direction vs On-Balance-Volume direction over the last 21 bars (least-squares slopes). "
        "CONV_UP / CONV_DOWN: volume confirms the move. BEAR_DIV: price up, OBV down. "
        "BULL_DIV: price down, OBV up. ACCUM / DISTRIB: price flat (<2%) while OBV rises / falls.")),
}

def style_df(df, regime_col=None, delta_col=None):
    styler = df.style
    if regime_col and regime_col in df.columns:
        styler = styler.map(colour_regime, subset=[regime_col])
    if delta_col and delta_col in df.columns:
        styler = styler.map(colour_delta, subset=[delta_col])
    div_cols = [c for c in ('rsi_div', 'obv_div') if c in df.columns]
    if div_cols:
        styler = styler.map(colour_divergence, subset=div_cols)
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

# ── Breadth overview chart ────────────────────────────────────────────────────
SECTOR_LINE_COLOURS = [
    '#4da3ff', '#ffd166', '#2dc653', '#e63946', '#c77dff', '#00d4c8',
    '#ff8c42', '#a0d911', '#ff5cad', '#7aa2ff', '#f4a261', '#5ce1e6',
    '#b5179e', '#95d5b2', '#ffb703', '#9d4edd', '#48cae4', '#e07a5f',
    '#8ac926', '#ef476f',
]

@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_index_ohlc(ticker, start):
    """OHLC for a reference index — price store first, yfinance fallback (cached 30 min)."""
    _st = store_ohlc(ticker, start)
    if _st is not None:
        return _st
    try:
        import yfinance as _yf
        df = _yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if df is None or len(df) == 0:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[['Open', 'High', 'Low', 'Close']].dropna()
    except Exception:
        return None


def render_breadth_chart(history, prefix='sec', index_ticker='^AORD',
                         index_label='XAO — All Ordinaries', key='au'):
    """Stacked breadth panels — market %>MA, reference index, per-sector %>20/50/200 MA."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if history is None or len(history) == 0:
        return

    df = history.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date')
    if len(df) == 0:
        return

    # Drop rows left behind by a partial data fetch — a run that only saw a
    # fraction of the universe plots as a breadth collapse that never happened.
    if 'total' in df.columns:
        _tot = pd.to_numeric(df['total'], errors='coerce')
        _med = _tot.median()
        if _med and _med > 0:
            df = df[_tot >= _med * 0.5]

    # Sector keys that carry all three SMA participation columns
    sec_keys = []
    for c in df.columns:
        if c.startswith(f'{prefix}_') and c.endswith('_total'):
            k = c[len(prefix) + 1:-len('_total')]
            if k in ('nan', 'index', 'miscellaneous'):
                continue
            if all(f'{prefix}_{k}_{s}' in df.columns for s in ('above20', 'above50', 'above200')):
                sec_keys.append(k)
    if not sec_keys:
        return

    def _size(k):
        try:
            return float(pd.to_numeric(df[f'{prefix}_{k}_total'], errors='coerce').ffill().iloc[-1])
        except Exception:
            return 0.0
    sec_keys.sort(key=_size, reverse=True)

    labels   = {k: k.replace('_', ' ').replace('-', ' ').title() for k in sec_keys}
    defaults = [labels[k] for k in sec_keys[:12]]

    _c1, _c2, _c3 = st.columns([900, 10000, 900])
    with _c2:
        ctl1, ctl2 = st.columns([1, 4])
        with ctl1:
            rng = st.selectbox('Range', ['3M', '6M', '1Y', 'All'], index=0,
                               key=f'{key}_brchart_range')
        with ctl2:
            picked = st.multiselect('Sectors', [labels[k] for k in sec_keys],
                                    default=defaults, key=f'{key}_brchart_secs')

    sel_keys = [k for k in sec_keys if labels[k] in picked]

    days = {'3M': 92, '6M': 183, '1Y': 365}.get(rng)
    if days:
        df = df[df['date'] >= df['date'].max() - pd.Timedelta(days=days)]
    if len(df) < 2:
        with _c2:
            st.info("Not enough breadth history for the selected range")
        return

    start_str = (df['date'].min() - pd.Timedelta(days=5)).strftime('%Y-%m-%d')
    idx = _fetch_index_ohlc(index_ticker, start_str)

    def pct_series(above_col, total_col):
        num = pd.to_numeric(df[above_col], errors='coerce')
        den = pd.to_numeric(df[total_col], errors='coerce')
        return (num / den.where(den > 0) * 100).round(1)

    fig = make_subplots(
        rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.025,
        row_heights=[0.16, 0.28, 0.1867, 0.1867, 0.1867],
        subplot_titles=('% of Stocks > MA — whole market', index_label,
                        'Sector Stocks > 20MA', 'Sector Stocks > 50MA',
                        'Sector Stocks > 200MA'),
    )

    x = df['date']

    # Row 1 — market-wide participation
    for col, name, colour in (('above_20', '20MA', '#4da3ff'),
                              ('above_50', '50MA', '#2dc653'),
                              ('above_200', '200MA', '#e63946')):
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=x, y=pct_series(col, 'total'), mode='lines', name=name,
                legendgroup='market', line=dict(color=colour, width=1.6),
            ), row=1, col=1)
    for lvl in (20, 40, 60, 80):
        fig.add_hline(y=lvl, line_dash='dot', line_width=1,
                      line_color='rgba(255,255,255,0.18)', row=1, col=1)

    # Row 2 — reference index
    if idx is not None and len(idx) > 0:
        fig.add_trace(go.Candlestick(
            x=idx.index, open=idx['Open'], high=idx['High'],
            low=idx['Low'], close=idx['Close'], name=index_ticker,
            increasing_line_color='#2dc653', decreasing_line_color='#e63946',
            showlegend=False,
        ), row=2, col=1)
    else:
        fig.add_annotation(text=f"{index_ticker} price unavailable",
                           xref='x domain', yref='y2 domain', x=0.5, y=0.5,
                           showarrow=False, font=dict(color='#888'), row=2, col=1)

    # Rows 3-5 — per-sector participation
    colour_of = {k: SECTOR_LINE_COLOURS[i % len(SECTOR_LINE_COLOURS)]
                 for i, k in enumerate(sel_keys)}

    def sector_hover(suffix):
        """Hover rows for each date, ranked high-to-low so they match the line order."""
        vals = pd.DataFrame(
            {k: pct_series(f'{prefix}_{k}_{suffix}', f'{prefix}_{k}_total') for k in sel_keys}
        )
        out = []
        for _, r in vals.iterrows():
            items = sorted([(k, v) for k, v in r.items() if pd.notna(v)],
                           key=lambda kv: kv[1], reverse=True)
            out.append('<br>'.join(
                f'<span style="color:{colour_of[k]}">▬</span> {labels[k]} <b>{v:.1f}%</b>'
                for k, v in items
            ))
        return out

    for row, suffix in ((3, 'above20'), (4, 'above50'), (5, 'above200')):
        for k in sel_keys:
            fig.add_trace(go.Scatter(
                x=x, y=pct_series(f'{prefix}_{k}_{suffix}', f'{prefix}_{k}_total'),
                mode='lines', name=labels[k], legendgroup=labels[k],
                showlegend=(row == 3), line=dict(color=colour_of[k], width=1.3),
                hoverinfo='skip',
            ), row=row, col=1)
        # Invisible anchor carries the ranked hover box for the whole panel
        if sel_keys:
            fig.add_trace(go.Scatter(
                x=x, y=[50] * len(df), mode='lines', name='',
                line=dict(color='rgba(0,0,0,0)', width=0), showlegend=False,
                hovertext=sector_hover(suffix), hovertemplate='%{hovertext}<extra></extra>',
            ), row=row, col=1)
        for lvl, dash_colour in ((20, 'rgba(230,57,70,0.35)'),
                                 (50, 'rgba(255,255,255,0.18)'),
                                 (70, 'rgba(45,198,83,0.35)')):
            fig.add_hline(y=lvl, line_dash='dot', line_width=1,
                          line_color=dash_colour, row=row, col=1)

    theme = get_chart_theme()
    _light = _get_theme_mode() == 'light'
    fig.update_layout(
        height        = 1250,
        hovermode     = 'x unified',
        plot_bgcolor  = theme['plot_bgcolor'],
        paper_bgcolor = theme['paper_bgcolor'],
        font          = dict(color=theme['font_color'], size=11),
        hoverlabel    = dict(align='left',
                             bgcolor='rgba(255,255,255,0.95)' if _light else 'rgba(18,18,28,0.92)',
                             bordercolor='rgba(0,0,0,0.2)' if _light else 'rgba(255,255,255,0.2)',
                             font=dict(size=11, color='#1a1a1a' if _light else '#eaeaea')),
        legend        = dict(font=dict(size=10), groupclick='togglegroup',
                             yanchor='top', y=1, xanchor='left', x=1.005),
        margin        = dict(l=50, r=170, t=40, b=30),
    )
    fig.update_xaxes(gridcolor=theme['gridcolor'], showspikes=True,
                     spikemode='across', spikethickness=1,
                     spikecolor='rgba(255,255,255,0.35)', spikedash='dot',
                     rangebreaks=[dict(bounds=['sat', 'mon'])])
    fig.update_xaxes(rangeslider_visible=False, row=2, col=1)
    fig.update_yaxes(gridcolor=theme['gridcolor'])
    for row in (1, 3, 4, 5):
        fig.update_yaxes(range=[0, 100], ticksuffix='%', row=row, col=1)
    for ann in fig.layout.annotations:
        ann.font.size = 12

    with _c2:
        st.plotly_chart(fig, width='stretch', key=f'{key}_brchart')
        st.caption(
            f"Sector lines = % of that sector's stocks above the 20/50/200 SMA. "
            f"Index panel: {index_ticker} daily candles. Click a sector in the legend "
            f"to toggle it across all three panels."
        )


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
                       if c not in ('nan', 'index')]

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
@st.cache_data(ttl=1800, show_spinner="Fetching RRG price data...")
def _fetch_custom_rrg(bm, tickers, tail, smooth):
    import yfinance as _yf2
    _all   = list(set([bm] + list(tickers)))
    _days  = max(tail * 4, 120)
    _end   = pd.Timestamp.today()
    _start = _end - pd.Timedelta(days=_days)
    try:
        _raw = _yf2.download(_all, start=_start, end=_end,
                              auto_adjust=True, progress=False)['Close']
        if isinstance(_raw, pd.Series): _raw = _raw.to_frame()
        return _raw.dropna(how='all')
    except: return None

@st.cache_data(ttl=3600)
def _fetch_stk(ticker, _v=3):
    _st = store_close(ticker, "1990-01-01")
    if _st is not None:
        return _st
    import yfinance as _yf
    df = _yf.download(ticker, start="1990-01-01", auto_adjust=True, progress=False)
    if df is None or df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df = df['Close']
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]
    else:
        df = df['Close']
    c = df.squeeze().dropna()
    if isinstance(c, pd.DataFrame): c = c.iloc[:, 0]
    c.index = pd.to_datetime(c.index).tz_localize(None)
    return c

@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_sea(ticker, _v=5):
    _st = store_close(ticker, "1928-01-01", max_lag_days=365 * 80)
    if _st is not None:
        return _st
    import yfinance as _yf
    try:
        _tk = _yf.Ticker(ticker)
        df  = _tk.history(start="1928-01-01", auto_adjust=True)
        if df is None or df.empty: return None
        close = df['Close'].squeeze().dropna()
        if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
        close.index = pd.to_datetime(close.index).tz_localize(None)
        return close
    except: return None

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
    _macro_txt, _macro_payload, _macro_date = MR.load_report('macro_report')
    report_file = _macro_date          # 'YYYY-MM-DD' of the latest stored report (None if none)
    if not report_file:
        macro_setup_notice("macro report (regime, alerts, cycle positioning)", "1", button="📊 Run Macro Report")

    def parse_macro_report(path):
        """Extract key values from the latest macro report (text in marketdb reports)"""
        if not path or not _macro_txt:
            return {}
        text = _macro_txt

        import re
        d = {}

        # ── Load companion snapshot for richer data ─────────────────────────
        # The report is text-formatted; the snapshot has full numeric data
        _, _snap, _ = MR.load_report('macro_snapshot', 'latest')
        if _snap:
            try:
                # Merge useful numeric fields directly
                for _k in ('margin_chg_1m', 'margin_chg_3m', 'margin_peak', 'margin_from_peak',
                           'margin_acceleration', 'cu_gold_ratio', 'cu_gold_chg_5d',
                           'cu_gold_chg_21d', 'cu_gold_chg_63d', 'gold_spx_ratio',
                           'gold_copper_ratio', 'cape_manual', 'pres_cycle_ret',
                           'pres_cycle_dd', 'pres_cycle_dd_now', 'pres_cycle_year',
                           'consumer_sentiment', 'pmi_manual', 'unemployment',
                           'vix', 'vvix', 'vix_vvix'):
                    if _k in _snap and _snap[_k] is not None:
                        d[_k] = _snap[_k]
                # Map JSON keys → dashboard keys where names differ
                if 'cape_manual' in _snap: d['cape'] = _snap['cape_manual']
                if 'pmi_manual'  in _snap: d['pmi']  = _snap['pmi_manual']
                if 'consumer_sentiment' in _snap: d['consumer_sent'] = _snap['consumer_sentiment']
            except Exception:
                pass

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
            @st.cache_data(ttl=300)
            def _fetch_live(_t): return yf.download(list(_t), period='10d', auto_adjust=True, progress=False)
            raw = _fetch_live(tuple(tickers))
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
                        width='stretch', hide_index=True
                    )

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — REGIME & ALERTS
    # ══════════════════════════════════════════════════════════════════════════
    st.subheader("⚠ Regime, Alerts & Indicators")

    if report_file:
        report_date = report_file.replace('-', '')
        _mc = MR.report_created('macro_report', report_file)
        st.caption(f"From macro report: {report_date} — saved {_mc or 'n/a'}")

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
        @st.cache_data(ttl=3600)
        def _fetch_hgx():
            _st = store_close('^HGX', (datetime.today() - timedelta(days=5 * 365)).strftime('%Y-%m-%d'))
            if _st is not None:
                return _st.to_frame('Close')
            return yf.Ticker('^HGX').history(period='5y')
        _hgx_hist = _fetch_hgx()
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
    _gdp_val,_gdp_date,_gdp_next=db_memo('fred_gdp', 12, _fetch_gdp_fred)
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
    _cpi_mom,_cpi_yoy,_cpi_date,_cpi_next,_cpi_idx=db_memo('fred_cpi', 12, _fetch_cpi_fred)
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

    _rec_sigs=db_memo('fred_recession_signals', 12, _fetch_recession_signals)

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
         'check':lambda:(macro.get('margin_from_peak') is not None and macro.get('margin_from_peak') > -2.0),
         'value_fn':lambda:f"From peak: {macro.get('margin_from_peak',0):+.2f}% (extreme >-2%) | 3m: {macro.get('margin_chg_3m',0):+.2f}% | Accel: {macro.get('margin_acceleration',0):+.3f}%",
         'detail':'Margin debt within 2% of all-time peak — leveraged speculation extreme'},
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

        @st.cache_data(ttl=3600, show_spinner=False)
        def _fetch_econ_series():
            """Latest FRED observations + dates for the regime table."""
            try:
                import pandas_datareader.data as _web
                from datetime import datetime as _edt
                out = {}
                for key, sid in (('unemp', 'UNRATE'), ('nfp', 'PAYEMS'), ('sent', 'UMCSENT')):
                    try:
                        s = _web.DataReader(sid, 'fred', _edt(2023, 1, 1), _edt.today()).dropna().iloc[:, 0]
                        out[key] = {
                            'last'  : float(s.iloc[-1]),
                            'prev'  : float(s.iloc[-2]) if len(s) > 1 else None,
                            'trough': float(s.tail(12).min()),
                            'chg'   : float(s.iloc[-1] - s.iloc[-2]) if len(s) > 1 else None,
                            'date'  : s.index[-1].strftime('%b %Y'),
                        }
                    except Exception:
                        pass
                return out
            except Exception:
                return {}
        _econ = db_memo('fred_econ_series', 6, _fetch_econ_series)

        def indicator_row(label, value, signal_text, good=True, neutral=False):
            colour = '#f77f00' if neutral else '#2dc653' if good else '#e63946'
            icon   = '→' if neutral else '✓' if good else '⚠'
            _ec_rows.append({'Indicator': label, 'Value': str(value), 'Signal': f"{icon} {signal_text}", '_colour': colour})
        _ec_rows = []

        # Unemployment — rising is the warning, not the level
        _ue = _econ.get('unemp', {})
        _ue_val  = _ue.get('last', unemp)
        _ue_date = f" ({_ue['date']})" if _ue.get('date') else ''
        if _ue_val:
            _ue_rising = ((_ue.get('chg') is not None and _ue['chg'] > 0) or
                          (_ue.get('trough') is not None and _ue_val >= _ue['trough'] + 0.3))
            if _ue_rising:
                _ue_from_trough = (f" (+{_ue_val - _ue['trough']:.1f}pp from trough {_ue['trough']:.1f}%)"
                                   if _ue.get('trough') is not None and _ue_val > _ue['trough'] else '')
                _ue_sig = f"RISING{_ue_from_trough} — labour market softening"
            else:
                _ue_sig = macro.get('unemp_label', '') or 'Stable'
            indicator_row("Unemployment", f"{_ue_val}%{_ue_date}", _ue_sig, good=not _ue_rising)

        if pmi:   indicator_row("PMI Mfg", f"{pmi} (manual entry)",
            macro.get('pmi_label',''), good=pmi >= 50)

        # NFP — show monthly change (the headline number) + date
        _nf = _econ.get('nfp', {})
        if _nf.get('last'):
            _nf_chg  = _nf.get('chg')
            _nf_val  = f"{_nf['last']:,.0f}K ({_nf['date']})"
            _nf_sig  = (f"{_nf_chg:+,.0f}K MoM" if _nf_chg is not None else '')
            indicator_row("Non-Farm Payrolls", _nf_val, _nf_sig,
                          good=(_nf_chg or 0) > 0, neutral=_nf_chg is None)
        elif nfp:
            indicator_row("Non-Farm Payrolls", nfp, "", good=True)

        _se = _econ.get('sent', {})
        _se_val  = _se.get('last', sent)
        _se_date = f" ({_se['date']})" if _se.get('date') else ''
        if _se_val: indicator_row("Consumer Sentiment", f"{_se_val}{_se_date}",
            macro.get('sent_label',''), good=_se_val > 70)

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

        # Volatility regime (VIX)
        _vix = macro.get('vix')
        _vvix = macro.get('vvix')
        if _vix is not None:
            if _vix < 15:
                _vix_st = '✓ COMPLACENT — risk on environment'; _vix_c = '#2dc653'
            elif _vix < 20:
                _vix_st = '✓ NORMAL — healthy volatility'; _vix_c = '#2dc653'
            elif _vix < 30:
                _vix_st = '→ ELEVATED — caution warranted'; _vix_c = '#f77f00'
            else:
                _vix_st = '⚠ STRESSED — risk off environment'; _vix_c = '#e63946'
            _vix_val = f"{_vix:.2f}" + (f" | VVIX {_vvix:.1f}" if _vvix is not None else "")
            _ec_rows.append({'Indicator':'VIX/Volatility','Value':_vix_val,'Signal':_vix_st,'_colour':_vix_c})

        if _ec_rows:
            import pandas as _pd3
            _ec_df = _pd3.DataFrame(_ec_rows)[['Indicator','Value','Signal']]
            def _ec_style(row):
                return ['','',f"color:{_ec_rows[row.name]['_colour']}"]
            st.dataframe(_ec_df.style.apply(_ec_style,axis=1),width='stretch',hide_index=True)

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
            st.dataframe(_cc_df.style.apply(_cc_style,axis=1),width='stretch',hide_index=True)

    with col3:
        st.markdown("**Valuation**")
        # Margin Debt — from JSON snapshot (% off all-time peak is the key extreme signal)
        _mfp = macro.get('margin_from_peak')
        _m3m = macro.get('margin_chg_3m')
        _m1m = macro.get('margin_chg_1m')
        _macc = macro.get('margin_acceleration')

        vals = []
        # Margin Debt vs Peak — extreme when within 2% of all-time high
        if _mfp is not None:
            extreme = _mfp > -2.0  # within 2% of peak = extreme
            vals.append(("Margin Debt vs Peak", f"{_mfp:+.2f}%", extreme,
                         "EXTREME — within 2% of all-time high" if extreme else "Off peak — normal range"))
        # 3-month margin debt change
        if _m3m is not None:
            extreme = _m3m > 5.0  # >5% in 3 months = leverage building
            vals.append(("Margin Debt 3m Δ", f"{_m3m:+.2f}%", extreme,
                         "Leverage building rapidly" if extreme else "Stable / deleveraging"))
        # Margin acceleration
        if _macc is not None:
            extreme = _macc > 0.5
            vals.append(("Margin Accel %", f"{_macc:+.3f}%", extreme,
                         "Accelerating — leverage building" if extreme else "Decelerating / stable"))
        # Buffett Indicator (only if parsed)
        _buf = macro.get('buffett')
        if _buf is not None:
            extreme = _buf > 150
            vals.append(("Buffett Ind %", f"{_buf}", extreme,
                         "Extreme above 150%" if extreme else "Normal range"))
        # Shiller CAPE
        _cape = macro.get('cape')
        if _cape is not None:
            extreme = _cape > 30
            vals.append(("Shiller CAPE", f"{_cape}", extreme,
                         "Extreme above 30 — bubble territory" if extreme else "Normal range"))

        _val_rows = []
        for lbl, val_str, extreme, signal_text in vals:
            colour = '#e63946' if extreme else '#2dc653'
            icon = '⚠' if extreme else '✓'
            _val_rows.append({'Indicator':lbl,'Value':val_str,'Signal':f"{icon} {signal_text}", '_c':colour})
        if _val_rows:
            import pandas as _pd5
            _val_df = _pd5.DataFrame(_val_rows)[['Indicator','Value','Signal']]
            def _val_style(row): return ['','',f"color:{_val_rows[row.name]['_c']}"]
            st.dataframe(_val_df.style.apply(_val_style,axis=1),width='stretch',hide_index=True)

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
            st.dataframe(_cr_df.style.apply(_cr_style,axis=1),width='stretch',hide_index=True)

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
    _cyc1, _cyc2 = st.columns(2)

    with _cyc1:
        _CYCLE_INFO = {
            'RECESSION'         : ('Healthcare, Utilities, Finance',     'Value / Size / Yield',      'PMI < 45',  'Defensive'),
            'EARLY RECOVERY'    : ('Finance, Technology, Cyclicals',     'Value / Size / Yield',      'PMI 45-50', 'Defensive > Growth'),
            'EARLY EXPANSION'   : ('Technology, Industrials, Materials', 'Momentum / Size / Value',   'PMI > 50',  'Growth'),
            'MID EXPANSION'     : ('Basic Materials, Energy, Staples',   'Momentum / Size / Value',   'PMI > 55',  'Cyclical'),
            'LATE EXPANSION'    : ('Energy, Staples, Healthcare',        'Momentum / Size / Value',   'PMI 50-55', 'Growth > Value'),
            'LATE CYCLE'        : ('Energy, Staples, Healthcare',        'Low vol / Quality / Value', 'PMI < 50',  'Value'),
            'EARLY CONTRACTION' : ('Healthcare, Utilities, Finance',     'Low vol / Quality / Value', 'PMI < 45',  'Defensive'),
        }
        _BIZ_COLOURS = {
            'EARLY EXPANSION':'#2dc653','MID EXPANSION':'#80b918','LATE EXPANSION':'#f77f00',
            'LATE CYCLE':'#e63946','EARLY CONTRACTION':'#c1121f','RECESSION':'#9b0000',
            'EARLY RECOVERY':'#2dc653',
        }
        # vocabulary = macro/cycle_classifier.classify_us_business_cycle (phase names are matched by substring)
        _PHASE_ORDER = ['RECESSION','EARLY RECOVERY','EARLY EXPANSION',
                        'MID EXPANSION','LATE EXPANSION','LATE CYCLE','EARLY CONTRACTION']
        biz        = macro.get('biz_cycle', '')
        score      = macro.get('biz_score', 0)
        biz_upper  = biz.upper()
        biz_colour = next((v for k,v in _BIZ_COLOURS.items() if k in biz_upper), '#888')
        phase_idx  = next((i for i,k in enumerate(_PHASE_ORDER) if k in biz_upper), -1)
        info       = next((v for k,v in _CYCLE_INFO.items() if k in biz_upper), ('—','—','—','—'))

        if biz:
            import math as _math
            _n = len(_PHASE_ORDER)
            _labels_short = ['Recession','Early Recov','Early Exp','Mid Exp','Late Exp','Late Cycle','Contraction']
            _svg_parts = []
            _pts = []
            for _i in range(_n):
                _a = _math.pi + (_i/(_n-1)) * _math.pi * 1.6
                _x = 50 + 40*_math.cos(_a)
                _y = 52 - 30*_math.sin(_a)
                _pts.append((_x,_y))
            _path = 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x,y in _pts)
            _svg_parts.append(f'<path d="{_path}" stroke="#555" stroke-width="1" fill="none" opacity="0.3"/>')
            for _i,(_x,_y) in enumerate(_pts):
                _is_curr = _i == phase_idx
                _c = biz_colour if _is_curr else '#555'
                _r = 9 if _is_curr else 4
                _op = '1' if _is_curr else '0.4'
                _lbl = _labels_short[_i]
                _svg_parts.append(f'<circle cx="{_x:.1f}" cy="{_y:.1f}" r="{_r}" fill="{_c}" opacity="{_op}"/>')
                _svg_parts.append(f'<text x="{_x:.1f}" y="{_y+14:.1f}" text-anchor="middle" font-size="5" fill="{_c}" opacity="{_op}">{_lbl}</text>')
            _wave_svg = '<svg viewBox="0 0 100 80" style="width:100%;max-height:100px">' + ''.join(_svg_parts) + '</svg>'
            st.markdown(
                f"<div style='border-left:4px solid {biz_colour};padding:12px 16px;border-radius:0 8px 8px 0'>"
                f"<div style='font-size:11px;color:#888;font-weight:600'>BUSINESS CYCLE</div>"
                f"<div style='color:{biz_colour};font-size:18px;font-weight:bold;margin:4px 0'>{biz} "
                f"<span style='font-size:11px;color:#888'>score: {score}/10</span></div>"
                f"{_wave_svg}"
                f"<div style='font-size:11px;margin-top:6px'>"
                f"<b>Sectors:</b> {info[0]} &nbsp;|&nbsp; <b>Factor:</b> {info[1]} &nbsp;|&nbsp; "
                f"<b>ISM:</b> {info[2]} &nbsp;|&nbsp; <b>Style:</b> {info[3]}"
                f"</div></div>",
                unsafe_allow_html=True
            )
        else:
            st.info("Business-cycle phase comes from the macro report — see the notice at the top of the page.")

    with _cyc2:

        _ps = _pres_cycle_stats()
        if not _ps:
            _pres_cycle_stats.clear()      # don't keep a failed fetch for the cache TTL
            st.caption("Presidential-cycle stats unavailable (index history not loaded) — reload to retry")
        if _ps:
            _pc_col  = '#4C8BF5' if _ps.get('party')=='D' else '#E8534A'
            _ytd     = _ps.get('ytd_ret', 0)
            _ahead   = _ytd - _ps.get('hist_avg', 0)
            _ytd_col = '#2dc653' if _ytd >= 0 else '#e63946'
            _ahd_col = '#2dc653' if _ahead >= 0 else '#e63946'
            st.markdown(
                f"<div style='border-left:4px solid {_pc_col};padding:12px 16px;border-radius:0 8px 8px 0'>"
                f"<div style='font-size:11px;color:#888;font-weight:600'>PRESIDENTIAL CYCLE</div>"
                f"<div style='color:{_pc_col};font-size:18px;font-weight:bold;margin:4px 0'>"
                f"{_ps['president']} Year {_ps['yr_in_term']} "
                f"<span style='font-size:11px;color:#888'>({_ps['party']}, since {_ps['term_start']})</span></div>"
                f"<div style='display:flex;gap:20px;flex-wrap:wrap;font-size:12px;margin-top:8px'>"
                f"<div><div style='color:#888;font-size:10px'>YTD RETURN</div>"
                f"<div style='color:{_ytd_col};font-weight:bold;font-size:16px'>{_ytd:+.1f}%</div>"
                f"<div style='color:{_ahd_col};font-size:10px'>{_ahead:+.1f}% vs hist avg</div></div>"
                f"<div><div style='color:#888;font-size:10px'>HIST AVG Yr {_ps['yr_in_term']} ({_ps['n_yrs']} presidents)</div>"
                f"<div style='font-weight:bold'>{_ps['hist_avg']:+.1f}% avg &nbsp; {_ps['hist_med']:+.1f}% median</div>"
                f"<div style='color:#888;font-size:10px'>{_ps['hist_pos']}% of years positive</div></div>"
                f"<div><div style='color:#888;font-size:10px'>AVG DRAWDOWN Yr {_ps['yr_in_term']}</div>"
                f"<div style='color:#e63946;font-weight:bold'>{_ps['avg_dd']:.1f}% avg &nbsp; {_ps['worst_dd']:.1f}% worst</div>"
                f"<div style='color:#888;font-size:10px'>{_ps['n_dds']}/{_ps['n_yrs']} years had DD >10%</div></div>"
                f"<div><div style='color:#888;font-size:10px'>{_ps['curr_mo'].upper()} SEASONALITY</div>"
                f"<div style='font-weight:bold'>{_ps['mo_avg']:+.1f}% hist avg</div>"
                f"<div style='color:#888;font-size:10px'>{_ps['mo_pos']}% of years positive</div></div>"
                f"</div></div>",
                unsafe_allow_html=True
            )
        else:
            st.info("Loading presidential cycle data...")

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════════════════════════════
elif page == "Seasonality":
    import plotly.graph_objects as go
    import plotly.express as px
    st.title("📅 Seasonality")

    # Presidential year lookup — available to all seasonality tabs
    _PRES_YEAR_MAP = {}
    _TERMS = [
        ("Hoover",1929,"R"),("Roosevelt T1",1933,"D"),("Roosevelt T2",1937,"D"),
        ("Roosevelt T3",1941,"D"),("Roosevelt T4",1945,"D"),("Truman",1945,"D"),
        ("Eisenhower T1",1953,"R"),("Eisenhower T2",1957,"R"),
        ("Kennedy",1961,"D"),("Johnson",1963,"D"),("Nixon T1",1969,"R"),
        ("Nixon T2",1973,"R"),("Ford",1974,"R"),("Carter",1977,"D"),
        ("Reagan T1",1981,"R"),("Reagan T2",1985,"R"),("Bush Sr",1989,"R"),
        ("Clinton T1",1993,"D"),("Clinton T2",1997,"D"),("Bush Jr T1",2001,"R"),
        ("Bush Jr T2",2005,"R"),("Obama T1",2009,"D"),("Obama T2",2013,"D"),
        ("Trump T1",2017,"R"),("Biden",2021,"D"),("Trump T2",2025,"R"),
    ]
    for _pn,_ps,_pp in _TERMS:
        for _yi in range(1,5):
            _yr = _ps + (_yi-1)
            if _yr not in _PRES_YEAR_MAP:
                _PRES_YEAR_MAP[_yr] = _yi

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
        _sc1, _sc2, _sc3, _sc4, _sc5, _sc6 = st.columns([3, 2, 2, 1, 2, 1])
        _groups    = list(_INSTRUMENTS.keys())
        _grp_sel   = _sc1.selectbox("Asset class", _groups, key="sea_group")
        _inst_map  = _INSTRUMENTS[_grp_sel]
        _inst_sel  = _sc2.selectbox("Instrument", list(_inst_map.keys()), key="sea_inst")
        _ticker    = _inst_map[_inst_sel]
        _show_sea_avg    = _sc5.toggle("Show average line", value=True, key="sea_show_avg")
        _gen_sea_report = _sc6.checkbox("📸 JPG", key="sea_gen_jpg")
        if 'sea_jpg_ready' in st.session_state and st.session_state['sea_jpg_ready']:
            _sc6.download_button("⬇ JPG", data=st.session_state['sea_jpg_data'],
                                 file_name=st.session_state['sea_jpg_name'],
                                 mime="image/jpeg", key="sea_jpg_top_dl")
        _pres_yr_filter  = _sc4.multiselect("Pres. Yr", [1,2,3,4], default=[],
                                            key="sea_pres_yr",
                                            help="Filter to US presidential term years. Empty = all years.")

        # Clear cached JPG if instrument or settings changed
        _sea_cache_key = f"{_ticker}_{_yr_range if '_yr_range' in dir() else ''}"
        if st.session_state.get('_sea_cache_key') != _sea_cache_key:
            st.session_state['sea_jpg_ready'] = False
            st.session_state['_sea_cache_key'] = _sea_cache_key

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

            # Apply presidential year filter
            if _pres_yr_filter:
                _selected_yrs = [y for y in _selected_yrs if _PRES_YEAR_MAP.get(y) in _pres_yr_filter]

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

                _palette = [
                    '#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd',
                    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
                    '#0055d4','#e65c00','#1a7a1a','#a00000','#5a3e8e',
                    '#4a2c2a','#9b3d7d','#4d4d4d','#7d7d00','#005f6b',
                    '#3399ff','#ff9933','#33cc33','#ff3333','#cc66ff',
                    '#996633','#ff66cc','#999999','#cccc00','#33cccc',
                ]

                # Assign colours by original year order so they stay consistent
                _yr_color = {_yr: _palette[_i % len(_palette)]
                             for _i, _yr in enumerate(_yearly.keys())}

                # Sort years by annual return (final indexed value) descending
                _legend_order = sorted(
                    [(_yr, _vals[-1]) for _yr, (_doys, _vals) in _yearly.items()],
                    key=lambda x: x[1], reverse=True
                )
                _top40 = {y for y, _ in _legend_order[:40]}

                # Build figure directly in sorted order — best return at top of legend
                _fig_sea2 = go.Figure()
                for _yr, _annual in _legend_order:
                    _doys, _vals = _yearly[_yr]
                    _sign = '+' if _annual >= 0 else ''
                    _fig_sea2.add_trace(go.Scatter(
                        x=_doys, y=_vals,
                        mode='lines',
                        name=f"{_yr} ({_sign}{_annual:.1f}%)",
                        line=dict(width=1, color=_yr_color[_yr]),
                        opacity=0.45,
                        showlegend=_yr in _top40,
                        hovertemplate=f"<b>{_yr}</b><br>Day %{{x}}: %{{y:.2f}}%<extra></extra>"
                    ))

                # Average line last — always shown, always on top visually
                if _show_sea_avg:
                    _avg_col = '#111111' if _get_theme_mode() == 'light' else '#ffffff'
                    _fig_sea2.add_trace(go.Scatter(
                        x=_avg_doy, y=_avg_vals,
                        mode='lines', name='Average',
                        line=dict(width=2.5, color=_avg_col, dash='dot'),
                        hovertemplate="<b>Average</b><br>Day %{x}: %{y:.2f}%<extra></extra>"
                    ))
                _fig_sea2.add_hline(y=0, line_dash="dash", line_color="rgba(128,128,128,0.4)", line_width=1)

                # X-axis ticks at month starts (approx day of year)
                _mo_days = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
                _mo_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
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
                        xanchor='left', x=1.02,
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
                    st.plotly_chart(_fig_sea2, width='stretch')
                # Store for report generation
                st.session_state['_sea_fig']  = _fig_sea2
                st.session_state['_sea_inst'] = _inst_sel
                st.session_state['_sea_yr']   = _yr_range

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
                            return f"background-color: rgba(45,198,83,{intensity/255:.2f}); color: {_UI_TEXT}"
                        elif v < 0:
                            intensity = min(int(abs(v) / 9 * 180), 200)
                            return f"background-color: rgba(230,57,70,{intensity/255:.2f}); color: {_UI_TEXT}"
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
                ), width='stretch', hide_index=True)

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
                            return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:{_UI_TEXT}"
                        elif n < 0:
                            intensity = min(abs(n) / 9, 1.0)
                            return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:{_UI_TEXT}"
                    except: pass
                    return ""

                _num_summ_cols = [c for c in _df_summ.columns if c != "Year"]
                st.dataframe(
                    _df_summ.style.map(_summ_heat, subset=_num_summ_cols),
                    width='stretch', hide_index=True
                )
                # Store dataframes for report
                st.session_state['_sea_df_disp'] = _df_disp
                st.session_state['_sea_df_summ'] = _df_summ
                st.session_state['_sea_filt']    = _sea_filt
                st.session_state['_sea_sel_yrs'] = _selected_yrs

                # ── AI Assessment ──────────────────────────────────────────────
                _sea_ai_settings = load_settings()
                if _sea_ai_settings.get('ai_features', {}).get('enabled', False):
                    import importlib as _imp_sea, sys as _sys_sea
                    if MACRO not in _sys_sea.path: _sys_sea.path.insert(0, MACRO)
                    _imp_sea.invalidate_caches()
                    from ai_assessment import render_ai_assessment
                    _sea_pfx = load_settings().get('ai_prompts', {}).get(
                        'sea_sectors', DEFAULT_SETTINGS['ai_prompts']['sea_sectors'])
                    _sea_ai_data = (
                        f"Instrument: {_inst_sel} ({_ticker})\n"
                        f"Year range: {_yr_range[0]}–{_yr_range[1]}\n"
                        f"Presidential year filter: {_pres_yr_filter if _pres_yr_filter else 'All years'}\n"
                        f"Current presidential year-in-term: {_PRES_YEAR_MAP.get(pd.Timestamp.now().year, 'N/A')}\n\n"
                        f"MONTHLY RETURNS TABLE:\n{_df_disp.to_string(index=False)}\n\n"
                        f"SUMMARY STATISTICS:\n{_df_summ.to_string(index=False)}"
                    )
                    render_ai_assessment(_sea_pfx + "\n\n" + _sea_ai_data,
                                         _sea_ai_settings, 'sea_sectors_summary')

                # ── JPG Report ────────────────────────────────────────────────
                if _gen_sea_report:
                    _r_inst    = st.session_state.get('_sea_inst', _inst_sel)
                    _r_yr      = st.session_state.get('_sea_yr',   _yr_range)
                    _r_df_disp = st.session_state.get('_sea_df_disp', _df_disp)
                    _r_df_summ = st.session_state.get('_sea_df_summ', _df_summ)
                    _r_filt    = st.session_state.get('_sea_filt',    _sea_filt)
                    _r_sel_yrs = st.session_state.get('_sea_sel_yrs', _selected_yrs)
                    try:
                        import io, matplotlib
                        matplotlib.use('Agg')
                        import matplotlib.pyplot as _plt
                        from PIL import Image as _PIL_IMG

                        def _cell_color(v):
                            try:
                                n = float(str(v).replace('%',''))
                                if n > 0:   return (45/255,198/255,83/255,  min(n/9,1)*0.7)
                                elif n < 0: return (230/255,57/255,70/255, min(abs(n)/9,1)*0.7)
                            except: pass
                            return (1,1,1,0)

                        def _render_table_img(df, title):
                            _nc, _nr = len(df.columns), len(df)
                            _widths  = [2.2] + [0.85]*(_nc-1)
                            _fig2, _ax2 = _plt.subplots(figsize=(sum(_widths), 0.35*_nr+0.7))
                            _ax2.axis('off')
                            _tbl2 = _ax2.table(cellText=df.values, colLabels=df.columns,
                                               cellLoc='center', loc='center',
                                               colWidths=[w/sum(_widths) for w in _widths])
                            _tbl2.auto_set_font_size(False); _tbl2.set_fontsize(7.5)
                            for _ci2 in range(_nc):
                                _tbl2[0,_ci2].set_facecolor('#2d2d2d')
                                _tbl2[0,_ci2].set_text_props(color='white', fontweight='bold')
                            for _ri2 in range(_nr):
                                for _ci2 in range(_nc):
                                    _tbl2[_ri2+1,_ci2].set_facecolor(_cell_color(df.iloc[_ri2,_ci2]))
                                if _nc > 0:
                                    _tbl2[_ri2+1,0].set_text_props(ha='left', fontsize=7)
                            _ax2.set_title(title, fontsize=9, pad=4, loc='left', color='#333')
                            _fig2.tight_layout(pad=0.3)
                            _b2 = io.BytesIO()
                            _fig2.savefig(_b2, format='png', dpi=150, bbox_inches='tight')
                            _plt.close(_fig2); _b2.seek(0)
                            return _PIL_IMG.open(_b2).copy()

                        # Spaghetti chart via matplotlib
                        _fig_r, _ax_r = _plt.subplots(figsize=(16, 6))
                        _ax_r.set_facecolor('#f8f8f8')
                        _fig_r.patch.set_facecolor('white')
                        _MO_T = [16,46,75,106,136,167,197,228,259,289,320,350]
                        _MO_N = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                        _CLR  = ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b',
                                 '#e377c2','#7f7f7f','#bcbd22','#17becf','#0055d4','#e65c00',
                                 '#1a7a1a','#a00000','#5a3e8e','#4a2c2a','#9b3d7d','#006400',
                                 '#8B0000','#00008B','#FF8C00','#4B0082','#006666']
                        _ci_r = 0
                        for _yr_r in sorted(_selected_yrs):
                            _yd_r = _sea_filt[_sea_filt.index.year == _yr_r]
                            if len(_yd_r) < 5: continue
                            _b_r = float(_yd_r.iloc[0])
                            if _b_r == 0: continue
                            _ix_r = (_yd_r / _b_r - 1) * 100
                            _ax_r.plot([d.timetuple().tm_yday for d in _ix_r.index],
                                       _ix_r.values, color=_CLR[_ci_r % len(_CLR)],
                                       linewidth=0.9, alpha=0.75, label=str(_yr_r))
                            _ci_r += 1
                        if _show_sea_avg and _ci_r > 1:
                            _avd = {}
                            for _yr_r in _selected_yrs:
                                _yd_r = _sea_filt[_sea_filt.index.year == _yr_r]
                                if len(_yd_r) < 5: continue
                                _b_r = float(_yd_r.iloc[0])
                                if _b_r == 0: continue
                                _ix_r = (_yd_r / _b_r - 1) * 100
                                for _d_r, _v_r in zip([d.timetuple().tm_yday for d in _ix_r.index], _ix_r.values):
                                    _avd.setdefault(_d_r, []).append(float(_v_r))
                            _ax_r.plot(sorted(_avd), [sum(_avd[d])/len(_avd[d]) for d in sorted(_avd)],
                                       'k--', linewidth=1.5, label='Average')
                        _ax_r.set_xticks(_MO_T); _ax_r.set_xticklabels(_MO_N, fontsize=8)
                        _ax_r.set_xlim(0, 366)
                        _ax_r.set_ylabel('Return from Jan 1 (%)', fontsize=8)
                        _ax_r.set_title(f"{_inst_sel} — Seasonal Returns ({_yr_range[0]}–{_yr_range[1]})",
                                        fontsize=10, loc='left')
                        _ax_r.legend(fontsize=6, ncol=max(1,_ci_r//8+1),
                                     loc='upper left', bbox_to_anchor=(1.01,1))
                        _ax_r.grid(True, alpha=0.3)
                        _fig_r.tight_layout()
                        _rb = io.BytesIO()
                        _fig_r.savefig(_rb, format='png', dpi=150, bbox_inches='tight')
                        _plt.close(_fig_r); _rb.seek(0)
                        _chart_img_r = _PIL_IMG.open(_rb).copy()

                        _heat_img_r = _render_table_img(_r_df_disp, f"Monthly Returns — {_r_inst}")
                        _summ_img_r = _render_table_img(_r_df_summ, "Summary")

                        _imgs_r  = [_chart_img_r, _heat_img_r, _summ_img_r]
                        _max_w_r = max(im.width for im in _imgs_r)
                        _tot_h_r = sum(im.height for im in _imgs_r) + 30
                        _canvas_r = _PIL_IMG.new('RGB', (_max_w_r, _tot_h_r), 'white')
                        _yp = 10
                        for _im_r in _imgs_r:
                            _canvas_r.paste(_im_r, (0, _yp)); _yp += _im_r.height
                        _out_r = io.BytesIO()
                        _canvas_r.save(_out_r, format='JPEG', quality=92)
                        _out_r.seek(0)
                        _fname = f"seasonality_{_r_inst.replace(' ','_')}_{_r_yr[0]}_{_r_yr[1]}.jpg"
                        st.session_state['sea_jpg_ready'] = True
                        st.session_state['sea_jpg_data']  = _out_r.getvalue()
                        st.session_state['sea_jpg_name']  = _fname
                    except Exception as _e:
                        import traceback
                        st.session_state['_sea_report_requested'] = False
                        st.error(f"Report failed: {_e}")
                        st.code(traceback.format_exc())
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

        _wl_keys  = list(UNIVERSE_LABELS.keys())
        _wl_sel   = _st_c1.selectbox("Universe", _wl_keys, format_func=lambda k: UNIVERSE_LABELS[k], key="stk_wl")
        _wl_df    = db_universe_members(_wl_sel) if _wl_sel else None
        _wl_path  = None   # legacy name — sector/industry now come from _wl_df

        _wl_tickers = []
        if _wl_df is not None and len(_wl_df):
            _wl_tickers = [f"{t} — {n}" for t, n in zip(_wl_df['ticker'], _wl_df['name'].fillna(''))]

        _stk_sel  = _st_c2.selectbox("Stock", _wl_tickers, key="stk_pick") if _wl_tickers else None
        _stk_ticker = _stk_sel.split(' — ')[0].strip() if _stk_sel else None

        # Detect AU vs US
        _is_au = _stk_ticker and _stk_ticker.endswith('.AX')

        # ── Sector comparison ─────────────────────────────────────────────────
        _cmp_mode = _st_c3.radio("Compare to", ["Auto sector", "Manual ticker", "Self average", "None"],
                                  horizontal=True, key="stk_cmp_mode")
        _cmp_ticker = None
        _cmp_label  = None
        _cmp_is_self_avg = False

        if _cmp_mode == "Manual ticker":
            _mc1, _mc2 = st.columns([2, 4])
            _cmp_manual = _mc1.text_input("Comparison ticker", placeholder="e.g. XLK or ^AXMJ",
                                           key="stk_cmp_manual")
            if _cmp_manual.strip():
                _cmp_ticker = _cmp_manual.strip().upper()
                _cmp_label  = _cmp_ticker

        elif _cmp_mode == "Self average":
            _cmp_is_self_avg = True
            _cmp_label = f"{_stk_ticker} (avg)" if _stk_ticker else None
            # _cmp_ticker stays None — handled specially below

        elif _cmp_mode == "Auto sector" and _stk_ticker:
            # Try to get sector from watchlist
            _stk_sector = None
            if _wl_df is not None:
                _match = _wl_df[_wl_df['ticker'] == _stk_ticker]
                if not _match.empty:
                    _stk_sector = _match.iloc[0]['sector']

            _sec_map = _SECTOR_MAP_AU if _is_au else _SECTOR_MAP_US
            # Get industry too for fuzzy matching
            _stk_industry = None
            if _wl_df is not None:
                _match3 = _wl_df[_wl_df['ticker'] == _stk_ticker]
                if not _match3.empty:
                    _stk_industry = _match3.iloc[0]['industry'] or None
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
            st.info("Select a universe and stock to view seasonality.")
        else:
            _stk_data = _fetch_stk(_stk_ticker)
            if _cmp_is_self_avg:
                # Self-average: comparison is the stock's own historical mean pattern.
                # We'll synthesize _cmp_data and _ann_rets_cmp after we know which years
                # are selected (handled below in the per-year loop).
                _cmp_data = None  # placeholder; populated below
            else:
                _cmp_data = _fetch_stk(_cmp_ticker) if _cmp_ticker else None

            if _stk_data is None or len(_stk_data) < 50:
                st.warning(f"No data found for {_stk_ticker}")
            else:
                _s_min = int(_stk_data.index.year.min())
                _s_max = int(_stk_data.index.year.max())

                _ss1, _ss2, _ss3, _ss4 = st.columns([3, 2, 1, 2])
                _s_range = _ss1.slider("Year range", _s_min, _s_max,
                                        (_s_max - min(15, _s_max - _s_min), _s_max),
                                        key="stk_yr")
                _s_excl  = _ss2.multiselect("Exclude years",
                                             list(range(_s_range[0], _s_range[1]+1)),
                                             default=[], key="stk_excl")
                _stk_pres_yr = _ss3.multiselect("Pres. Yr", [1,2,3,4], default=[],
                                                  key="stk_pres_yr",
                                                  help="Filter to US presidential term years")
                _show_stk_avg    = _ss4.toggle("Show average", value=True, key="stk_avg")
                _gen_stk_report  = st.button("📸 JPG", key="stk_gen_jpg", help="Generate JPG report")

                _s_yrs = [y for y in range(_s_range[0], _s_range[1]+1) if y not in _s_excl]
                if _stk_pres_yr:
                    _s_yrs = [y for y in _s_yrs if _PRES_YEAR_MAP.get(y) in _stk_pres_yr]

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

                # ── Self-average mode: build comparison from the stock's own pattern ──
                if _cmp_is_self_avg and _stk_yearly:
                    # The "comparison" is the leave-one-out average of all OTHER years.
                    # For each year Y, _cmp_yearly[Y] = average pattern across all other selected years.
                    # This way correlation measures how well Y's pattern tracks the typical pattern.
                    _all_doys_self = sorted(set(d for doys,_ in _stk_yearly.values() for d in doys))
                    for _yr in list(_stk_yearly.keys()):
                        _other_yrs = [y for y in _stk_yearly.keys() if y != _yr]
                        if not _other_yrs:
                            continue
                        _xs_avg, _ys_avg = [], []
                        for _d in _all_doys_self:
                            _pts = []
                            for _oy in _other_yrs:
                                _odoys, _ovals = _stk_yearly[_oy]
                                for _di, _dd in enumerate(_odoys):
                                    if _dd == _d:
                                        _pts.append(_ovals[_di])
                                        break
                            if _pts:
                                _xs_avg.append(_d)
                                _ys_avg.append(sum(_pts)/len(_pts))
                        if _xs_avg:
                            _cmp_yearly[_yr] = (_xs_avg, _ys_avg)
                            _ann_rets_cmp[_yr] = round(_ys_avg[-1], 2)
                    # Set a sentinel so downstream "if _cmp_data is not None" passes
                    _cmp_data = _stk_data  # any non-None value

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
                _palette = [
                    '#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd',
                    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
                    '#0055d4','#e65c00','#1a7a1a','#a00000','#5a3e8e',
                    '#4a2c2a','#9b3d7d','#4d4d4d','#7d7d00','#005f6b',
                    '#3399ff','#ff9933','#33cc33','#ff3333','#cc66ff',
                    '#996633','#ff66cc','#999999','#cccc00','#33cccc',
                ]

                # Assign colours by original year order so they stay consistent
                _stk_yr_color = {_yr: _palette[_i % len(_palette)]
                                 for _i, _yr in enumerate(_stk_yearly.keys())}

                # Sort years by annual return descending — best return at top of legend
                _stk_legend_order = sorted(
                    [(_yr, _ann_rets_stk[_yr]) for _yr in _stk_yearly if _yr in _ann_rets_stk],
                    key=lambda x: x[1], reverse=True
                )
                _stk_top40 = {y for y, _ in _stk_legend_order[:40]}

                for _yr, _annual in _stk_legend_order:
                    _doys, _vals = _stk_yearly[_yr]
                    _sign = '+' if _annual >= 0 else ''
                    _fig_stk.add_trace(go.Scatter(
                        x=_doys, y=_vals, mode='lines',
                        name=f"{_yr} ({_sign}{_annual:.1f}%)",
                        line=dict(width=1, color=_stk_yr_color[_yr]),
                        opacity=0.4,
                        showlegend=_yr in _stk_top40,
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
                    st.plotly_chart(_fig_stk, width='stretch')

                # ── Monthly returns heatmap ───────────────────────────────────
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

                _df_stk_disp = pd.DataFrame()
                _df_stk_summ = pd.DataFrame()
                if _stk_mo_rows:
                    _df_stk_heat = pd.DataFrame(_stk_mo_rows)
                    def _stk_heat_style(val, col):
                        if col == "Year" or val is None: return ""
                        try:
                            v = float(val)
                            if v > 0:
                                intensity = min(int(abs(v)/9*180), 200)
                                return f"background-color:rgba(45,198,83,{intensity/255:.2f});color:{_UI_TEXT}"
                            elif v < 0:
                                intensity = min(int(abs(v)/9*180), 200)
                                return f"background-color:rgba(230,57,70,{intensity/255:.2f});color:{_UI_TEXT}"
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
                        ), width='stretch', hide_index=True
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
                                return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:{_UI_TEXT}"
                            elif n < 0:
                                intensity = min(abs(n)/9, 1.0)
                                return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:{_UI_TEXT}"
                        except: pass
                        return ""
                    _stk_num_cols = [c for c in _df_stk_summ.columns if c != "Year"]
                    for _cn in _stk_num_cols:
                        _df_stk_summ[_cn] = _df_stk_summ[_cn].apply(
                            lambda x: x if isinstance(x, str) else
                            f"{x:.2f}%" if pd.notna(x) and x is not None else "—")
                    st.markdown("**Summary**")
                    st.dataframe(
                        _df_stk_summ.style.map(_stk_summ_heat, subset=_stk_num_cols),
                        width='stretch', hide_index=True
                    )

                # ── AI Assessment ─────────────────────────────────────────────
                if not _df_stk_disp.empty and not _df_stk_summ.empty:
                    _stk_ai_settings = load_settings()
                    if _stk_ai_settings.get('ai_features', {}).get('enabled', False):
                        import importlib as _imp_stk, sys as _sys_stk
                        if MACRO not in _sys_stk.path: _sys_stk.path.insert(0, MACRO)
                        _imp_stk.invalidate_caches()
                        from ai_assessment import render_ai_assessment
                        _stk_pfx = load_settings().get('ai_prompts', {}).get(
                            'sea_stocks', DEFAULT_SETTINGS['ai_prompts']['sea_stocks'])
                        _stk_ai_data = (
                            f"Instrument: {_stk_ticker}\n"
                            f"Year range: {_s_range[0]}–{_s_range[1]}\n"
                            f"Presidential year filter: {_stk_pres_yr if _stk_pres_yr else 'All years'}\n"
                            f"Current presidential year-in-term: {_PRES_YEAR_MAP.get(pd.Timestamp.now().year, 'N/A')}\n\n"
                            f"MONTHLY RETURNS TABLE:\n{_df_stk_disp.to_string(index=False)}\n\n"
                            f"SUMMARY STATISTICS:\n{_df_stk_summ.to_string(index=False)}"
                        )
                        render_ai_assessment(_stk_pfx + "\n\n" + _stk_ai_data,
                                             _stk_ai_settings, 'sea_stocks_summary')

                # ── JPG Report ────────────────────────────────────────────────
                if _gen_stk_report and not _df_stk_disp.empty:
                    try:
                        import io as _io2
                        from PIL import Image as _Img2, ImageDraw as _IDraw2
                        import plotly.io as _pio2
                        import plotly.graph_objects as _go3

                        _stk_imgs = []

                        # Spaghetti chart
                        _stk_imgs.append(_Img2.open(_io2.BytesIO(
                            _pio2.to_image(_fig_stk, format='png', width=1400, height=700, scale=2))))

                        # Monthly heatmap table
                        _stk_tbl_fig = _go3.Figure(data=[_go3.Table(
                            header=dict(values=list(_df_stk_disp.columns),
                                        fill_color='#333', font=dict(color='white',size=11),
                                        align='center', height=28),
                            cells=dict(values=[_df_stk_disp[c].tolist() for c in _df_stk_disp.columns],
                                       font=dict(size=10), align='center', height=24)
                        )])
                        _stk_tbl_fig.update_layout(
                            margin=dict(l=10,r=10,t=30,b=10),
                            height=max(300, 28+len(_df_stk_disp)*24+40),
                            title=dict(text=f"Monthly Returns — {_stk_ticker}", font=dict(size=13)),
                            paper_bgcolor='white')
                        _stk_imgs.append(_Img2.open(_io2.BytesIO(
                            _pio2.to_image(_stk_tbl_fig, format='png', width=1400, scale=2))))

                        # Summary table
                        _stk_summ_fig = _go3.Figure(data=[_go3.Table(
                            header=dict(values=list(_df_stk_summ.columns),
                                        fill_color='#333', font=dict(color='white',size=11),
                                        align='center', height=28),
                            cells=dict(values=[_df_stk_summ[c].tolist() for c in _df_stk_summ.columns],
                                       font=dict(size=10), align='center', height=24)
                        )])
                        _stk_summ_fig.update_layout(
                            margin=dict(l=10,r=10,t=30,b=10),
                            height=max(200, 28+len(_df_stk_summ)*24+40),
                            title=dict(text="Summary", font=dict(size=13)),
                            paper_bgcolor='white')
                        _stk_imgs.append(_Img2.open(_io2.BytesIO(
                            _pio2.to_image(_stk_summ_fig, format='png', width=1400, scale=2))))

                        # Stack vertically
                        _stk_total_h = sum(im.height for im in _stk_imgs)
                        _stk_max_w   = max(im.width  for im in _stk_imgs)
                        _stk_canvas  = _Img2.new('RGB', (_stk_max_w, _stk_total_h+60), color='white')
                        _stk_draw    = _IDraw2.Draw(_stk_canvas)
                        _stk_draw.text((20,10), f"Seasonality — {_stk_ticker} ({_s_range[0]}–{_s_range[1]})", fill='#333')
                        _stk_y = 40
                        for _im in _stk_imgs:
                            _stk_canvas.paste(_im, (0, _stk_y))
                            _stk_y += _im.height

                        _stk_buf = _io2.BytesIO()
                        _stk_canvas.save(_stk_buf, format='JPEG', quality=92)
                        _stk_buf.seek(0)
                        st.download_button(
                            label="⬇ Download JPG",
                            data=_stk_buf,
                            file_name=f"seasonality_{_stk_ticker}_{_s_range[0]}_{_s_range[1]}.jpg",
                            mime="image/jpeg",
                            key="stk_jpg_dl"
                        )
                    except Exception as _e:
                        st.error(f"Report failed: {_e}")

                # ── Correlation stats (only when a comparison is selected) ────
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

                        # ── Combined annual returns + correlation table ────────
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
                                    if n >= 0.7:   return f'background-color:rgba(45,198,83,0.6);color:{_UI_TEXT};font-weight:bold'
                                    elif n >= 0.3:  return f'background-color:rgba(247,127,0,0.5);color:{_UI_TEXT};font-weight:bold'
                                    elif n >= 0:    return f'background-color:rgba(247,127,0,0.2);color:{_UI_TEXT}'
                                    else:           return f'background-color:rgba(230,57,70,0.5);color:{_UI_TEXT};font-weight:bold'
                                else:
                                    if n > 0:
                                        intensity = min(n / 9, 1.0)
                                        return f'background-color:rgba(45,198,83,{intensity*0.7:.2f});color:{_UI_TEXT}'
                                    elif n < 0:
                                        intensity = min(abs(n) / 9, 1.0)
                                        return f'background-color:rgba(230,57,70,{intensity*0.7:.2f});color:{_UI_TEXT}'
                            except: pass
                            return ''

                        _heat_cols = [c for c in _df_tbl.columns if c != 'Year']
                        st.dataframe(
                            _df_tbl.style.apply(
                                lambda col: [_tbl_heat(v, col.name) for v in col]
                                if col.name in _heat_cols else ['']*len(col), axis=0
                            ),
                            width='stretch', hide_index=True
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
                        st.plotly_chart(_fig_scatter, width='stretch')

                    else:
                        st.info("Need at least 5 years of overlapping data for correlation analysis.")


    with _sea_tab3:
        # Presidents from 1929 onwards (S&P data reliable from ~1928)
        # Split multi-term presidents into 4-year blocks
        _PRESIDENTS = [
            ("Hoover",         1929, 1933, "Republican"),
            ("Roosevelt T1",   1933, 1937, "Democrat"),
            ("Roosevelt T2",   1937, 1941, "Democrat"),
            ("Roosevelt T3",   1941, 1945, "Democrat"),
            ("Roosevelt T4",   1945, 1945, "Democrat"),
            ("Truman",         1945, 1953, "Democrat"),
            ("Eisenhower T1",  1953, 1957, "Republican"),
            ("Eisenhower T2",  1957, 1961, "Republican"),
            ("Kennedy",        1961, 1963, "Democrat"),
            ("Johnson",        1963, 1969, "Democrat"),
            ("Nixon T1",       1969, 1973, "Republican"),
            ("Nixon T2",       1973, 1974, "Republican"),
            ("Ford",           1974, 1977, "Republican"),
            ("Carter",         1977, 1981, "Democrat"),
            ("Reagan T1",      1981, 1985, "Republican"),
            ("Reagan T2",      1985, 1989, "Republican"),
            ("Bush Sr",        1989, 1993, "Republican"),
            ("Clinton T1",     1993, 1997, "Democrat"),
            ("Clinton T2",     1997, 2001, "Democrat"),
            ("Bush Jr T1",     2001, 2005, "Republican"),
            ("Bush Jr T2",     2005, 2009, "Republican"),
            ("Obama T1",       2009, 2013, "Democrat"),
            ("Obama T2",       2013, 2017, "Democrat"),
            ("Trump T1",       2017, 2021, "Republican"),
            ("Biden",          2021, 2025, "Democrat"),
            ("Trump T2",       2025, 2029, "Republican"),
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
            _st = store_close("^GSPC", "1927-01-01")
            if _st is not None:
                return _st
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
            )
            _pc_spacer, _pc_plot = st.columns([0.115, 0.885])
            with _pc_plot:
                st.plotly_chart(_fig_pc, width='stretch')


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
                            return f"background-color:rgba(45,198,83,{intensity/255:.2f});color:{_UI_TEXT}"
                        elif v < 0:
                            intensity = min(int(abs(v)/9*180), 200)
                            return f"background-color:rgba(230,57,70,{intensity/255:.2f});color:{_UI_TEXT}"
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
                        .map(_pres_col_style, subset=["President"]),
                    column_config=_pc_col_cfg,
                    width='stretch', hide_index=True
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
                            return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:{_UI_TEXT}"
                        elif n < 0:
                            intensity = min(abs(n)/9, 1.0)
                            return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:{_UI_TEXT}"
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
                        .map(_pc_summ_heat, subset=_pc_num_cols),
                    column_config=_pc_summ_col_cfg,
                    width='stretch', hide_index=True
                )

            # ── AI Assessment ──────────────────────────────────────────────
            _pc_ai_settings = load_settings()
            if _pc_ai_settings.get('ai_features', {}).get('enabled', False):
                import importlib as _imp_pc, sys as _sys_pc
                if MACRO not in _sys_pc.path: _sys_pc.path.insert(0, MACRO)
                _imp_pc.invalidate_caches()
                from ai_assessment import render_ai_assessment
                _pc_pfx = load_settings().get('ai_prompts', {}).get(
                    'sea_presidential', DEFAULT_SETTINGS['ai_prompts']['sea_presidential'])
                if st.button("🤖 AI Presidential Cycle Summary", key="ai_sea_pres_btn"):
                    _ps2 = _pres_cycle_stats()
                    _pc_ai_data = (
                        f"Presidential cycle context:\n"
                        f"Current president: {_ps2.get('president','?')} Year {_ps2.get('yr_in_term','?')} ({_ps2.get('party','?')})\n"
                        f"YTD S&P 500: {_ps2.get('ytd_ret',0):+.1f}%\n"
                        f"Historical avg Yr {_ps2.get('yr_in_term','?')}: {_ps2.get('hist_avg',0):+.1f}% "
                        f"(median {_ps2.get('hist_med',0):+.1f}%, {_ps2.get('hist_pos',0):.0f}% positive)\n"
                        f"Avg max drawdown Yr {_ps2.get('yr_in_term','?')}: {_ps2.get('avg_dd',0):.1f}% "
                        f"(worst {_ps2.get('worst_dd',0):.1f}%, {_ps2.get('n_dds',0)}/{_ps2.get('n_yrs',0)} yrs >10% DD)\n"
                        f"Current month ({_ps2.get('curr_mo','?')}) hist avg: {_ps2.get('mo_avg',0):+.1f}% "
                        f"({_ps2.get('mo_pos',0):.0f}% positive)\n\n"
                        f"Year filter: Yr {_yr_sel}\n"
                        f"Party filter: {_party_sel}\n\n"
                        f"MONTHLY RETURNS TABLE:\n{_df_pc_heat.to_string(index=False) if '_df_pc_heat' in dir() else 'not available'}\n\n"
                        f"SUMMARY:\n{_df_pc_summ.to_string(index=False) if '_df_pc_summ' in dir() else 'not available'}"
                    )
                    render_ai_assessment(_pc_pfx + "\n\n" + _pc_ai_data,
                                         _pc_ai_settings, 'sea_pres_summary')

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
                        return f"background-color:rgba(45,198,83,{intensity*0.7:.2f});color:{_UI_TEXT};font-weight:bold"
                    elif n < 0:
                        intensity = min(abs(n) / 9, 1.0)
                        return f"background-color:rgba(230,57,70,{intensity*0.7:.2f});color:{_UI_TEXT};font-weight:bold"
                except: pass
                return ""

            st.dataframe(
                _df_pc.style
                    .map(_pc_heat,    subset=["Yr 1","Yr 2","Yr 3","Yr 4"])
                    .map(_party_style, subset=["Party"]),
                width='stretch', hide_index=True
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
            run_script(os.path.join(MACRO, 'au_credit.py'), MACRO)
            st.rerun()
    with _dh4:
        st.markdown("<br>", unsafe_allow_html=True)
        _debt_txt, _, _ = MR.load_report('consumer_credit')
        if _debt_txt:
            st.download_button("⬇ Download Report", _debt_txt,
                               file_name="debt_markets_report.txt", key='top_debt_dl')
    st.markdown("""
        <div class="info-card">
            Tracks the health of consumer, corporate and sovereign credit markets using
            Federal Reserve (FRED) data and daily credit ETF prices. Delinquency series
            are quarterly — slow-moving but highly reliable leading indicators. Credit ETFs
            (HYG, JNK, LQD, TLT, EMB), MOVE index, yields and breakeven inflation are
            <b>daily</b> for real-time signals.
            <b>Rate of change</b> is more important than the level — accelerating
            delinquencies signal deteriorating credit conditions before they appear in
            employment or GDP data. Alerts feed into the Macro page change alerts.
        </div>
    """, unsafe_allow_html=True)

    _tab_us, _tab_au = st.tabs(['🇺🇸 United States', '🇦🇺 Australia'])

    with _tab_us:
        # ── Load latest snapshot ──────────────────────────────────────────────────
        json_files   = MR.report_dates('consumer_credit')

        if not json_files:
            macro_setup_notice("consumer credit report", "16", button="▶ Run Debt Markets Report")
            if st.button("▶ Run Debt Markets Report", type="primary"):
                run_script(os.path.join(MACRO, 'consumer_credit.py'), MACRO)
                st.rerun()
        else:
            # Date selector
            dates      = [d.replace('-', '') for d in json_files][:30]
            sel_date   = st.selectbox("Report date", dates, index=0)
            _cc_iso    = f"{sel_date[:4]}-{sel_date[4:6]}-{sel_date[6:]}"
            _cc_txt, snap, _ = MR.load_report('consumer_credit', _cc_iso)
            snap = snap or {}

            credit_data    = snap.get('credit_data', {})
            pe_data        = snap.get('pe_data', {})
            credit_market  = snap.get('credit_market', {})
            alerts         = snap.get('alerts', [])

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

    Write a structured assessment using these exact section headers:

    **STRESS READ** — Where consumer stress sits across card, auto and mortgage. Distinguish
    the level from the trajectory (qoq and 3-month change). Note that charge-offs lag
    delinquencies by 1-2 quarters — say what the delinquency-vs-chargeoff gap implies about
    banks' write-down pace. Which borrower tier is under pressure (cards/autos = lower income
    first, mortgage = middle income)?

    **CROSS-CHECK WITH FLOWS** — If NY Fed transition-flow data is provided, use it: flows lead
    the bank-reported stock rates by 1-2 quarters, so a rising flow with a flat stock rate is
    an early warning. Comment on subprime origination share — is lending quality deteriorating?

    **SPENDING & MARKETS** — What this combined picture implies for consumer spending and
    equities over the next 1-2 quarters.

    **WATCH LIST** — The 2-3 metrics and specific levels most worth watching next.

    Be direct and quantitative — cite actual numbers and their changes. Aim for 300-400 words.

    Credit card delinquency: {cc.get('current','n/a')}% (qoq change: {cc.get('roc','n/a')}, 3m: {cc.get('roc_3m','n/a')})
    Auto loan delinquency: {aut.get('current','n/a')}% (qoq: {aut.get('roc','n/a')})
    Mortgage delinquency: {mor.get('current','n/a')}% (qoq: {mor.get('roc','n/a')})
    Charge-off rate: {cho.get('current','n/a')}% (qoq: {cho.get('roc','n/a')})"""
                _f90c = credit_data.get('flow90_cc', {})
                _f90a = credit_data.get('flow90_auto', {})
                _f90m = credit_data.get('flow90_mortgage', {})
                _msub = credit_data.get('mortgage_subprime_share', {})
                _asub = credit_data.get('auto_subprime_share', {})
                if _f90c:
                    prompt += f"""

    NY Fed transition flows into 90+ delinquency (leading, all lenders):
    CC flow: {_f90c.get('current','n/a')}% (qoq: {_f90c.get('roc','n/a')})
    Auto flow: {_f90a.get('current','n/a')}% (qoq: {_f90a.get('roc','n/a')})
    Mortgage flow: {_f90m.get('current','n/a')}% (qoq: {_f90m.get('roc','n/a')})
    Subprime origination share — mortgage: {_msub.get('current','n/a')}%, auto: {_asub.get('current','n/a')}%"""
                render_ai_assessment(prompt, ai_settings, 'consumer_credit_assessment',
                                     max_tokens=2000)

            st.divider()

            # ══════════════════════════════════════════════════════════════════════
            # SECTION 1B — NY FED HOUSEHOLD DEBT FLOWS (Equifax panel)
            # ══════════════════════════════════════════════════════════════════════
            if any(k in credit_data for k in ('flow90_cc', 'flow30_cc', 'hh_debt_total')):
                _hhdc_q = snap.get('hhdc_quarter', '')
                st.subheader(f"🏠 Household Debt Flows — NY Fed{f' ({_hhdc_q})' if _hhdc_q else ''}")
                st.markdown("""
                    <div class="info-card">
                        NY Fed Quarterly Report on Household Debt and Credit, built from the
                        Equifax consumer credit panel (all lenders, not just banks). These are
                        <b>transition rates</b> — the share of current balances newly flowing into
                        delinquency each quarter — which lead the bank-reported stock delinquency
                        rates above by 1-2 quarters. Subprime origination share shows the credit
                        quality of NEW lending: rising subprime share late in the cycle is how
                        lenders reach for growth before the bust.
                    </div>
                """, unsafe_allow_html=True)

                h1, h2 = st.columns(2)
                with h1:
                    credit_card('flow90_cc',
                        'Share of current credit card balances newly transitioning to 90+ days delinquent (annualised).',
                        'The most sensitive consumer stress flow. Pre-GFC normal ~5%, GFC peak ~13.7%. Leads the bank-reported CC delinquency stock rate.',
                        'WARN >7.0% | ALERT >9.5%')
                    credit_chart('flow90_cc', 'CC Flow into Serious Delinquency (90+)')

                    credit_card('flow90_auto',
                        'Share of current auto loan balances newly transitioning to 90+ days delinquent.',
                        'Consumers default on autos before housing. GFC peak ~5.3%. Rising alongside subprime share = lending quality problem.',
                        'WARN >2.5% | ALERT >4.0%')
                    credit_chart('flow90_auto', 'Auto Flow into Serious Delinquency (90+)')

                    credit_card('mortgage_subprime_share',
                        'Share of mortgage origination volume to <620 credit scores.',
                        'Pre-GFC this ran 10-15%; post-2010 lending standards keep it under 5%. A sustained rise is a late-cycle warning.',
                        'WARN >8% | ALERT >12%')
                    credit_chart('mortgage_subprime_share', 'Mortgage Subprime Origination Share %')

                with h2:
                    credit_card('flow90_mortgage',
                        'Share of current mortgage balances newly transitioning to 90+ days delinquent.',
                        'The confirmation signal — when mortgage flows rise the stress has spread to middle-income households. GFC peak ~8.9%.',
                        'WARN >2.0% | ALERT >4.0%')
                    credit_chart('flow90_mortgage', 'Mortgage Flow into Serious Delinquency (90+)')

                    credit_card('flow90_student',
                        'Share of current student loan balances newly transitioning to 90+ days delinquent.',
                        'Distorted by the 2020-2024 payment moratorium and reporting pause — the post-resumption spike overstates fresh stress. Watch the trend, not the level.',
                        'WARN >8% | ALERT >12%')
                    credit_chart('flow90_student', 'Student Flow into Serious Delinquency (90+)')

                    credit_card('auto_subprime_share',
                        'Share of auto loan origination volume to <620 credit scores.',
                        'Auto lending routinely runs more subprime than mortgages (~15-20%). Above ~25% signals aggressive reach-for-yield by lenders.',
                        'WARN >22% | ALERT >28%')
                    credit_chart('auto_subprime_share', 'Auto Subprime Origination Share %')

                credit_card('hh_debt_total',
                    'Total US household debt across all products in trillions (mortgage, HELOC, auto, credit card, student, other).',
                    'Level matters less than composition and flows — but contraction here is deleveraging, which is recessionary.',
                    'Monitor trend and composition')
                credit_chart('hh_debt_total', 'Total Household Debt ($T)')

                with st.expander("ℹ Early-delinquency flows (30+ days)"):
                    e1, e2, e3 = st.columns(3)
                    for _col, _key, _title in [(e1, 'flow30_cc', 'CC 30+ Flow'),
                                                (e2, 'flow30_auto', 'Auto 30+ Flow'),
                                                (e3, 'flow30_mortgage', 'Mortgage 30+ Flow')]:
                        with _col:
                            if _key in credit_data:
                                _d = credit_data[_key]
                                st.metric(_title, f"{_d['current']:.2f}%",
                                          delta=f"{_d.get('roc') or 0:+.2f} qoq",
                                          delta_color="inverse")
                    st.caption("30+ flows are noisier but turn first — a sustained 2-3 quarter "
                               "rise here precedes the 90+ flows above.")

                # AI assessment for household debt flows
                _hh_ai_settings = load_settings()
                if _hh_ai_settings.get('ai_features', {}).get('enabled', False):
                    import sys as _hh_sys
                    import importlib as _hh_il
                    if MACRO not in _hh_sys.path:
                        _hh_sys.path.insert(0, MACRO)
                    _hh_il.invalidate_caches()
                    from ai_assessment import render_ai_assessment

                    def _hh_line(key, name):
                        d = credit_data.get(key, {})
                        if not d:
                            return f"{name}: n/a"
                        return (f"{name}: {d.get('current','n/a')}% "
                                f"(qoq: {d.get('roc','n/a')}, 3m: {d.get('roc_3m','n/a')}, "
                                f"level: {d.get('alert_level','OK')})")

                    _hh_pfx = load_settings().get('ai_prompts', {}).get('hhdc_flows',
                        DEFAULT_SETTINGS['ai_prompts']['hhdc_flows'])
                    _hh_total = credit_data.get('hh_debt_total', {})
                    _hh_prompt = f"""{_hh_pfx}

    Write a structured assessment using these exact section headers:

    **FLOW READ** — Where transition-into-delinquency is accelerating vs easing, by loan type.
    Distinguish the 30+ early flows (turn first, noisier) from the 90+ serious flows they feed
    1-2 quarters later — is the early-flow trajectory pointing to higher serious flows ahead?
    Explicitly discount the student loan series (moratorium/reporting distortion) — note it but
    don't treat its level as fresh stress.

    **SPREADING?** — Is stress confined to lower-income tiers (cards, autos) or spreading to
    housing (mortgage flows)? The mortgage flow is the confirmation signal for broad
    middle-income stress — state clearly which regime we're in.

    **LENDER BEHAVIOUR** — What subprime origination share (mortgage and auto) says about
    lending standards. Rising subprime share late in the cycle is a reach-for-growth warning.

    **NEXT QUARTER** — The 2-3 flows and specific levels most worth watching, and what would
    escalate the read.

    Be direct and quantitative — cite actual numbers and qoq changes, flag any WARN/ALERT.
    Aim for 300-400 words.

    Report quarter: {_hhdc_q or 'n/a'}
    Flows into serious delinquency (90+):
    {_hh_line('flow90_cc', 'Credit card')}
    {_hh_line('flow90_auto', 'Auto loan')}
    {_hh_line('flow90_mortgage', 'Mortgage')}
    {_hh_line('flow90_student', 'Student loan (moratorium-distorted)')}

    Flows into early delinquency (30+):
    {_hh_line('flow30_cc', 'Credit card')}
    {_hh_line('flow30_auto', 'Auto loan')}
    {_hh_line('flow30_mortgage', 'Mortgage')}

    Origination quality:
    {_hh_line('mortgage_subprime_share', 'Mortgage subprime share')}
    {_hh_line('auto_subprime_share', 'Auto subprime share')}

    Total household debt: ${_hh_total.get('current','n/a')}T (qoq: {_hh_total.get('roc','n/a')})"""
                    render_ai_assessment(_hh_prompt, _hh_ai_settings, 'hhdc_flows_assessment',
                                         max_tokens=2000)

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
            # SECTION 2b — REAL-TIME CREDIT MARKET ETFs
            # ══════════════════════════════════════════════════════════════════════
            st.subheader("📊 Real-Time Credit Markets")
            st.markdown("""
                <div class="info-card">
                    Daily credit ETF prices provide a real-time view of credit market risk appetite.
                    <b>HYG/JNK</b> track high-yield bonds — falling prices signal risk-off.
                    <b>LQD</b> tracks investment-grade — weakness here confirms stress spreading.
                    <b>TLT/SHY</b> reflect Treasury demand (flight-to-safety).
                    <b>EMB</b> tracks emerging market debt — sensitive to dollar strength and global risk.
                    <b>MOVE</b> is bond-market volatility — spikes precede equity volatility (VIX) by days.
                </div>
            """, unsafe_allow_html=True)

            if credit_market:
                cm_rows = []
                for ticker, d in credit_market.items():
                    cm_rows.append({
                        'Ticker'  : ticker,
                        'Name'    : d['name'],
                        'Price'   : f"{d['price']:.2f}" if d.get('price') is not None else 'n/a',
                        '1W %'    : f"{d['ret_1w']:+.1f}%" if d.get('ret_1w') is not None else 'n/a',
                        '1M %'    : f"{d['ret_1m']:+.1f}%" if d.get('ret_1m') is not None else 'n/a',
                        '3M %'    : f"{d['ret_3m']:+.1f}%" if d.get('ret_3m') is not None else 'n/a',
                        '12M %'   : f"{d['ret_12m']:+.1f}%" if d.get('ret_12m') is not None else 'n/a',
                    })

                df_cm = pd.DataFrame(cm_rows)

                def colour_cm_ret(val):
                    try:
                        v = float(str(val).replace('%','').replace('+',''))
                        if v > 0: return 'color: #2dc653'
                        if v < 0: return 'color: #e63946'
                    except: pass
                    return ''

                st.dataframe(
                    df_cm.style.map(colour_cm_ret, subset=['1W %','1M %','3M %','12M %']),
                    width='stretch', hide_index=True
                )

                move_data = credit_market.get('^MOVE', {})
                if move_data:
                    move_colour = '#e63946' if move_data.get('price', 0) > 120 else '#f77f00' if move_data.get('price', 0) > 100 else '#2dc653'
                    move_1w = f"{move_data['ret_1w']:+.1f}%" if move_data.get('ret_1w') is not None else 'n/a'
                    move_1m = f"{move_data['ret_1m']:+.1f}%" if move_data.get('ret_1m') is not None else 'n/a'
                    st.markdown(f"""
                        <div class="macro-card" style="border-left:4px solid {move_colour}">
                            <div class="macro-label">MOVE Index — Bond Market Volatility</div>
                            <div style="font-size:22px;font-weight:bold;color:{move_colour}">{move_data['price']:.1f}</div>
                            <div style="font-size:11px;color:#888">
                                1w: <span style="color:{move_colour}">{move_1w}</span>
                                &nbsp;|&nbsp; 1m: {move_1m}
                                &nbsp;|&nbsp; <span style="color:#888">Below 80 = calm &nbsp;|&nbsp; 100-120 = elevated &nbsp;|&nbsp; 120+ = stress</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No credit market ETF data — run a fresh report to populate")

            st.divider()

            # ══════════════════════════════════════════════════════════════════════
            # SECTION 2c — RATES & YIELD CURVE
            # ══════════════════════════════════════════════════════════════════════
            st.subheader("📈 Rates & Yield Curve")
            st.markdown("""
                <div class="info-card">
                    Daily Treasury yields and the yield curve from FRED. An inverted curve
                    (10Y-2Y below zero) has preceded every US recession since the 1960s.
                    The <b>un-inversion</b> is often the more immediate recession signal —
                    the curve steepening back toward positive after an inversion period
                    typically occurs as the Fed begins cutting into weakness.
                </div>
            """, unsafe_allow_html=True)

            rate_keys = ['us10y', 'us02y', 'us03m', 'yield_curve', 'fed_funds']
            rate_cols = st.columns(len([k for k in rate_keys if k in credit_data]))
            col_idx = 0
            for key in rate_keys:
                if key not in credit_data:
                    continue
                d = credit_data[key]
                val = d['current']
                roc = d.get('roc', 0) or 0
                arrow = '▲' if roc > 0 else '▼' if roc < 0 else '→'
                colour = '#e63946' if key == 'yield_curve' and val < 0 else '#2dc653' if key == 'yield_curve' and val > 0 else '#00b4d8'
                with rate_cols[col_idx]:
                    st.markdown(f"""
                        <div class="macro-card" style="border-left:3px solid {colour}">
                            <div class="macro-label">{d['label']}</div>
                            <div style="font-size:20px;font-weight:bold;color:{colour}">{val:.2f}%</div>
                            <div style="font-size:11px;color:#888">{arrow} {roc:+.3f}</div>
                        </div>
                    """, unsafe_allow_html=True)
                col_idx += 1

            st.divider()

            # ══════════════════════════════════════════════════════════════════════
            # SECTION 2d — INFLATION EXPECTATIONS
            # ══════════════════════════════════════════════════════════════════════
            st.subheader("🔥 Inflation Expectations")
            st.markdown("""
                <div class="info-card">
                    Breakeven inflation rates from TIPS spreads — what the bond market is
                    pricing for future inflation. Rising breakevens with falling equities
                    signals stagflation risk. 5Y breakevens above 3% historically trigger
                    hawkish Fed response. Divergence between 5Y and 10Y suggests market
                    expects near-term inflation pressure to be transitory vs structural.
                </div>
            """, unsafe_allow_html=True)

            inf_keys = ['breakeven_5y', 'breakeven_10y']
            ic1, ic2 = st.columns(2)
            for i, key in enumerate(inf_keys):
                if key not in credit_data:
                    continue
                d = credit_data[key]
                val = d['current']
                roc = d.get('roc', 0) or 0
                level = d.get('alert_level', 'OK')
                arrow = '▲' if roc > 0 else '▼' if roc < 0 else '→'
                colours = {'ALERT': '#e63946', 'WARN': '#f77f00', 'OK': '#2dc653'}
                colour = colours.get(level, '#888')
                icon = '⚠' if level == 'ALERT' else '!' if level == 'WARN' else '✓'
                thresh = THRESHOLDS.get(key, {}) if 'THRESHOLDS' in dir() else {}
                thresh_txt = f"WARN >{d.get('warn','?')}% | ALERT >{d.get('alert','?')}%" if thresh else ''

                with [ic1, ic2][i]:
                    st.markdown(f"""
                        <div class="macro-card" style="border-left:4px solid {colour}">
                            <div style="display:flex;justify-content:space-between;align-items:center">
                                <div>
                                    <div class="macro-label">{d['label']}</div>
                                    <div style="font-size:22px;font-weight:bold;color:{colour}">{val:.2f}%</div>
                                    <div style="font-size:11px;color:#888">{arrow} {roc:+.3f}</div>
                                </div>
                                <div style="text-align:right">
                                    <div style="color:{colour};font-size:18px">{icon} {level}</div>
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    credit_chart(key, d['label'])

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
            rpt_txt = _cc_txt
            if rpt_txt:
                st.download_button(
                    label     = f"⬇ Download {sel_date} Report",
                    data      = rpt_txt,
                    file_name = f"{sel_date}_consumer_credit_report.txt",
                    mime      = 'text/plain'
                )

    # ══════════════════════════════════════════════════════════════════════════
    # AU TAB — RBA / ASX debt market health
    # ══════════════════════════════════════════════════════════════════════════
    with _tab_au:
        au_files = MR.report_dates('au_credit')
        _au_run_col1, _au_run_col2 = st.columns([3, 1])
        with _au_run_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Run AU Debt Data", key='au_debt_refresh'):
                run_script(os.path.join(MACRO, 'au_credit.py'), MACRO)
                st.rerun()

        if not au_files:
            macro_setup_notice("AU debt-markets report", "17", button="🔄 Run AU Debt Data")
        else:
            with _au_run_col1:
                au_dates    = [d.replace('-', '') for d in au_files][:30]
                au_sel_date = st.selectbox("Report date", au_dates, index=0,
                                           key='au_debt_date')
            _, au_snap, _ = MR.load_report('au_credit', f"{au_sel_date[:4]}-{au_sel_date[4:6]}-{au_sel_date[6:]}")
            au_snap = au_snap or {}

            au_data    = au_snap.get('credit_data', {})
            au_market  = au_snap.get('credit_market', {})
            au_alerts  = au_snap.get('alerts', [])

            st.markdown("""
                <div class="info-card">
                    Australian debt market health from RBA statistical tables and ASX credit
                    ETFs. Australia has no free arrears series, so household stress is read
                    through <b>leverage</b> (debt-to-income among the highest in the developed
                    world) and <b>credit growth</b> (investor housing credit accelerating late
                    in the cycle is the classic AU warning). Corporate spreads are computed
                    from RBA non-financial corporate bond yields vs same-tenor AGS.
                </div>
            """, unsafe_allow_html=True)

            if au_alerts:
                st.markdown("**⚠ Active Alerts**")
                for alert in au_alerts:
                    colour = '#e63946' if alert['type'] == 'ALERT' else '#f77f00'
                    st.markdown(f"""
                        <div class="macro-card" style="border-left:3px solid {colour}">
                            <span style="color:{colour};font-weight:bold">{alert['type']}</span>
                            &nbsp; {alert['message']}
                        </div>
                    """, unsafe_allow_html=True)
                st.divider()

            def au_card(key, description, context, thresholds_text, suffix='%'):
                if key not in au_data:
                    return
                d       = au_data[key]
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
                                    {val:.2f}{suffix}
                                </div>
                                <div style="font-size:11px;color:#888">
                                    {arrow} {roc:+.3f} chg &nbsp;|&nbsp; 3-period: {roc_3m:+.3f}
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

            def au_chart(key, title):
                if key not in au_data:
                    return
                history = au_data[key].get('history', {})
                if not history:
                    return
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=list(history.keys()), y=list(history.values()),
                    mode='lines+markers',
                    line=dict(color='#00b4d8', width=2), marker=dict(size=5),
                    name=title,
                    hovertemplate="%{x}: %{y:.2f}<extra></extra>"))
                fig.update_layout(
                    title=title, height=260,
                    margin=dict(l=10, r=10, t=40, b=10),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#ccc'),
                    xaxis=dict(gridcolor='#2d3250'),
                    yaxis=dict(gridcolor='#2d3250'), showlegend=False)
                st.plotly_chart(fig, width="stretch", key=f'au_chart_{key}')

            # ── Section 1: Household leverage
            st.subheader("🏠 Household Leverage")
            a1, a2 = st.columns(2)
            with a1:
                au_card('au_hh_debt_income',
                    'Total household debt as a percentage of annualised disposable income (RBA E2, quarterly).',
                    'Australia runs among the highest household leverage in the developed world (~180%). Rising leverage with rising rates compresses spending capacity.',
                    'WARN >185% | ALERT >200%')
                au_chart('au_hh_debt_income', 'Household Debt to Income %')
            with a2:
                au_card('au_housing_debt_income',
                    'Housing debt only as a percentage of disposable income.',
                    'The mortgage share of household leverage — what RBA rate hikes squeeze directly.',
                    'WARN >135% | ALERT >150%')
                au_chart('au_housing_debt_income', 'Housing Debt to Income %')
            au_card('au_hh_debt_assets',
                'Household debt as a percentage of total household assets.',
                'A balance-sheet solvency read — stays low while house prices rise, spikes when asset values fall against fixed debt.',
                'WARN >20% | ALERT >24%')
            au_chart('au_hh_debt_assets', 'Household Debt to Assets %')
            st.divider()

            # ── Section 1B: Mortgage arrears (APRA)
            st.subheader("🏦 Mortgage Arrears (APRA)")
            st.markdown("""
                <div class="info-card">
                    From APRA's quarterly ADI property exposures statistics — the source
                    behind Cotality/CoreLogic arrears headlines. Total arrears =
                    30-89 days past due + non-performing (90+ or impaired). The
                    <b>new NPL flow</b> is the share of the mortgage book newly turning
                    non-performing each quarter — the AU cousin of the NY Fed
                    flow-into-delinquency series on the US tab.
                </div>
            """, unsafe_allow_html=True)
            m1_, m2_ = st.columns(2)
            with m1_:
                au_card('au_mortgage_arrears',
                    'Total mortgage arrears: 30-89 days past due plus non-performing loans, as % of credit outstanding (all ADIs).',
                    'COVID peak ~1.9%. Sub-1.5% is healthy. This is the headline number Cotality quotes each quarter.',
                    'WARN >1.8% | ALERT >2.3%')
                au_chart('au_mortgage_arrears', 'Total Mortgage Arrears % (30+dpd)')
                au_card('au_mortgage_arrears_3089',
                    'Early-stage arrears only — 30-89 days past due as % of credit outstanding.',
                    'The leading edge — borrowers newly missing payments. Rises here show up in non-performing 1-2 quarters later.',
                    'WARN >0.85% | ALERT >1.1%')
                au_chart('au_mortgage_arrears_3089', 'Early Arrears 30-89dpd %')
            with m2_:
                au_card('au_mortgage_npl',
                    'Non-performing mortgages (90+ days past due or impaired) as % of credit outstanding.',
                    'The stock of serious stress. Slow to build and slow to clear — direction matters more than level.',
                    'WARN >1.2% | ALERT >1.6%')
                au_chart('au_mortgage_npl', 'Non-Performing Mortgages %')
                au_card('au_new_npl_flow',
                    'NEW non-performing loans during the quarter as % of the mortgage book.',
                    'The flow measure — how fast fresh stress is arriving, regardless of how fast old NPLs cure. Turns before the NPL stock.',
                    'WARN >0.30% | ALERT >0.45%')
                au_chart('au_new_npl_flow', 'New NPL Flow % of Book')
            st.divider()

            # ── Section 2: Credit growth
            st.subheader("📈 Credit Growth (12-month ended)")
            b1_, b2_ = st.columns(2)
            with b1_:
                au_card('au_housing_credit',
                    'Total housing credit growth, 12-month ended (RBA D1, monthly).',
                    'Sustained growth above ~8% historically precedes APRA macroprudential intervention. Contraction is deleveraging.',
                    'WARN >8% | ALERT >10%')
                au_chart('au_housing_credit', 'Housing Credit Growth 12m %')
                au_card('au_personal_credit',
                    'Personal (non-housing) credit growth, 12-month ended.',
                    'Structurally declining for a decade — a sharp acceleration means households are borrowing to fund consumption (stress), not confidence.',
                    'Watch direction changes')
                au_chart('au_personal_credit', 'Personal Credit Growth 12m %')
            with b2_:
                au_card('au_investor_credit',
                    'Investor housing credit growth, 12-month ended.',
                    'The classic AU late-cycle signal — investor credit accelerating above 10% preceded both the 2015 and 2017 APRA crackdowns.',
                    'WARN >8% | ALERT >10%')
                au_chart('au_investor_credit', 'Investor Housing Credit Growth 12m %')
                au_card('au_business_credit',
                    'Business credit growth, 12-month ended.',
                    'Healthy expansion runs 4-8%. Collapse toward zero signals firms pulling back investment before the labour market turns.',
                    'WARN >10% | ALERT >13%')
                au_chart('au_business_credit', 'Business Credit Growth 12m %')
            st.divider()

            # ── Section 3: Corporate credit
            st.subheader("🏢 Corporate Credit")
            c1_, c2_ = st.columns(2)
            with c1_:
                au_card('au_bbb_spread',
                    'Non-financial corporate BBB-rated 5-year yield minus 5-year AGS (RBA F3 vs F2).',
                    'The AU equivalent of a HY-adjacent spread — BBB is the lowest broadly-issued rating tier here. Normal ~1.0-2.0%.',
                    'WARN >2.5% | ALERT >3.5%')
                au_chart('au_bbb_spread', 'BBB Corporate Spread (5y vs AGS)')
            with c2_:
                au_card('au_a_spread',
                    'Non-financial corporate A-rated 5-year yield minus 5-year AGS.',
                    'When A-rated spreads widen alongside BBB the stress is systemic, not idiosyncratic.',
                    'WARN >1.8% | ALERT >2.5%')
                au_chart('au_a_spread', 'A-rated Corporate Spread (5y vs AGS)')
            st.divider()

            # ── Section 4: Rates, curve, sovereign
            st.subheader("📉 Rates & Sovereign")
            r1, r2, r3, r4, r5 = st.columns(5)
            for _col, _key, _lbl in [(r1, 'au_cash_rate', 'RBA Cash Rate'),
                                      (r2, 'au_02y', '2Y AGS'),
                                      (r3, 'au_05y', '5Y AGS'),
                                      (r4, 'au_10y', '10Y AGS'),
                                      (r5, 'au_yield_curve', '10Y − Cash')]:
                if _key in au_data:
                    _d = au_data[_key]
                    _delta = f"{_d.get('roc') or 0:+.2f}" if _d.get('roc') is not None else None
                    _col.metric(_lbl, f"{_d['current']:.2f}%", delta=_delta)
            _curve_d = au_data.get('au_yield_curve', {})
            if _curve_d.get('alert_level') == 'WARN':
                st.warning("AU yield curve (10Y minus cash rate) is inverted — "
                           "historically a growth warning, though less reliable than the US curve.")
            au_card('au_debt_gdp',
                'Australian general government gross debt as % of GDP (IMF via FRED, annual).',
                'Low by developed-world standards (~50% vs US ~123%) — the sovereign is not the risk in Australia; the household balance sheet is.',
                'WARN >55% | ALERT >65%')
            au_chart('au_debt_gdp', 'AU Government Debt % GDP')
            st.divider()

            # ── Section 5: Credit market ETFs
            st.subheader("📊 Credit Market (Daily)")
            if au_market:
                _au_rows = []
                for tkr, d in au_market.items():
                    _au_rows.append({
                        'Ticker': tkr, 'Name': d.get('name', ''),
                        'Price': d.get('price'),
                        '1w %': d.get('ret_1w'), '1m %': d.get('ret_1m'),
                        '3m %': d.get('ret_3m'), '12m %': d.get('ret_12m'),
                    })
                st.dataframe(pd.DataFrame(_au_rows), width="stretch", hide_index=True)
                st.caption("Falling credit ETF prices with a rising AU VIX = spread widening "
                           "in real time between monthly RBA prints. HBRD (hybrids) is the "
                           "closest AU proxy for high-yield risk appetite.")

            # ── AI assessment
            _au_ai = load_settings()
            if _au_ai.get('ai_features', {}).get('enabled', False):
                import importlib as _au_il
                if MACRO not in sys.path:
                    sys.path.insert(0, MACRO)
                _au_il.invalidate_caches()
                from ai_assessment import render_ai_assessment

                def _au_line(key, name):
                    d = au_data.get(key, {})
                    if not d:
                        return f"{name}: n/a"
                    return (f"{name}: {d.get('current','n/a')} "
                            f"(chg: {d.get('roc','n/a')}, level: {d.get('alert_level','OK')})")

                _au_pfx = load_settings().get('ai_prompts', {}).get('au_credit',
                    DEFAULT_SETTINGS['ai_prompts']['au_credit'])
                _au_prompt = f"""{_au_pfx}

Write a structured, in-depth assessment using these exact section headers:

**HOUSEHOLD STRESS** — Read the leverage ratios against the cash rate and the arrears
data together. Distinguish STOCK (debt-to-income, non-performing %) from FLOW (30-89dpd
early arrears, new NPL flow). Is fresh stress arriving faster than old stress is curing?
Note that early arrears (30-89dpd) lead non-performing by 1-2 quarters — say what the
early-vs-serious gap implies. Quantify: at ~180% debt-to-income, how sensitive is the
household sector to the 4.35% cash rate?

**CYCLE POSITION** — Interpret credit growth composition. Investor housing credit
acceleration is the classic AU late-cycle / speculative signal (it preceded the 2015 and
2017 APRA macroprudential crackdowns). Compare investor vs owner-occupier vs business
growth — what does the mix say about where we are in the cycle and whether APRA
intervention risk is rising?

**CORPORATE & RATES** — BBB and A-rated spreads vs AGS, the yield curve, and what the
rate environment implies for refinancing and the household squeeze ahead.

**SIGNAL SUMMARY** — The 2-3 metrics most worth watching next quarter and the specific
levels that would flip the read from benign to concerning. Be explicit about thresholds.

Be direct and quantitative — cite the actual numbers and their quarter-on-quarter changes.
Flag any metric already at WARN or ALERT. Aim for 350-450 words.

Household leverage:
{_au_line('au_hh_debt_income', 'Household debt to income %')}
{_au_line('au_housing_debt_income', 'Housing debt to income %')}
{_au_line('au_hh_debt_assets', 'Household debt to assets %')}

Mortgage arrears (APRA):
{_au_line('au_mortgage_arrears', 'Total arrears % (30+dpd)')}
{_au_line('au_mortgage_arrears_3089', 'Early arrears 30-89dpd %')}
{_au_line('au_mortgage_npl', 'Non-performing %')}
{_au_line('au_new_npl_flow', 'New NPL flow % of book')}

Credit growth (12m ended):
{_au_line('au_housing_credit', 'Housing credit')}
{_au_line('au_investor_credit', 'Investor housing credit')}
{_au_line('au_personal_credit', 'Personal credit')}
{_au_line('au_business_credit', 'Business credit')}

Corporate & rates:
{_au_line('au_bbb_spread', 'BBB 5y spread vs AGS')}
{_au_line('au_a_spread', 'A-rated 5y spread vs AGS')}
{_au_line('au_cash_rate', 'RBA cash rate %')}
{_au_line('au_10y', 'AU 10y yield %')}
{_au_line('au_yield_curve', '10y minus cash %')}
{_au_line('au_debt_gdp', 'Govt debt % GDP')}"""
                render_ai_assessment(_au_prompt, _au_ai, 'au_credit_assessment',
                                     max_tokens=2200)

# ═══════════════════════════════════════════════════════════════════════════════
# AU MARKET PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "AU Market":
    marketdb_ready()
    _ph1, _ph2, _ph3, _ph4 = st.columns([900, 5200, 1800, 900])
    with _ph2:
        st.title("AU Total Market")
    with _ph3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Update AU Market", key='upd_au', help="One incremental price update, then screener, benchmark and breadth for every universe on this page"):
            run_marketdb('--universe', 'au_total_market')
            st.rerun()
    with _ph4:
        st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Breadth", "Zweig Thrust", "Benchmark", "Screener",
                                            "Substantial Holders"])

    with tab5:
        st.subheader("Substantial Holder Notices (ASIC 603 / 604 / 605)")
        _sh1, _sh2 = st.columns([10000, 1800])
        with _sh1:
            st.markdown("""
                <div class="info-card">
                    Substantial holder filings from ASX announcements — the institutional footprint.
                    <b>603 Becoming</b> — a holder crossed above 5%: accumulation signal.
                    <b>604 Change</b> — an existing substantial holder moved ≥1%: adding or reducing
                    (open the PDF to see direction).
                    <b>605 Ceasing</b> — dropped below 5%: distribution signal.
                    Clusters of 603/604s in a name with rising relative strength are smart-money
                    confirmation; 605s into strength are worth respecting. Run daily to build the
                    history — each run captures today + the previous trading day.
                </div>
            """, unsafe_allow_html=True)
        with _sh2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Fetch Notices", key='run_sub_holders'):
                run_script(os.path.join(STOCKS, 'asx_substantial_holders.py'), STOCKS)
                st.rerun()

        _df_sh = MR.holder_notices()
        if _df_sh is None or _df_sh.empty:
            st.info("No notices yet — click Fetch Notices to pull today's filings")
        else:
            st.caption(f"{len(_df_sh)} notices on record — latest {_df_sh['date'].max()}")

            # join AU benchmark rank for context
            _df_bm = MR.latest('benchmark', 'au_total_market')
            if _df_bm is not None and 'ticker' in _df_bm.columns:
                _bm = _df_bm.reset_index()[['ticker', 'rank', 'name', 'sector', 'cap_band']].copy()
                _bm['ticker'] = _bm['ticker'].str.replace('.AX', '', regex=False)
                _df_sh = _df_sh.merge(_bm, on='ticker', how='left')

            _fc1, _fc2, _fc3 = st.columns([2, 2, 3])
            with _fc1:
                _sh_action = st.multiselect("Form type",
                                             ['BECOMING', 'CHANGE', 'CEASING'],
                                             default=['BECOMING', 'CHANGE', 'CEASING'],
                                             key='sh_action_filter',
                                             format_func=lambda a: {'BECOMING': '603 Becoming',
                                                                    'CHANGE': '604 Change',
                                                                    'CEASING': '605 Ceasing'}[a])
            with _fc2:
                _sh_days = st.selectbox("Window", [7, 14, 30, 90, 365], index=2,
                                         key='sh_days_filter',
                                         format_func=lambda d: f"Last {d} days")
            with _fc3:
                _sh_tick = st.text_input("Ticker filter", key='sh_ticker_filter',
                                          placeholder="e.g. BHP (blank = all)")

            _dfv = _df_sh[_df_sh['action'].isin(_sh_action)].copy()
            _cutoff = (datetime.now() - timedelta(days=int(_sh_days))).strftime('%Y-%m-%d')
            _dfv = _dfv[_dfv['date'] >= _cutoff]
            if _sh_tick.strip():
                _dfv = _dfv[_dfv['ticker'].str.contains(_sh_tick.strip().upper(), na=False)]

            _show = pd.DataFrame({
                'Date'    : _dfv['date'],
                'Ticker'  : _dfv['ticker'],
                'Form'    : _dfv['form'],
                'Action'  : _dfv['action'],
                'Company' : _dfv['name'] if 'name' in _dfv.columns else '',
                'Sector'  : _dfv['sector'] if 'sector' in _dfv.columns else '',
                'RS Rank' : _dfv['rank'] if 'rank' in _dfv.columns else None,
                'Notice'  : _dfv['pdf_url'],
            })

            def _sh_colour(val):
                if val == 'BECOMING': return 'color: #2dc653'
                if val == 'CEASING': return 'color: #e63946'
                if val == 'CHANGE': return 'color: #f77f00'
                return ''

            st.dataframe(
                _show.style.map(_sh_colour, subset=['Action']),
                width='stretch', hide_index=True, height=520,
                column_config={
                    'Notice': st.column_config.LinkColumn('Notice', display_text='📄 PDF'),
                    'RS Rank': st.column_config.NumberColumn('RS Rank', format='%d',
                                                             help='Rank in the latest AU benchmark — low rank + accumulation = confirmation'),
                })

            # repeat filers: names with multiple notices in the window
            _rep = _dfv.groupby('ticker').size()
            _rep = _rep[_rep >= 2].sort_values(ascending=False)
            if len(_rep):
                st.markdown("**Repeat activity in window** — " +
                            ', '.join(f"{t} ({n})" for t, n in _rep.items()))

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

        history = MR.breadth_history('au_total_market')

        if history is not None:
            today_str = str(history.iloc[-1]['date'])
            _dc1, _dc2, _dc3 = st.columns([900, 10000, 900])
            with _dc2:
                st.caption(f"Latest: {today_str} — {db_age('breadth', 'au_total_market')}")

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

        if history is not None:
            # ── Sector breadth chart (XAO reference) ──────────────────────
            render_breadth_chart(history, prefix='sec', index_ticker='^AORD',
                                 index_label='XAO — All Ordinaries', key='au')

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
                         if c not in ('nan', 'index')]
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
        zweig_history = MR.breadth_history('au_total_market')
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
        df = MR.formatted('benchmark', 'au_total_market')
        if df is not None:
            st.caption(f"Last updated: {db_age('benchmark', 'au_total_market')} — {len(df)} stocks")
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
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
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
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='au_bm_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='au_bm_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='au_bm_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='au_bm_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No benchmark results found")

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
        df = MR.formatted('screener', 'au_total_market')
        if df is not None:
            st.caption(f"Last updated: {db_age('screener', 'au_total_market')} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
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
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='au_sc_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='au_sc_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='au_sc_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='au_sc_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No screener results found")

# ═══════════════════════════════════════════════════════════════════════════════
# US MARKET PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "US Market":
    marketdb_ready()
    _ph1, _ph2, _ph3, _ph4 = st.columns([900, 5200, 1800, 900])
    with _ph2:
        st.title("US Total Market")
    with _ph3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Update US Market", key='upd_us', help="One incremental price update, then screener, benchmark and breadth for every universe on this page"):
            run_marketdb('--universe', 'us_total_market', 'nasdaq100')
            st.rerun()
    with _ph4:
        st.markdown("<br>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Breadth", "Zweig Thrust", "S&P 500 Benchmark", "S&P 500 Screener", "Nasdaq 100 Screener", "Nasdaq Benchmark"])

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

        history = MR.breadth_history('us_total_market')
        history_file = ('breadth', 'us_total_market')

        if history is not None:
            today_str = str(history.iloc[-1]['date'])
            _dc1, _dc2, _dc3 = st.columns([900, 10000, 900])
            with _dc2:
                st.caption(f"Latest: {today_str} — {db_age(*history_file)}")

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

        if history is not None:   # tables render regardless of the AI-assessment setting
            # ── Sector breadth chart (S&P 500 reference) ──────────────────
            render_breadth_chart(history, prefix='sec', index_ticker='^GSPC',
                                 index_label='SPX — S&P 500', key='us')

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
                        if c not in ('nan', 'index')]
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
                           if c not in ('nan', 'index')]
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
                            if c not in ('nan', 'index')]
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
        history = MR.breadth_history('us_total_market')
        history_file = ('breadth', 'us_total_market')
        if history is not None:
            render_zweig_section(history, 'sp_sec', 'US Market', show_sector=True)
        else:
            st.warning("No breadth history found — run US breadth script first")

    with tab3:
        st.subheader("S&P 500 Benchmark")
        st.markdown("""
            <div class="info-card">
                Ranks US stocks by relative strength versus <b style="color:#ccc">SPY</b> (S&P 500 ETF).
                Same regime and scoring methodology as AU Benchmark.
                <b style="color:#ccc">Acc Watch</b> signals are particularly useful in the US market — large/mid cap institutional accumulation below key SMAs often precedes significant moves.
                Filter by sector to identify which industries are producing the most leaders relative to the broader market.
            </div>
        """, unsafe_allow_html=True)
        df = MR.formatted('benchmark', 'us_total_market')
        bm_file = ('benchmark', 'us_total_market')  # marketdb key (was a CSV path)
        if df is not None:
            st.caption(f"Last updated: {db_age(*bm_file)} — {len(df)} stocks")
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
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
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
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='us_bm_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='us_bm_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='us_bm_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='us_bm_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No benchmark results found")

    with tab4:
        st.subheader("S&P 500 Sector Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks US stocks by relative strength versus their <b style="color:#ccc">sector peers</b>.
                With 1,500+ stocks the peer group is large — a Peer RS Score above 90 means genuinely exceptional relative performance within the sector.
                Cross-reference with the RRG Charts page to confirm sector-level momentum before drilling into individual names.
            </div>
        """, unsafe_allow_html=True)
        df = MR.formatted('screener', 'us_total_market')
        sc_file = ('screener', 'us_total_market')  # marketdb key (was a CSV path)
        if df is not None:
            st.caption(f"Last updated: {db_age(*sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

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
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='us_sc_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='us_sc_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='us_sc_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='us_sc_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No screener results found — run S&P 500 screener first")

    with tab5:
        st.subheader("Nasdaq 100 Screener")
        st.markdown("""
            <div class="info-card">
                Ranks <b style="color:#ccc">Nasdaq 100</b> stocks by relative strength versus their sector peers <i>within the Nasdaq 100 universe</i>.
                Peer RS scores reflect competition against the highest-quality tech-heavy names — a score above 75 is particularly meaningful here.
            </div>
        """, unsafe_allow_html=True)
        df = MR.formatted('screener', 'nasdaq100')
        ndx_sc_file = ('screener', 'nasdaq100')  # marketdb key (was a CSV path)
        if df is not None:
            st.caption(f"Last updated: {db_age(*ndx_sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            col1, col2, col3 = st.columns(3)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['LEADER','CONTENDER','LAGGARD','WEAK'],
                    default=['LEADER','CONTENDER'],
                    key='ndx_sc_regime')
            with col2:
                sector_filter = st.multiselect("Filter sector",
                    sorted(df['sector'].dropna().unique().tolist()),
                    key='ndx_sc_sector')
            with col3:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='ndx_sc_acc')
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='ndx_sc_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='ndx_sc_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='ndx_sc_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='ndx_sc_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No Nasdaq 100 screener results found — run Nasdaq 100 screener first")

    with tab6:
        st.subheader("Nasdaq Benchmark (All US Stocks vs ^NDX)")
        st.markdown("""
            <div class="info-card">
                Ranks the full US stock universe by relative strength versus the <b style="color:#ccc">Nasdaq 100 (^NDX)</b>.
                Identifies which S&P 500 names are keeping pace with or outperforming the Nasdaq — useful for spotting non-tech leadership and rotation signals.
                <b style="color:#ccc">TREND+LEAD</b> = above 200 SMA and outperforming ^NDX over 12 months.
            </div>
        """, unsafe_allow_html=True)
        df = MR.formatted('benchmark', 'nasdaq100')
        ndx_bm_file = ('benchmark', 'nasdaq100')  # marketdb key (was a CSV path)
        if df is not None:
            st.caption(f"Last updated: {db_age(*ndx_bm_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','sector','cap_band','close',
                    'rs_ratio','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
            cols = [c for c in cols if c in df.columns]

            col1, col2, col3 = st.columns(3)
            with col1:
                regime_filter = st.multiselect("Filter regime",
                    ['TREND+LEAD','TREND_ONLY','WEAK'],
                    default=['TREND+LEAD','TREND_ONLY'],
                    key='ndx_bm_regime')
            with col2:
                sector_filter = st.multiselect("Filter sector",
                    sorted(df['sector'].dropna().unique().tolist()),
                    key='ndx_bm_sector')
            with col3:
                acc_filter = st.multiselect("Filter acc_watch",
                    ['EARLY','PROGRESS','SHIFT','-'],
                    default=[],
                    key='ndx_bm_acc')
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='ndx_bm_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='ndx_bm_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='ndx_bm_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='ndx_bm_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if sector_filter:
                df = df[df['sector'].isin(sector_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No Nasdaq benchmark results found — run Nasdaq benchmark first")

# ═══════════════════════════════════════════════════════════════════════════════
# COMMODITIES PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Commodities":
    marketdb_ready()
    _ph1, _ph2, _ph3, _ph4 = st.columns([900, 5200, 1800, 900])
    with _ph2:
        st.title("⛏ All Major Commodities")
    with _ph3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Update Commodities", key='upd_comm', help="One incremental price update, then screener, benchmark and breadth for every universe on this page"):
            run_marketdb('--universe', 'all_major_commodities', 'uranium', 'au_gold_miners')
            st.rerun()
    with _ph4:
        st.markdown("<br>", unsafe_allow_html=True)

    _main_tabs = st.tabs(["⛏ All Commodities", "🪙 Metals", "⚡ Energy", "🪨 Exposures"])

    with _main_tabs[0]:
        tab1, tab2, tab3 = st.tabs(["Breadth", "Benchmark", "Screener"])

    with tab1:
        st.subheader("Commodities Breadth")
        _hc1, _hc2, _hc3 = st.columns([900, 10000, 900])
        with _hc2:
            st.markdown("""
                <div class="info-card">
                    Breadth analysis across every AU/US stock carrying a commodity exposure — gold, silver, copper, platinum, palladium (Metals) and uranium, lithium, oil &amp; gas (Energy). Each stock is counted under its <b style="color:#ccc">primary</b> exposure (Settings → Commodity Exposures).
                    <b style="color:#ccc">By Commodity</b> shows leader counts and SMA participation per metal — useful for identifying which commodity groups are leading.
                    <b style="color:#ccc">Junior vs Senior Rotation</b> shows large/mid/small cap breakdown within each commodity — junior miners leading seniors is a classic early cycle signal.
                    <b style="color:#ccc">By Type</b> shows producers vs explorers vs ETFs — explorer breadth expanding signals speculative risk appetite returning.
                    <br><span style="color:#666;font-size:16px">💡 Download the breadth history CSV for AI analysis — commodity breadth history is particularly useful for identifying cycle turning points.</span>
                </div>
            """, unsafe_allow_html=True)

        history = MR.breadth_history('all_major_commodities')
        history_file = ('breadth', 'all_major_commodities')

        if history is not None:
            today_str = str(history.iloc[-1]['date'])
            _dc1, _dc2, _dc3 = st.columns([900, 10000, 900])
            with _dc2:
                st.caption(f"Latest: {today_str} — {db_age(*history_file)}")

            # ── Commodity breadth chart (GSCI reference) ──────────────────
            render_breadth_chart(history, prefix='comm', index_ticker='^SPGSCI',
                                 index_label='GSCI — S&P GSCI Commodity Index', key='comm')

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
        df = MR.formatted('benchmark', 'all_major_commodities')
        bm_file = ('benchmark', 'all_major_commodities')  # marketdb key (was a CSV path)
        if df is not None:
            st.caption(f"Last updated: {db_age(*bm_file)} — {len(df)} stocks")
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
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
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
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='comm_bm_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='comm_bm_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='comm_bm_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='comm_bm_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if comm_filter:
                df = df[df['commodity'].isin(comm_filter)]
            if type_filter:
                df = df[df['type'].isin(type_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No benchmark results found")

    with tab3:
        st.subheader("Peer Screener")
        st.markdown("""
            <div class="info-card">
                Ranks commodity stocks by relative strength versus <b style="color:#ccc">commodity peers</b> — gold stocks vs gold stocks, copper vs copper etc.
                Use the commodity filter to focus on a single metal and find the intra-commodity leaders.
                Combined with the Benchmark tab — a stock leading both its commodity peers AND the commodity ETF is the highest conviction name in that metal.
            </div>
        """, unsafe_allow_html=True)

        df = MR.formatted('screener', 'all_major_commodities')
        sc_file = ('screener', 'all_major_commodities')  # marketdb key (was a CSV path)
        if df is not None:
            st.caption(f"Last updated: {db_age(*sc_file)} — {len(df)} stocks")
            cols = ['delta_rank','ticker','name','commodity','type','cap_band','close',
                    'peer_rs_score','rs_trend','ret_6m','ret_12m','max_dd',
                    'vol_label','acc_watch','rsi_div','obv_div','regime_label','score_final']
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
            _n_all = len(df)
            _fv1, _fv2, _fv3, _fv4 = st.columns(4)
            vol_filter = _fv1.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='comm_sc_vol')
            cap_filter = _fv2.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='comm_sc_cap')
            rsi_filter = _fv3.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='comm_sc_rsi')
            obv_filter = _fv4.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='comm_sc_obv')

            if regime_filter:
                df = df[df['regime_label'].isin(regime_filter)]
            if comm_filter:
                df = df[df['commodity'].isin(comm_filter)]
            if type_filter:
                df = df[df['type'].isin(type_filter)]
            if acc_filter:
                df = df[df['acc_watch'].isin(acc_filter)]
            if vol_filter:
                df = df[df['vol_label'].isin(vol_filter)]
            if cap_filter:
                df = df[df['cap_band'].isin(cap_filter)]
            if rsi_filter and 'rsi_div' in df.columns:
                df = df[df['rsi_div'].isin(rsi_filter)]
            if obv_filter and 'obv_div' in df.columns:
                df = df[df['obv_div'].isin(obv_filter)]
            st.caption(f"{len(df)} of {_n_all} stocks after filters")

            st.dataframe(style_df(format_screener_df(df, cols), 'regime_label', 'delta_rank'),
                         width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)
        else:
            st.warning("No screener results found")

# ═══════════════════════════════════════════════════════════════════════════════
# URANIUM PAGE
# ═══════════════════════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════════════════════
    # METALS / ENERGY GROUP TABS — filtered views of the all_major_commodities studies
    # ═══════════════════════════════════════════════════════════════════════════════
    _COMM_LABELS = MU.commodity_labels()
    _COMM_GROUPS = MU.commodity_groups()

    def _comm_region(t):
        return 'AU' if str(t).upper().endswith('.AX') else 'US'

    def _render_commodity_group(gkey, gcfg):
        _comms = gcfg['commodities']
        _lab = lambda k: _COMM_LABELS.get(k, k.title())
        st.title(f"{'🪙' if gkey == 'metals' else '⚡'} {gcfg['name']}")
        st.markdown(f"""
            <div class="info-card">
                {gcfg['name']} names from the all-commodities universe — {', '.join(_lab(c) for c in _comms)}.
                Every stock has one <b style="color:#ccc">primary</b> exposure (its peer group for RS) and may carry
                more: assign them under <b style="color:#ccc">Settings → 🪨 Commodity Exposures</b> (e.g. BHP: copper,
                uranium, silver). Tick <b style="color:#ccc">include secondary exposures</b> to pull in stocks whose
                primary is elsewhere but which carry one of these commodities.
            </div>
        """, unsafe_allow_html=True)

        # ── Filters ───────────────────────────────────────────────────────────
        _f1, _f2, _f3, _f4, _f5 = st.columns([1.2, 2.2, 1.6, 1.6, 1.4])
        _sel_region = _f1.multiselect("Country", ['AU', 'US'], default=['AU', 'US'], key=f'{gkey}_region')
        _sel_comm = _f2.multiselect("Commodity", _comms, default=_comms, format_func=_lab, key=f'{gkey}_comm')
        _sel_type = _f3.multiselect("Type", MU.config().get('commodity_types', []), default=[], key=f'{gkey}_type',
                                    help="Empty = all types")
        _sel_cap = _f4.multiselect("Cap band", ['large', 'mid', 'small'], default=[], key=f'{gkey}_cap',
                                   help="Empty = all bands")
        _incl_secondary = _f5.toggle("Include secondary exposures", value=False, key=f'{gkey}_secondary')

        # tickers carrying any selected commodity as a secondary exposure
        _secondary = set()
        if _incl_secondary and _sel_comm:
            _q = ",".join("?" * len(_sel_comm))
            _secondary = set(mdb.read_df(
                f"SELECT DISTINCT ticker FROM security_groups WHERE group_type='commodity' AND group_key IN ({_q})",
                tuple(_sel_comm))['ticker'])

        def _apply(df):
            if df is None:
                return None
            m = df['commodity'].isin(_sel_comm)
            if _secondary:
                m = m | df['ticker'].isin(_secondary)
            df = df[m]
            if _sel_region:
                df = df[df['ticker'].map(_comm_region).isin(_sel_region)]
            if _sel_type and 'type' in df.columns:
                df = df[df['type'].isin(_sel_type)]
            if _sel_cap:
                df = df[df['cap_band'].isin(_sel_cap)]
            return df

        _t_breadth, _t_bm, _t_sc = st.tabs(["Breadth", "Benchmark", "Screener"])

        # ── Breadth by commodity (subset of the commodity breadth history) ────
        with _t_breadth:
            _h = MR.breadth_history('all_major_commodities')
            if _h is None:
                st.warning("No breadth history found")
            else:
                _today = _h.iloc[-1]
                _ts = str(_today['date'])
                _d5, _d63 = get_past_row(_h, _ts, 7), get_past_row(_h, _ts, 91)
                st.caption(f"Latest: {_ts} — {db_age('breadth', 'all_major_commodities')}")

                def _dl(key, past):
                    try:
                        v = int(_today[key]) - int(past[key])
                        return f"+{v}" if v > 0 else str(v)
                    except Exception:
                        return 'n/a'
                _rows = []
                for ck in _sel_comm:
                    if f'comm_{ck}_total' not in _h.columns:
                        continue
                    _tot = int(_today[f'comm_{ck}_total'])
                    _pct = lambda m: f"{round(int(_today[f'comm_{ck}_{m}']) / _tot * 100, 1)}%" if _tot else '0%'
                    _rows.append({'Commodity': _lab(ck), 'Total': _tot, 'Leaders': int(_today[f'comm_{ck}_leaders']),
                                  'dL5': _dl(f'comm_{ck}_leaders', _d5) if _d5 is not None else 'n/a',
                                  'dL63': _dl(f'comm_{ck}_leaders', _d63) if _d63 is not None else 'n/a',
                                  'Ab20%': _pct('above20'), 'Ab50%': _pct('above50'), 'Ab200%': _pct('above200'),
                                  'HVol': int(_today[f'comm_{ck}_high_vol']), 'AccEarly': int(_today[f'comm_{ck}_acc_early'])})
                if _rows:
                    st.dataframe(style_breadth(pd.DataFrame(_rows), delta_cols=['dL5', 'dL63']),
                                 width='stretch', hide_index=True, height=min(60 + 38 * len(_rows), 400))
                # junior vs senior within each commodity
                _cap_rows = []
                for ck in _sel_comm:
                    for band in ('large', 'mid', 'small'):
                        if f'comm_{ck}_{band}_total' in _h.columns:
                            _cap_rows.append({'Commodity': _lab(ck), 'Band': band,
                                              'Total': int(_today[f'comm_{ck}_{band}_total']),
                                              'Leaders': int(_today[f'comm_{ck}_{band}_leaders']),
                                              'Ab200': int(_today[f'comm_{ck}_{band}_above200']),
                                              'dL5': _dl(f'comm_{ck}_{band}_leaders', _d5) if _d5 is not None else 'n/a',
                                              'dL63': _dl(f'comm_{ck}_{band}_leaders', _d63) if _d63 is not None else 'n/a'})
                if _cap_rows:
                    st.markdown("**Junior vs Senior (cap band within commodity)**")
                    st.dataframe(style_breadth(pd.DataFrame(_cap_rows), delta_cols=['dL5', 'dL63']),
                                 width='stretch', hide_index=True, height=min(60 + 38 * len(_cap_rows), 520))
                _chart_keys = [c for c in _sel_comm if f'comm_{c}_above20' in _h.columns]
                if _chart_keys:
                    _hsub = _h[['date'] + [c for c in _h.columns if any(c.startswith(f'comm_{k}_') for k in _chart_keys)]
                               + [c for c in ('total',) if c in _h.columns]]
                    render_breadth_chart(_hsub, prefix='comm', index_ticker='^SPGSCI',
                                         index_label='GSCI — S&P GSCI Commodity Index', key=f'comm_{gkey}')

        # ── Benchmark / Screener tables ───────────────────────────────────────
        for _tab, _study, _rs_col, _regimes, _def_regimes in (
                (_t_bm, 'benchmark', 'rs_ratio', ['TREND+LEAD', 'TREND_ONLY', 'WEAK'], ['TREND+LEAD', 'TREND_ONLY']),
                (_t_sc, 'screener', 'peer_rs_score', ['LEADER', 'CONTENDER', 'LAGGARD', 'WEAK'], ['LEADER', 'CONTENDER'])):
            with _tab:
                _df = _apply(MR.formatted(_study, 'all_major_commodities'))
                if _df is None:
                    st.warning(f"No {_study} results found")
                    continue
                st.caption(f"Last updated: {db_age(_study, 'all_major_commodities')} — {len(_df)} stocks after filters"
                           + (" (benchmark = each stock's own commodity ETF)" if _study == 'benchmark' else
                              " (peer RS within each stock's primary commodity)"))
                _n_all = len(_df)
                _c1, _c2, _c3, _c4, _c5 = st.columns(5)
                _rf = _c1.multiselect("Filter regime", _regimes, default=_def_regimes, key=f'{gkey}_{_study}_regime')
                _af = _c2.multiselect("Filter acc_watch", ['EARLY', 'PROGRESS', 'SHIFT', '-'], default=[],
                                      key=f'{gkey}_{_study}_acc')
                _vf = _c3.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key=f'{gkey}_{_study}_vol')
                _xf = _c4.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key=f'{gkey}_{_study}_rsi')
                _of = _c5.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key=f'{gkey}_{_study}_obv')
                if _rf:
                    _df = _df[_df['regime_label'].isin(_rf)]
                if _af:
                    _df = _df[_df['acc_watch'].isin(_af)]
                if _vf:
                    _df = _df[_df['vol_label'].isin(_vf)]
                if _xf and 'rsi_div' in _df.columns:
                    _df = _df[_df['rsi_div'].isin(_xf)]
                if _of and 'obv_div' in _df.columns:
                    _df = _df[_df['obv_div'].isin(_of)]
                st.caption(f"{len(_df)} of {_n_all} stocks after filters")
                _cols = ['delta_rank', 'ticker', 'name', 'commodity', 'type', 'cap_band', 'close', _rs_col, 'rs_trend',
                         'ret_6m', 'ret_12m', 'max_dd', 'vol_label', 'acc_watch', 'rsi_div', 'obv_div',
                         'regime_label', 'score_final']
                _cols = [c for c in _cols if c in _df.columns]
                st.dataframe(style_df(format_screener_df(_df, _cols), 'regime_label', 'delta_rank'),
                             width='stretch', height=600, column_config=DIVERGENCE_COLUMN_CONFIG)

    with _main_tabs[1]:
        _render_commodity_group('metals', _COMM_GROUPS.get('metals', {'name': 'Metals', 'commodities': []}))

    with _main_tabs[2]:
        _render_commodity_group('energy', _COMM_GROUPS.get('energy', {'name': 'Energy', 'commodities': []}))

    # ═══════════════════════════════════════════════════════════════════════════════
    # EXPOSURES TAB — which commodities each stock carries, and which one is primary
    # ═══════════════════════════════════════════════════════════════════════════════
    with _main_tabs[3]:
        st.title("🪨 Commodity Exposures")
        st.markdown("""
            <div class="info-card">
                A stock can carry any number of commodity exposures (BHP: copper, iron ore, uranium, silver …).
                The <b style="color:#ccc">primary</b> exposure is its peer group for Peer RS and the commodity it is
                listed under; the others make it appear in the Metals / Energy tabs when
                "include secondary exposures" is ticked. Saved to the database <i>and</i> to
                <code>stocks/universe_overrides.json</code>, so the monthly universe refresh keeps them.
            </div>
        """, unsafe_allow_html=True)
        _ce_labels = MU.commodity_labels()
        _ce_types = MU.config().get('commodity_types', ['producer', 'explorer', 'royalty', 'ETF'])
        _ce_c1, _ce_c2 = st.columns([2, 3])
        _ce_q = _ce_c1.text_input("Find a stock (ticker or name)", placeholder="BHP, Pilbara, CCJ …", key='ce_search')
        _ce_sel = None
        if _ce_q.strip():
            _ce_hits = MU.search_securities(_ce_q)
            if _ce_hits is None or len(_ce_hits) == 0:
                _ce_c2.info("No match in the AU/US universe")
            else:
                _ce_opts = [f"{r.ticker} — {r.name} ({r.region}, {r.sector or '—'}{'' if r.active else ', inactive'})"
                            for r in _ce_hits.itertuples()]
                _ce_pick = _ce_c2.selectbox("Match", _ce_opts, key='ce_pick')
                _ce_sel = _ce_pick.split(' — ')[0]
        if _ce_sel:
            _ce_cur = MU.exposures(_ce_sel)
            _cur_keys = _ce_cur['commodity'].tolist() if _ce_cur is not None and len(_ce_cur) else []
            _cur_prim = next((r.commodity for r in _ce_cur.itertuples() if int(r.priority) == 0), None) if _cur_keys else None
            _cur_types = dict(zip(_ce_cur['commodity'], _ce_cur['type'])) if _cur_keys else {}
            st.markdown(f"**{_ce_sel}** — "
                        + (", ".join(f"{_ce_labels.get(k, k)}{' ★' if k == _cur_prim or (not _cur_prim and i == 0) else ''}"
                                     for i, k in enumerate(_cur_keys)) if _cur_keys else "no commodity exposures yet"))
            _e1, _e2, _e3, _e4 = st.columns([3, 1.6, 1.4, 1.2])
            _new_keys = _e1.multiselect("Commodities", list(_ce_labels.keys()), default=_cur_keys,
                                        format_func=lambda k: _ce_labels[k], key=f'ce_multi_{_ce_sel}')
            _prim_opts = _new_keys or []
            _prim_default = _cur_prim if _cur_prim in _prim_opts else (_prim_opts[0] if _prim_opts else None)
            _new_prim = _e2.selectbox("Primary", _prim_opts, index=_prim_opts.index(_prim_default) if _prim_default else 0,
                                      format_func=lambda k: _ce_labels[k], key=f'ce_prim_{_ce_sel}') if _prim_opts else None
            _type_default = _cur_types.get(_new_prim) or 'producer'
            _new_type = _e3.selectbox("Type", _ce_types, index=_ce_types.index(_type_default) if _type_default in _ce_types else 0,
                                      key=f'ce_type_{_ce_sel}', help="Applied to the exposures you add; existing ones keep theirs")
            _e4.markdown("<br>", unsafe_allow_html=True)
            if _e4.button("💾 Save", type="primary", key=f'ce_save_{_ce_sel}'):
                for k in [k for k in _cur_keys if k not in _new_keys]:
                    MU.remove_exposure(_ce_sel, k)
                for k in _new_keys:
                    MU.set_exposure(_ce_sel, k, _cur_types.get(k) or _new_type, primary=(k == _new_prim))
                st.success(f"{_ce_sel}: " + (", ".join(f"{_ce_labels[k]}{' ★' if k == _new_prim else ''}" for k in _new_keys)
                                             if _new_keys else "all exposures removed"))
                st.rerun()
            st.caption("Membership updates immediately; rankings pick the change up on the next Update Commodities run.")

        st.divider()
        with st.expander("➕ Add a new commodity (iron ore, nickel, coal, rare earths …)", expanded=False):
            st.caption("Registers the commodity in `marketdb/universe_config.json`. Then tag stocks with it above, "
                       "or give it Yahoo industries / name keywords and it is auto-flagged on every universe refresh. "
                       "Without an ETF the group's default benchmark is used (Metals → XME, Energy → XLE, Other → PICK).")
            _nc1, _nc2, _nc3 = st.columns([1.5, 1.5, 1.5])
            _nc_label = _nc1.text_input("Name", placeholder="Iron Ore", key='nc_label')
            _nc_key = _nc2.text_input("Key (slug)", value="", placeholder="iron_ore", key='nc_key',
                                      help="Lower-case identifier used in the database; defaults to the name")
            _nc_groups = MU.commodity_groups()
            _nc_group = _nc3.selectbox("Group", list(_nc_groups.keys()) + ['(new group…)'],
                                       format_func=lambda g: _nc_groups[g]['name'] if g in _nc_groups else g, key='nc_group')
            if _nc_group == '(new group…)':
                _nc_group = st.text_input("New group key", placeholder="bulks", key='nc_newgroup').strip().lower()
            _nc4, _nc5 = st.columns([1.5, 3])
            _nc_bench = _nc4.text_input("Benchmark ETF (optional)", placeholder="e.g. PICK, XME, SLX", key='nc_bench')
            _nc_inds = _nc5.multiselect("Yahoo industries that auto-flag this commodity (optional)",
                                        MU.yahoo_industries(), key='nc_inds')
            _nc_kws = st.text_input("Name keywords for auto-flagging (comma separated, mining names only — optional)",
                                    placeholder="nickel, iron ore", key='nc_kws')
            if st.button("➕ Create commodity", type="primary", key='nc_create'):
                _k = (_nc_key or _nc_label).strip()
                if not _k:
                    st.error("Give the commodity a name")
                elif not _nc_group:
                    st.error("Choose or name a group")
                else:
                    try:
                        MU.add_commodity(_k, _nc_label or _k, _nc_group, benchmark=_nc_bench or None,
                                         industries=_nc_inds, keywords=[w for w in _nc_kws.split(',') if w.strip()])
                        if _nc_bench.strip():
                            from marketdb import fetch as MF
                            with mdb.session() as _con:
                                _ok = MF.ensure_securities([_nc_bench.strip().upper()], _con, role='benchmark')
                                if _ok:
                                    MF.update_prices(_ok, _con, log=lambda m: None)
                        st.success(f"Commodity '{_k}' created in group '{_nc_group}'. Tag stocks with it above, or run auto-flags.")
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Could not create commodity: {_e}")
            if st.button("⚙ Apply auto-flags now (industries / keywords, no network)", key='nc_autoflag'):
                from marketdb import refresh_universe as MRU
                with mdb.session() as _con:
                    _n = MRU.apply_commodity_flags(_con, log=lambda m: None)
                    MRU.apply_overrides(_con, log=lambda m: None)
                st.success(f"Auto-flag pass done ({_n} candidate flags checked). Run Update Commodities to re-rank.")

        st.divider()
        # ── Secondary exposures from Yahoo business summaries ─────────────────
        from marketdb import summary_scan as MSS
        with st.expander("🔎 Secondary exposures from business summaries", expanded=True):
            st.caption("Reads each flagged stock's Yahoo business summary (stored in the database, refreshed every "
                       f"{MSS.cfg()['max_age_days']} days) and lists commodities it mentions that the stock is not yet "
                       "flagged with — a gold miner with a lithium project, a silver-copper producer, PGM by-products. "
                       "Tick the ones that are real and apply them as **secondary** exposures (the primary never changes). "
                       "Keywords live in `universe_config.json` → `summary_scan`.")
            _ss1, _ss2, _ss3 = st.columns([2, 2, 3])
            _ss_src = ", ".join(_ce_labels.get(k, k) for k in MSS.cfg()['source_commodities'])
            if _ss1.button(f"🔎 Scan {_ss_src} stocks", key='ss_scan',
                           help="First run downloads the summaries (~6 min for ~650 stocks); later runs are instant"):
                run_marketdb(module='marketdb.summary_scan', label="Fetching summaries and scanning…")
                st.rerun()
            if _ss2.button("🔎 Scan every commodity stock", key='ss_scan_all',
                           help="All commodity-flagged AU/US stocks (~1,300) — first run ~12 min"):
                run_marketdb('--all', module='marketdb.summary_scan', label="Fetching summaries and scanning…")
                st.rerun()
            _ss_cands, _ss_date = MSS.latest_candidates()
            if _ss_cands is None:
                _ss3.info("No scan yet")
            else:
                _have = mdb.read_df("SELECT ticker, group_key FROM security_groups WHERE group_type='commodity'")
                _have_set = set(zip(_have['ticker'], _have['group_key']))
                _rej = {(g['ticker'], g['group_key']) for g in (MU.load_overrides() or {}).get('remove_groups', [])
                        if g.get('group_type') == 'commodity'}
                if len(_ss_cands):
                    _ss_open = _ss_cands[[(t, c) not in _have_set and (t, c) not in _rej
                                          for t, c in zip(_ss_cands['ticker'], _ss_cands['commodity'])]].copy()
                else:
                    _ss_open = _ss_cands
                _ss3.markdown(f"Last scan **{_ss_date}** — {len(_ss_cands)} candidates, **{len(_ss_open)} awaiting review**")
                if len(_ss_open):
                    _ss_f1, _ss_f2, _ss_f3 = st.columns([2, 1.5, 2.5])
                    _ss_comm_f = _ss_f1.multiselect("Commodity", sorted(_ss_open['commodity'].unique()),
                                                    format_func=lambda k: _ce_labels.get(k, k), key='ss_comm_f')
                    _ss_cap_f = _ss_f2.multiselect("Cap band", ['large', 'mid', 'small', 'ETF'], key='ss_cap_f')
                    _ss_min = _ss_f3.slider("Minimum mentions", 1, int(max(1, _ss_open['hits'].max())), 1, key='ss_min')
                    _ss_view = _ss_open[_ss_open['hits'] >= _ss_min]
                    if _ss_comm_f:
                        _ss_view = _ss_view[_ss_view['commodity'].isin(_ss_comm_f)]
                    if _ss_cap_f and 'cap_band' in _ss_view.columns:
                        _ss_view = _ss_view[_ss_view['cap_band'].isin(_ss_cap_f)]
                    _ss_view = _ss_view.assign(apply=True,
                                               commodity_label=_ss_view['commodity'].map(lambda k: _ce_labels.get(k, k)),
                                               primary_label=_ss_view['primary'].map(lambda k: _ce_labels.get(k, k)))
                    _ss_edit = st.data_editor(
                        _ss_view[[c for c in ['apply', 'ticker', 'name', 'cap_band', 'primary_label', 'commodity_label',
                                               'primary_type', 'hits', 'snippet'] if c in _ss_view.columns]],
                        hide_index=True, width='stretch', height=min(60 + 36 * len(_ss_view), 520),
                        disabled=['ticker', 'name', 'cap_band', 'primary_label', 'commodity_label', 'primary_type', 'hits', 'snippet'],
                        column_config={'apply': st.column_config.CheckboxColumn('apply', width='small'),
                                       'primary_label': st.column_config.TextColumn('primary'),
                                       'commodity_label': st.column_config.TextColumn('secondary'),
                                       'primary_type': st.column_config.TextColumn('type'),
                                       'snippet': st.column_config.TextColumn('summary excerpt', width='large')},
                        key=f'ss_editor_{_ss_date}')
                    _ss_ticked = _ss_view.loc[_ss_edit['apply'].values]
                    _ss_unticked = _ss_view.loc[~_ss_edit['apply'].values]
                    _ss_b1, _ss_b2, _ss_b3 = st.columns([2, 2.5, 3])
                    if _ss_b1.button(f"✅ Apply {len(_ss_ticked)} ticked as secondary", type="primary", key='ss_apply',
                                     disabled=len(_ss_ticked) == 0):
                        with mdb.session() as _con:
                            _n = MSS.apply(_ss_ticked, _con, log=lambda m: None)
                        st.success(f"{_n} secondary exposures added (source = summary). Run Update Commodities to re-rank.")
                        st.rerun()
                    if _ss_b2.button(f"✖ Reject {len(_ss_unticked)} unticked (won't reappear)", key='ss_reject',
                                     disabled=len(_ss_unticked) == 0):
                        for _r in _ss_unticked.itertuples():
                            MU.remove_exposure(_r.ticker, _r.commodity)
                        st.success(f"{len(_ss_unticked)} candidates rejected — recorded in universe_overrides.json")
                        st.rerun()
                    _ss_b3.caption("Rejections are stored as `remove_groups` overrides; un-reject by editing that file.")

        st.divider()
        _ce_manual = mdb.read_df("""SELECT g.ticker, s.name, g.group_key AS commodity, g.attr AS type, g.source, g.priority, g.updated
                                    FROM security_groups g LEFT JOIN securities s ON s.ticker=g.ticker
                                    WHERE g.group_type='commodity' AND g.source IN ('manual', 'summary')
                                    ORDER BY g.ticker, g.priority""")
        _n_man = int((_ce_manual['source'] == 'manual').sum()) if len(_ce_manual) else 0
        _n_sum = int((_ce_manual['source'] == 'summary').sum()) if len(_ce_manual) else 0
        st.markdown(f"**Exposures on record — {_n_man} manual, {_n_sum} from business summaries**")
        if len(_ce_manual):
            _ce_manual['commodity'] = _ce_manual['commodity'].map(lambda k: _ce_labels.get(k, k))
            _ce_manual['primary'] = _ce_manual['priority'].map(lambda p: '★' if int(p) == 0 else '')
            st.dataframe(_ce_manual.drop(columns=['priority']), width='stretch', hide_index=True,
                         height=min(60 + 38 * len(_ce_manual), 400))
        _ce_groups = MU.commodity_groups()
        st.caption("Groups: " + " · ".join(f"**{g['name']}** = {', '.join(_ce_labels.get(c, c) for c in g['commodities'])}"
                                          for g in _ce_groups.values() if g.get('commodities'))
                   + "  (edit in `marketdb/universe_config.json`)")

elif page == "Relative Strength Charts":
    marketdb_ready()
    import plotly.graph_objects as go

    _rh1, _rh2 = st.columns([5200, 1800])
    with _rh1:
        st.title("📡 Relative Rotation Graph")
        st.caption("RS-Ratio vs RS-Momentum — tails show last 63 trading days")
    with _rh2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Update RRG data", key='upd_rrg', help="Incremental price update, then all four RRG studies"):
            run_marketdb('--studies', 'rrg')
            st.rerun()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🇦🇺 AU vs XJO", "🇺🇸 US vs SPY/RSP", "📈 Dow 30 vs DJI",
        "🇦🇺 AU Breadth RRG", "🇺🇸 US Breadth RRG", "⛏ Comm Breadth RRG",
        "⚙️ Custom RRG"
    ])

    def build_rrg(rrg_study, title):
        history = MR.rrg_history(rrg_study)
        if history is None or len(history) == 0:
            st.warning(f"No RRG data found — run data collection script first")
            return

        history['date'] = pd.to_datetime(history['date'])
        latest_date     = history['date'].max()
        st.caption(f"Latest: {latest_date.strftime('%d %b %Y')} — {db_age('rrg', rrg_study)}")

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
            smooth_span = st.slider("Smoothing (EWM span)", 1, 20, 4, key=f"span_{title}")
        with col4:
            all_tickers = sorted(history['ticker'].unique().tolist())
            sel_tickers = st.multiselect("Filter tickers", all_tickers, default=[],
                                          key=f"tick_{title}", placeholder="All tickers")

        # Filter by date window and group/ticker
        cutoff_from = latest_date - pd.Timedelta(days=int(tail_from * 1.5))
        cutoff_to   = latest_date - pd.Timedelta(days=max(0, tail_to - 1))
        df      = history[(history['date'] >= cutoff_from) & (history['date'] <= cutoff_to + pd.Timedelta(days=2))].copy()
        # Cap to tail_from rows per ticker
        df      = df.sort_values(['ticker', 'date']).groupby('ticker', group_keys=False).tail(tail_from)
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
            st.plotly_chart(fig, width='stretch')

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

        _png_ss_key = f"png_rrg_{title}"
        if st.button(f"📸 Render PNG ({tail_days}d tail)", key=f"prep_rrg_{title}"):
            with st.spinner("Rendering PNG…"):
                st.session_state[_png_ss_key] = fig_export.to_image(format='png', width=2400, height=1000, scale=2)
        if _png_ss_key in st.session_state:
            st.download_button(
                label     = f"⬇ Download PNG",
                data      = st.session_state[_png_ss_key],
                file_name = f"rrg_{title.replace(' ','_').replace('/','_')}_{tail_to}to{tail_from}d_{datetime.today().strftime('%Y%m%d')}.png",
                mime      = 'image/png',
                key       = f"dl_rrg_{title}"
            )

    with tab1:
        build_rrg('au', 'AU Sectors & ETFs vs XJO')

    with tab2:
        _spy_rsp = st.toggle("Use RSP (equal-weight) benchmark", value=False, key='rrg_us_rsp',
                             help="SPY = cap-weighted S&P 500 | RSP = equal-weight S&P 500")
        if _spy_rsp:
            _us_study = 'us_rsp'
            _us_title = 'US Sectors & ETFs vs RSP (Equal Weight)'
        else:
            _us_study = 'us'
            _us_title = 'US Sectors & ETFs vs SPY'
        build_rrg(_us_study, _us_title)

    with tab3:
        build_rrg('dow', 'Dow 30 vs DJI')

# ═══════════════════════════════════════════════════════════════════════════════
# BREADTH RRG PAGE
# ═══════════════════════════════════════════════════════════════════════════════

    def build_breadth_rrg(hist_df, sector_keys, prefix, sma_col, title, tail_days=20, smooth_span=3):
        """
        Build breadth RRG from history CSV.
        Columns: sec_{key}_leaders, sec_{key}_total, sec_{key}_above20/50/200
        RS-Ratio  = (leaders/total)*100 normalised vs universe mean
        RS-Momentum = rate of change of RS-Ratio
        """
        import plotly.graph_objects as go
        if hist_df is None or len(hist_df) < 5:
            st.warning("Insufficient breadth history data.")
            return
        hist_df = hist_df.copy()
        hist_df['date'] = pd.to_datetime(hist_df['date'])
        hist_df = hist_df.sort_values('date').reset_index(drop=True)

        # Use selected SMA col or leaders as signal
        sma_suffix_map = {'above20': 'above20', 'above50': 'above50', 'above200': 'above200'}
        sig_suffix = sma_suffix_map.get(sma_col, 'above50')

        # Build RS series for each sector
        rs_series = {}
        for sk in sector_keys:
            total_col = f'{prefix}_{sk}_total'
            sig_col   = f'{prefix}_{sk}_{sig_suffix}'
            if total_col not in hist_df.columns or sig_col not in hist_df.columns:
                # Try leaders as fallback
                sig_col = f'{prefix}_{sk}_leaders'
                if sig_col not in hist_df.columns: continue
            tot = pd.to_numeric(hist_df[total_col], errors='coerce')
            sig = pd.to_numeric(hist_df[sig_col],   errors='coerce')
            mask = tot > 0
            pct = pd.Series(index=hist_df.index, dtype=float)
            pct[mask] = (sig[mask] / tot[mask]) * 100
            rs_series[sk] = pct.ffill()

        if not rs_series:
            st.warning("No matching sector columns found.")
            return

        rs_df = pd.DataFrame(rs_series, index=hist_df.index)
        # Normalise: RS-Ratio = sector pct / universe mean pct * 100
        univ_mean = rs_df.mean(axis=1).replace(0, float('nan'))
        rs_norm = rs_df.divide(univ_mean, axis=0) * 100

        # Smooth
        rs_smooth = rs_norm.ewm(span=smooth_span, adjust=False).mean()

        # RS-Momentum = 1-period change of smoothed RS
        rs_mom = rs_smooth.diff(1)
        rs_mom_smooth = rs_mom.ewm(span=smooth_span, adjust=False).mean()

        # Normalise momentum around 100
        mom_mean = rs_mom_smooth.mean()
        mom_std  = rs_mom_smooth.std().replace(0, 1)
        rs_mom_norm = (rs_mom_smooth - mom_mean) / mom_std * 10 + 100

        # Get tail window
        tail = min(tail_days, len(rs_smooth))
        rs_tail   = rs_smooth.iloc[-tail:]
        mom_tail  = rs_mom_norm.iloc[-tail:]

        fig   = go.Figure()
        theme = get_chart_theme()
        COLOURS = ['#00b4d8','#f77f00','#2dc653','#e63946','#9b5de5',
                   '#f15bb5','#fee440','#06d6a0','#118ab2','#ef476f',
                   '#aacc00','#48cae4','#fcbf49','#c77dff','#ff6b6b',
                   '#e63946','#80b918','#c77dff','#ff6b6b','#48cae4']

        for i, sk in enumerate(sector_keys):
            if sk not in rs_tail.columns: continue
            x = rs_tail[sk].dropna()
            y = mom_tail[sk].reindex(x.index).dropna()
            x = x.reindex(y.index)
            if len(x) < 2: continue
            col   = COLOURS[i % len(COLOURS)]
            label = sk.replace('_', ' ').title()
            # Tail line
            fig.add_trace(go.Scatter(
                x=x.values, y=y.values, mode='lines',
                line=dict(width=1.5, color=col), opacity=0.6,
                showlegend=False, hoverinfo='skip'
            ))
            # Latest dot + label
            fig.add_trace(go.Scatter(
                x=[x.iloc[-1]], y=[y.iloc[-1]],
                mode='markers+text', text=[label], textposition='top center',
                textfont=dict(size=9, color=col),
                marker=dict(size=9, color=col,
                            line=dict(width=1, color='rgba(255,255,255,0.5)')),
                name=label,
                hovertemplate=f"<b>{label}</b><br>RS-Ratio: %{{x:.1f}}<br>RS-Mom: %{{y:.1f}}<extra></extra>"
            ))

        fig.add_hline(y=100, line_dash="dash", line_color="rgba(128,128,128,0.5)", line_width=1)
        fig.add_vline(x=100, line_dash="dash", line_color="rgba(128,128,128,0.5)", line_width=1)

        # Dynamic axis range
        all_x = [t for tr in fig.data for t in (list(tr.x) if tr.x is not None else [])]
        all_y = [t for tr in fig.data for t in (list(tr.y) if tr.y is not None else [])]
        xr = [min(all_x or [95])-2, max(all_x or [105])+2]
        yr = [min(all_y or [95])-2, max(all_y or [105])+2]

        fig.update_layout(
            plot_bgcolor=theme['plot_bgcolor'], paper_bgcolor=theme['paper_bgcolor'],
            font=dict(color=theme['font_color']),
            xaxis=dict(title="RS-Ratio (breadth vs universe)", gridcolor=theme['gridcolor'],
                       zeroline=False, range=xr),
            yaxis=dict(title="RS-Momentum", gridcolor=theme['gridcolor'],
                       zeroline=False, range=yr),
            title=dict(text=title, font=dict(size=14)),
            height=650, showlegend=True,
            legend=dict(x=1.01, y=1, font=dict(size=9)),
            margin=dict(l=60, r=160, t=60, b=40),
        )
        xmid = (xr[0]+xr[1])/2
        ymid = (yr[0]+yr[1])/2
        for txt, x, y in [("Leading",xmid+0.5,ymid+0.5),("Weakening",xmid-0.5,ymid+0.5),
                           ("Lagging",xmid-0.5,ymid-0.5),("Improving",xmid+0.5,ymid-0.5)]:
            fig.add_annotation(x=x, y=y, text=txt, showarrow=False,
                               font=dict(size=10, color="rgba(128,128,128,0.5)"),
                               xanchor='center', yanchor='middle')
        st.plotly_chart(fig, width='stretch')

    with tab4:
        au_hist = MR.breadth_history('au_total_market')
        au_hist_file = ('breadth', 'au_total_market')
        if au_hist is not None:
            sec_cols = [c for c in au_hist.columns if c.startswith('sec_') and c.endswith('_total')
                        and not c.startswith('sp_') and not c.startswith('rus_')]
            sec_keys = [c.replace('sec_','').replace('_total','') for c in sec_cols
                        if c not in ('nan', 'index')]

            st.caption(f"Latest: {au_hist.iloc[-1]['date']} — {db_age(*au_hist_file)}")

            _bc1, _bc2, _bc3 = st.columns(3)
            sma_choice    = _bc1.radio("SMA Level", ["Above 20", "Above 50", "Above 200"],
                                        horizontal=True, key='brrg_au_sma')
            _brrg_tail    = _bc2.slider("Tail days", 5, 63, 20, key='brrg_au_tail')
            _brrg_smooth  = _bc3.slider("Smoothing", 1, 20, 5, key='brrg_au_smooth')
            sma_col_map   = {"Above 20": "above20", "Above 50": "above50", "Above 200": "above200"}
            sma_col       = sma_col_map[sma_choice]

            build_breadth_rrg(au_hist, sec_keys, 'sec', sma_col,
                              f'AU Sector Breadth — {sma_choice} SMA', _brrg_tail, _brrg_smooth)
        else:
            st.warning("No AU breadth history found — run AU breadth script first")

    # ── US ─────────────────────────────────────────────────────────────────────

    with tab5:
        us_hist = MR.breadth_history('us_total_market')
        us_hist_file = ('breadth', 'us_total_market')
        if us_hist is not None:
            sp_cols = [c for c in us_hist.columns if c.startswith('sp_sec_') and c.endswith('_total')]
            sp_keys = [c.replace('sp_sec_','').replace('_total','') for c in sp_cols
                       if c not in ('nan', 'index')]

            st.caption(f"Latest: {us_hist.iloc[-1]['date']} — {db_age(*us_hist_file)}")

            sma_choice = st.radio("SMA Level", ["Above 20", "Above 50", "Above 200"],
                                   horizontal=True, key='brrg_us_sma')
            sma_col_map = {"Above 20": "above20", "Above 50": "above50", "Above 200": "above200"}
            sma_col = sma_col_map[sma_choice]

            _bc1b, _bc2b, _bc3b = st.columns(3)
            _brrg_tail_us   = _bc2b.slider("Tail days", 5, 63, 20, key='brrg_us_tail')
            _brrg_smooth_us = _bc3b.slider("Smoothing", 1, 20, 5, key='brrg_us_smooth')
            build_breadth_rrg(us_hist, sp_keys, 'sp_sec', sma_col,
                              f'US Sector Breadth — {sma_choice} SMA', _brrg_tail_us, _brrg_smooth_us)
        else:
            st.warning("No US breadth history found — run US breadth script first")

    # ── Commodities ────────────────────────────────────────────────────────────

    with tab6:
        comm_hist = MR.breadth_history('all_major_commodities')
        comm_hist_file = ('breadth', 'all_major_commodities')
        if comm_hist is not None:
            comm_cols = [c for c in comm_hist.columns if c.startswith('comm_') and c.endswith('_total')
                         and c.count('_') == 2]
            comm_keys = [c.replace('comm_','').replace('_total','') for c in comm_cols]

            st.caption(f"Latest: {comm_hist.iloc[-1]['date']} — {db_age(*comm_hist_file)}")

            sma_choice = st.radio("SMA Level", ["Above 20", "Above 50", "Above 200"],
                                   horizontal=True, key='brrg_comm_sma')
            sma_col_map = {"Above 20": "above20", "Above 50": "above50", "Above 200": "above200"}
            sma_col = sma_col_map[sma_choice]

            _bc1c, _bc2c, _bc3c = st.columns(3)
            _brrg_tail_cm   = _bc2c.slider("Tail days", 5, 63, 20, key='brrg_cm_tail')
            _brrg_smooth_cm = _bc3c.slider("Smoothing", 1, 20, 5, key='brrg_cm_smooth')
            build_breadth_rrg(comm_hist, comm_keys, 'comm', sma_col,
                              f'Commodity Breadth — {sma_choice} SMA', _brrg_tail_cm, _brrg_smooth_cm)
        else:
            st.warning("No commodities breadth history found — run commodities breadth script first")

# ═══════════════════════════════════════════════════════════════════════════════
# DRAWDOWN ANALYSIS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

    # ── Custom RRG ─────────────────────────────────────────────────────────────
    with tab7:
        import plotly.graph_objects as go

        st.markdown("#### Custom RRG — Specify Benchmark + Universe")

        _cc1, _cc2, _cc3 = st.columns([2,2,2])
        _custom_bm = _cc1.text_input("Benchmark ticker", value="^GSPC",
                                      placeholder="e.g. ^AXJO, SPY, GLD",
                                      key="custom_rrg_bm").strip().upper()
        _custom_tail   = _cc2.slider("Tail days", 1, 63, 20, key="custom_rrg_tail")
        _custom_smooth = _cc3.slider("Smoothing", 1, 10, 3, key="custom_rrg_smooth")

        st.markdown("**Universe**")
        _cu1, _cu2 = st.columns([3,2])
        _ug_source = _cu1.radio("Source", ["Watchlist", "Manual tickers", "AU Sectors", "US Sectors"],
                                 horizontal=True, key="custom_rrg_src")

        _custom_tickers = []
        if _ug_source == "Watchlist":
            _wl_keys_rrg  = list(UNIVERSE_LABELS.keys())
            _wl_sel_rrg   = st.selectbox("Universe", _wl_keys_rrg, format_func=lambda k: UNIVERSE_LABELS[k],
                                         key="custom_rrg_wl")

            if _wl_sel_rrg:
                try:
                    _wl_df_rrg = db_universe_members(_wl_sel_rrg)
                    _bm_rrg = MR.latest('benchmark', _wl_sel_rrg)
                    if _bm_rrg is not None:
                        _wl_df_rrg = _wl_df_rrg.merge(_bm_rrg[['ticker', 'regime_label']], on='ticker', how='left')
                    # Filters
                    _fc1, _fc2, _fc3 = st.columns(3)
                    _sect_opts = sorted(_wl_df_rrg['sector'].dropna().unique().tolist()) if 'sector' in _wl_df_rrg.columns else []
                    _cap_opts  = sorted(_wl_df_rrg['cap_band'].dropna().unique().tolist()) if 'cap_band' in _wl_df_rrg.columns else []
                    _reg_opts  = sorted(_wl_df_rrg['regime_label'].dropna().unique().tolist()) if 'regime_label' in _wl_df_rrg.columns else []

                    _f_sect = _fc1.multiselect("Sector filter",   _sect_opts, key="custom_rrg_sect")
                    _f_cap  = _fc2.multiselect("Cap band filter", _cap_opts,  key="custom_rrg_cap")
                    _f_reg  = _fc3.multiselect("Regime filter",   _reg_opts,  key="custom_rrg_reg")

                    _fdf = _wl_df_rrg.copy()
                    if _f_sect and 'sector'       in _fdf.columns: _fdf = _fdf[_fdf['sector'].isin(_f_sect)]
                    if _f_cap  and 'cap_band'     in _fdf.columns: _fdf = _fdf[_fdf['cap_band'].isin(_f_cap)]
                    if _f_reg  and 'regime_label' in _fdf.columns: _fdf = _fdf[_fdf['regime_label'].isin(_f_reg)]

                    _ticker_col = 'ticker' if 'ticker' in _fdf.columns else _fdf.columns[0]
                    _custom_tickers = _fdf[_ticker_col].dropna().tolist()[:20]
                    st.caption(f"{len(_custom_tickers)} tickers selected (max 20)")
                except Exception as _e:
                    st.warning(f"Could not read watchlist: {_e}")
        elif _ug_source == "Manual tickers":
            _manual_input = st.text_area("Enter tickers (one per line or comma-separated)",
                                          height=100, key="custom_rrg_manual",
                                          placeholder="BHP.AX, CBA.AX, RIO.AX")
            _custom_tickers = [t.strip().upper() for t in
                                _manual_input.replace(',',' ').split() if t.strip()][:20]
            if _custom_tickers:
                st.caption(f"{len(_custom_tickers)} tickers entered")

        elif _ug_source in ("AU Sectors", "US Sectors"):
            _rrg_h2 = MR.rrg_history('au' if _ug_source == "AU Sectors" else 'us')
            if _rrg_h2 is not None:
                if True:
                    _sect_opts2 = sorted(_rrg_h2['name'].dropna().unique().tolist()) if 'name' in _rrg_h2.columns else                                   sorted(_rrg_h2['ticker'].dropna().unique().tolist())
                    _f_sect2 = st.multiselect("Filter by sector/instrument", _sect_opts2, key="custom_rrg_sect2")
                    if _f_sect2:
                        _name_col = 'name' if 'name' in _rrg_h2.columns else 'ticker'
                        _fh2 = _rrg_h2[_rrg_h2[_name_col].isin(_f_sect2)]
                    else:
                        _fh2 = _rrg_h2
                    _custom_tickers = _fh2['ticker'].dropna().unique().tolist()[:20]
                    st.caption(f"{len(_custom_tickers)} tickers | last: {_rrg_h2['date'].max()}")
            else:
                st.warning(f"No {_ug_source} RRG history found — run data collection first")

        # Submit button to avoid constant re-fetching
        _run_custom = st.button("▶ Build RRG", type="primary", key="custom_rrg_run")

        if _run_custom and _custom_tickers:
            _fig_crrg = go.Figure()
            _theme    = get_chart_theme()
            _COLOURS  = ['#00b4d8','#f77f00','#2dc653','#e63946','#9b5de5',
                          '#f15bb5','#fee440','#06d6a0','#118ab2','#ef476f',
                          '#aacc00','#48cae4','#fcbf49','#c77dff','#ff6b6b']

            if _ug_source in ("AU Sectors", "US Sectors"):
                # Use pre-computed history files
                _rrg_h = MR.rrg_history('au' if _ug_source == "AU Sectors" else 'us')
                if _rrg_h is not None:
                    _rrg_h['date'] = pd.to_datetime(_rrg_h['date'])
                    _rrg_h  = _rrg_h[_rrg_h['ticker'].isin(_custom_tickers)].sort_values('date')
                    for _i, _tk in enumerate(_custom_tickers):
                        _tdf = _rrg_h[_rrg_h['ticker']==_tk].tail(_custom_tail)
                        if len(_tdf) < 2: continue
                        _rs  = _tdf['rs_ratio'].ewm(span=_custom_smooth, adjust=False).mean()
                        _mom = _tdf['rs_momentum'].ewm(span=_custom_smooth, adjust=False).mean()
                        _lbl = _tdf['name'].iloc[-1] if 'name' in _tdf.columns else _tk
                        _col = _COLOURS[_i % len(_COLOURS)]
                        _fig_crrg.add_trace(go.Scatter(
                            x=_rs.values, y=_mom.values, mode='lines',
                            line=dict(width=1.5, color=_col), opacity=0.5,
                            showlegend=False, hoverinfo='skip'))
                        _fig_crrg.add_trace(go.Scatter(
                            x=[_rs.iloc[-1]], y=[_mom.iloc[-1]],
                            mode='markers+text', text=[_lbl], textposition='top center',
                            textfont=dict(size=9, color=_col),
                            marker=dict(size=9, color=_col), name=_lbl,
                            hovertemplate=f"<b>{_lbl}</b><br>RS: %{{x:.2f}}<br>Mom: %{{y:.2f}}<extra></extra>"))
                else:
                    st.error("Could not load sector RRG history — run data collection first")

            else:
                # Watchlist/Manual: fetch live from yfinance
                _price_df = _fetch_custom_rrg(_custom_bm, _custom_tickers,
                                               _custom_tail, _custom_smooth)
                if _price_df is None or _custom_bm not in _price_df.columns:
                    st.error(f"Could not fetch data for benchmark {_custom_bm}")
                else:
                    _bm_series = _price_df[_custom_bm].dropna()
                    for _i, _tk in enumerate(_custom_tickers):
                        if _tk not in _price_df.columns: continue
                        _tk_s  = _price_df[_tk].dropna()
                        _common = _tk_s.index.intersection(_bm_series.index)
                        if len(_common) < 10: continue
                        _rs_raw    = _tk_s[_common] / _bm_series[_common]
                        _rs_norm   = (_rs_raw / _rs_raw.mean()) * 100
                        _rs_smooth = _rs_norm.ewm(span=_custom_smooth, adjust=False).mean()
                        _rs_mom    = _rs_smooth.pct_change(5) * 100
                        _rs_mom_s  = _rs_mom.ewm(span=_custom_smooth, adjust=False).mean()
                        _rs_mom_n  = (_rs_mom_s / _rs_mom_s.abs().mean() * 10 + 100)
                        _tail_rs   = _rs_smooth.iloc[-_custom_tail:]
                        _tail_mom  = _rs_mom_n.reindex(_tail_rs.index)
                        if _tail_rs.isna().all() or _tail_mom.isna().all(): continue
                        _col = _COLOURS[_i % len(_COLOURS)]
                        _fig_crrg.add_trace(go.Scatter(
                            x=_tail_rs.values, y=_tail_mom.values, mode='lines',
                            line=dict(width=1.5, color=_col), opacity=0.5,
                            showlegend=False, hoverinfo='skip'))
                        _fig_crrg.add_trace(go.Scatter(
                            x=[_tail_rs.iloc[-1]], y=[_tail_mom.iloc[-1]],
                            mode='markers+text', text=[_tk], textposition='top center',
                            textfont=dict(size=9, color=_col),
                            marker=dict(size=9, color=_col), name=_tk,
                            hovertemplate=f"<b>{_tk}</b><br>RS: %{{x:.2f}}<br>Mom: %{{y:.2f}}<extra></extra>"))
                    _missing = [t for t in _custom_tickers if t not in _price_df.columns]
                    if _missing:
                        st.caption(f"Not found: {', '.join(_missing)}")

            # Shared chart layout
            _bm_label = _ug_source if _ug_source in ("AU Sectors","US Sectors") else _custom_bm
            _fig_crrg.add_hline(y=100, line_dash="dash", line_color="rgba(128,128,128,0.4)", line_width=1)
            _fig_crrg.add_vline(x=100, line_dash="dash", line_color="rgba(128,128,128,0.4)", line_width=1)
            _fig_crrg.update_layout(
                plot_bgcolor=_theme['plot_bgcolor'], paper_bgcolor=_theme['paper_bgcolor'],
                font=dict(color=_theme['font_color']),
                xaxis=dict(title=f"RS-Ratio vs {_bm_label}", gridcolor=_theme['gridcolor'],
                           zeroline=False, range=[55, 170]),
                yaxis=dict(title="RS-Momentum", gridcolor=_theme['gridcolor'],
                           zeroline=False, range=[55, 160]),
                title=dict(text=f"Custom RRG — {_bm_label} | Tail: {_custom_tail}d",
                           font=dict(size=14)),
                height=650, showlegend=True,
                legend=dict(orientation='h', yanchor='top', y=-0.08, xanchor='center', x=0.5,
                            font=dict(size=9), bgcolor=_theme['plot_bgcolor'],
                            borderwidth=1, bordercolor=_theme['gridcolor']),
                margin=dict(l=60, r=40, t=60, b=120),
            )
            for _qt, _qx, _qy in [("Leading",112.5,112.5),("Weakening",87.5,112.5),
                                    ("Lagging",87.5,87.5),("Improving",112.5,87.5)]:
                _fig_crrg.add_annotation(x=_qx, y=_qy, text=_qt, showarrow=False,
                                          font=dict(size=10, color="rgba(128,128,128,0.5)"),
                                          xanchor='center', yanchor='middle')
            st.plotly_chart(_fig_crrg, width='stretch')

        elif not _run_custom and _custom_tickers:
            st.info("Press **▶ Build RRG** to generate the chart.")


elif page == "Drawdown Analysis":
    marketdb_ready()
    from marketdb import drawdown as MDD

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
        wl_selected = st.selectbox("Universe", list(UNIVERSE_LABELS.keys()),
                                   format_func=lambda k: UNIVERSE_LABELS[k], key='dd_universe')

    with col2:
        study_name = st.text_input("Study name", value=wl_selected)

    # Universe members for filter options
    wl_preview = db_universe_members(wl_selected)
    filter_col = None
    filter_val = None

    if wl_preview is not None:
        col3, col4 = st.columns(2)
        with col3:
            if wl_preview['commodity'].isna().all():
                sectors     = sorted(wl_preview['sector'].dropna().unique().tolist())
                sector_opts = ['All sectors'] + sectors
                sel_sector  = st.selectbox("Filter by sector", sector_opts)
                if sel_sector != 'All sectors':
                    filter_col = 'sector'
                    filter_val = sel_sector
        with col4:
            if wl_preview['commodity'].notna().any():
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
        bench_override = None
        if filter_col and filter_val:
            _region = wl_preview['region'].mode().iloc[0] if 'region' in wl_preview.columns and len(wl_preview) else None
            bench_override = MDD.sector_benchmark(filter_col, filter_val, _region)
            if bench_override:
                st.info(f"Using sector benchmark: {bench_override} for {filter_val}")
            else:
                st.info(f"No sector ETF mapping found for {filter_val} — using universe benchmark")

        all_periods_data = []
        with st.spinner("Running drawdown analysis from the price store..."):
            try:
                with mdb.session() as _con:
                    all_periods_data = MDD.run_study(
                        wl_selected, periods, _con, study_name=study_name,
                        filter_col=filter_col, filter_val=filter_val,
                        weights=_dd_weights, bench_override=bench_override, log=lambda m: None)
            except Exception as _e:
                st.error(f"Drawdown analysis failed: {_e}")
        for _p in periods:
            if not any(x[3] == _p['label'] for x in all_periods_data):
                st.warning(f"Insufficient data for period {_p['label']} from {_p['date']}")

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

    _studies    = MDD.list_studies()
    study_names = _studies['study'].tolist() if _studies is not None and len(_studies) else []
    study_dirs  = study_names   # legacy name — studies now live in the DB

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
                st.download_button(
                    label     = "⬇ Download Study",
                    data      = MDD.study_zip(dl_selected),
                    file_name = f"{dl_selected}.zip",
                    mime      = 'application/zip',
                    key       = 'dl_study_btn'
                )

    # ── View previous study ───────────────────────────────────────────────────
    if study_dirs:
        selected = st.selectbox("Load previous study", ['-- select --'] + study_names)
        if selected != '-- select --':
            for df, _bench_ret, _bench_dd, _lbl, _start in MDD.load_study(selected):
                label = f"{selected}_{_lbl}_{str(_start).replace('-', '')}_drawdown"
                with st.expander(label, expanded=True):
                    st.caption(f"Benchmark return: {_bench_ret:+.2f}%   Benchmark max DD: {_bench_dd:.2f}%")
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
elif page == "Screeners & Exports":
    marketdb_ready()
    st.title("📋 Screeners & TradingView Exports")
    st.caption("Filtered actionable stocks grouped by market — from the marketdb study results.")

    _all_runs = MR.study_dates_all()
    _run_dates = sorted(set(mdb.read_df("SELECT DISTINCT run_date FROM study_results")['run_date']), reverse=True) \
        if _all_runs is not None and len(_all_runs) else []

    if not _run_dates:
        st.info("No study results found — run the daily update first")
    else:
        dates    = _run_dates
        sel_date = st.selectbox("Select date", dates, key="act_date")
        _pf1, _pf2, _pf3, _pf4, _pf5, _pf6 = st.columns(6)
        _pf_regime = _pf1.multiselect("Filter regime", ['LEADER', 'CONTENDER', 'LAGGARD', 'WEAK', 'TREND+LEAD', 'TREND_ONLY'],
                                      default=[], key='act_pf_regime')
        _pf_vol = _pf2.multiselect("Filter volume", ['HIGH', 'MED', 'LOW'], default=[], key='act_pf_vol')
        _pf_cap = _pf3.multiselect("Filter cap band", ['large', 'mid', 'small', 'ETF'], default=[], key='act_pf_cap')
        _pf_acc = _pf4.multiselect("Filter acc_watch", ['TRENDING', 'REACCUM', 'CONSOLIDATE', 'SHIFT', 'PROGRESS', 'EARLY', '-'],
                                   default=[], key='act_pf_acc')
        _pf_rsi = _pf5.multiselect("Filter rsi_div", ['BULL', 'HID_BULL', 'BEAR', 'HID_BEAR', '-'], default=[], key='act_pf_rsi')
        _pf_obv = _pf6.multiselect("Filter obv_div", ['BULL_DIV', 'CONV_UP', 'ACCUM', 'BEAR_DIV', 'CONV_DOWN', 'DISTRIB', '-'], default=[], key='act_pf_obv')
        st.caption("Page filters apply to every section below and to the TradingView / CSV exports. "
                   "Empty = use each market's saved Screener settings (Settings → 📋 Screeners).")

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

        def _show_section(label, study, universe, is_hc, cfg_key):
            _df_src  = MR.actionable(study, universe, run_date=sel_date, high_conv=is_hc)
            has_csv  = _df_src is not None
            has_tv   = has_csv
            csv_stem = f"{universe}_{study}_{'highconv' if is_hc else 'actionable'}.csv"
            tv_stem  = csv_stem.replace('.csv', '_tvimport.txt')
            hc_badge = " 🔥" if is_hc else ""
            st.markdown(f"**{label}{hc_badge}**")
            # Always show settings caption if config exists
            _cap = _settings_caption(cfg_key)
            if _cap:
                st.caption(_cap)
            elif not _act_cfg:
                st.caption("⚙️ No filter settings saved — configure in Actionable Settings page")
            if not has_csv:
                st.caption(f"No {study} results for {universe} on {sel_date}")
                return
            _c1, _c2 = st.columns([4, 1])
            _df = _df_src
            with _c1:
                if has_csv:
                    _df = _df_src
                    if _df is not None and len(_df) > 0:
                        # Apply all filters from actionable settings
                        _sma_cfg = _act_cfg.get(cfg_key, {})
                        _s_filt  = {**_AS_DISPLAY_DEFAULTS.get(cfg_key,{}), **_act_cfg.get(cfg_key,{})}
                        if _pf_regime: _s_filt['regimes'] = _pf_regime
                        if _pf_vol:    _s_filt['vol'] = _pf_vol
                        if _pf_cap:    _s_filt['cap_bands'] = _pf_cap

                        # Regime filter
                        _reg_filter = _s_filt.get('regimes', [])
                        if _reg_filter and 'regime_label' in _df.columns:
                            _df = _df[_df['regime_label'].isin(_reg_filter)]

                        # Vol filter
                        _vol_filter = _s_filt.get('vol', [])
                        if _vol_filter and 'vol_label' in _df.columns:
                            _df = _df[_df['vol_label'].isin(_vol_filter)]

                        # Cap band filter
                        _cap_filter = _s_filt.get('cap_bands', [])
                        if _cap_filter and 'cap_band' in _df.columns:
                            _df = _df[_df['cap_band'].isin(_cap_filter)]

                        # RSI / OBV divergence filters (page-level only — not part of the saved settings)
                        if _pf_rsi and 'rsi_div' in _df.columns:
                            _df = _df[_df['rsi_div'].isin(_pf_rsi)]
                        if _pf_obv and 'obv_div' in _df.columns:
                            _df = _df[_df['obv_div'].isin(_pf_obv)]

                        # Min score filter
                        _min_score = _s_filt.get('min_score', 0.0)
                        if _min_score and 'score_final' in _df.columns:
                            _df = _df[pd.to_numeric(_df['score_final'], errors='coerce') >= _min_score]
                        if all(c in _df.columns for c in ['close','sma20','sma50','sma200']):
                            def _check_conds(p, s20, s50, s200, conds, logic='AND'):
                                """Check condition strings with AND or OR logic."""
                                _map = {
                                    'Price > SMA20': p > s20,  'Price < SMA20': p < s20,
                                    'Price > SMA50': p > s50,  'Price < SMA50': p < s50,
                                    'Price > SMA200': p > s200,'Price < SMA200': p < s200,
                                    'SMA20 > SMA50': s20 > s50,'SMA20 < SMA50': s20 < s50,
                                    'SMA20 > SMA200': s20>s200,'SMA20 < SMA200': s20<s200,
                                    'SMA50 > SMA20': s50 > s20,'SMA50 < SMA20': s50 < s20,
                                    'SMA50 > SMA200': s50>s200,'SMA50 < SMA200': s50<s200,
                                    'SMA200 > SMA20': s200>s20,'SMA200 < SMA20': s200<s20,
                                    'SMA200 > SMA50': s200>s50,'SMA200 < SMA50': s200<s50,
                                }
                                _results = [_map.get(c, True) for c in conds]
                                return all(_results) if logic == 'AND' else any(_results)

                            def _derive_acc(row):
                                _p,_s20,_s50,_s200 = row['close'],row['sma20'],row['sma50'],row['sma200']
                                if any(pd.isna(x) for x in [_p,_s20,_s50,_s200]): return row['acc_watch']
                                for _atype in ['TRENDING','REACCUM','CONSOLIDATE','SHIFT','PROGRESS','EARLY']:
                                    _cfg = _sma_cfg.get(f'sma_{_atype.lower()}', {})
                                    if not _cfg: continue
                                    # Handle old list format vs new dict format
                                    if isinstance(_cfg, list): continue
                                    _all_conds = (_cfg.get('price',[])+_cfg.get('sma20',[])+
                                                  _cfg.get('sma50',[])+_cfg.get('sma200',[]))
                                    _logic = _cfg.get('logic','AND')
                                    if _all_conds and _check_conds(_p,_s20,_s50,_s200,_all_conds,_logic):
                                        return _atype
                                return row['acc_watch']

                            _df = _df.copy()
                            _df['acc_watch'] = _df.apply(_derive_acc, axis=1)
                            _acc_filter = _pf_acc or _sma_cfg.get('acc_watch', [])
                            if _acc_filter:
                                _df = _df[_df['acc_watch'].isin(_acc_filter)]
                        if _sma_cfg.get('sma_early') or _sma_cfg.get('sma_progress') or _sma_cfg.get('sma_shift'):
                            _sma_logic = _sma_cfg.get('sma_logic', 'AND')
                            def _sma_pass(row):
                                _aw = row.get('acc_watch', '-')
                                _sma_map = {
                                    'EARLY'   : _sma_cfg.get('sma_early', []),
                                    'PROGRESS': _sma_cfg.get('sma_progress', []),
                                    'SHIFT'   : _sma_cfg.get('sma_shift', []),
                                }
                                _conditions = _sma_map.get(_aw, [])
                                if not _conditions: return True
                                _close = row.get('close', 0)
                                _checks = []
                                for _cond in _conditions:
                                    if _cond == 'Above 20':  _checks.append(_close > row.get('sma20',  _close))
                                    elif _cond == 'Below 20':  _checks.append(_close < row.get('sma20',  _close))
                                    elif _cond == 'Above 50':  _checks.append(_close > row.get('sma50',  _close))
                                    elif _cond == 'Below 50':  _checks.append(_close < row.get('sma50',  _close))
                                    elif _cond == 'Above 200': _checks.append(_close > row.get('sma200', _close))
                                    elif _cond == 'Below 200': _checks.append(_close < row.get('sma200', _close))
                                return all(_checks) if _sma_logic == 'AND' else any(_checks)
                            if all(c in _df.columns for c in ['close','sma20','sma50','sma200']):
                                _df = _df[_df.apply(_sma_pass, axis=1)].copy()
                        _bc = ['ticker','name','cap_band','close','vol_label','acc_watch','regime_label','score_final']
                        _ec = ['sector','commodity','type','rs_ratio','peer_rs_score','ret_6m','ret_12m','max_dd','rs_trend',
                               'rsi_div','obv_div','delta_rank']
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
                            _df_fmt['close'] = pd.to_numeric(_df_fmt['close'], errors='coerce').round(3)
                        st.dataframe(style_df(_df_fmt,'regime_label','delta_rank'),
                                     width='stretch', height=min(len(_df)*35+40,350),
                                     column_config=DIVERGENCE_COLUMN_CONFIG)
                    else:
                        st.caption("No results")
            with _c2:
                # exports = exactly the rows shown after all filters
                _tv = MR.tv_import(_df)
                st.metric("Tickers", len(_df))
                st.download_button("⬇ TradingView", _tv, file_name=tv_stem,
                                   mime='text/plain', key=f"tv_{cfg_key}_{label}_{sel_date}")
                st.download_button("⬇ CSV", _df.to_csv(),
                                   file_name=csv_stem, mime='text/csv',
                                   key=f"csv_{cfg_key}_{label}_{sel_date}")
            st.markdown("---")
        # Group definitions — (label, study, universe, high_conviction)
        _GROUPS = [
            ("🇦🇺 AU Market", "au_market", [
                ("Benchmark",       "benchmark", "au_total_market", False),
                ("Screener",        "screener",  "au_total_market", False),
                ("High Conviction", "screener",  "au_total_market", True),
            ]),
            ("🇺🇸 US Market", "us_market", [
                ("S&P 500 Benchmark",   "benchmark", "us_total_market", False),
                ("S&P 500 Screener",    "screener",  "us_total_market", False),
                ("S&P 500 High Conv",   "screener",  "us_total_market", True),
                ("Nasdaq 100 Screener", "screener",  "nasdaq100",       False),
                ("Nasdaq Benchmark",    "benchmark", "nasdaq100",       False),
            ]),
            ("⛏ Commodities", "commodities", [
                ("Benchmark",       "benchmark", "all_major_commodities", False),
                ("Screener",        "screener",  "all_major_commodities", False),
                ("High Conviction", "screener",  "all_major_commodities", True),
            ]),
            ("☢ Uranium", "uranium", [
                ("Benchmark",       "benchmark", "uranium", False),
                ("Screener",        "screener",  "uranium", False),
                ("High Conviction", "screener",  "uranium", True),
            ]),
            ("🥇 AU Gold", "au_gold", [
                ("Benchmark",       "benchmark", "au_gold_miners", False),
                ("Screener",        "screener",  "au_gold_miners", False),
                ("High Conviction", "screener",  "au_gold_miners", True),
            ]),
        ]

        _grp_tabs = st.tabs([g[0] for g in _GROUPS] + ["🔍 Burry Value Screen"])
        for _gtab, (_glabel, _cfg_key, _studies) in zip(_grp_tabs, _GROUPS):
            with _gtab:
                for _slabel, _study, _uni, _is_hc in _studies:
                    _show_section(_slabel, _study, _uni, _is_hc, _cfg_key)

        # ── Burry Value Screen tab ────────────────────────────────────────────
        with _grp_tabs[-1]:
            st.markdown("##### Michael Burry Value Screen")
            st.caption("Small/micro-cap, absolutely cheap, strong balance sheet, low share count — based on Burry's VIC write-ups.")

            _burry_settings = load_settings()
            _burry_cfg = _burry_settings.get('burry_screener', DEFAULT_SETTINGS['burry_screener'])

            # show current filter summary
            _bcap_m = _burry_cfg.get('max_market_cap', 300_000_000)
            _bcap_label = f"${_bcap_m/1e9:.1f}B" if _bcap_m >= 1e9 else f"${_bcap_m/1e6:.0f}M"
            st.caption(
                f"Filters — MCap: **< {_bcap_label}** | "
                f"P/E: **< {_burry_cfg.get('max_pe', 15)}** | "
                f"P/B: **< {_burry_cfg.get('max_pb', 1.5)}** | "
                f"P/S: **< {_burry_cfg.get('max_ps', 1.0)}** | "
                f"D/E: **< {_burry_cfg.get('max_debt_equity', 50)}** | "
                f"Current Ratio: **> {_burry_cfg.get('min_current_ratio', 1.5)}** | "
                f"Shares: **< {_burry_cfg.get('max_shares', 100_000_000)/1e6:.0f}M**"
            )

            # inline adjustable filters (initialise from saved defaults, expander overrides)
            _bf_mcap   = int(_burry_cfg.get('max_market_cap', 300_000_000) / 1e6)
            _bf_pe     = float(_burry_cfg.get('max_pe', 15.0))
            _bf_pb     = float(_burry_cfg.get('max_pb', 1.5))
            _bf_ps     = float(_burry_cfg.get('max_ps', 1.0))
            _bf_de     = float(_burry_cfg.get('max_debt_equity', 50.0))
            _bf_cr     = float(_burry_cfg.get('min_current_ratio', 1.5))
            _bf_roe    = float(_burry_cfg.get('min_roe', 0.0))
            _bf_shares = int(_burry_cfg.get('max_shares', 100_000_000) / 1e6)
            _bf_markets = _burry_cfg.get('markets', ['us'])

            with st.expander("⚙️ Adjust Filters", expanded=False):
                _bf_c1, _bf_c2, _bf_c3, _bf_c4 = st.columns(4)
                _bf_mcap = _bf_c1.number_input("Max Market Cap ($M)", 10, 5000,
                                                _bf_mcap, step=50, key='burry_f_mcap')
                _bf_pe   = _bf_c2.number_input("Max P/E", 1.0, 100.0,
                                                _bf_pe, step=1.0, key='burry_f_pe')
                _bf_pb   = _bf_c3.number_input("Max P/B", 0.1, 10.0,
                                                _bf_pb, step=0.1, key='burry_f_pb')
                _bf_ps   = _bf_c4.number_input("Max P/S", 0.1, 10.0,
                                                _bf_ps, step=0.1, key='burry_f_ps')

                _bf_c5, _bf_c6, _bf_c7, _bf_c8 = st.columns(4)
                _bf_de   = _bf_c5.number_input("Max D/E", 0.0, 200.0,
                                                _bf_de, step=5.0, key='burry_f_de')
                _bf_cr   = _bf_c6.number_input("Min Current Ratio", 0.0, 10.0,
                                                _bf_cr, step=0.1, key='burry_f_cr')
                _bf_roe  = _bf_c7.number_input("Min ROE (%)", -100.0, 100.0,
                                                _bf_roe, step=1.0, key='burry_f_roe')
                _bf_shares = _bf_c8.number_input("Max Shares (M)", 1, 1000,
                                                  _bf_shares, step=10, key='burry_f_shares')

                st.caption("Select the stock universe from the dropdown below to choose the market.")

            # scan source — all available screener and benchmark universes
            _BURRY_SOURCES = {
                'AU Total Market (Screener)'  : ('screener',  'au_total_market'),
                'US Total Market (Screener)'  : ('screener',  'us_total_market'),
                'NASDAQ 100 (Screener)'       : ('screener',  'nasdaq100'),
                'Commodities (Screener)'      : ('screener',  'all_major_commodities'),
                'Uranium (Screener)'          : ('screener',  'uranium'),
                'AU Gold Miners (Screener)'   : ('screener',  'au_gold_miners'),
                'AU Total Market (Benchmark)' : ('benchmark', 'au_total_market'),
                'US Benchmark'                : ('benchmark', 'us_total_market'),
                'NASDAQ Benchmark'            : ('benchmark', 'nasdaq100'),
                'Commodities Benchmark'       : ('benchmark', 'all_major_commodities'),
            }
            _burry_src_avail = {k: v for k, v in _BURRY_SOURCES.items() if MR.run_dates(*v)}
            _BURRY_PREFIX = 'burry/'          # frames: burry/<YYYYMMDD>_burry_<source>

            def _format_burry_df(df):
                """Format raw Burry screen dataframe for display."""
                fmt = df.copy()
                if 'mkt_cap' in fmt.columns:
                    fmt['mkt_cap'] = pd.to_numeric(fmt['mkt_cap'], errors='coerce').apply(
                        lambda x: f"${x/1e6:.0f}M" if pd.notna(x) else '')
                for _fc in ['P/E', 'P/B', 'P/S', 'EV/FCF', 'D/E', 'cur_ratio']:
                    if _fc in fmt.columns:
                        fmt[_fc] = pd.to_numeric(fmt[_fc], errors='coerce').apply(
                            lambda x: f"{x:.2f}" if pd.notna(x) else '')
                if 'ROE' in fmt.columns:
                    fmt['ROE'] = pd.to_numeric(fmt['ROE'], errors='coerce').apply(
                        lambda x: f"{x*100:.1f}%" if pd.notna(x) and abs(x) < 10 else
                                  (f"{x:.1f}%" if pd.notna(x) else ''))
                if 'shares' in fmt.columns:
                    fmt['shares'] = pd.to_numeric(fmt['shares'], errors='coerce').apply(
                        lambda x: f"{x/1e6:.1f}M" if pd.notna(x) and x >= 1e6 else
                                  (f"{x/1e3:.0f}K" if pd.notna(x) else ''))
                if 'FCF' in fmt.columns:
                    fmt['FCF'] = pd.to_numeric(fmt['FCF'], errors='coerce').apply(
                        lambda x: f"${x/1e6:.1f}M" if pd.notna(x) else '')
                if 'price' in fmt.columns:
                    fmt['price'] = pd.to_numeric(fmt['price'], errors='coerce').apply(
                        lambda x: f"${x:.2f}" if pd.notna(x) else '')
                if '52w_chg' in fmt.columns:
                    fmt['52w_chg'] = pd.to_numeric(fmt['52w_chg'], errors='coerce').apply(
                        lambda x: f"{x*100:.1f}%" if pd.notna(x) and abs(x) < 10 else
                                  (f"{x:.1f}%" if pd.notna(x) else ''))
                return fmt

            if not _burry_src_avail:
                st.info("No screener data found — run the daily update first to populate the stock universe.")
            else:
                _burry_source = st.selectbox("Stock Universe", list(_burry_src_avail.keys()), key='burry_universe')

                if st.button("🔍 Run Burry Screen", type="primary", key='burry_run'):
                    _src_df = MR.latest(*_burry_src_avail[_burry_source])
                    if _src_df is None or len(_src_df) == 0:
                        st.error("No tickers in source results")
                    else:
                        _tickers = _src_df['ticker'].dropna().unique().tolist()
                        _progress = st.progress(0, text="Screening...")
                        _results = []

                        import yfinance as yf
                        from datetime import datetime

                        for _i, _t in enumerate(_tickers):
                            _progress.progress((_i + 1) / len(_tickers), text=f"Screening {_t} ({_i+1}/{len(_tickers)})")
                            try:
                                _info = yf.Ticker(_t).info
                                if not _info or not _info.get('regularMarketPrice'):
                                    continue

                                _mcap = _info.get('marketCap')
                                _pe   = _info.get('trailingPE')
                                _pb   = _info.get('priceToBook')
                                _ps   = _info.get('priceToSalesTrailing12Months')
                                _de   = _info.get('debtToEquity')
                                _cr   = _info.get('currentRatio')
                                _roe  = _info.get('returnOnEquity')
                                _so   = _info.get('sharesOutstanding')
                                _fcf  = _info.get('freeCashflow')
                                _ev   = _info.get('enterpriseValue')

                                if _mcap is not None and _mcap > _bf_mcap * 1e6:
                                    continue
                                if _pe is not None and (_pe <= 0 or _pe > _bf_pe):
                                    continue
                                if _pb is not None and _pb > _bf_pb:
                                    continue
                                if _ps is not None and _ps > _bf_ps:
                                    continue
                                if _de is not None and _de > _bf_de:
                                    continue
                                if _cr is not None and _cr < _bf_cr:
                                    continue
                                if _roe is not None and _roe * 100 < _bf_roe:
                                    continue
                                if _so is not None and _so > _bf_shares * 1e6:
                                    continue

                                if _mcap is None:
                                    continue
                                if all(v is None for v in [_pe, _pb, _ps]):
                                    continue

                                _ev_fcf = None
                                if _ev and _fcf and _fcf > 0:
                                    _ev_fcf = _ev / _fcf

                                _results.append({
                                    'ticker': _t,
                                    'name': _info.get('shortName', _info.get('longName', _t)),
                                    'sector': _info.get('sector', ''),
                                    'mkt_cap': _mcap,
                                    'price': _info.get('regularMarketPrice', _info.get('currentPrice')),
                                    'P/E': _pe,
                                    'P/B': _pb,
                                    'P/S': _ps,
                                    'EV/FCF': _ev_fcf,
                                    'D/E': _de,
                                    'cur_ratio': _cr,
                                    'ROE': _roe,
                                    'shares': _so,
                                    'FCF': _fcf,
                                    '52w_chg': _info.get('52WeekChange'),
                                })
                            except Exception:
                                continue

                        _progress.empty()

                        if not _results:
                            st.warning("No stocks passed all filters. Try relaxing the criteria.")
                        else:
                            _rdf = pd.DataFrame(_results)

                            # derive a short source tag for the filename
                            _src_tag = _burry_source.lower().replace(' ', '_').replace('(', '').replace(')', '')
                            _date_str = datetime.now().strftime('%Y%m%d')
                            _csv_name = f"{_date_str}_burry_{_src_tag}.csv"
                            _tv_name  = f"{_date_str}_burry_{_src_tag}_tvimport.txt"
                            MR.save_frame(_BURRY_PREFIX + _csv_name[:-4], _rdf)
                            _tv_tickers = MR.tv_import(_rdf)

                            st.success(f"Found {len(_rdf)} stocks — saved as `{_csv_name[:-4]}`")
                            st.dataframe(_format_burry_df(_rdf), width='stretch',
                                         height=min(len(_rdf)*35+40, 500))

                            _dl1, _dl2, _ = st.columns([1, 1, 3])
                            _dl1.download_button("⬇ TradingView", _tv_tickers,
                                                  file_name=_tv_name, mime='text/plain',
                                                  key='burry_tv_export')
                            _dl2.download_button("⬇ CSV", _rdf.to_csv(index=False),
                                                  file_name=_csv_name, mime='text/csv',
                                                  key='burry_csv_export')

            # ── Past runs ─────────────────────────────────────────────────────
            st.markdown("---")
            st.markdown("##### Past Runs")
            _past_runs = MR.list_frames(_BURRY_PREFIX)
            _past_labels = [n[len(_BURRY_PREFIX):] for n in _past_runs['name']] if len(_past_runs) else []

            if not _past_labels:
                st.caption("No saved runs yet — run a screen above to get started.")
            else:
                _sel_past = st.selectbox("Select run", _past_labels, key='burry_past_sel')
                _past_df = MR.load_frame(_BURRY_PREFIX + _sel_past)
                if _past_df is not None and len(_past_df) > 0:
                    st.caption(f"{len(_past_df)} stocks")
                    st.dataframe(_format_burry_df(_past_df), width='stretch',
                                 height=min(len(_past_df)*35+40, 500))

                    _pdl1, _pdl2, _ = st.columns([1, 1, 3])
                    _pdl1.download_button("⬇ TradingView", MR.tv_import(_past_df),
                                           file_name=f"{_sel_past}_tvimport.txt",
                                           mime='text/plain', key='burry_past_tv')
                    _pdl2.download_button("⬇ CSV", _past_df.to_csv(index=False),
                                           file_name=f"{_sel_past}.csv",
                                           mime='text/csv', key='burry_past_csv')
                else:
                    st.caption("Empty results")


elif page == "Fundamental Analysis":
    st.title("Fundamental Analysis")
    st.caption("Burry/Buffett lens — local LLM with RAG context from methodology documents")

    _fa_settings = load_settings()
    _fa_cfg = _fa_settings.get('fa_features', DEFAULT_SETTINGS.get('fa_features', {}))

    _fa_tab_single, _fa_tab_compare = st.tabs(["🔎 Single Ticker", "⚖️ Value Comparison"])

    # ── Scan selector — actionable runs (folder → specific run) ─────────────
    _RAW_SCREENERS = {f"{UNIVERSE_LABELS[u]} ({st_.title()})": (st_, u)
                      for (st_, u) in [('screener', 'au_total_market'), ('screener', 'us_total_market'),
                                       ('screener', 'nasdaq100'), ('screener', 'all_major_commodities'),
                                       ('screener', 'uranium'), ('screener', 'au_gold_miners'),
                                       ('benchmark', 'au_total_market'), ('benchmark', 'us_total_market'),
                                       ('benchmark', 'nasdaq100')]
                      if MR.run_dates(st_, u)}

    # Scan "folders" are now result kinds in the DB; the Burry screen keeps its on-disk folder
    _ACT_KINDS = {'Actionable — screener': ('screener', False),
                  'Actionable — benchmark': ('benchmark', False),
                  'High conviction — screener': ('screener', True)}
    _act_folders = list(_ACT_KINDS.keys())
    _burry_runs_fa = MR.list_frames('burry/')
    if len(_burry_runs_fa):
        _act_folders.append('burry_screen')

    _RAW_LABEL = 'Raw screeners (latest)'
    _folder_options = _act_folders + [_RAW_LABEL]

    import sys as _sys
    if os.path.join(BASE, 'utilities') not in _sys.path:
        _sys.path.insert(0, os.path.join(BASE, 'utilities'))

    with _fa_tab_single:
        _fa_col1, _fa_col2, _fa_col3 = st.columns([1.5, 2.5, 1])
        with _fa_col1:
            _sel_folder = st.selectbox("Scan folder", _folder_options, key='fa_folder_select')
        with _fa_col2:
            _scan_df = None
            _scan_label = ''
            if _sel_folder == _RAW_LABEL:
                _sel_scan = st.selectbox("Scan", list(_RAW_SCREENERS.keys()), key='fa_scan_select')
                if _sel_scan:
                    _scan_df = MR.latest(*_RAW_SCREENERS[_sel_scan])
                    _scan_df = _scan_df.reset_index() if _scan_df is not None else None
                    _scan_label = _sel_scan
            elif _sel_folder in _ACT_KINDS:
                _kind_study, _kind_hc = _ACT_KINDS[_sel_folder]
                _runs_df = mdb.read_df("SELECT universe, run_date FROM study_results WHERE study=? "
                                       "GROUP BY 1,2 ORDER BY run_date DESC, universe", (_kind_study,))
                _run_opts = [f"{r.run_date} · {UNIVERSE_LABELS.get(r.universe, r.universe)}|{r.universe}"
                             for r in _runs_df.itertuples()]
                _sel_run = st.selectbox("Run", _run_opts, format_func=lambda x: x.split('|')[0],
                                        key=f'fa_run_select_{_sel_folder}')
                if _sel_run:
                    _rd, _uni = _sel_run.split(' · ')[0], _sel_run.split('|')[1]
                    _scan_df = MR.actionable(_kind_study, _uni, run_date=_rd, high_conv=_kind_hc)
                    _scan_df = _scan_df.reset_index() if _scan_df is not None else None
                    _scan_label = _sel_run.split('|')[0]
            else:  # burry_screen runs stored in marketdb frames
                _run_files = _burry_runs_fa['name'].tolist()
                def _run_label(n):
                    b = n.split('/', 1)[1]
                    if len(b) > 9 and b[:8].isdigit() and b[8] == '_':
                        return f"{b[:4]}-{b[4:6]}-{b[6:8]} · {b[9:]}"
                    return b
                _sel_run = st.selectbox("Run", _run_files, format_func=_run_label,
                                        key=f'fa_run_select_{_sel_folder}')
                if _sel_run:
                    _scan_df = MR.load_frame(_sel_run)
                    _scan_label = _run_label(_sel_run)
        with _fa_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            _prov_badges = {'ollama': '🟢 Ollama', 'lmstudio': '🔵 LM Studio',
                            'openai': '🟣 OpenAI'}
            _fa_provider_label = f"{_prov_badges.get(_fa_cfg.get('provider'), '🟢 Ollama')} — {_fa_cfg.get('model', 'llama3.1:8b')}"
            st.caption(_fa_provider_label)

        # ── Load and display scan data ───────────────────────────────────────
        if _scan_df is not None and len(_scan_df):
            _display_cols = [c for c in ['rank', 'ticker', 'name', 'sector', 'cap_band', 'close',
                                          'regime_label', 'score_final', 'rel_vol', 'vol_label',
                                          'ret_12m', 'max_dd', 'rs_trend'] if c in _scan_df.columns]
            if not _display_cols:
                _display_cols = list(_scan_df.columns[:12])

            st.dataframe(
                _scan_df[_display_cols],
                width="stretch",
                height=350,
                hide_index=True,
            )
            st.caption(f"{len(_scan_df)} stocks — {_scan_label}")
        else:
            _scan_df = None
            st.info("No scan data found — run the daily update first.")

        st.divider()

        # ── Ticker analysis ──────────────────────────────────────────────────
        st.markdown("##### Analyse a Ticker")
        _fa_tc1, _fa_tc2 = st.columns([2, 1])
        with _fa_tc1:
            _fa_ticker = st.text_input("Ticker", placeholder="e.g. AAPL, BHP.AX, LULU", key='fa_ticker_input')
        with _fa_tc2:
            st.markdown("<br>", unsafe_allow_html=True)
            _fa_go = st.button("Analyse", key='fa_analyse_btn', type='primary')

        if _fa_go and _fa_ticker.strip():
            _ticker = _fa_ticker.strip().upper()
            from fa_assessment import render_fa_assessment
            _fa_custom_prompt = load_settings().get('ai_prompts', {}).get('fa_system') or None
            render_fa_assessment(_ticker, _fa_settings, system_prompt=_fa_custom_prompt)
        elif _fa_go:
            st.warning("Enter a ticker symbol")

    # ── Value comparison tab — pick 2-6 candidates, one LLM call decides ────
    with _fa_tab_compare:
        st.caption("Head-to-head value comparison — e.g. two or three similar miners, "
                   "let the balance sheet decide. Best kept to 2-6 tickers.")

        # candidate sources: current scan, watchlist file, manual entry
        _cmp_sources = []
        if _scan_df is not None and 'ticker' in _scan_df.columns:
            _cmp_sources.append("Current scan (Single Ticker tab)")
        _wl_files = list(UNIVERSE_LABELS.keys())
        if _wl_files:
            _cmp_sources.append("Universe")
        _cmp_sources.append("Manual entry only")

        _cmp_src = st.radio("Pick candidates from", _cmp_sources, horizontal=True,
                            key='fa_cmp_source')

        _cmp_pool = []
        if _cmp_src == "Current scan (Single Ticker tab)" and _scan_df is not None:
            _pool_df = _scan_df
            if 'name' in _pool_df.columns:
                _pool_labels = {r['ticker']: f"{r['ticker']} — {r['name']}"
                                for _, r in _pool_df.iterrows()}
            else:
                _pool_labels = {t: t for t in _pool_df['ticker']}
            _cmp_pool = st.multiselect(
                "Candidates", list(_pool_labels.keys()),
                format_func=lambda t: _pool_labels.get(t, t),
                max_selections=6, key='fa_cmp_scan_pick')
        elif _cmp_src == "Universe":
            _sel_wl = st.selectbox("Universe", _wl_files,
                                   format_func=lambda k: UNIVERSE_LABELS[k],
                                   key='fa_cmp_wl_select')
            try:
                _wl_df = db_universe_members(_sel_wl)
                _wl_tickers = _wl_df['ticker'].dropna().astype(str).str.strip().tolist()
            except Exception:
                _wl_tickers = []
            _cmp_pool = st.multiselect("Candidates", _wl_tickers,
                                       max_selections=6, key='fa_cmp_wl_pick')

        _cmp_manual = st.text_input(
            "Add tickers (comma separated)",
            placeholder="e.g. BHP.AX, RIO.AX, FMG.AX", key='fa_cmp_manual')
        _manual_list = [t.strip().upper() for t in _cmp_manual.split(',') if t.strip()]

        _cmp_tickers = list(dict.fromkeys(list(_cmp_pool) + _manual_list))  # dedupe, keep order

        if _cmp_tickers:
            st.caption(f"Comparing: {', '.join(_cmp_tickers)}")
        _cmp_go = st.button("Compare", key='fa_cmp_btn', type='primary',
                            disabled=len(_cmp_tickers) < 2)

        if _cmp_go:
            if len(_cmp_tickers) > 6:
                st.warning("Capped to the first 6 tickers to keep the comparison focused.")
                _cmp_tickers = _cmp_tickers[:6]
            from fa_assessment import render_fa_comparison
            _cmp_custom_prompt = load_settings().get('ai_prompts', {}).get('fa_comparison') or None
            _cmp_text = render_fa_comparison(_cmp_tickers, _fa_settings, system_prompt=_cmp_custom_prompt)
            if _cmp_text:
                st.session_state['fa_cmp_last'] = (_cmp_tickers, _cmp_text)
        elif 'fa_cmp_last' in st.session_state:
            _last_tickers, _last_text = st.session_state['fa_cmp_last']
            with st.expander(f"Last comparison: {', '.join(_last_tickers)}", expanded=False):
                st.markdown(_last_text)


elif page == "Sentiment":
    import sys as _sys
    _sent_dir = os.path.join(BASE, 'sentiment')
    if _sent_dir not in _sys.path:
        _sys.path.insert(0, _sent_dir)
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from sentiment_data import (
        fetch_aaii, fetch_naaim, fetch_index_weekly, fetch_cot, import_aaii_file,
        INDEX_SYMBOLS, COT_MARKETS,
    )

    st.title("🧭 Sentiment")
    st.caption("Weekly AAII survey, NAAIM manager exposure and CFTC COT positioning against the market.")

    SENT_BULL_COLOR = "#2e9e4f"
    SENT_BEAR_COLOR = "#d94848"
    SENT_SPREAD_POS = "#555555"
    SENT_SPREAD_NEG = "#c9486e"
    SENT_NAAIM_COLOR = "#d99b2e"
    SENT_BAR_W_MS = 6 * 24 * 3600 * 1000  # chunky weekly histogram bars

    sc_a, sc_b, sc_c = st.columns([1.4, 1, 3])
    with sc_a:
        sent_index_name = st.selectbox("Price panel", list(INDEX_SYMBOLS.keys()),
                                       index=0, key="sent_price_panel")
    with sc_b:
        sent_window = st.selectbox("Window", ["2y", "5y", "10y", "20y", "Max"],
                                   index=1, key="sent_window")
    with sc_c:
        st.write("")
        sent_force = st.button("🔄 Refresh data", key="sent_refresh")

    try:
        with st.spinner("Loading sentiment and price data..."):
            aaii = fetch_aaii(force=sent_force)
            sent_px = fetch_index_weekly(INDEX_SYMBOLS[sent_index_name], force=sent_force)
    except Exception as e:
        st.error(f"Could not load data automatically: {e}")
        st.markdown(
            "Download the survey file manually from "
            "[aaii.com/sentimentsurvey](https://www.aaii.com/sentimentsurvey/sent_results) "
            "(`sentiment.xls`) and import it below."
        )
        sent_up = st.file_uploader("Import sentiment.xls", type=["xls"], key="sent_upload")
        if sent_up is not None:
            aaii = import_aaii_file(sent_up)
            st.success(f"Imported {len(aaii)} weekly readings.")
            sent_px = fetch_index_weekly(INDEX_SYMBOLS[sent_index_name])
        else:
            st.stop()

    naaim = None
    naaim_err = None
    try:
        naaim = fetch_naaim(force=sent_force)
    except Exception as e:
        naaim_err = str(e)

    # MAs over full history so they are valid at the left edge of the window
    sent_px = sent_px.sort_values("date").reset_index(drop=True)
    sent_px["ma40"] = sent_px["close"].rolling(40).mean()
    sent_px["ma150"] = sent_px["close"].rolling(150).mean()

    sent_end = max(sent_px["date"].max(), aaii["date"].max())
    if sent_window == "Max":
        sent_start = aaii["date"].min()
    else:
        sent_start = sent_end - timedelta(days=int(sent_window[:-1]) * 365)

    sent_px_w = sent_px[sent_px["date"] >= sent_start]
    aaii_w = aaii[aaii["date"] >= sent_start]
    naaim_w = naaim[naaim["date"] >= sent_start] if naaim is not None else None

    if aaii_w.empty or sent_px_w.empty:
        st.warning("No data in the selected window.")
        st.stop()

    # Full-history averages for the dashed reference lines
    bull_avg = aaii["bullish"].mean()
    bear_avg = aaii["bearish"].mean()
    aaii_latest = aaii.iloc[-1]
    aaii_prev = aaii.iloc[-2] if len(aaii) > 1 else aaii_latest

    sm1, sm2, sm3, sm4, sm5, sm6 = st.columns(6)
    sm1.metric("Survey date", aaii_latest["date"].strftime("%d %b %Y"))
    sm2.metric("Bullish", f"{aaii_latest['bullish']:.1f}%",
               f"{aaii_latest['bullish'] - aaii_prev['bullish']:+.1f}")
    sm3.metric("Neutral", f"{aaii_latest['neutral']:.1f}%",
               f"{aaii_latest['neutral'] - aaii_prev['neutral']:+.1f}")
    sm4.metric("Bearish", f"{aaii_latest['bearish']:.1f}%",
               f"{aaii_latest['bearish'] - aaii_prev['bearish']:+.1f}", delta_color="inverse")
    sm5.metric("Bull-Bear spread", f"{aaii_latest['spread']:+.1f}",
               f"{aaii_latest['spread'] - aaii_prev['spread']:+.1f}")
    if naaim is not None and len(naaim) > 1:
        n_last, n_prev = naaim.iloc[-1], naaim.iloc[-2]
        sm6.metric("NAAIM exposure", f"{n_last['exposure']:.0f}",
                   f"{n_last['exposure'] - n_prev['exposure']:+.0f}")
    else:
        sm6.metric("NAAIM exposure", "n/a")

    has_naaim = naaim_w is not None and not naaim_w.empty
    sent_rows = 4 if has_naaim else 3
    sent_heights = [0.42, 0.22, 0.16, 0.20] if has_naaim else [0.52, 0.28, 0.20]
    sent_titles = [
        f"{sent_index_name} weekly — MA(40) blue / MA(150) red",
        f"AAII Bullish {aaii_latest['bullish']:.1f} / Bearish {aaii_latest['bearish']:.1f}",
        f"Bull-Bear spread {aaii_latest['spread']:+.1f}",
    ]
    if has_naaim:
        sent_titles.append(f"NAAIM Exposure Index {naaim.iloc[-1]['exposure']:.0f}")

    sent_fig = make_subplots(
        rows=sent_rows, cols=1, shared_xaxes=True,
        row_heights=sent_heights, vertical_spacing=0.03,
        subplot_titles=sent_titles,
    )
    sent_fig.add_trace(go.Ohlc(
        x=sent_px_w["date"], open=sent_px_w["open"], high=sent_px_w["high"],
        low=sent_px_w["low"], close=sent_px_w["close"], name=sent_index_name,
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        line_width=1.2, showlegend=False,
    ), row=1, col=1)
    sent_fig.add_trace(go.Scatter(
        x=sent_px_w["date"], y=sent_px_w["ma40"], name="MA(40)",
        line=dict(color="#4a6fd9", width=1.5), showlegend=False,
    ), row=1, col=1)
    sent_fig.add_trace(go.Scatter(
        x=sent_px_w["date"], y=sent_px_w["ma150"], name="MA(150)",
        line=dict(color="#c0392b", width=1.5), showlegend=False,
    ), row=1, col=1)
    sent_fig.add_trace(go.Bar(
        x=aaii_w["date"], y=aaii_w["bullish"], name="Bullish %",
        marker_color=SENT_BULL_COLOR, width=SENT_BAR_W_MS, showlegend=False,
        hovertemplate="%{x|%d %b %Y}<br>Bullish %{y:.1f}%<extra></extra>",
    ), row=2, col=1)
    sent_fig.add_trace(go.Bar(
        x=aaii_w["date"], y=-aaii_w["bearish"], name="Bearish %",
        marker_color=SENT_BEAR_COLOR, width=SENT_BAR_W_MS, showlegend=False,
        customdata=aaii_w["bearish"],
        hovertemplate="%{x|%d %b %Y}<br>Bearish %{customdata:.1f}%<extra></extra>",
    ), row=2, col=1)
    sent_fig.add_hline(y=bull_avg, line_dash="dash", line_color="#d048d0", line_width=1,
                       annotation_text=f"avg {bull_avg:.1f}", annotation_font_size=10,
                       row=2, col=1)
    sent_fig.add_hline(y=-bear_avg, line_dash="dash", line_color="#4a6fd9", line_width=1,
                       annotation_text=f"avg -{bear_avg:.1f}", annotation_font_size=10,
                       annotation_position="bottom right", row=2, col=1)
    sent_spread_colors = [SENT_SPREAD_POS if v >= 0 else SENT_SPREAD_NEG
                          for v in aaii_w["spread"]]
    sent_fig.add_trace(go.Bar(
        x=aaii_w["date"], y=aaii_w["spread"], name="Bull-Bear",
        marker_color=sent_spread_colors, width=SENT_BAR_W_MS, showlegend=False,
        hovertemplate="%{x|%d %b %Y}<br>Spread %{y:+.1f}<extra></extra>",
    ), row=3, col=1)
    sent_fig.add_hline(y=0, line_dash="dash", line_color="#2e9e4f", line_width=1,
                       row=3, col=1)
    if has_naaim:
        sent_fig.add_trace(go.Scatter(
            x=naaim_w["date"], y=naaim_w["q3"], name="Q3",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ), row=4, col=1)
        sent_fig.add_trace(go.Scatter(
            x=naaim_w["date"], y=naaim_w["q1"], name="Q1-Q3",
            line=dict(width=0), fill="tonexty",
            fillcolor="rgba(217,155,46,0.15)", showlegend=False, hoverinfo="skip",
        ), row=4, col=1)
        sent_fig.add_trace(go.Scatter(
            x=naaim_w["date"], y=naaim_w["exposure"], name="NAAIM",
            line=dict(color=SENT_NAAIM_COLOR, width=1.5), showlegend=False,
            hovertemplate="%{x|%d %b %Y}<br>Exposure %{y:.0f}<extra></extra>",
        ), row=4, col=1)
        naaim_avg = naaim["exposure"].mean()
        sent_fig.add_hline(y=naaim_avg, line_dash="dash", line_color="#888", line_width=1,
                           annotation_text=f"avg {naaim_avg:.0f}", annotation_font_size=10,
                           row=4, col=1)
        # Regime zones: 80-100 risk-on, 40-70 neutral/transition, 0-30 risk-off
        # (must come after the row-4 traces — add_hrect no-ops on an empty subplot)
        for _lo, _hi, _col, _lbl in [
            (80, 100, "rgba(46,158,79,0.10)",   "Risk-on 80-100"),
            (40, 70,  "rgba(150,150,150,0.12)", "Neutral / transition 40-70"),
            (0, 30,   "rgba(217,72,72,0.10)",   "Risk-off 0-30"),
        ]:
            sent_fig.add_hrect(y0=_lo, y1=_hi, fillcolor=_col, line_width=0,
                               annotation_text=_lbl, annotation_position="top left",
                               annotation_font_size=10,
                               annotation_font_color=_col.replace("0.10", "0.9").replace("0.12", "0.9"),
                               row=4, col=1)

    sent_fig.update_layout(
        height=1000 if has_naaim else 900, barmode="overlay", bargap=0,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False, hovermode="x unified",
    )
    sent_fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    sent_fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", side="right")
    sent_fig.update_annotations(font_size=11, x=0.01, xanchor="left",
                                selector=dict(xref="paper"))
    st.plotly_chart(sent_fig, use_container_width=True, key="sentiment_chart")

    if naaim_err:
        st.warning(f"NAAIM Exposure Index unavailable: {naaim_err}")

    sent_cap = (
        f"AAII survey: {aaii['date'].min():%b %Y} – {aaii['date'].max():%d %b %Y} "
        f"({len(aaii)} weeks); long-term averages bullish {bull_avg:.1f}% / "
        f"bearish {bear_avg:.1f}%. "
    )
    if naaim is not None:
        sent_cap += (f"NAAIM Exposure Index: {naaim['date'].min():%b %Y} – "
                     f"{naaim['date'].max():%d %b %Y}; shaded band = manager Q1–Q3 range. ")
    sent_cap += ("AAII posts Thursdays, NAAIM Wednesdays; cached data refreshes "
                 "automatically when older than 3 days.")
    st.caption(sent_cap)

    # ── CFTC COT positioning ─────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏛️ CFTC COT Positioning")

    cot_market = st.selectbox("Market", list(COT_MARKETS.keys()), index=0,
                              key="sent_cot_market")
    try:
        with st.spinner("Loading COT data..."):
            cot = fetch_cot(COT_MARKETS[cot_market]["code"], force=sent_force)
            cot_px = fetch_index_weekly(COT_MARKETS[cot_market]["price"], force=sent_force)
    except Exception as e:
        st.warning(f"COT data unavailable: {e}")
        st.stop()

    cot_w = cot[cot["date"] >= sent_start]
    cot_px_w = cot_px[cot_px["date"] >= sent_start]

    if cot_w.empty:
        st.warning("No COT data in the selected window.")
        st.stop()

    c_last = cot.iloc[-1]
    c_prev = cot.iloc[-2] if len(cot) > 1 else c_last
    sk1, sk2, sk3, sk4, sk5 = st.columns(5)
    sk1.metric("Report date (Tue)", c_last["date"].strftime("%d %b %Y"))
    sk2.metric("Large spec net", f"{c_last['noncomm_net']:+,.0f}",
               f"{c_last['noncomm_net'] - c_prev['noncomm_net']:+,.0f}")
    sk3.metric("Commercial net", f"{c_last['comm_net']:+,.0f}",
               f"{c_last['comm_net'] - c_prev['comm_net']:+,.0f}")
    sk4.metric("Spec net % of OI", f"{c_last['noncomm_net_pct_oi']:+.1f}%",
               f"{c_last['noncomm_net_pct_oi'] - c_prev['noncomm_net_pct_oi']:+.1f}")
    sk5.metric("Open interest", f"{c_last['open_interest']:,.0f}",
               f"{c_last['open_interest'] - c_prev['open_interest']:+,.0f}")

    cot_fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.45, 0.32, 0.23], vertical_spacing=0.04,
        subplot_titles=(
            f"{cot_market} — price",
            f"Net positions — large specs {c_last['noncomm_net']:+,.0f} / "
            f"commercials {c_last['comm_net']:+,.0f}",
            f"Large spec net as % of open interest {c_last['noncomm_net_pct_oi']:+.1f}%",
        ),
    )
    cot_fig.add_trace(go.Ohlc(
        x=cot_px_w["date"], open=cot_px_w["open"], high=cot_px_w["high"],
        low=cot_px_w["low"], close=cot_px_w["close"], name="Price",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        line_width=1.2, showlegend=False,
    ), row=1, col=1)
    cot_net_colors = [SENT_BULL_COLOR if v >= 0 else SENT_BEAR_COLOR
                      for v in cot_w["noncomm_net"]]
    cot_fig.add_trace(go.Bar(
        x=cot_w["date"], y=cot_w["noncomm_net"], name="Large spec net",
        marker_color=cot_net_colors, width=SENT_BAR_W_MS, showlegend=True,
        hovertemplate="%{x|%d %b %Y}<br>Spec net %{y:+,.0f}<extra></extra>",
    ), row=2, col=1)
    cot_fig.add_trace(go.Scatter(
        x=cot_w["date"], y=cot_w["comm_net"], name="Commercial net",
        line=dict(color="#888", width=1.3), showlegend=True,
        hovertemplate="%{x|%d %b %Y}<br>Comm net %{y:+,.0f}<extra></extra>",
    ), row=2, col=1)
    cot_fig.add_hline(y=0, line_dash="dash", line_color="#666", line_width=1, row=2, col=1)
    cot_fig.add_trace(go.Scatter(
        x=cot_w["date"], y=cot_w["noncomm_net_pct_oi"], name="Spec net % OI",
        line=dict(color=SENT_NAAIM_COLOR, width=1.5), fill="tozeroy",
        fillcolor="rgba(217,155,46,0.12)", showlegend=False,
        hovertemplate="%{x|%d %b %Y}<br>%{y:+.1f}% of OI<extra></extra>",
    ), row=3, col=1)
    cot_fig.add_hline(y=0, line_dash="dash", line_color="#666", line_width=1, row=3, col=1)

    cot_fig.update_layout(
        height=750, bargap=0,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    cot_fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    cot_fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", side="right")
    cot_fig.update_annotations(font_size=11, x=0.01, xanchor="left",
                               selector=dict(xref="paper"))
    st.plotly_chart(cot_fig, use_container_width=True, key="sent_cot_chart")

    st.caption(
        f"CFTC legacy futures-only Commitment of Traders, {cot['date'].min():%b %Y} – "
        f"{cot['date'].max():%d %b %Y}. Large specs = non-commercials (funds); "
        f"commercials = hedgers, typically positioned opposite. Reports are as-of "
        f"Tuesday, published Friday ~3:30pm ET."
    )

elif page == "Run Scripts":
    marketdb_ready()
    st.title("🚀 Run Scripts")
    st.caption("Scripts run synchronously — page will wait until complete")

    # ── Data layer status ────────────────────────────────────────────────────
    try:
        _last_fetch = mdb.scalar("SELECT MAX(finished) FROM runs WHERE kind='fetch' AND status IN ('ok','partial')")
        _last_px    = MP.last_date()
        _last_ref   = mdb.get_meta('last_universe_refresh')
        _n_sec      = mdb.scalar("SELECT COUNT(*) FROM securities WHERE active=1")
        _stale_n    = mdb.scalar("SELECT COUNT(*) FROM fetch_log WHERE consecutive_failures >= 3")
        _s1, _s2, _s3, _s4, _s5 = st.columns(5)
        _s1.metric("Active securities", f"{_n_sec:,}" if _n_sec else "0")
        _s2.metric("Latest price bar", _last_px or "—")
        _s3.metric("Last price fetch", db_age('fetch'))
        _s4.metric("Universe refreshed", (str(_last_ref)[:10] if _last_ref else "never (migration only)"))
        _s5.metric("DB size", f"{mdb.db_size_mb()} MB")
        if _stale_n:
            st.caption(f"⚠ {_stale_n} tickers have failed 3+ consecutive fetches — see the monthly refresh / "
                       f"`data/migration_dropped_tickers.csv`")
    except Exception as _e:
        st.warning(f"marketdb status unavailable: {_e}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Daily — all markets")
        st.caption("One price update for every universe (incremental, ~1–3 min), then every screener, "
                   "benchmark, breadth and RRG study.")
        if st.button("🔄 Run ALL — Full daily run", type="primary"):
            run_script(os.path.join(MACRO, 'macro_report.py'), MACRO)
            run_marketdb()
        if st.button("📥 Update prices only"):
            run_marketdb('--universe', *UNIVERSE_LABELS.keys(), '--studies')
        if st.button("📊 Re-run studies only (no fetch)"):
            run_marketdb('--skip-fetch')

        st.subheader("Macro")
        if st.button("Run Macro Report"):
            run_script(os.path.join(MACRO, 'macro_report.py'), MACRO)

        st.subheader("Debt Markets")
        if st.button("Run Debt Markets Report"):
            run_script(os.path.join(MACRO, 'consumer_credit.py'), MACRO)
        if st.button("Run AU Credit Report"):
            run_script(os.path.join(MACRO, 'au_credit.py'), MACRO)

        st.subheader("Per market")
        if st.button("🇦🇺 Run ALL AU Market", type="secondary"):
            run_marketdb('--universe', 'au_total_market', 'au_gold_miners')
        if st.button("🇺🇸 Run ALL US Market", type="secondary"):
            run_marketdb('--universe', 'us_total_market', 'nasdaq100', 'uranium')
        if st.button("⛏ Run ALL Commodities", type="secondary"):
            run_marketdb('--universe', 'all_major_commodities', 'uranium', 'au_gold_miners')

    with col2:
        st.subheader("Single studies")
        _ru1, _ru2 = st.columns(2)
        _run_uni = _ru1.selectbox("Universe", list(UNIVERSE_LABELS.keys()),
                                  format_func=lambda k: UNIVERSE_LABELS[k], key='run_single_uni')
        _run_study = _ru2.selectbox("Study", ['screener', 'benchmark', 'breadth'], key='run_single_study')
        if st.button("▶ Run study"):
            run_marketdb('--universe', _run_uni, '--studies', _run_study)
        if st.button("📈 Update RRG data (all four)"):
            run_marketdb('--studies', 'rrg')
        if st.button("📈 Run DeMark Scan (US ≥ $1B)"):
            from marketdb import demark as MDM
            with st.spinner("Running DeMark scan..."):
                _dm_df, _ = MDM.run_scan(None, 'us_total_market', log=lambda m: None)
            st.success(f"✓ DeMark scan complete — {0 if _dm_df is None else len(_dm_df)} stocks")
        if st.button("📰 Fetch ASX substantial-holder notices"):
            run_script(os.path.join(STOCKS, 'asx_substantial_holders.py'), STOCKS)

        st.subheader("Monthly — universe refresh")
        st.caption("Rebuilds the AU/US universe from Yahoo (new listings, delistings, sector/industry, "
                   "market caps, index membership, commodity flags). Also runs automatically from the "
                   "daily run when more than 31 days old.")
        if st.button("🌐 Refresh universe now"):
            run_marketdb('--refresh-universe', '--skip-fetch', '--studies')
        if st.button("🌐 Refresh universe + full daily run"):
            run_marketdb('--refresh-universe')

        st.subheader("Maintenance")
        if st.button("♻ Re-pull full price history (slow)"):
            run_marketdb('--full', '--studies')
        if st.button("🔁 Retry stale tickers"):
            run_marketdb('--retry-stale', '--studies')

# ═══════════════════════════════════════════════════════════════════════════════
# ETF INCOME PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "ETF Income":
    _eh1, _eh2, _eh3 = st.columns([900, 5000, 1500])
    with _eh2:
        st.title("💰 ETF Income")
    with _eh3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Run Scoring", key='top_etf_refresh'):
            run_script(os.path.join(ETF, 'etf_income_data.py'), ETF)
            st.rerun()

    st.markdown("""
        <div class="info-card">
            Quarterly-rebalance income ETF strategy. Scores a universe of weekly and
            monthly distribution ETFs on <b>NAV trend</b>, <b>risk-adjusted return</b>,
            and <b>distribution quality</b> (slope + consistency). Headline yield is
            deliberately under-weighted — a high yield with declining NAV is return of
            capital, not income. ETFs with negative 3-month NAV change are disqualified.
        </div>
    """, unsafe_allow_html=True)

    _etf_tabs = st.tabs(["🏆 Rankings", "📈 Backtest", "⚖️ Rebalance"])

    # ── Rankings tab ──────────────────────────────────────────────────────────
    with _etf_tabs[0]:
        etf_files = MR.list_frames('etf_income/')['name'].tolist()

        if not etf_files:
            st.warning("No ETF income data — run the scoring script first")
            if st.button("▶ Run ETF Income Scoring", type="primary", key='etf_first_run'):
                run_script(os.path.join(ETF, 'etf_income_data.py'), ETF)
                st.rerun()
        else:
            _etf_dates = [n.split('/', 1)[1] for n in etf_files][:30]
            _etf_sel = st.selectbox("Report date", _etf_dates, index=0, key='etf_date_sel')
            df_etf = MR.load_frame(f"etf_income/{_etf_sel}")

            if df_etf is not None:
                st.caption(f"Report date: {datetime.strptime(_etf_sel, '%Y%m%d').strftime('%d %b %Y')} — saved {MR.frame_updated(f'etf_income/{_etf_sel}') or ''}")

                _fc1, _fc2, _fc3 = st.columns([2, 2, 6])
                with _fc1:
                    _q_only = st.checkbox("Qualified only", value=True, key='etf_q_only')
                with _fc2:
                    _freq_f = st.selectbox("Frequency", ['All', 'weekly', 'monthly'], key='etf_freq_f')

                _dfv = df_etf.copy()
                if _q_only:
                    _dfv = _dfv[_dfv['qualified'] == True]
                if _freq_f != 'All':
                    _dfv = _dfv[_dfv['freq'] == _freq_f]

                def _etf_colour(val):
                    try:
                        v = float(val)
                        if v > 0: return 'color: #2dc653'
                        if v < 0: return 'color: #e63946'
                    except: pass
                    return ''

                _show_cols = ['rank', 'ticker', 'name', 'underlying', 'freq', 'price',
                              'score', 'chg_3m', 'chg_12m', 'total_ret_12m', 'sharpe',
                              'yield_ttm', 'dist_slope', 'dist_consist', 'underlying_rs']
                _dfv = _dfv[[c for c in _show_cols if c in _dfv.columns]]
                st.dataframe(
                    _dfv.style.map(_etf_colour, subset=[c for c in
                        ['chg_3m', 'chg_12m', 'total_ret_12m', 'sharpe', 'dist_slope', 'underlying_rs']
                        if c in _dfv.columns]).format({
                            'price': '{:.2f}', 'score': '{:.1f}', 'chg_3m': '{:+.1f}%',
                            'chg_12m': '{:+.1f}%', 'total_ret_12m': '{:+.1f}%',
                            'sharpe': '{:.2f}', 'yield_ttm': '{:.1f}%',
                            'dist_slope': '{:+.2f}', 'dist_consist': '{:.2f}',
                            'underlying_rs': '{:+.1f}',
                        }, na_rep='—'),
                    width='stretch', hide_index=True, height=600
                )

                st.markdown("""
                    <div style="font-size:12px;color:#888;line-height:1.6">
                    <b>score</b> — weighted rank composite: NAV 3m (0.20), underlying RS (0.20), Sharpe (0.15),
                    dist slope (0.15), NAV 12m (0.10), yield (0.10), dist consistency (0.10)<br>
                    <b>underlying_rs</b> — the underlying's blended 3m/12m return vs SPY in percentage points.
                    Positive = outperforming. Themes (diversified, VIX-short) score neutral.<br>
                    <b>dist_slope</b> — distribution trend as % of average payout per period. Negative = payouts shrinking.<br>
                    <b>dist_consist</b> — 1 minus coefficient of variation. 1.0 = identical payouts, below 0.5 = erratic.<br>
                    <b>qualified</b> — positive 3-month NAV change. A negative NAV trend means the yield is eating principal.
                    </div>
                """, unsafe_allow_html=True)

    # ── Backtest tab ──────────────────────────────────────────────────────────
    with _etf_tabs[1]:
        import plotly.graph_objects as go

        st.markdown("""
            <div class="info-card">
                Simulates the strategy historically: at each quarter start the universe
                is scored using only data available at that date, the top-N qualified
                ETFs are equal-weighted, and distributions accumulate as cash until
                redeployed at the next rebalance. Benchmarked against SPY (same
                distribution treatment). Quarters with few qualified ETFs go partially
                to cash — that is the NAV filter going defensive.
            </div>
        """, unsafe_allow_html=True)

        _bt_cfg_file = os.path.join(ETF, 'backtest_config.json')
        _bt_cfg = {'top_n': 5, 'years': 3, 'start_capital': 100000, 'freq_filter': 'all'}
        if os.path.exists(_bt_cfg_file):
            try:
                with open(_bt_cfg_file) as _f:
                    _bt_cfg.update(json.load(_f))
            except: pass

        _bc1, _bc2, _bc3, _bc4, _bc5 = st.columns(5)
        with _bc1:
            _bt_topn = st.number_input("Top N holdings", 1, 15, int(_bt_cfg['top_n']), key='bt_topn')
        with _bc2:
            _bt_years = st.number_input("Years", 1, 10, int(_bt_cfg['years']), key='bt_years')
        with _bc3:
            _bt_cap = st.number_input("Start capital", 10000, 10000000, int(_bt_cfg['start_capital']),
                                       step=10000, key='bt_cap')
        with _bc4:
            _bt_freq = st.selectbox("Universe", ['all', 'weekly', 'monthly'],
                                     index=['all', 'weekly', 'monthly'].index(_bt_cfg.get('freq_filter', 'all')),
                                     key='bt_freq')
        with _bc5:
            _bt_rfreq = st.selectbox("Rebalance", ['quarterly', 'monthly', 'semiannual'],
                                      index=['quarterly', 'monthly', 'semiannual'].index(
                                          _bt_cfg.get('rebal_freq', 'quarterly')),
                                      key='bt_rfreq',
                                      help="Monthly tested ~10pp worse over 3y — churns on 3m-NAV noise. Quarterly is the default for a reason.")

        _bd1, _bd2, _bd3, _bd4, _bd6, _bd5 = st.columns([2, 2, 2, 2, 2, 3])
        with _bd6:
            _bt_stop = st.number_input("Stop loss %", 0, 50,
                                        int(float(_bt_cfg.get('stop_loss_pct', 0.0)) * 100),
                                        step=5, key='bt_stop',
                                        help="Total-return stop from entry (price + distributions received). 0 = off. Tested: 20% = disaster brake (2 hits/3y, costless); 10-15% = whipsaw, destroys returns")
        with _bd1:
            _bt_mode = st.selectbox("Income mode", ['reinvest', 'draw'],
                                     index=['reinvest', 'draw'].index(_bt_cfg.get('income_mode', 'reinvest')),
                                     key='bt_mode',
                                     help="Reinvest: distributions compound. Draw: prop-style — withdraw the excess above start capital + buffer at each rebalance")
        with _bd2:
            _bt_buffer = st.number_input("Draw buffer %", 0, 50,
                                          int(float(_bt_cfg.get('draw_threshold_pct', 0.10)) * 100),
                                          step=5, key='bt_buffer', disabled=_bt_mode != 'draw',
                                          help="No withdrawals until equity exceeds start capital + this buffer; each draw leaves the buffer working")
        with _bd3:
            st.markdown("<br>", unsafe_allow_html=True)
            _bt_hedge = st.checkbox("VIX hedge", value=bool(_bt_cfg.get('hedge_enabled', False)),
                                     key='bt_hedge',
                                     help="Hold VIXY while the VIX term structure is inverted (VIX ≥ VIX3M)")
        with _bd4:
            _bt_hpct = st.number_input("Hedge %", 5, 30, int(float(_bt_cfg.get('hedge_pct', 0.10)) * 100),
                                        step=5, key='bt_hpct', disabled=not _bt_hedge)
        with _bd5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("▶ Run Backtest", type="primary", key='bt_run'):
                with open(_bt_cfg_file, 'w') as _f:
                    json.dump({'top_n': int(_bt_topn), 'years': int(_bt_years),
                               'start_capital': int(_bt_cap), 'freq_filter': _bt_freq,
                               'hedge_enabled': bool(_bt_hedge),
                               'hedge_pct': float(_bt_hpct) / 100,
                               'income_mode': _bt_mode,
                               'draw_threshold_pct': float(_bt_buffer) / 100,
                               'rebal_freq': _bt_rfreq,
                               'stop_loss_pct': float(_bt_stop) / 100}, _f, indent=2)
                run_script(os.path.join(ETF, 'etf_backtest.py'), ETF)
                st.rerun()

        _bt_summaries = MR.report_dates('etf_backtest')

        if not _bt_summaries:
            st.caption("No backtest runs yet")
        else:
            _bt_dates = [d.replace('-', '') for d in _bt_summaries][:20]
            _bt_sel = st.selectbox("Run date", _bt_dates, index=0, key='bt_date_sel')

            _, _bt_sum, _ = MR.load_report('etf_backtest', f"{_bt_sel[:4]}-{_bt_sel[4:6]}-{_bt_sel[6:]}")
            _bt_sum = _bt_sum or {}

            _sc1, _sc2, _sc3, _sc4, _sc5 = st.columns(5)
            _ret_col = '#2dc653' if _bt_sum['total_return'] > 0 else '#e63946'
            _exc_col = '#2dc653' if _bt_sum['excess_return'] > 0 else '#e63946'
            with _sc1:
                st.markdown(f"""<div class="macro-card"><div class="macro-label">Final Value</div>
                    <div style="font-size:20px;font-weight:bold">${_bt_sum['final_value']:,.0f}</div>
                    <div style="font-size:11px;color:{_ret_col}">{_bt_sum['total_return']:+.1f}% total</div></div>""",
                    unsafe_allow_html=True)
            with _sc2:
                st.markdown(f"""<div class="macro-card"><div class="macro-label">CAGR</div>
                    <div style="font-size:20px;font-weight:bold;color:{_ret_col}">{_bt_sum['cagr']:+.1f}%</div>
                    <div style="font-size:11px;color:#888">{_bt_sum['n_quarters']} quarters</div></div>""",
                    unsafe_allow_html=True)
            with _sc3:
                st.markdown(f"""<div class="macro-card"><div class="macro-label">Max Drawdown</div>
                    <div style="font-size:20px;font-weight:bold;color:#e63946">{_bt_sum['max_drawdown']:.1f}%</div>
                    </div>""", unsafe_allow_html=True)
            with _sc4:
                _int_txt = f" | +${_bt_sum['interest_total']:,.0f} interest" if _bt_sum.get('interest_total') else ''
                st.markdown(f"""<div class="macro-card"><div class="macro-label">Income Collected</div>
                    <div style="font-size:20px;font-weight:bold;color:#00b4d8">${_bt_sum['income_total']:,.0f}</div>
                    <div style="font-size:11px;color:#888">${_bt_sum['income_avg_qtr']:,.0f}/qtr avg{_int_txt}</div></div>""",
                    unsafe_allow_html=True)
            with _sc5:
                _bench_tkr = _bt_sum.get('bench_ticker', 'JEPI')
                _bench_ret = _bt_sum.get('bench_return')
                _bench_exc = _bt_sum.get('excess_vs_bench')
                if _bench_exc is not None:
                    _bex_col = '#2dc653' if _bench_exc > 0 else '#e63946'
                    st.markdown(f"""<div class="macro-card"><div class="macro-label">vs {_bench_tkr} passive</div>
                        <div style="font-size:20px;font-weight:bold;color:{_bex_col}">{_bench_exc:+.1f}%</div>
                        <div style="font-size:11px;color:#888">{_bench_tkr}: {_bench_ret:+.1f}% |
                        SPY ref: {_bt_sum['spy_return']:+.1f}%</div></div>""",
                        unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div class="macro-card"><div class="macro-label">vs SPY</div>
                        <div style="font-size:20px;font-weight:bold;color:{_exc_col}">{_bt_sum['excess_return']:+.1f}%</div>
                        <div style="font-size:11px;color:#888">SPY: {_bt_sum['spy_return']:+.1f}%</div></div>""",
                        unsafe_allow_html=True)

            if _bt_sum.get('income_mode') == 'draw':
                st.markdown(f"""<div class="macro-card" style="border-left:3px solid #2dc653">
                    <div class="macro-label">Income Draw — prop-style withdrawals</div>
                    <div style="font-size:13px;color:#ccc">
                        Withdrawn: <span style="color:#2dc653;font-weight:bold">${_bt_sum.get('withdrawn_total', 0):,.0f}</span>
                        (${_bt_sum.get('withdrawn_avg_qtr', 0):,.0f}/qtr avg)
                        &nbsp;|&nbsp; Maintain level: ${_bt_sum.get('maintain_level') or 0:,.0f}
                        &nbsp;|&nbsp; <span style="color:#888">Final value is the remaining capital base;
                        total return and drawdown include withdrawals (a draw is not a loss)</span>
                    </div></div>""", unsafe_allow_html=True)

            if _bt_sum.get('stop_loss_pct', 0) > 0:
                _stop_evs = _bt_sum.get('stop_events', [])
                _ev_txt = ' &nbsp;|&nbsp; '.join(
                    f"{e['date']} {e['ticker']} ({e['tr']:+.1f}%)" for e in _stop_evs) if _stop_evs else 'none triggered'
                st.markdown(f"""<div class="macro-card" style="border-left:3px solid #9b5de5">
                    <div class="macro-label">Stop Loss — {_bt_sum['stop_loss_pct']:.0%} total-return from entry</div>
                    <div style="font-size:13px;color:#ccc">{_bt_sum.get('stops_hit', 0)} hit: {_ev_txt}</div>
                    </div>""", unsafe_allow_html=True)

            if _bt_sum.get('hedge_enabled'):
                _hp_col = '#2dc653' if _bt_sum.get('hedge_pnl', 0) > 0 else '#e63946'
                st.markdown(f"""<div class="macro-card" style="border-left:3px solid #f77f00">
                    <div class="macro-label">VIX Hedge — VIXY on term-structure inversion</div>
                    <div style="font-size:13px;color:#ccc">
                        Hedged {_bt_sum.get('hedge_days', 0)} days ({_bt_sum.get('hedge_days_pct', 0)}% of period)
                        &nbsp;|&nbsp; Hedge P&L: <span style="color:{_hp_col};font-weight:bold">${_bt_sum.get('hedge_pnl', 0):+,.0f}</span>
                        &nbsp;|&nbsp; <span style="color:#888">Compare max drawdown and CAGR against an unhedged run to price the insurance</span>
                    </div></div>""", unsafe_allow_html=True)

            _df_eq = MR.load_frame(f"etf_backtest/{_bt_sel}/equity")
            if _df_eq is not None:
                _fig_bt = go.Figure()
                _fig_bt.add_trace(go.Scatter(x=_df_eq['date'], y=_df_eq['value'],
                    mode='lines', name='Strategy', line=dict(color='#00b4d8', width=2)))
                if 'bench' in _df_eq.columns:
                    _fig_bt.add_trace(go.Scatter(x=_df_eq['date'], y=_df_eq['bench'],
                        mode='lines', name=f"{_bt_sum.get('bench_ticker', 'JEPI')} passive (same rules)",
                        line=dict(color='#f4a261', width=1.8)))
                if 'spy' in _df_eq.columns:
                    _fig_bt.add_trace(go.Scatter(x=_df_eq['date'], y=_df_eq['spy'],
                        mode='lines', name='SPY (growth ref)', line=dict(color='#666', width=1, dash='dot')))
                _fig_bt.update_layout(
                    title='Equity Curve', height=380,
                    plot_bgcolor=get_chart_theme()['plot_bgcolor'],
                    paper_bgcolor=get_chart_theme()['paper_bgcolor'],
                    font=dict(color=get_chart_theme()['font_color']),
                    xaxis=dict(gridcolor=get_chart_theme()['gridcolor']),
                    yaxis=dict(gridcolor=get_chart_theme()['gridcolor'], tickprefix='$'),
                    legend=dict(orientation='h', y=1.08),
                    margin=dict(l=60, r=20, t=50, b=30),
                )
                st.plotly_chart(_fig_bt, width='stretch')

                # Money flows: cash sawtooth + cumulative income
                if 'cash' in _df_eq.columns and 'income_cum' in _df_eq.columns:
                    _fig_mf = go.Figure()
                    _fig_mf.add_trace(go.Scatter(
                        x=_df_eq['date'], y=_df_eq['cash'],
                        mode='lines', name='Cash (distributions awaiting rebalance)',
                        line=dict(color='#f77f00', width=1.5),
                        fill='tozeroy', fillcolor='rgba(247,127,0,0.15)'))
                    if 'hedge' in _df_eq.columns and _df_eq['hedge'].max() > 0:
                        _fig_mf.add_trace(go.Scatter(
                            x=_df_eq['date'], y=_df_eq['hedge'],
                            mode='lines', name='VIXY hedge position',
                            line=dict(color='#9b5de5', width=1.5),
                            fill='tozeroy', fillcolor='rgba(155,93,229,0.15)'))
                    _fig_mf.add_trace(go.Scatter(
                        x=_df_eq['date'], y=_df_eq['income_cum'],
                        mode='lines', name='Cumulative income collected',
                        line=dict(color='#00b4d8', width=2), yaxis='y2'))
                    if 'withdrawn_cum' in _df_eq.columns and _df_eq['withdrawn_cum'].max() > 0:
                        _fig_mf.add_trace(go.Scatter(
                            x=_df_eq['date'], y=_df_eq['withdrawn_cum'],
                            mode='lines', name='Cumulative withdrawn (in pocket)',
                            line=dict(color='#2dc653', width=2, dash='dash'), yaxis='y2'))
                    _fig_mf.update_layout(
                        title='Money Flows — distributions in, redeployed each quarter',
                        height=320,
                        plot_bgcolor=get_chart_theme()['plot_bgcolor'],
                        paper_bgcolor=get_chart_theme()['paper_bgcolor'],
                        font=dict(color=get_chart_theme()['font_color']),
                        xaxis=dict(gridcolor=get_chart_theme()['gridcolor']),
                        yaxis=dict(gridcolor=get_chart_theme()['gridcolor'], tickprefix='$',
                                   title='Cash balance'),
                        yaxis2=dict(overlaying='y', side='right', tickprefix='$',
                                    title='Cumulative income', showgrid=False),
                        legend=dict(orientation='h', y=1.12),
                        margin=dict(l=60, r=60, t=50, b=30),
                    )
                    st.plotly_chart(_fig_mf, width='stretch')
                    st.markdown("""
                        <div style="font-size:12px;color:#888;line-height:1.6">
                        The orange sawtooth is the cash account: each distribution payment adds to it
                        through the quarter, then it drops to zero at rebalance when everything is
                        redeployed into the new top-N. Each tooth ≈ one quarter's income. The blue line
                        is total income collected since the start — its slope is your income run-rate.
                        In <b>draw</b> mode the green dashed line is cash actually withdrawn (in pocket) —
                        the gap between it and the blue line is income that stayed invested to hold the
                        maintain level.
                        </div>
                    """, unsafe_allow_html=True)

            _df_qtr = MR.load_frame(f"etf_backtest/{_bt_sel}/quarters")
            if _df_qtr is not None:
                st.markdown("**Quarterly holdings**")
                st.dataframe(_df_qtr, width='stretch', hide_index=True)

    # ── Rebalance tab ─────────────────────────────────────────────────────────
    with _etf_tabs[2]:
        st.markdown("""
            <div class="info-card">
                Enter your current holdings and compare against the latest rankings.
                <b>HOLD</b> — still qualified and ranked inside the buy zone.
                <b>REVIEW</b> — qualified but slipped outside the top ranks.
                <b>SELL</b> — disqualified (negative 3-month NAV trend).
                Candidates are top-ranked qualified ETFs you don't hold.
            </div>
        """, unsafe_allow_html=True)

        # ── Live VIX hedge signal ─────────────────────────────────────────────
        @st.cache_data(ttl=3600, show_spinner=False)
        def _fetch_vix_signal():
            import yfinance as _yf
            vix = _yf.Ticker('^VIX').history(period='6mo')['Close']
            vix3m = _yf.Ticker('^VIX3M').history(period='6mo')['Close']
            # normalise both to naive dates — the two indices carry different timestamps
            vix.index = vix.index.tz_localize(None).normalize()
            vix3m.index = vix3m.index.tz_localize(None).normalize()
            ratio = (vix / vix3m.reindex(vix.index).ffill()).dropna()
            # hysteresis walk: on >= 1.0, off <= 0.95
            state = False
            for r in ratio.values:
                if not state and r >= 1.0: state = True
                elif state and r <= 0.95: state = False
            return float(ratio.iloc[-1]), state, float(vix.iloc[-1])

        try:
            _vr, _hedge_on, _vix_now = _fetch_vix_signal()
            if _hedge_on:
                st.markdown(f"""
                    <div class="macro-card" style="border-left:4px solid #e63946">
                        <div style="font-weight:bold;color:#e63946">🛡 HEDGE ON — VIX term structure inverted</div>
                        <div style="font-size:12px;color:#aaa">VIX/VIX3M: {_vr:.3f} (≥ 1.0 = backwardation) &nbsp;|&nbsp;
                        VIX: {_vix_now:.1f} &nbsp;|&nbsp; Strategy holds ~10% VIXY while inverted; exits below 0.95</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div class="macro-card" style="border-left:4px solid #2dc653">
                        <div style="font-weight:bold;color:#2dc653">🛡 HEDGE OFF — VIX term structure in contango</div>
                        <div style="font-size:12px;color:#aaa">VIX/VIX3M: {_vr:.3f} (hedge triggers at ≥ 1.0) &nbsp;|&nbsp;
                        VIX: {_vix_now:.1f} &nbsp;|&nbsp; Long-vol ETPs decay in contango — no hedge held</div>
                    </div>""", unsafe_allow_html=True)
        except Exception:
            st.caption("VIX signal unavailable")

        # strategy settings (stop level, buy zone) — fresh read each render
        import sys as _sys
        if ETF not in _sys.path:
            _sys.path.insert(0, ETF)
        from etf_income_data import load_etf_settings as _load_etf_s
        _etf_s = _load_etf_s()
        _live_stop = float(_etf_s.get('stop_loss_pct', 0.20))

        _hold_file = os.path.join(ETF, 'holdings.json')
        _holdings = []
        if os.path.exists(_hold_file):
            try:
                with open(_hold_file) as _f:
                    _holdings = json.load(_f).get('holdings', [])
            except: pass

        # ── Ticker price check — for filling entry price on a manual add ──────
        _tc1, _tc2, _tc3 = st.columns([2, 1, 5])
        with _tc1:
            _chk_ticker = st.text_input("Check ticker", key='etf_chk_ticker',
                                         placeholder="e.g. AMDY",
                                         label_visibility="collapsed")
        with _tc2:
            _chk_clicked = st.button("💲 Check Price", key='etf_chk_btn')
        if _chk_clicked and _chk_ticker.strip():
            _ct = _chk_ticker.strip().upper()
            try:
                import yfinance as _yf
                _ch = _yf.Ticker(_ct).history(period='1mo', auto_adjust=False)
                if _ch is None or _ch.empty:
                    st.session_state['etf_chk_result'] = f"❌ {_ct}: no data returned"
                else:
                    _ch.index = _ch.index.tz_localize(None)
                    _cp = float(_ch['Close'].iloc[-1])
                    _pp = float(_ch['Close'].iloc[-2]) if len(_ch) > 1 else _cp
                    _chg = (_cp / _pp - 1) * 100
                    _pxdate = _ch.index[-1].strftime('%d %b')
                    _dv = _ch['Dividends'][_ch['Dividends'] > 0]
                    _dv_txt = (f" | last dist: {float(_dv.iloc[-1]):.4f} on {_dv.index[-1].strftime('%d %b')}"
                               if len(_dv) else " | no dists last month")
                    st.session_state['etf_chk_result'] = (
                        f"✅ **{_ct}**: **{_cp:.2f}** ({_chg:+.2f}% vs prior close, as of {_pxdate}){_dv_txt}")
            except Exception as _e:
                st.session_state['etf_chk_result'] = f"❌ {_ct}: {_e}"
        if st.session_state.get('etf_chk_result'):
            with _tc3:
                st.markdown(st.session_state['etf_chk_result'])

        _flash = st.session_state.pop('etf_add_flash', None)
        if _flash:
            st.success(_flash)

        _hold_cols = ['ticker', 'shares', 'entry_price', 'entry_date']
        if _holdings:
            _df_hold = pd.DataFrame(_holdings)
            for _c in _hold_cols:
                if _c not in _df_hold.columns:
                    _df_hold[_c] = None
            _df_hold = _df_hold[_hold_cols]
        else:
            _df_hold = pd.DataFrame({'ticker': [''], 'shares': [0.0],
                                     'entry_price': [0.0], 'entry_date': ['']})
        _edited = st.data_editor(_df_hold, num_rows='dynamic', width='stretch',
                                  key='etf_hold_editor',
                                  column_config={
                                      'ticker': st.column_config.TextColumn('Ticker'),
                                      'shares': st.column_config.NumberColumn('Shares', format='%.2f'),
                                      'entry_price': st.column_config.NumberColumn(
                                          'Entry Price', format='%.2f',
                                          help='Fill price — needed for the live total-return stop'),
                                      'entry_date': st.column_config.TextColumn(
                                          'Entry Date', help='YYYY-MM-DD — distributions after this date count toward total return'),
                                  })
        if st.button("💾 Save Holdings", key='etf_save_hold'):
            _clean = []
            for _, r in _edited.iterrows():
                if not str(r['ticker']).strip():
                    continue
                _clean.append({
                    'ticker'     : str(r['ticker']).strip().upper(),
                    'shares'     : float(r['shares'] or 0),
                    'entry_price': float(r['entry_price']) if r['entry_price'] else None,
                    'entry_date' : str(r['entry_date']).strip() or None,
                })
            with open(_hold_file, 'w') as _f:
                json.dump({'holdings': _clean, 'updated': datetime.now().isoformat()}, _f, indent=2)
            st.success(f"Saved {len(_clean)} holdings")

        @st.cache_data(ttl=900, show_spinner=False)
        def _fetch_holding_tr(ticker, entry_price, entry_date):
            """Live total-return from entry: (price + divs received) / entry - 1."""
            import yfinance as _yf
            try:
                h = _yf.Ticker(ticker).history(period='2y', auto_adjust=False)
                if h is None or h.empty:
                    return None
                h.index = h.index.tz_localize(None)
                px = float(h['Close'].iloc[-1])
                divs_ps = 0.0
                if entry_date:
                    _ed = pd.Timestamp(entry_date)
                    divs_ps = float(h['Dividends'][h.index > _ed].sum())
                return (px + divs_ps) / float(entry_price) - 1
            except Exception:
                return None

        @st.cache_data(ttl=900, show_spinner=False)
        def _fetch_next_dist(ticker):
            """Estimate next distribution date from recent dividend cadence.
            Returns (date_str, inferred_freq) or (None, None)."""
            import yfinance as _yf
            try:
                h = _yf.Ticker(ticker).history(period='6mo', auto_adjust=False)
                if h is None or h.empty:
                    return None, None
                h.index = h.index.tz_localize(None)
                dv = h['Dividends'][h['Dividends'] > 0]
                if len(dv) < 2:
                    return None, None
                _dates = dv.index[-8:]
                _gaps = _dates.to_series().diff().dropna().dt.days
                _gap = int(_gaps.median())
                _freq = ('weekly' if _gap <= 10 else
                         'monthly' if _gap <= 45 else 'quarterly')
                _nxt = _dates[-1] + pd.Timedelta(days=_gap)
                _today = pd.Timestamp.now().normalize()
                while _nxt < _today:
                    _nxt += pd.Timedelta(days=_gap)
                return _nxt.strftime('%d %b'), _freq
            except Exception:
                return None, None

        # Signals vs latest rankings
        _rank_files = MR.list_frames('etf_income/')['name'].tolist()
        if not _rank_files:
            st.caption("Run the scoring first to generate rebalance signals")
        else:
            _df_rank = MR.load_frame(_rank_files[0])
            _rank_date = _rank_files[0].split('/', 1)[1]
            st.caption(f"Signals vs rankings from {datetime.strptime(_rank_date, '%Y%m%d').strftime('%d %b %Y')}")

            _held_rows = [r for _, r in _edited.iterrows() if str(r['ticker']).strip()]
            _held = [str(r['ticker']).strip().upper() for r in _held_rows]
            _buy_zone = int(_etf_s.get('buy_zone', 8))  # rank threshold for HOLD vs REVIEW

            if _held and _df_rank is not None:
                _sig_rows = []
                for _hr in _held_rows:
                    _t = str(_hr['ticker']).strip().upper()
                    # live total-return from entry vs the stop
                    _tr_txt, _stop_txt = '—', '—'
                    if _hr['entry_price'] and float(_hr['entry_price'] or 0) > 0:
                        _tr = _fetch_holding_tr(_t, float(_hr['entry_price']),
                                                 str(_hr['entry_date'] or '').strip() or None)
                        if _tr is not None:
                            _tr_txt = f"{_tr * 100:+.1f}%"
                            if _tr <= -_live_stop:
                                _stop_txt = '⛔ HIT'
                            elif _tr <= -_live_stop * 0.75:
                                _stop_txt = '⚠ NEAR'
                            else:
                                _stop_txt = '✓ OK'

                    # distribution cadence + estimated next payment
                    _nxt_date, _inf_freq = _fetch_next_dist(_t)
                    _nxt_txt = _nxt_date or '—'

                    _row = _df_rank[_df_rank['ticker'] == _t]
                    if _row.empty:
                        _sig_rows.append({'Ticker': _t, 'Freq': _inf_freq or '—',
                                          'Next Pay (est)': _nxt_txt,
                                          'Rank': '—', 'Score': '—',
                                          'Qualified': '—', 'Signal': 'NOT IN UNIVERSE',
                                          'TR from entry': _tr_txt, 'Stop': _stop_txt})
                        continue
                    _r = _row.iloc[0]
                    _freq = str(_r['freq']) if 'freq' in _row.columns and pd.notna(_r.get('freq')) else (_inf_freq or '—')
                    _qual = bool(_r['qualified'])
                    if not _qual:
                        _sig = 'SELL'
                    elif int(_r['rank']) <= _buy_zone:
                        _sig = 'HOLD'
                    else:
                        _sig = 'REVIEW'
                    _sig_rows.append({'Ticker': _t, 'Freq': _freq,
                                      'Next Pay (est)': _nxt_txt,
                                      'Rank': int(_r['rank']),
                                      'Score': f"{_r['score']:.1f}",
                                      'Qualified': '✓' if _qual else '✗', 'Signal': _sig,
                                      'TR from entry': _tr_txt, 'Stop': _stop_txt})

                def _sig_colour(val):
                    if val == 'HOLD': return 'color: #2dc653'
                    if val == 'REVIEW': return 'color: #f77f00'
                    if val in ('SELL', 'NOT IN UNIVERSE'): return 'color: #e63946'
                    return ''

                def _stop_colour(val):
                    if '✓' in str(val): return 'color: #2dc653'
                    if '⚠' in str(val): return 'color: #f77f00'
                    if '⛔' in str(val): return 'color: #e63946'
                    return ''

                st.markdown(f"**Your holdings** &nbsp; <span style='font-size:12px;color:#888'>"
                            f"stop: -{_live_stop:.0%} total-return from entry (price + distributions received) "
                            f"&nbsp;|&nbsp; next pay estimated from recent distribution cadence (ex-date)</span>",
                            unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(_sig_rows).style
                             .map(_sig_colour, subset=['Signal'])
                             .map(_stop_colour, subset=['Stop']),
                             width='stretch', hide_index=True)

            if _df_rank is not None:
                _cands = _df_rank[(_df_rank['qualified'] == True) &
                                  (~_df_rank['ticker'].isin(_held))].head(_buy_zone)
                if not _cands.empty:
                    st.markdown("**Top candidates not held**")
                    _cand_cols = [c for c in ['rank', 'ticker', 'name', 'freq', 'score',
                                              'chg_3m', 'yield_ttm', 'dist_slope'] if c in _cands.columns]
                    st.dataframe(_cands[_cand_cols], width='stretch', hide_index=True)

                    if st.button(f"➕ Add all {len(_cands)} candidates to holdings",
                                 key='etf_add_cands',
                                 help="Adds each with the scan price as entry price and today as entry date — "
                                      "update to your actual fill prices and share counts after buying"):
                        _cur_hold = []
                        if os.path.exists(_hold_file):
                            try:
                                with open(_hold_file) as _f:
                                    _cur_hold = json.load(_f).get('holdings', [])
                            except: pass
                        _have = {str(h.get('ticker', '')).upper() for h in _cur_hold}
                        _added = []
                        for _, _c in _cands.iterrows():
                            _ct = str(_c['ticker']).upper()
                            if _ct in _have:
                                continue
                            _cur_hold.append({
                                'ticker'     : _ct,
                                'shares'     : 0.0,
                                'entry_price': float(_c['price']) if 'price' in _cands.columns
                                               and pd.notna(_c.get('price')) else None,
                                'entry_date' : datetime.now().strftime('%Y-%m-%d'),
                            })
                            _added.append(_ct)
                        with open(_hold_file, 'w') as _f:
                            json.dump({'holdings': _cur_hold,
                                       'updated': datetime.now().isoformat()}, _f, indent=2)
                        if 'etf_hold_editor' in st.session_state:
                            del st.session_state['etf_hold_editor']
                        st.session_state['etf_add_flash'] = (
                            f"Added {', '.join(_added) if _added else 'nothing new'} — "
                            "now edit shares and entry prices to your actual fills, then Save Holdings")
                        st.rerun()

                # ── Position size calculator (AUD account) ────────────────────
                st.divider()
                with st.expander("🧮 Position Size Calculator — AUD account", expanded=False):
                    @st.cache_data(ttl=1800, show_spinner=False)
                    def _fetch_audusd():
                        import yfinance as _yf
                        try:
                            _h = _yf.Ticker('AUDUSD=X').history(period='5d')
                            return float(_h['Close'].iloc[-1]) if _h is not None and not _h.empty else None
                        except Exception:
                            return None

                    _fx_live = _fetch_audusd()
                    _pc1, _pc2, _pc3 = st.columns(3)
                    with _pc1:
                        _aud_bal = st.number_input("Account balance (AUD)", 0.0, 100000000.0,
                                                    100000.0, step=1000.0, key='etf_calc_aud')
                    with _pc2:
                        _fx = st.number_input("AUD/USD rate", 0.30, 1.50,
                                               round(_fx_live, 4) if _fx_live else 0.6500,
                                               step=0.0010, format="%.4f", key='etf_calc_fx',
                                               help="Live rate prefilled — override with your broker's rate to include their FX spread")
                    _usd_bal = _aud_bal * _fx
                    with _pc3:
                        st.markdown(f"""<div class="macro-card"><div class="macro-label">USD equivalent</div>
                            <div style="font-size:20px;font-weight:bold;color:#00b4d8">${_usd_bal:,.0f}</div>
                            <div style="font-size:11px;color:#888">at {_fx:.4f}</div></div>""",
                            unsafe_allow_html=True)

                    _qual_tickers = list(_df_rank[_df_rank['qualified'] == True]['ticker'])
                    _default_buy = _qual_tickers[:_buy_zone]
                    _buy_sel = st.multiselect("Buy list", options=list(_df_rank['ticker']),
                                               default=_default_buy, key='etf_calc_buylist',
                                               help="Defaults to the qualified funds inside the buy zone — adjust to your actual buy list")

                    if _buy_sel:
                        _alloc = _usd_bal / len(_buy_sel)
                        _calc_rows, _spend = [], 0.0
                        for _t in _buy_sel:
                            _prow = _df_rank[_df_rank['ticker'] == _t]
                            _p = float(_prow.iloc[0]['price']) if not _prow.empty and pd.notna(_prow.iloc[0].get('price')) else None
                            if not _p:
                                _calc_rows.append({'Ticker': _t, 'Price (USD)': 'n/a', 'Shares': '—',
                                                   'Cost (USD)': '—', 'Cost (AUD)': '—'})
                                continue
                            _sh = int(_alloc // _p)
                            _cost = _sh * _p
                            _spend += _cost
                            _calc_rows.append({
                                'Ticker'    : _t,
                                'Price (USD)': f"{_p:.2f}",
                                'Shares'    : _sh,
                                'Cost (USD)': f"${_cost:,.2f}",
                                'Cost (AUD)': f"${_cost / _fx:,.2f}" if _fx else '—',
                            })
                        st.dataframe(pd.DataFrame(_calc_rows), width='stretch', hide_index=True)
                        _left = _usd_bal - _spend
                        st.caption(f"Per position: \\${_alloc:,.0f} USD &nbsp;|&nbsp; "
                                   f"Total spend: \\${_spend:,.2f} USD &nbsp;|&nbsp; "
                                   f"Leftover cash: \\${_left:,.2f} USD (≈A\\${_left / _fx:,.2f}) &nbsp;|&nbsp; "
                                   f"Whole shares, floored — prices from the {datetime.strptime(_rank_date, '%Y%m%d').strftime('%d %b')} scan, "
                                   f"actual fills will differ slightly")

# ═══════════════════════════════════════════════════════════════════════════════
# DEMARK SIGNALS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "DeMark Signals":
    marketdb_ready()
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

    from marketdb import demark as MDM

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
        with st.spinner("Scanning signals from the price store..."):
            cap_min_val = int(cap_min * 1e9) if cap_min > 0 else 0
            cap_max_val = int(cap_max * 1e9) if cap_max_enabled and cap_max else None
            df_scan, report = MDM.run_scan(
                None, 'us_total_market',
                market_cap_min = cap_min_val,
                market_cap_max = cap_max_val,
                end_date       = scan_date.strftime('%Y-%m-%d'),
                log            = lambda m: None,
            )
        if df_scan is not None:
            st.success(f"✓ Scan complete — {len(df_scan)} stocks analysed")
            st.rerun()

    # ── Date selector ─────────────────────────────────────────────────────────
    report_dates = MR.demark_dates()

    if not report_dates:
        st.info("No scan results found — run the scanner above")
    else:
        dates     = report_dates[:10]
        sel_date  = st.selectbox("Select scan date", dates)
        df, report_txt_db = MR.demark_latest(run_date=sel_date)

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
                report_txt = report_txt_db
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
    st.title("⚙️ Settings")
    _stab_ai, _stab_fa, _stab_models, _stab_etf, _stab_rank, _stab_act, _stab_gen = st.tabs([
        "🤖 AI",
        "📊 Fundamental Analysis",
        "🧠 Models",
        "💰 ETF Income",
        "🎛️ Rank",
        "📋 Screeners",
        "🔧 General",
    ])

    with _stab_ai:
            st.title("🤖 AI Settings")

            _ai_s    = load_settings()
            _ai_feat = _ai_s.get('ai_features', {})
            _ai_prmp = _ai_s.get('ai_prompts', DEFAULT_SETTINGS.get('ai_prompts', {}))

            def _save_ai_settings(feat, prompts):
                s = load_settings()
                s['ai_features'] = feat
                s['ai_prompts']  = prompts
                save_settings(s)

            # ── Tabs ──────────────────────────────────────────────────────────────────
            _ai_tabs = st.tabs([
                "⚙️ General",
                "🇦🇺 AU Breadth",
                "🇺🇸 US Breadth",
                "💳 Debt Markets",
                "📊 AU Benchmark",
                "📊 US Benchmark",
                "🪨 Commodities",
                "📅 Sea Sectors",
                "📅 Sea Stocks",
                "📅 Sea Presidential",
                "🏦 Fundamental Analysis",
                "⚖️ FA Comparison",
            ])

            # ── General tab ───────────────────────────────────────────────────────────
            with _ai_tabs[0]:
                _ai_enabled = st.toggle("Enable AI Assessments", value=_ai_feat.get('enabled', False))
                st.markdown("#### Active Provider")
                _provider_list = ["anthropic", "openai", "ollama"]
                _provider_labels = {
                    "anthropic": "🟣 Claude (Anthropic)",
                    "openai":    "🟢 ChatGPT (OpenAI)",
                    "ollama":    "🦙 Ollama (Local)",
                }
                _cur_prov = _ai_feat.get('provider', 'anthropic')
                _provider = st.radio("Active provider", options=_provider_list,
                                      index=_provider_list.index(_cur_prov) if _cur_prov in _provider_list else 0,
                                      horizontal=True,
                                      format_func=lambda x: _provider_labels.get(x, x),
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
                _oi_ids, _oi_labels, _oi_models = get_model_options('openai')
                _oi_cur = _ai_feat.get('openai_model', 'gpt-4o')
                if _oi_ids:
                    _oi_options = _oi_ids + ['__custom__']
                    _oi_display = _oi_labels + ['✏️ Custom model...']
                    _oi_idx = _oi_options.index(_oi_cur) if _oi_cur in _oi_options else len(_oi_options) - 1
                    _openai_model = st.selectbox("OpenAI Model", options=_oi_options, index=_oi_idx,
                                                  format_func=lambda x: _oi_display[_oi_options.index(x)],
                                                  key='openai_model_sel')
                    if _openai_model == '__custom__':
                        _openai_model = st.text_input("Custom model name", value=_oi_cur if _oi_cur not in _oi_ids else '',
                                                       key='openai_model_custom')
                    else:
                        _sel_oi = next((m for m in _oi_models if m['id'] == _openai_model), None)
                        if _sel_oi and _sel_oi.get('notes'):
                            st.caption(f"ℹ️ {_sel_oi['notes']}")
                else:
                    _openai_model = st.text_input("OpenAI Model", value=_oi_cur)

                st.divider()
                st.markdown("#### 🦙 Ollama (Local)")
                _ollama_url   = st.text_input("Ollama URL", value=_ai_feat.get('ollama_url', 'http://localhost:11434'),
                                               help="URL where Ollama is running")
                _ol_ids, _ol_labels, _ol_models = get_model_options('ollama', _ollama_url)
                _ol_cur = _ai_feat.get('ollama_model', 'llama3.1:8b')
                if _ol_ids:
                    _ol_options = _ol_ids + ['__custom__']
                    _ol_display = _ol_labels + ['✏️ Custom model...']
                    _ol_idx = _ol_options.index(_ol_cur) if _ol_cur in _ol_options else len(_ol_options) - 1
                    _ol_sel = st.selectbox("Ollama Model", options=_ol_options, index=_ol_idx,
                                            format_func=lambda x: _ol_display[_ol_options.index(x)],
                                            key='ollama_model_sel')
                    if _ol_sel == '__custom__':
                        _ollama_model = st.text_input("Custom model name", value=_ol_cur if _ol_cur not in _ol_ids else '',
                                                       key='ollama_model_custom', help="e.g. deepseek-r1:8b")
                    else:
                        _ollama_model = _ol_sel
                        _sel_info = next((m for m in _ol_models if m['id'] == _ol_sel), None)
                        if _sel_info and _sel_info.get('notes'):
                            st.caption(f"ℹ️ {_sel_info['notes']}")
                else:
                    _ollama_model = st.text_input("Ollama Model", value=_ol_cur,
                                                   help="Add models to models.json for a dropdown")

                st.markdown("")
                if st.button("💾 Save General Settings", type="primary", key='ai_save_general'):
                    _new_feat = {
                        'enabled'          : _ai_enabled,
                        'provider'         : _provider,
                        'anthropic_api_key': _claude_key,
                        'model'            : _claude_model,
                        'openai_api_key'   : _openai_key,
                        'openai_model'     : _openai_model,
                        'ollama_url'       : _ollama_url,
                        'ollama_model'     : _ollama_model,
                    }
                    _save_ai_settings(_new_feat, _ai_prmp)
                    _prov_names = {'anthropic': 'Claude', 'openai': 'ChatGPT', 'ollama': f'Ollama ({_ollama_model})'}
                    st.success(f"Saved — using {_prov_names.get(_provider, _provider)}")

            # ── Prompt tabs ───────────────────────────────────────────────────────────
            _prompt_defs = [
                ('au_breadth',       'AU Breadth', '🇦🇺 AU Breadth', _ai_tabs[1]),
                ('us_breadth',       'US Breadth', '🇺🇸 US Breadth', _ai_tabs[2]),
                ('consumer_credit',  'Debt Markets — Consumer Credit', '💳 Consumer', _ai_tabs[3]),
                ('au_benchmark',     'AU Benchmark', '📊 AU Benchmark', _ai_tabs[4]),
                ('us_benchmark',     'US Benchmark', '📊 US Benchmark', _ai_tabs[5]),
                ('comm_benchmark',   'Commodities Benchmark', '🪨 Commodities', _ai_tabs[6]),
                ('sea_sectors',       'Seasonality — Sectors',  '📅 Sea Sectors',     _ai_tabs[7]),
                ('sea_stocks',        'Seasonality — Stocks',   '📅 Sea Stocks',      _ai_tabs[8]),
                ('sea_presidential',  'Seasonality — Presidential Cycle', '📅 Sea Presidential', _ai_tabs[9]),
                ('fa_system',         'Fundamental Analysis — System Prompt', '🏦 Fundamental Analysis', _ai_tabs[10]),
                ('fa_comparison',     'FA Value Comparison — System Prompt', '⚖️ FA Comparison', _ai_tabs[11]),
            ]

            def _get_default_prompt(pk):
                if pk in ('fa_system', 'fa_comparison'):
                    # defaults live in the FA module — imported lazily so the
                    # dashboard doesn't pay the chromadb import at startup
                    try:
                        import sys as _sys
                        _util = os.path.join(BASE, 'utilities')
                        if _util not in _sys.path:
                            _sys.path.insert(0, _util)
                        from fa_assessment import SYSTEM_PROMPT as _FA_SP, COMPARISON_SYSTEM_PROMPT as _FA_CP
                        return _FA_SP if pk == 'fa_system' else _FA_CP
                    except Exception as _e:
                        # A broken FA install must not take down the whole
                        # Settings page — fall back to the saved prompt.
                        st.warning(f"Could not load FA default prompt: {_e}")
                        return ''
                return DEFAULT_SETTINGS.get('ai_prompts', {}).get(pk, '')

            for _pk, _plabel, _ptab_label, _ptab in _prompt_defs:
                with _ptab:
                    st.markdown(f"#### {_plabel} Prompt")
                    if _pk == 'fa_system':
                        st.caption("The full Burry/Buffett system prompt for the Fundamental Analysis page. "
                                   "RAG excerpts, financial data and market conditions are appended automatically at runtime.")
                    elif _pk == 'fa_comparison':
                        st.caption("The system prompt for the FA Value Comparison tab — the multi-stock head-to-head. "
                                   "The candidates' financial data is appended automatically at runtime.")
                    else:
                        st.caption("Edit the system instruction sent to the AI. The live market data is appended automatically.")
                    _default_prompt = _get_default_prompt(_pk)
                    _current_prompt = _ai_prmp.get(_pk, _default_prompt)
                    _new_prompt = st.text_area(
                        "Prompt", value=_current_prompt,
                        height=500 if _pk == 'fa_system' else 320 if _pk == 'fa_comparison' else 200,
                        key=f"ai_prompt_{_pk}",
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

    with _stab_fa:
            st.title("📊 Fundamental Analysis Settings")
            st.caption("Configure the local LLM connection for Burry/Buffett fundamental analysis.")

            _fa_s   = load_settings()
            _fa_feat = _fa_s.get('fa_features', DEFAULT_SETTINGS.get('fa_features', {}))

            st.markdown("#### LLM Provider")
            _fa_prov_labels = {"ollama": "🟢 Ollama", "lmstudio": "🔵 LM Studio",
                               "openai": "🟣 OpenAI (ChatGPT)"}
            _fa_prov_opts = list(_fa_prov_labels.keys())
            _fa_cur_prov = _fa_feat.get('provider', 'ollama')
            _fa_provider = st.radio("Provider", options=_fa_prov_opts,
                                     index=_fa_prov_opts.index(_fa_cur_prov)
                                           if _fa_cur_prov in _fa_prov_opts else 0,
                                     horizontal=True,
                                     format_func=lambda x: _fa_prov_labels[x],
                                     label_visibility="collapsed",
                                     key='fa_provider_radio')

            st.divider()

            if _fa_provider == 'ollama':
                st.markdown("#### 🟢 Ollama")
                _fa_ollama_url = st.text_input("Ollama URL", value=_fa_feat.get('ollama_url', 'http://localhost:11434'),
                                                key='fa_ollama_url')
                _fa_ol_ids, _fa_ol_labels, _fa_ol_models = get_model_options('ollama', _fa_ollama_url)
                _fa_ol_cur = _fa_feat.get('model', 'llama3.1:8b')
                if _fa_ol_ids:
                    _fa_ol_opts = _fa_ol_ids + ['__custom__']
                    _fa_ol_disp = _fa_ol_labels + ['✏️ Custom model...']
                    _fa_ol_idx = _fa_ol_opts.index(_fa_ol_cur) if _fa_ol_cur in _fa_ol_opts else len(_fa_ol_opts) - 1
                    _fa_ol_sel = st.selectbox("Model", options=_fa_ol_opts, index=_fa_ol_idx,
                                               format_func=lambda x: _fa_ol_disp[_fa_ol_opts.index(x)],
                                               key='fa_model_ollama')
                    if _fa_ol_sel == '__custom__':
                        _fa_model = st.text_input("Custom model name", value=_fa_ol_cur if _fa_ol_cur not in _fa_ol_ids else '',
                                                    key='fa_model_ollama_custom')
                    else:
                        _fa_model = _fa_ol_sel
                        _fa_sel_info = next((m for m in _fa_ol_models if m['id'] == _fa_ol_sel), None)
                        if _fa_sel_info and _fa_sel_info.get('notes'):
                            st.caption(f"ℹ️ {_fa_sel_info['notes']}")
                else:
                    _fa_model = st.text_input("Model", value=_fa_ol_cur,
                                               help="Add models to models.json for a dropdown", key='fa_model_ollama')
            elif _fa_provider == 'openai':
                st.markdown("#### 🟣 OpenAI (ChatGPT)")
                _fa_openai_url = st.text_input("API base URL", value=_fa_feat.get('openai_url', 'https://api.openai.com'),
                                               help="Change only for OpenAI-compatible proxies", key='fa_openai_url')
                _fa_openai_key = st.text_input("API key", value=_fa_feat.get('openai_api_key', ''),
                                               type="password", key='fa_openai_key')
                _fa_oi_ids, _fa_oi_labels, _fa_oi_models = get_model_options('openai')
                _fa_oi_cur = _fa_feat.get('model') if str(_fa_feat.get('model', '')).startswith('gpt') else 'gpt-4o-mini'
                if _fa_oi_ids:
                    _fa_oi_opts = _fa_oi_ids + ['__custom__']
                    _fa_oi_disp = _fa_oi_labels + ['✏️ Custom model...']
                    _fa_oi_idx = _fa_oi_opts.index(_fa_oi_cur) if _fa_oi_cur in _fa_oi_opts else len(_fa_oi_opts) - 1
                    _fa_oi_sel = st.selectbox("Model", options=_fa_oi_opts, index=_fa_oi_idx,
                                               format_func=lambda x: _fa_oi_disp[_fa_oi_opts.index(x)],
                                               key='fa_model_openai')
                    if _fa_oi_sel == '__custom__':
                        _fa_model = st.text_input("Custom model name", value=_fa_oi_cur if _fa_oi_cur not in _fa_oi_ids else '',
                                                    key='fa_model_openai_custom')
                    else:
                        _fa_model = _fa_oi_sel
                else:
                    _fa_model = st.text_input("Model", value=_fa_oi_cur, key='fa_model_openai')
                st.caption("⚠️ Hosted API — your financial data and RAG excerpts are sent to OpenAI. The key is stored in plain text in dashboard_settings.json.")
            else:
                st.markdown("#### 🔵 LM Studio")
                _fa_lmstudio_url = st.text_input("LM Studio URL", value=_fa_feat.get('lmstudio_url', 'http://localhost:1234'),
                                                   key='fa_lmstudio_url')
                _fa_lm_ids, _fa_lm_labels, _fa_lm_models = get_model_options('lmstudio')
                _fa_lm_cur = _fa_feat.get('model', 'llama3.1:8b')
                if _fa_lm_ids:
                    _fa_lm_opts = _fa_lm_ids + ['__custom__']
                    _fa_lm_disp = _fa_lm_labels + ['✏️ Custom model...']
                    _fa_lm_idx = _fa_lm_opts.index(_fa_lm_cur) if _fa_lm_cur in _fa_lm_opts else len(_fa_lm_opts) - 1
                    _fa_lm_sel = st.selectbox("Model", options=_fa_lm_opts, index=_fa_lm_idx,
                                               format_func=lambda x: _fa_lm_disp[_fa_lm_opts.index(x)],
                                               key='fa_model_lmstudio')
                    if _fa_lm_sel == '__custom__':
                        _fa_model = st.text_input("Custom model name", value=_fa_lm_cur if _fa_lm_cur not in _fa_lm_ids else '',
                                                    key='fa_model_lmstudio_custom')
                    else:
                        _fa_model = _fa_lm_sel
                else:
                    _fa_model = st.text_input("Model", value=_fa_lm_cur,
                                               help="Model identifier loaded in LM Studio", key='fa_model_lmstudio')

            st.divider()
            st.markdown("#### RAG Vector Store")
            _chroma_dir = os.path.join(BASE, 'data', 'fa_chromadb')
            _docs_dir = os.path.join(BASE, 'docs', 'fa_reference')
            _doc_count = len([f for f in os.listdir(_docs_dir) if f.endswith('.txt')]) if os.path.exists(_docs_dir) else 0
            _chroma_exists = os.path.exists(_chroma_dir) and os.listdir(_chroma_dir)

            st.caption(f"Reference docs: **{_doc_count}** files in docs/fa_reference/")
            if _chroma_exists:
                st.caption("Vector store: ✅ Built")
            else:
                st.caption("Vector store: ❌ Not built — click below to build")

            if st.button("🔄 Rebuild Vector Store", key='fa_rebuild_rag'):
                import sys as _sys
                if os.path.join(BASE, 'utilities') not in _sys.path:
                    _sys.path.insert(0, os.path.join(BASE, 'utilities'))
                with st.spinner("Building vector store..."):
                    from fa_rag_setup import build_vector_store
                    build_vector_store()
                st.success("Vector store rebuilt successfully")

            st.divider()
            if st.button("💾 Save FA Settings", type="primary", key='fa_save_settings'):
                _new_fa = {
                    'provider'      : _fa_provider,
                    'ollama_url'    : _fa_ollama_url if _fa_provider == 'ollama' else _fa_feat.get('ollama_url', 'http://localhost:11434'),
                    'lmstudio_url'  : _fa_lmstudio_url if _fa_provider == 'lmstudio' else _fa_feat.get('lmstudio_url', 'http://localhost:1234'),
                    'openai_url'    : _fa_openai_url if _fa_provider == 'openai' else _fa_feat.get('openai_url', 'https://api.openai.com'),
                    'openai_api_key': _fa_openai_key if _fa_provider == 'openai' else _fa_feat.get('openai_api_key', ''),
                    'model'         : _fa_model,
                }
                s = load_settings()
                s['fa_features'] = _new_fa
                save_settings(s)
                st.success(f"Saved — using {_fa_provider} with model {_fa_model}")

    with _stab_models:
            st.title("🧠 Model Registry")
            st.caption("Manage available LLM models. These populate the dropdowns across AI and FA settings.")
            st.markdown(f"Config file: `models.json`")

            _mr_models = load_models()

            for _mr_provider in ['ollama', 'openai', 'lmstudio']:
                _mr_label = {'ollama': '🦙 Ollama', 'openai': '🟣 OpenAI', 'lmstudio': '🔵 LM Studio'}[_mr_provider]
                st.markdown(f"#### {_mr_label}")
                _mr_list = _mr_models.get(_mr_provider, [])

                if _mr_list:
                    _mr_rows = []
                    for m in _mr_list:
                        _mr_rows.append({
                            'Model ID': m['id'],
                            'Name': m.get('name', m['id']),
                            'Params': m.get('params', ''),
                            'Notes': m.get('notes', ''),
                        })
                    st.dataframe(pd.DataFrame(_mr_rows), width='stretch', hide_index=True)
                else:
                    st.caption("No models configured")

                with st.expander(f"Add {_mr_provider} model"):
                    _mr_new_id = st.text_input("Model ID", key=f'mr_new_id_{_mr_provider}',
                                                help="e.g. qwen3:8b, gpt-4o")
                    _mr_new_name = st.text_input("Display Name", key=f'mr_new_name_{_mr_provider}',
                                                  help="e.g. Qwen 3 8B")
                    _mr_new_params = st.text_input("Parameters", key=f'mr_new_params_{_mr_provider}',
                                                    help="e.g. 8B, 14B (optional)")
                    _mr_new_notes = st.text_input("Notes", key=f'mr_new_notes_{_mr_provider}',
                                                   help="e.g. Good for financial analysis (optional)")
                    if st.button(f"➕ Add to {_mr_provider}", key=f'mr_add_{_mr_provider}'):
                        if _mr_new_id:
                            _mr_entry = {'id': _mr_new_id, 'name': _mr_new_name or _mr_new_id}
                            if _mr_new_params: _mr_entry['params'] = _mr_new_params
                            if _mr_new_notes:  _mr_entry['notes'] = _mr_new_notes
                            _mr_models.setdefault(_mr_provider, []).append(_mr_entry)
                            with open(MODELS_FILE, 'w') as f:
                                json.dump(_mr_models, f, indent=2)
                            st.success(f"Added {_mr_new_id}")
                            st.rerun()
                        else:
                            st.warning("Model ID is required")

                if _mr_list:
                    with st.expander(f"Remove {_mr_provider} model"):
                        _mr_del_opts = [m['id'] for m in _mr_list]
                        _mr_del_sel = st.selectbox("Select model to remove", _mr_del_opts,
                                                    key=f'mr_del_{_mr_provider}')
                        if st.button(f"🗑 Remove", key=f'mr_remove_{_mr_provider}'):
                            _mr_models[_mr_provider] = [m for m in _mr_list if m['id'] != _mr_del_sel]
                            with open(MODELS_FILE, 'w') as f:
                                json.dump(_mr_models, f, indent=2)
                            st.success(f"Removed {_mr_del_sel}")
                            st.rerun()

                st.divider()

    with _stab_etf:
            st.title("💰 ETF Income Strategy Settings")
            st.caption("The full filtering pipeline, in the order it runs — with the levers that control each layer. "
                       "Saved to etf/etf_settings.json; the scorer and backtester read it on their next run.")

            import sys as _sys
            if ETF not in _sys.path:
                _sys.path.insert(0, ETF)
            import importlib as _il
            _il.invalidate_caches()
            from etf_income_data import (FULL_UNIVERSE as _ETF_FULL, DEFAULT_WEIGHTS as _ETF_DEFW,
                                          load_etf_settings as _etf_load_s)
            _es = _etf_load_s()

            # ── Pipeline explainer ────────────────────────────────────────────
            st.markdown("""
                <div class="info-card">
                <b style="color:#ccc">How a fund gets from universe to portfolio — every gate in order:</b><br><br>
                <b>1. Universe</b> — ~32 weekly/monthly option-income ETFs (YieldMax, Defiance, Roundhill,
                   Global X, JPMorgan, NEOS, Amplify, Simplify), minus the blocklist below.<br>
                <b>2. Data</b> — 12 months of price history + every distribution, fetched live from yfinance.
                   Funds with under ~3 months of trading history are skipped (too young to judge).<br>
                <b>3. Metrics</b> — each fund gets: 3m &amp; 12m NAV change, 90-day Sharpe, trailing yield,
                   distribution slope (payouts growing or shrinking), distribution consistency,
                   and the underlying's relative strength vs SPY.<br>
                <b>4. Score</b> — each metric is ranked across the universe (percentile), then blended with
                   the weights below. Rank-based, so one extreme value can't dominate.<br>
                <b>5. Qualifier</b> — hard gate, runs after scoring: negative 3-month NAV change = disqualified,
                   no matter how high the score. A high yield on a shrinking NAV is your own capital coming back.<br>
                <b>6. Selection</b> — backtest holds the top-N qualified; the Rebalance tab flags your holdings
                   HOLD (rank inside the buy zone), REVIEW (qualified but slipped), or SELL (disqualified).<br>
                <b>7. In-trade protection</b> — the live stop cuts a holding whose <i>total return</i> from entry
                   (price + distributions received) breaches the stop level. Total-return basis matters:
                   these funds mechanically bleed price via distributions, so a raw price stop would
                   false-trigger on healthy funds.<br>
                <b>8. Optional VIX hedge</b> — the Rebalance tab banner watches the VIX term structure;
                   backtests can hold VIXY while it's inverted.
                </div>
            """, unsafe_allow_html=True)

            st.divider()

            # ── Score weights ─────────────────────────────────────────────────
            st.markdown("#### Score Weights")
            st.caption("Percentile rank of each metric × weight, summed × 100. Weights should total 1.0. "
                       "Yield is deliberately low — chasing headline yield is how NAV-decay funds trap people.")
            _w_labels = {
                'nav_3m'       : ('NAV 3m',           'Recent price trend — also the qualifier metric'),
                'nav_12m'      : ('NAV 12m',          'Longer price trend'),
                'sharpe'       : ('Sharpe 90d',       'Risk-adjusted recent return'),
                'yield_ttm'    : ('Yield TTM',        'Trailing yield — kept low on purpose'),
                'dist_slope'   : ('Dist slope',       'Are payouts growing or shrinking?'),
                'dist_consist' : ('Dist consistency', 'Payout stability (1 − CV)'),
                'underlying_rs': ('Underlying RS',    "Underlying's 3m/12m blend vs SPY"),
            }
            _new_w = {}
            _wc = st.columns(4)
            for _i, (_wk, (_wl, _wh)) in enumerate(_w_labels.items()):
                with _wc[_i % 4]:
                    _new_w[_wk] = st.number_input(
                        _wl, 0.0, 0.6, float(_es['weights'].get(_wk, _ETF_DEFW[_wk])),
                        step=0.05, key=f'etfw_{_wk}', help=_wh)
            _w_sum = sum(_new_w.values())
            if abs(_w_sum - 1.0) > 0.001:
                st.warning(f"Weights sum to {_w_sum:.2f} — should be 1.00")

            st.divider()

            # ── Qualifier / selection / stop ──────────────────────────────────
            st.markdown("#### Gates & Protection")
            _gc1, _gc2, _gc3 = st.columns(3)
            with _gc1:
                st.markdown("""<div class="macro-card"><div class="macro-label">Qualifier (fixed)</div>
                    <div style="font-size:14px;color:#ccc">3-month NAV change &gt; 0</div>
                    <div style="font-size:11px;color:#888">Strict by design — benched the whole universe
                    through the 2022 bear, which beat holding it. Not configurable from here.</div>
                    </div>""", unsafe_allow_html=True)
            with _gc2:
                _new_buyzone = st.number_input("Buy zone (rank ≤)", 3, 20, int(_es.get('buy_zone', 8)),
                                                key='etf_buyzone',
                                                help="Holdings ranked inside this = HOLD, outside = REVIEW on the Rebalance tab")
            with _gc3:
                _new_stop = st.number_input("Live stop loss %", 5, 50,
                                             int(float(_es.get('stop_loss_pct', 0.20)) * 100),
                                             step=5, key='etf_live_stop',
                                             help="Total-return from entry. Tested: 20% fires only on genuine collapses; 10-15% whipsaws on normal volatility")

            st.divider()

            # ── Blocklist ─────────────────────────────────────────────────────
            st.markdown("#### Blocklist")
            st.caption("Hard-excluded from scoring, backtests and candidates regardless of score.")
            _block_sel = st.multiselect(
                "Excluded funds",
                options=sorted(_ETF_FULL.keys()),
                default=[t for t in _es.get('excluded', []) if t in _ETF_FULL],
                key='etf_blocklist',
                format_func=lambda t: f"{t} — {_ETF_FULL[t][0]}")

            st.divider()
            if st.button("💾 Save ETF Strategy Settings", type="primary", key='etf_save_settings'):
                _out = {
                    'weights'      : {k: round(v, 3) for k, v in _new_w.items()},
                    'excluded'     : _block_sel,
                    'stop_loss_pct': float(_new_stop) / 100,
                    'buy_zone'     : int(_new_buyzone),
                }
                with open(os.path.join(ETF, 'etf_settings.json'), 'w') as _f:
                    json.dump(_out, _f, indent=2)
                st.success("Saved — next scoring run and backtest will use these settings. "
                           "Note: changing weights makes past backtest results non-comparable.")

    with _stab_rank:
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

            def _div_score_widgets(tab_key, cur, _rk):
                """RSI / OBV divergence bonus inputs (shared by benchmark and screener). Returns the dict to merge."""
                st.markdown("#### RSI Divergence Bonus")
                st.caption("Regular divergence = reversal signal, hidden = trend continuation. Added once per stock "
                           "before the volume multiplier; 0 disables.")
                c1, c2, c3, c4 = st.columns(4)
                out = {}
                out['rsi_div_bull']     = c1.number_input("BULL — std 1.0",      -2.0, 2.0, float(cur.get('rsi_div_bull', 1.0)),      0.05, key=f"rdb_{tab_key}_{_rk}", help="Price lower low, RSI higher low")
                out['rsi_div_hid_bull'] = c2.number_input("HID_BULL — std 0.5",  -2.0, 2.0, float(cur.get('rsi_div_hid_bull', 0.5)),  0.05, key=f"rdhb_{tab_key}_{_rk}", help="Price higher low, RSI lower low (uptrend pullback)")
                out['rsi_div_bear']     = c3.number_input("BEAR — std -1.0",     -2.0, 2.0, float(cur.get('rsi_div_bear', -1.0)),     0.05, key=f"rdr_{tab_key}_{_rk}", help="Price higher high, RSI lower high")
                out['rsi_div_hid_bear'] = c4.number_input("HID_BEAR — std -0.5", -2.0, 2.0, float(cur.get('rsi_div_hid_bear', -0.5)), 0.05, key=f"rdhr_{tab_key}_{_rk}", help="Price lower high, RSI higher high (downtrend bounce)")
                st.markdown("#### OBV vs Price Bonus")
                st.caption("21-bar direction of price vs On-Balance Volume: CONV = volume confirms the move, "
                           "BULL_DIV / BEAR_DIV = price and volume disagree, ACCUM / DISTRIB = flat price with OBV moving.")
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                out['obv_conv_up']   = c1.number_input("CONV_UP — std 0.5",    -2.0, 2.0, float(cur.get('obv_conv_up', 0.5)),    0.05, key=f"ocu_{tab_key}_{_rk}")
                out['obv_bull_div']  = c2.number_input("BULL_DIV — std 1.0",   -2.0, 2.0, float(cur.get('obv_bull_div', 1.0)),   0.05, key=f"obd_{tab_key}_{_rk}", help="Price down, OBV up — accumulation")
                out['obv_accum']     = c3.number_input("ACCUM — std 0.5",      -2.0, 2.0, float(cur.get('obv_accum', 0.5)),      0.05, key=f"oac_{tab_key}_{_rk}")
                out['obv_conv_down'] = c4.number_input("CONV_DOWN — std -0.5", -2.0, 2.0, float(cur.get('obv_conv_down', -0.5)), 0.05, key=f"ocd_{tab_key}_{_rk}")
                out['obv_bear_div']  = c5.number_input("BEAR_DIV — std -1.0",  -2.0, 2.0, float(cur.get('obv_bear_div', -1.0)),  0.05, key=f"obr_{tab_key}_{_rk}", help="Price up, OBV down — distribution")
                out['obv_distrib']   = c6.number_input("DISTRIB — std -0.5",   -2.0, 2.0, float(cur.get('obv_distrib', -0.5)),   0.05, key=f"odi_{tab_key}_{_rk}")
                return out

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
                    f" + rs_trend_bonus + rsi_div_bonus + obv_bonus  →  × vol_multiplier",
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
                v_div = _div_score_widgets(tab_key, cur, _rk)
                new_s = {
                    'ret_12m_weight': v_ret, 'persist_weight': v_per, 'mqs_weight': v_mqs,
                    'trend_bonus': v_tb, 'lead_bonus': v_lb,
                    'dd_weight_large': v_ddl, 'dd_weight_mid': v_ddm, 'dd_weight_small': v_dds, 'dd_weight_etf': v_dde,
                    'vol_high': v_vh, 'vol_med': v_vm, 'vol_low': v_vl,
                    'rs_trend_strong_up': v_rsu, 'rs_trend_up': v_ru, 'rs_trend_flat': v_rf,
                    'rs_trend_down': v_rd, 'rs_trend_strong_down': v_rsd,
                    **v_div,
                }
                b1,b2 = st.columns([2,1])
                if b1.button("💾 Save as Active", type="primary", key=f"save_{tab_key}"):
                    _save_active(tab_key, new_s)
                if b2.button("🔄 Save & Run", key=f"run_{tab_key}"):
                    _save_active(tab_key, new_s)
                    run_marketdb('--universe', *script, '--studies', 'benchmark', '--skip-fetch')
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
                    f" + rs_trend_bonus + regime_bonus + rsi_div_bonus + obv_bonus  →  × vol_multiplier",
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
                v_div = _div_score_widgets(tab_key, cur, _rk)
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
                    **v_div,
                }
                b1,b2,b3 = st.columns([2,2,1])
                if b1.button("💾 Save as Active", type="primary", key=f"save_{tab_key}"):
                    _save_active(tab_key, new_s)
                if b2.button("🔄 Save & Run Screener", key=f"run_sc_{tab_key}"):
                    _save_active(tab_key, new_s)
                    run_marketdb('--universe', *sc_script, '--studies', 'screener', '--skip-fetch')
                    st.success("Screener done")
                if b3.button("📊 Run Benchmark", key=f"run_bm_{tab_key}"):
                    run_marketdb('--universe', *bm_script, '--studies', 'benchmark', '--skip-fetch')
                    st.success("Benchmark done")
                return new_s

            # ── Tabs ──────────────────────────────────────────────────────────────────
            _rs_tabs = st.tabs([
                "🇦🇺 AU Benchmark", "🇺🇸 US Benchmark", "🪨 Comm Benchmark",
                "🔍 AU Screener",   "🔍 US Screener",   "🔍 Comm Screener",
            ])
            _AU_U, _US_U, _COMM_U = ['au_total_market'], ['us_total_market', 'nasdaq100'], ['all_major_commodities', 'uranium', 'au_gold_miners']
            with _rs_tabs[0]: _bm_score_widgets('au_benchmark',   _AU_U,   BM_DEFAULTS)
            with _rs_tabs[1]: _bm_score_widgets('us_benchmark',   _US_U,   BM_DEFAULTS)
            with _rs_tabs[2]: _bm_score_widgets('comm_benchmark', _COMM_U, BM_DEFAULTS)
            with _rs_tabs[3]: _sc_score_widgets('au_screener',   _AU_U,   _AU_U,   SC_DEFAULTS)
            with _rs_tabs[4]: _sc_score_widgets('us_screener',   _US_U,   _US_U,   SC_DEFAULTS)
            with _rs_tabs[5]: _sc_score_widgets('comm_screener', _COMM_U, _COMM_U, SC_DEFAULTS)

    with _stab_act:
            st.title("⚙️ Screener Settings")
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
            _as_tabs=st.tabs(["🇦🇺 AU Market","🇺🇸 US Market","⛏ Commodities","☢ Uranium","🥇 AU Gold","🔍 Burry Screen"])
            _SMA_OPTS = ['Above 20', 'Below 20', 'Above 50', 'Below 50', 'Above 200', 'Below 200']
            _SMA_DEFAULTS = {
                'EARLY'   : ['Below 20', 'Below 50', 'Below 200'],
                'PROGRESS': ['Above 20', 'Below 50', 'Below 200'],
                'SHIFT'   : ['Above 20', 'Above 50', 'Below 200'],
            }

            for _k,_t in zip(['au_market','us_market','commodities','uranium','au_gold'],_as_tabs):
                with _t:
                    _s=_as[_k]
                    st.markdown("#### Filter Parameters")
                    st.caption("Settings saved here are displayed under each table on the Screeners & Exports page.")
                    _c1,_c2=st.columns(2)
                    _ms =_c1.number_input("Min score_final",-5.0,10.0,float(_s['min_score']),0.1,key=f"as_ms_{_k}")
                    _acc_opts = ['EARLY','PROGRESS','SHIFT','TRENDING','REACCUM','CONSOLIDATE','-']
                    _acc_def  = _s['acc_watch'] if isinstance(_s['acc_watch'],list) else (['EARLY','PROGRESS','SHIFT'] if _s['acc_watch'] else [])
                    _acc=_c2.multiselect("Acc watch filter",_acc_opts,default=_acc_def,key=f"as_acc_{_k}",help="Leave empty = no filter.")
                    _reg=st.multiselect("Allowed regimes",['LEADER','CONTENDER','LAGGARD','WEAK','TREND+LEAD','TREND_ONLY'],default=_s['regimes'],key=f"as_reg_{_k}")
                    _vol=st.multiselect("Volume filter",['HIGH','MED','LOW'],default=_s['vol'],key=f"as_vol_{_k}")
                    _cap=st.multiselect("Cap bands",['large','mid','small','ETF'],default=_s['cap_bands'],key=f"as_cap_{_k}")

                    st.markdown("#### SMA Conditions per Acc Watch Type")
                    st.caption("Each type has 4 independent criteria. Leave empty = no filter for that criterion.")

                    _PRICE_OPTS = ['Price > SMA20', 'Price < SMA20',
                                   'Price > SMA50', 'Price < SMA50',
                                   'Price > SMA200','Price < SMA200']
                    _SMA20_OPTS = ['SMA20 > SMA50', 'SMA20 < SMA50',
                                   'SMA20 > SMA200','SMA20 < SMA200']
                    _SMA50_OPTS = ['SMA50 > SMA20', 'SMA50 < SMA20',
                                   'SMA50 > SMA200','SMA50 < SMA200']
                    _SMA200_OPTS= ['SMA200 > SMA20','SMA200 < SMA20',
                                   'SMA200 > SMA50','SMA200 < SMA50']

                    _ACC_TYPES = [
                        ('EARLY',       {'price': ['Price < SMA20','Price < SMA50','Price < SMA200'],
                                         'sma20': ['SMA20 < SMA50','SMA20 < SMA200'],
                                         'sma50': ['SMA50 < SMA200'], 'sma200': []}),
                        ('PROGRESS',    {'price': ['Price > SMA20','Price < SMA50','Price < SMA200'],
                                         'sma20': ['SMA20 < SMA50','SMA20 < SMA200'],
                                         'sma50': ['SMA50 < SMA200'], 'sma200': []}),
                        ('SHIFT',       {'price': ['Price > SMA20','Price > SMA50','Price < SMA200'],
                                         'sma20': ['SMA20 < SMA200'],
                                         'sma50': ['SMA50 < SMA200'], 'sma200': []}),
                        ('TRENDING',    {'price': ['Price > SMA20','Price > SMA50','Price > SMA200'],
                                         'sma20': ['SMA20 > SMA50','SMA20 > SMA200'],
                                         'sma50': ['SMA50 > SMA200'], 'sma200': []}),
                        ('REACCUM',     {'price': ['Price < SMA20','Price > SMA50','Price > SMA200'],
                                         'sma20': ['SMA20 > SMA50','SMA20 > SMA200'],
                                         'sma50': ['SMA50 > SMA200'], 'sma200': []}),
                        ('CONSOLIDATE', {'price': ['Price < SMA20','Price > SMA200'],
                                         'sma20': ['SMA20 < SMA50','SMA20 > SMA200'],
                                         'sma50': ['SMA50 > SMA200'], 'sma200': []}),
                    ]

                    _sma_settings = {}
                    st.markdown("---")
                    for _atype, _adefaults in _ACC_TYPES:
                        st.markdown(f"**{_atype}**")
                        _r1, _r2, _r3, _r4 = st.columns(4)
                        _key_p   = f"as_{_atype}_price_{_k}"
                        _key_20  = f"as_{_atype}_sma20_{_k}"
                        _key_50  = f"as_{_atype}_sma50_{_k}"
                        _key_200 = f"as_{_atype}_sma200_{_k}"
                        _saved   = _s.get(f'sma_{_atype.lower()}', {})
                        if isinstance(_saved, list): _saved = {}  # reset old format
                        _logic_sel = st.radio("Logic", ["AND","OR"], horizontal=True,
                                       index=0 if _saved.get('logic','AND')=='AND' else 1,
                                       key=f"as_{_atype}_logic_{_k}")
                        _p_sel  = _r1.multiselect("Price vs SMA",  _PRICE_OPTS,
                                    default=_saved.get('price',  _adefaults['price']),  key=_key_p)
                        _20_sel = _r2.multiselect("SMA20 vs SMAs", _SMA20_OPTS,
                                    default=_saved.get('sma20',  _adefaults['sma20']),  key=_key_20)
                        _50_sel = _r3.multiselect("SMA50 vs SMAs", _SMA50_OPTS,
                                    default=_saved.get('sma50',  _adefaults['sma50']),  key=_key_50)
                        _200_sel= _r4.multiselect("SMA200 vs SMAs",_SMA200_OPTS,
                                    default=_saved.get('sma200', _adefaults['sma200']), key=_key_200)
                        _sma_settings[f'sma_{_atype.lower()}'] = {
                            'logic': _logic_sel,
                            'price': _p_sel, 'sma20': _20_sel,
                            'sma50': _50_sel, 'sma200': _200_sel,
                        }
                        st.markdown("---")
                    st.markdown("")
                    if st.button("💾 Save",type="primary",key=f"as_save_{_k}"):
                        _as[_k]={
                            'min_score'   : _ms,
                            'acc_watch'   : _acc,
                            'regimes'     : _reg,
                            'vol'         : _vol,
                            'cap_bands'   : _cap,
                            **_sma_settings,
                        }
                        _save_as(_as)

            # ── Burry Screen settings tab ─────────────────────────────────────
            with _as_tabs[5]:
                st.markdown("#### Burry Value Screen Defaults")
                st.caption("Default filter values for the Burry screen. You can also adjust filters inline on the Screeners page.")
                _bs = load_settings().get('burry_screener', DEFAULT_SETTINGS['burry_screener'])

                _bs_c1, _bs_c2, _bs_c3, _bs_c4 = st.columns(4)
                _bs_mcap = _bs_c1.number_input("Max Market Cap ($M)", 10, 5000,
                                                int(_bs.get('max_market_cap', 300_000_000) / 1e6),
                                                step=50, key='bs_mcap')
                _bs_pe   = _bs_c2.number_input("Max P/E", 1.0, 100.0,
                                                float(_bs.get('max_pe', 15.0)),
                                                step=1.0, key='bs_pe')
                _bs_pb   = _bs_c3.number_input("Max P/B", 0.1, 10.0,
                                                float(_bs.get('max_pb', 1.5)),
                                                step=0.1, key='bs_pb')
                _bs_ps   = _bs_c4.number_input("Max P/S", 0.1, 10.0,
                                                float(_bs.get('max_ps', 1.0)),
                                                step=0.1, key='bs_ps')

                _bs_c5, _bs_c6, _bs_c7, _bs_c8 = st.columns(4)
                _bs_de   = _bs_c5.number_input("Max D/E", 0.0, 200.0,
                                                float(_bs.get('max_debt_equity', 50.0)),
                                                step=5.0, key='bs_de')
                _bs_cr   = _bs_c6.number_input("Min Current Ratio", 0.0, 10.0,
                                                float(_bs.get('min_current_ratio', 1.5)),
                                                step=0.1, key='bs_cr')
                _bs_roe  = _bs_c7.number_input("Min ROE (%)", -100.0, 100.0,
                                                float(_bs.get('min_roe', 0.0)),
                                                step=1.0, key='bs_roe')
                _bs_shares = _bs_c8.number_input("Max Shares (M)", 1, 1000,
                                                  int(_bs.get('max_shares', 100_000_000) / 1e6),
                                                  step=10, key='bs_shares')

                _bs_markets = st.multiselect("Default Markets", ['us', 'au'],
                                              default=_bs.get('markets', ['us']),
                                              key='bs_markets')

                if st.button("💾 Save Burry Defaults", type="primary", key='bs_save'):
                    _s = load_settings()
                    _s['burry_screener'] = {
                        'max_market_cap'   : _bs_mcap * 1_000_000,
                        'max_pe'           : _bs_pe,
                        'max_pb'           : _bs_pb,
                        'max_ps'           : _bs_ps,
                        'max_debt_equity'  : _bs_de,
                        'min_current_ratio': _bs_cr,
                        'min_roe'          : _bs_roe,
                        'max_shares'       : _bs_shares * 1_000_000,
                        'markets'          : _bs_markets,
                    }
                    save_settings(_s)
                    st.success("Burry screen defaults saved")

    with _stab_gen:
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
            st.caption("Quick toggle — configure providers in the 🤖 AI Settings tab above.")

            ai_enabled = st.toggle(
                "Enable AI assessments",
                value=current.get('ai_features', {}).get('enabled', False),
                key='setting_ai_enabled'
            )
            _cur_ai = current.get('ai_features', {})
            api_key = _cur_ai.get('anthropic_api_key', '')
            model   = _cur_ai.get('model', 'claude-sonnet-4-6')

            # ── Save / Reset ──────────────────────────────────────────────────────────
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Save & Reload", type="primary"):
                    current['pages']       = updated_pages
                    _existing_ai = current.get('ai_features', {})
                    _existing_ai['enabled'] = ai_enabled
                    current['ai_features'] = _existing_ai
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

            # ── Network Access ────────────────────────────────────────────────────────
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
                # Read existing config
                import re as _re_net2
                if os.path.isfile(_net_cfg_file):
                    _nc = open(_net_cfg_file).read()
                else:
                    _nc = '[server]\n'

                # Update or insert address
                if 'address' in _nc:
                    _nc = _re_net2.sub(r'address\s*=\s*"[^"]*"', f'address = "{_net_addr}"', _nc)
                else:
                    _nc = _nc.rstrip() + '\n' + f'address = "{_net_addr}"\n'

                # Update or insert port
                if _re_net2.search(r'port\s*=\s*\d+', _nc):
                    _nc = _re_net2.sub(r'port\s*=\s*\d+', f'port = {_port}', _nc)
                else:
                    _nc = _nc.rstrip() + '\n' + f'port = {_port}\n'

                os.makedirs(os.path.dirname(_net_cfg_file), exist_ok=True)
                with open(_net_cfg_file, 'w') as _f: _f.write(_nc)
                st.success(f"Network settings saved — restart Streamlit to apply (address={_net_addr}, port={_port})")