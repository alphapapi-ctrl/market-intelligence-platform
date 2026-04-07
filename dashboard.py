import streamlit as st
import pandas as pd
import os
import subprocess
from datetime import datetime, timedelta
import glob
from streamlit_option_menu import option_menu
import json

# ── Config ────────────────────────────────────────────────────────────────────
BASE    = os.path.dirname(os.path.abspath(__file__))
MACRO   = os.path.join(BASE, 'macro')
STOCKS  = os.path.join(BASE, 'stocks')
EA      = os.path.join(BASE, 'ea')
PYTHON  = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')

st.set_page_config(
    page_title   = "Market Intelligence",
    page_icon    = "📊",
    layout       = "wide",
    initial_sidebar_state = "collapsed"
)

st.markdown("""
    <style>
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
    'pages': {
        'Macro'               : True,
        'AU Market'           : True,
        'US Market'           : True,
        'Commodities'         : True,
        'Uranium'             : True,
        'AU Gold Miners'      : True,
        'RRG Charts'          : True,
        'Breadth RRG'         : True,
        'Drawdown Analysis'   : True,
        'Actionable & Exports': True,
        'EA Comparator'       : True,
        'MT5 Analysis'        : True,
        'Run Scripts'         : True,
        'Settings'            : True,
    }
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                # Merge with defaults in case new pages were added
                merged = DEFAULT_SETTINGS.copy()
                merged['pages'].update(saved.get('pages', {}))
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
    ("AU Market",            "flag"),
    ("US Market",            "flag"),
    ("Commodities",          "hammer"),
    ("Uranium",              "radioactive"),
    ("AU Gold Miners",       "star"),
    ("RRG Charts",           "broadcast"),
    ("Breadth RRG",          "grid-3x3"),
    ("Drawdown Analysis",    "graph-down"),
    ("Actionable & Exports", "file-earmark-arrow-down"),
    ("EA Comparator",        "sliders"),
    ("MT5 Analysis",         "bar-chart-line"),
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
            today_val = val

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

    rows = []
    for sec_key in sector_keys:
        try:
            total_key = f'{prefix}_{sec_key}_total'
            total     = int(today[total_key])
            leaders   = int(today[f'{prefix}_{sec_key}_leaders'])
            above20   = int(today.get(f'{prefix}_{sec_key}_above20',  0))
            above50   = int(today.get(f'{prefix}_{sec_key}_above50',  0))
            above200  = int(today[f'{prefix}_{sec_key}_above200'])
            high_vol  = int(today.get(f'{prefix}_{sec_key}_high_vol', 0))

            rows.append({
                'Sector'  : sec_key.replace('_', ' ').replace('-', ' ').title(),
                'HVol'    : high_vol,
                'Total'   : total,
                'Leaders' : leaders,
                'dL5'     : delta(f'{prefix}_{sec_key}_leaders',  d5)  if d5  is not None else 'n/a',
                'dL63'    : delta(f'{prefix}_{sec_key}_leaders',  d63) if d63 is not None else 'n/a',
                'Ab20%'   : f"{pct(above20,  total)}%",
                'Ab50%'   : f"{pct(above50,  total)}%",
                'Ab200%'  : f"{pct(above200, total)}%",
            })
        except:
            continue

    return pd.DataFrame(rows) if rows else None

def style_breadth(df, pct_cols=None, delta_cols=None):
    def colour_delta(val):
        try:
            v = int(str(val).replace('+',''))
            if v > 0:  return 'background-color: rgba(0,180,0,0.12); color: #00cc44'
            if v < 0:  return 'background-color: rgba(180,0,0,0.12); color: #ff4444'
        except:
            pass
        return ''

    def colour_pct(val, vmin, vmax):
        try:
            v = float(val)
            if v >= 60: return 'background-color: rgba(0,180,0,0.10)'
            if v <= 30: return 'background-color: rgba(180,0,0,0.10)'
        except:
            pass
        return ''

    styler = df.style
    if delta_cols:
        for col in delta_cols:
            if col in df.columns:
                styler = styler.map(colour_delta, subset=[col])
    return styler

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

        for group_name, keys in groups:
            st.markdown(f"**{group_name}**")
            cols = st.columns(len(keys))
            for i, key in enumerate(keys):
                if key not in live:
                    continue
                d     = live[key]
                price = d['price']
                c1d   = d['chg_1d']
                c5d   = d['chg_5d']
                col   = metric_colour(c5d)

                # Format price
                if price > 1000:   fmt = f"{price:,.2f}"
                elif price > 10:   fmt = f"{price:.2f}"
                elif price > 1:    fmt = f"{price:.4f}"
                else:              fmt = f"{price:.5f}"

                cols[i].markdown(f"""
                    <div class="macro-card" style="text-align:center">
                        <div class="macro-label">{d['label']}</div>
                        <div class="macro-value">{fmt}</div>
                        <div style="color:{metric_colour(c1d)};font-size:12px">
                            {arrow(c1d)} {abs(c1d):.2f}% 1D</div>
                        <div style="color:{metric_colour(c5d)};font-size:13px;font-weight:bold">
                            {arrow(c5d)} {abs(c5d):.2f}% 5D</div>
                    </div>
                """, unsafe_allow_html=True)
        spacer_html = "<div style='margin-top:16px'></div>"
        st.markdown(spacer_html, unsafe_allow_html=True)

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

    # Four columns: Economic | Consumer Cycle | Valuation | Credit
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**Economic Regime**")
        unemp = macro.get('unemployment', None)
        pmi   = macro.get('pmi', None)
        nfp   = macro.get('nfp', '')
        sent  = macro.get('consumer_sent', None)

        def indicator_row(label, value, signal_text, good=True):
            colour = '#2dc653' if good else '#e63946'
            icon   = '✓' if good else '⚠'
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">{label}</div>
                    <div class="macro-value">{value}</div>
                    <div class="macro-signal" style="color:{colour}">{icon} {signal_text}</div>
                </div>
            """, unsafe_allow_html=True)

        if unemp: indicator_row("Unemployment", f"{unemp}%",
            macro.get('unemp_label',''), good=unemp < 4.5)
        if pmi:   indicator_row("PMI Mfg", f"{pmi}",
            macro.get('pmi_label',''), good=pmi >= 50)
        if nfp:   indicator_row("Non-Farm Payrolls", nfp, "", good=True)
        if sent:  indicator_row("Consumer Sentiment", f"{sent}",
            macro.get('sent_label',''), good=sent > 70)

    with col2:
        st.markdown("**Consumer Cycle**")
        xly = macro.get('xly_xlp', None)
        rsp = macro.get('rspd_rsps', None)
        sec = macro.get('sector_ratio', None)

        if xly:
            lbl    = macro.get('xly_xlp_label','')
            good   = 'RISK OFF' not in lbl
            colour = '#2dc653' if good else '#e63946'
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">XLY/XLP Ratio</div>
                    <div class="macro-value">{xly}</div>
                    <div class="macro-signal" style="color:{colour}">{lbl[:50]}</div>
                </div>
            """, unsafe_allow_html=True)
        if rsp:
            lbl    = macro.get('rspd_rsps_label','')
            good   = 'RISK OFF' not in lbl
            colour = '#2dc653' if good else '#e63946'
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">RSPD/RSPS Ratio</div>
                    <div class="macro-value">{rsp}</div>
                    <div class="macro-signal" style="color:{colour}">{lbl[:50]}</div>
                </div>
            """, unsafe_allow_html=True)
        if sec:
            lbl    = macro.get('sector_ratio_label','')
            good   = 'NEUTRAL' in lbl or 'RISK ON' in lbl
            colour = '#2dc653' if good else '#f77f00'
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">Sector Risk On/Off</div>
                    <div class="macro-value">{sec}</div>
                    <div class="macro-signal" style="color:{colour}">{lbl[:50]}</div>
                </div>
            """, unsafe_allow_html=True)

    with col3:
        st.markdown("**Valuation**")
        vals = [
            ("SPX/M2",        macro.get('spx_m2'),   0.25, "Extreme above 0.25"),
            ("Margin/M2",     macro.get('margin_m2'),1.4,  "Extreme above 1.4"),
            ("Buffett Ind %", macro.get('buffett'),  150,  "Extreme above 150%"),
            ("Shiller CAPE",  macro.get('cape'),     30,   "Extreme above 30"),
        ]
        for lbl, val, threshold, warning in vals:
            if val is None: continue
            extreme = val > threshold
            colour  = '#e63946' if extreme else '#2dc653'
            icon    = '⚠' if extreme else '✓'
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">{lbl}</div>
                    <div class="macro-value">{val}</div>
                    <div class="macro-signal" style="color:{colour}">{icon} {warning if extreme else 'Normal range'}</div>
                </div>
            """, unsafe_allow_html=True)

    with col4:
        st.markdown("**Credit & Rates**")
        credit_items = [
            ("Fed Funds",         macro.get('fed_funds'),   "%"),
            ("US 10Y",            macro.get('us10y'),       "%"),
            ("US 2Y",             macro.get('us2y'),        "%"),
            ("AU 10Y",            macro.get('au10y'),       "%"),
            ("Yield Curve",       macro.get('yield_curve'), "%"),
            ("HY Spread",         macro.get('hy_spread'),   "%"),
            ("Fed Balance Sheet", macro.get('fed_bs'),      "T"),
        ]
        for lbl, val, suffix in credit_items:
            if val is None: continue
            if lbl == "Yield Curve":
                colour = '#2dc653' if val > 0 else '#e63946'
                icon   = '✓ Uninverted' if val > 0 else '⚠ Inverted'
            elif lbl == "HY Spread":
                colour = '#2dc653' if val < 4 else '#f77f00' if val < 6 else '#e63946'
                icon   = 'Contained' if val < 4 else 'Widening' if val < 6 else 'Stress'
            else:
                colour = '#888'
                icon   = ''
            st.markdown(f"""
                <div class="macro-card">
                    <div class="macro-label">{lbl}</div>
                    <div class="macro-value">{val}{suffix}</div>
                    <div class="macro-signal" style="color:{colour}">{icon}</div>
                </div>
            """, unsafe_allow_html=True)

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
                            st.dataframe(grp_df, use_container_width=True,
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

    CYCLE_CONFIG = {
        '18-21 YEAR LAND CYCLE': {
            'total_years' : 20,
            'phases'      : ['UPTURN','MID','PEAK','DOWNTURN'],
            'phase_years' : [5, 5, 5, 5],
            'colour'      : '#9b5de5',
        },
        '40/80 YEAR RATE CYCLE': {
            'total_years' : 40,
            'phases'      : ['EARLY UP','MID UP','PEAK','EARLY DOWN','MID DOWN','TROUGH'],
            'phase_years' : [8, 8, 6, 6, 6, 6],
            'colour'      : '#00b4d8',
        },
        'COMMODITY VS EQUITY CYCLE': {
            'total_years' : 18,
            'phases'      : ['EARLY','MID','LATE','TRANSITION'],
            'phase_years' : [4, 5, 5, 4],
            'colour'      : '#f77f00',
        },
    }

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

    # Long cycle progress bars
    LONG_CYCLES = [
        {
            'name'        : '18-21 Year Land Cycle',
            'total_years' : 20,
            'years_in'    : 19.7,
            'phase'       : 'DOWNTURN',
            'colour'      : '#9b5de5',
            'phases'      : [('UPTURN',5),('MID',5),('PEAK',5),('DOWNTURN',5)],
        },
        {
            'name'        : '40/80 Year Rate Cycle',
            'total_years' : 40,
            'years_in'    : 5.7,
            'phase'       : 'EARLY UP',
            'colour'      : '#00b4d8',
            'phases'      : [('TROUGH',5),('EARLY UP',8),('MID UP',8),('PEAK',6),('EARLY DOWN',7),('MID DOWN',6)],
        },
        {
            'name'        : 'Commodity vs Equity Cycle',
            'total_years' : 18,
            'years_in'    : 5.7,
            'phase'       : 'MID',
            'colour'      : '#f77f00',
            'phases'      : [('EARLY',4),('MID',5),('LATE',5),('TRANSITION',4)],
        },
    ]

    for cycle in LONG_CYCLES:
        pct = min(cycle['years_in'] / cycle['total_years'] * 100, 100)
        st.markdown(f"""
            <div style="background:rgba(255,255,255,0.04);border-radius:8px;
                        padding:14px 16px;margin-bottom:10px">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px">
                    <span style="color:white;font-weight:bold;font-size:13px">{cycle['name']}</span>
                    <span style="color:{cycle['colour']};font-size:13px;font-weight:bold">
                        {cycle['phase']} &nbsp;|&nbsp; Year {cycle['years_in']} of {cycle['total_years']}
                    </span>
                </div>
                <div style="background:rgba(255,255,255,0.08);border-radius:4px;height:10px;position:relative">
                    <div style="background:{cycle['colour']};width:{pct:.1f}%;height:10px;
                                border-radius:4px;opacity:0.85"></div>
                </div>
                <div style="display:flex;justify-content:space-between;margin-top:4px">
                    {''.join(f'<span style="color:#666;font-size:9px">{p[0]}</span>' for p in cycle['phases'])}
                </div>
            </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# AU MARKET PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "AU Market":
    st.title("AU Total Market")

    tab1, tab2, tab3 = st.tabs(["Breadth", "Benchmark", "Screener"])

    with tab1:
        st.subheader("AU Market Breadth")
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
            st.caption(f"Latest: {today_str} — {file_age(history_file)}")

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
                st.dataframe(
                    style_breadth(df_overall, delta_cols=['D5','D20','D63']),
                    use_container_width=True, hide_index=True, height=460
                )

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
                st.dataframe(
                    style_breadth(df_cap, delta_cols=['D5','D20','D63']),
                    use_container_width=True, hide_index=True, height=370
                )

            st.markdown("**Sector Breadth**")
            sec_cols  = [c for c in history.columns if c.startswith('sec_') and c.endswith('_total')
                         and not c.startswith('sp_sec_') and not c.startswith('rus_sec_')]
            sec_keys  = [c.replace('sec_','').replace('_total','') for c in sec_cols
                         if 'nan' not in c and 'index' not in c]
            df_sector = build_sector_table(history, sec_keys, prefix='sec')
            if df_sector is not None:
                sector_breadth_caption()
                st.dataframe(
                    style_breadth(df_sector, delta_cols=['dL5','dL63']),
                    use_container_width=True, hide_index=True, height=600
                )
        else:
            st.warning("No breadth history found")

        if st.button("🔄 Run AU Breadth", key='au_breadth'):
            run_script(os.path.join(STOCKS, 'au_total_market_breadth.py'), STOCKS)
            st.rerun()

    with tab2:
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
                         use_container_width=True, height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run AU Benchmark", key='au_bm'):
            run_script(os.path.join(STOCKS, 'au_total_market_benchmark.py'), STOCKS)
            st.rerun()

    with tab3:
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
                         use_container_width=True, height=600)
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

    tab1, tab2, tab3 = st.tabs(["Breadth", "Benchmark", "Screener"])

    with tab1:
        st.subheader("US Market Breadth")
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
            st.caption(f"Latest: {today_str} — {file_age(history_file)}")

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

            st.markdown("**Layer 1 — Full Universe**")
            df_l1 = build_breadth_table(history, overall_metrics)
            if df_l1 is not None:
                st.dataframe(style_breadth(df_l1, delta_cols=['D5','D20','D63']),
                             use_container_width=True, hide_index=True, height=680)

            sec_cols = [c for c in history.columns if c.startswith('sec_') and c.endswith('_total')
                        and not c.startswith('sp_sec_') and not c.startswith('rus_sec_')]
            sec_keys = [c.replace('sec_','').replace('_total','') for c in sec_cols
                        if 'nan' not in c and 'index' not in c]
            st.markdown("**Layer 1 Sector Breadth**")
            df_sec = build_sector_table(history, sec_keys, prefix='sec')
            if df_sec is not None:
                sector_breadth_caption()
                st.dataframe(style_breadth(df_sec, delta_cols=['dL5','dL63']),
                             use_container_width=True, hide_index=True, height=500)

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
                st.dataframe(style_breadth(df_l2, delta_cols=['D5','D20','D63']),
                             use_container_width=True, hide_index=True, height=520)

            sp_sec_cols = [c for c in history.columns if c.startswith('sp_sec_') and c.endswith('_total')]
            sp_sec_keys = [c.replace('sp_sec_','').replace('_total','') for c in sp_sec_cols
                           if 'nan' not in c and 'index' not in c]
            if sp_sec_keys:
                st.markdown("**Layer 2 Sector Breadth**")
                df_sp_sec = build_sector_table(history, sp_sec_keys, prefix='sp_sec')
                if df_sp_sec is not None:
                    sector_breadth_caption()
                    st.dataframe(style_breadth(df_sp_sec, delta_cols=['dL5','dL63']),
                                 use_container_width=True, hide_index=True, height=500)

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
                st.dataframe(style_breadth(df_l3, delta_cols=['D5','D20','D63']),
                             use_container_width=True, hide_index=True, height=520)

            rus_sec_cols = [c for c in history.columns if c.startswith('rus_sec_') and c.endswith('_total')]
            rus_sec_keys = [c.replace('rus_sec_','').replace('_total','') for c in rus_sec_cols
                            if 'nan' not in c and 'index' not in c]
            if rus_sec_keys:
                st.markdown("**Layer 3 Sector Breadth**")
                df_rus_sec = build_sector_table(history, rus_sec_keys, prefix='rus_sec')
                if df_rus_sec is not None:
                    sector_breadth_caption()
                    st.dataframe(style_breadth(df_rus_sec, delta_cols=['dL5','dL63']),
                                 use_container_width=True, hide_index=True, height=500)
        else:
            st.warning("No breadth history found")

        if st.button("🔄 Run US Breadth", key='us_breadth'):
            run_script(os.path.join(STOCKS, 'us_total_market_breadth.py'), STOCKS)
            st.rerun()

    with tab2:
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
                         use_container_width=True, height=600)
        else:
            st.warning("No benchmark results found")
        if st.button("🔄 Run US Benchmark", key='us_bm'):
            run_script(os.path.join(STOCKS, 'us_total_market_benchmark.py'), STOCKS)
            st.rerun()

    with tab3:
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
                         use_container_width=True, height=600)
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
        st.subheader("Commodities Breadth")
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
            st.caption(f"Latest: {today_str} — {file_age(history_file)}")

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
                st.dataframe(style_breadth(df_overall, delta_cols=['D5','D20','D63']),
                             use_container_width=True, hide_index=True, height=520)

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
                sector_breadth_caption()
                st.dataframe(style_breadth(df_comm, delta_cols=['dL5','dL63']),
                             use_container_width=True, hide_index=True)

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
                st.dataframe(style_breadth(df_jr, delta_cols=['dL5','dL63']),
                             use_container_width=True, hide_index=True)

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
                st.dataframe(style_breadth(df_type, delta_cols=['dL5','dL63']),
                             use_container_width=True, hide_index=True)
        else:
            st.warning("No breadth history found")

        if st.button("🔄 Run Commodities Breadth", key='comm_breadth'):
            run_script(os.path.join(STOCKS, 'all_major_commodities_breadth.py'), STOCKS)
            st.rerun()

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
                         use_container_width=True, height=600)
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
                         use_container_width=True, height=600)
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
                         use_container_width=True, height=600)
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
                         use_container_width=True, height=600)
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
                         use_container_width=True, height=600)
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
                         use_container_width=True, height=600)
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
            tail_days   = st.slider("Tail length (trading days)", 5, 63, 30, key=f"tail_{title}")
        with col2:
            groups      = sorted(history['group'].unique().tolist())
            sel_groups  = st.multiselect("Filter groups", groups, default=groups, key=f"grp_{title}")
        with col3:
            show_labels = st.toggle("Show labels", value=True, key=f"lbl_{title}")
        with col4:
            smooth_span = st.slider("Smoothing (EWM span)", 1, 20, 20, key=f"span_{title}")

        # Filter
        cutoff  = latest_date - pd.Timedelta(days=tail_days * 1.5)
        df      = history[history['date'] >= cutoff].copy()
        df      = df[df['group'].isin(sel_groups)]
        tickers = df['ticker'].unique()

        # Colour palette — distinct per ticker
        COLOURS = [
            '#00b4d8','#90e0ef','#48cae4',  # blues
            '#f77f00','#fcbf49','#eae2b7',  # oranges
            '#2dc653','#80b918','#aacc00',  # greens
            '#e63946','#ff6b6b','#ffadad',  # reds
            '#9b5de5','#c77dff','#e0aaff',  # purples
            '#f15bb5','#fee440','#00bbf9',  # mixed
            '#06d6a0','#118ab2','#ffd166',  # teal/blue/yellow
            '#ef476f','#b7e4c7','#40916c',  # pink/greens
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
        }

        fig = go.Figure()

        # Quadrant backgrounds
        fig.add_shape(type='rect', x0=100, y0=100, x1=135, y1=135,
                      fillcolor='rgba(0,180,0,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=65,  y0=100, x1=100, y1=135,
                      fillcolor='rgba(100,100,255,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=65,  y0=65,  x1=100, y1=100,
                      fillcolor='rgba(255,50,50,0.06)', line_width=0, layer='below')
        fig.add_shape(type='rect', x0=100, y0=65,  x1=135, y1=100,
                      fillcolor='rgba(255,180,0,0.06)', line_width=0, layer='below')

        # Quadrant labels
        for text, x, y in [
            ('LEADING',    132, 133),
            ('WEAKENING',  132, 67),
            ('LAGGING',    68,  67),
            ('IMPROVING',  68,  133),
        ]:
            fig.add_annotation(x=x, y=y, text=text, showarrow=False,
                               font=dict(size=12, color='rgba(255,255,255,0.25)'),
                               xanchor='center')

        # Centre lines
        fig.add_hline(y=100, line_width=1, line_dash='dash',
                      line_color='rgba(255,255,255,0.2)')
        fig.add_vline(x=100, line_width=1, line_dash='dash',
                      line_color='rgba(255,255,255,0.2)')

        # Track current positions for legend sorting
        current_positions = {}

        # Plot each ticker
        for ticker in tickers:
            tdf    = df[df['ticker'] == ticker].sort_values('date').tail(tail_days)
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

        sorted_tickers = sorted(
            current_positions.items(),
            key=lambda item: (get_quadrant(item[1][0], item[1][1])[0], -item[1][0])
        )

        fig.update_layout(
            title        = dict(text=title, font=dict(size=16, color='white')),
            xaxis_title  = 'RS-Ratio',
            yaxis_title  = 'RS-Momentum',
            height       = 750,
            plot_bgcolor = 'rgba(15,15,25,1)',
            paper_bgcolor= 'rgba(15,15,25,1)',
            font         = dict(color='white'),
            xaxis        = dict(range=[65,135], gridcolor='rgba(255,255,255,0.05)',
                                tickfont=dict(size=10), title_font=dict(size=11)),
            yaxis        = dict(range=[65,135], gridcolor='rgba(255,255,255,0.05)',
                                tickfont=dict(size=10), title_font=dict(size=11)),
            showlegend   = False,
            margin       = dict(r=40, l=60, t=60, b=60),
        )

        st.plotly_chart(fig, use_container_width=True)

        # ── Streamlit legend below chart ──────────────────────────────────────
        quad_groups = {'1_LEADING': [], '2_WEAKENING': [], '3_IMPROVING': [], '4_LAGGING': []}
        quad_labels = {
            '1_LEADING'  : ('🟢 LEADING',   '#2dc653'),
            '2_WEAKENING': ('🟡 WEAKENING',  '#f77f00'),
            '3_IMPROVING': ('🔵 IMPROVING',  '#00b4d8'),
            '4_LAGGING'  : ('🔴 LAGGING',    '#e63946'),
        }
        for ticker, (x, y, label, colour) in sorted_tickers:
            quad = get_quadrant(x, y)[0]
            quad_groups[quad].append((label, colour))

        leg_cols = st.columns(4)
        for i, (quad_key, items) in enumerate(quad_groups.items()):
            qname, qcolour = quad_labels[quad_key]
            with leg_cols[i]:
                st.markdown(f"<div style='color:{qcolour};font-weight:bold;font-size:13px;margin-bottom:6px'>{qname}</div>",
                            unsafe_allow_html=True)
                for label, colour in items:
                    st.markdown(f"<div style='font-size:12px;margin-bottom:3px'>"
                                f"<span style='color:{colour}'>●</span> {label}</div>",
                                unsafe_allow_html=True)

        # ── PNG export with embedded legend ───────────────────────────────────
        fig_export = go.Figure(fig)
        legend_x  = 1.02
        y_pos     = 1.0
        lh        = 0.048
        last_quad = None

        for ticker, (x, y, label, colour) in sorted_tickers:
            quad, icon = get_quadrant(x, y)
            qname      = quad.split('_')[1]
            if quad != last_quad:
                fig_export.add_annotation(
                    x=legend_x, y=y_pos, xref='paper', yref='paper',
                    text=f"<b>{icon} {qname}</b>",
                    showarrow=False,
                    font=dict(size=11, color='rgba(255,255,255,0.8)'),
                    xanchor='left',
                )
                y_pos    -= lh * 0.8
                last_quad = quad
            fig_export.add_annotation(
                x=legend_x, y=y_pos, xref='paper', yref='paper',
                text=f"● {label}  {x:.1f}/{y:.1f}",
                showarrow=False,
                font=dict(size=9, color=colour),
                xanchor='left',
            )
            y_pos -= lh

        fig_export.update_layout(margin=dict(r=220, l=60, t=60, b=60))

        img_bytes = fig_export.to_image(format='png', width=1800, height=900, scale=2)
        st.download_button(
            label     = f"⬇ Download PNG ({tail_days}d tail)",
            data      = img_bytes,
            file_name = f"rrg_{title.replace(' ','_').replace('/','_')}_{tail_days}d_{datetime.today().strftime('%Y%m%d')}.png",
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
        COLOURS = [
            '#00b4d8','#f77f00','#2dc653','#e63946','#9b5de5',
            '#f15bb5','#fee440','#06d6a0','#118ab2','#ffd166',
            '#ef476f','#b7e4c7','#40916c','#fcbf49','#eae2b7',
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

        sorted_tickers = sorted(
            current_positions.items(),
            key=lambda item: (get_quadrant(item[1][0], item[1][1])[0], -item[1][0])
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
            height       = 700,
            plot_bgcolor = 'rgba(15,15,25,1)',
            paper_bgcolor= 'rgba(15,15,25,1)',
            font         = dict(color='white'),
            xaxis        = dict(range=[x_min, x_max], gridcolor='rgba(255,255,255,0.05)',
                                title='Breadth Strength (vs universe avg)', title_font=dict(size=10)),
            yaxis        = dict(range=[y_min, y_max], gridcolor='rgba(255,255,255,0.05)',
                                title='Breadth Momentum (21d ROC)', title_font=dict(size=10)),
            showlegend   = False,
            margin       = dict(r=40, l=60, t=50, b=50),
        )

        st.plotly_chart(fig, use_container_width=True)

        # ── Streamlit legend below chart ──────────────────────────────────────
        quad_groups = {'1_LEADING': [], '2_WEAKENING': [], '3_IMPROVING': [], '4_LAGGING': []}
        quad_labels = {
            '1_LEADING'  : ('🟢 LEADING',   '#2dc653'),
            '2_WEAKENING': ('🟡 WEAKENING',  '#f77f00'),
            '3_IMPROVING': ('🔵 IMPROVING',  '#00b4d8'),
            '4_LAGGING'  : ('🔴 LAGGING',    '#e63946'),
        }
        for sec_key, (x, y, label, colour) in sorted_tickers:
            quad = get_quadrant(x, y)[0]
            quad_groups[quad].append((label, colour))

        leg_cols = st.columns(4)
        for i, (quad_key, items) in enumerate(quad_groups.items()):
            qname, qcolour = quad_labels[quad_key]
            with leg_cols[i]:
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
                    use_container_width=True,
                    hide_index=False,
                    height=500
                )

            with col2:
                st.markdown("**Bottom 10 — weakest vs benchmark**")
                st.dataframe(
                    format_drawdown_df(df, cols_show).tail(10).style.map(colour_rs, subset=['rs_vs_bench','dd_vs_bench']),
                    use_container_width=True,
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
                use_container_width=True,
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
                                use_container_width=True, hide_index=False, height=500
                            )
                        with col2:
                            st.markdown("**Bottom 10**")
                            st.dataframe(
                                format_drawdown_df(df, cols_show).tail(10).style.map(colour_rs, subset=['rs_vs_bench','dd_vs_bench']),
                                use_container_width=True, hide_index=False, height=280
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
                            use_container_width=True,
                            height=300
                        )
                else:
                    st.info("No CSV available for this study — TradingView import only")

            st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# EA COMPARATOR PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "EA Comparator":
    import sys
    sys.path.insert(0, EA)
    from set_comparator import parse_set_file, build_comparison_df, export_set_file, create_zip

    st.markdown("""
        <style>
        [data-testid="stDataFrame"] {
            margin-left: auto;
            margin-right: auto;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("⚙ EA Settings Comparator")

    # ── Session state init ────────────────────────────────────────────────────
    if 'ea_files'    not in st.session_state: st.session_state['ea_files']    = {}
    if 'ea_raw'      not in st.session_state: st.session_state['ea_raw']      = {}
    if 'ea_order'    not in st.session_state: st.session_state['ea_order']    = {}
    if 'ea_bytes'    not in st.session_state: st.session_state['ea_bytes']    = {}
    if 'ea_edited'   not in st.session_state: st.session_state['ea_edited']   = {}

    # ── Controls ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        n_files = st.selectbox("Number of files", list(range(2, 11)), index=0)
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑 Clear All", type="secondary"):
            for key in ['ea_files','ea_raw','ea_order','ea_bytes','ea_edited']:
                st.session_state[key] = {}
            st.rerun()

    # ── File upload slots ─────────────────────────────────────────────────────
    st.divider()
    upload_cols = st.columns(min(n_files, 5))
    for i in range(n_files):
        with upload_cols[i % 5]:
            uploaded = st.file_uploader(
                f"File {i+1}",
                type=['set'],
                key=f"ea_upload_{i}"
            )
            if uploaded is not None:
                file_bytes = uploaded.read()
                fname      = uploaded.name
                params, raw_lines, order = parse_set_file(file_bytes, fname)
                st.session_state['ea_files'][fname]  = params
                st.session_state['ea_raw'][fname]    = raw_lines
                st.session_state['ea_order'][fname]  = order
                st.session_state['ea_bytes'][fname]  = file_bytes
                if fname not in st.session_state['ea_edited']:
                    st.session_state['ea_edited'][fname] = params.copy()
                st.success(f"✓ {fname} — {len(params)} params")

    # ── Comparison table ──────────────────────────────────────────────────────
     
    files_data = st.session_state['ea_files']

    if len(files_data) >= 2:
        st.divider()

        filenames = list(files_data.keys())

        col1, col2, col3 = st.columns(3)
        with col1:
            source_file = st.selectbox("Source file for comparison", filenames)
        with col2:
            pct_threshold = st.slider("Highlight % variation from source", 0, 100, 10)
        with col3:
            show_diff_only = st.toggle("Show different rows only", value=False)

        # Build comparison df
        files_list = [(fn, st.session_state['ea_files'][fn],
                       st.session_state['ea_raw'][fn],
                       st.session_state['ea_order'][fn])
                      for fn in filenames]
        df = build_comparison_df(files_list)

        # Identify rows with differences
        value_cols   = [c for c in df.columns if c != 'Parameter']
        df['_diff']  = df[value_cols].nunique(axis=1) > 1

        if show_diff_only:
            df_display = df[df['_diff']].copy()
        else:
            df_display = df.copy()

        df_display = df_display.drop(columns=['_diff'])

        # Style function
        source_vals = files_data.get(source_file, {})

        def style_cells(row):
            styles = [''] * len(row)
            param  = row['Parameter']
            src_v  = source_vals.get(param, '')

            for j, col in enumerate(row.index):
                if col == 'Parameter':
                    continue
                cell_v = row[col]
                if col == source_file:
                    styles[j] = 'background-color: rgba(100,100,255,0.15)'
                    continue
                if cell_v == '' or src_v == '':
                    if cell_v != src_v:
                        styles[j] = 'background-color: rgba(255,180,0,0.2)'
                    continue
                # Try numeric comparison
                try:
                    sv = float(src_v)
                    cv = float(cell_v)
                    if sv == 0:
                        if cv != 0:
                            styles[j] = 'background-color: rgba(255,100,100,0.2)'
                    else:
                        pct_diff = abs((cv - sv) / sv) * 100
                        if pct_diff > pct_threshold:
                            styles[j] = 'background-color: rgba(255,100,100,0.2)'
                        elif pct_diff > 0:
                            styles[j] = 'background-color: rgba(255,180,0,0.15)'
                except:
                    # String comparison
                    if cell_v != src_v:
                        styles[j] = 'background-color: rgba(255,180,0,0.2)'

            return styles

        st.markdown(f"**{len(df_display)} parameters** — "
                    f"{int(df[df['_diff']].shape[0])} rows differ across files")

        styled = df_display.style.apply(style_cells, axis=1)
        row_height   = 35
        table_height = min(len(df_display) * row_height + 40, 2000)

        col_config = {'Parameter': st.column_config.TextColumn('Parameter', width='medium')}
        for fn in filenames:
            col_config[fn] = st.column_config.TextColumn(fn, width='small')

        st.dataframe(
            styled,
            use_container_width=False,
            hide_index=True,
            height=table_height,
            column_config=col_config
        )

        # ── Edit & Export ─────────────────────────────────────────────────────
        st.divider()
        st.subheader("Edit & Export")

        edit_file = st.selectbox("Select file to edit", filenames, key='ea_edit_sel')

        if edit_file:
            edited_params = st.session_state['ea_edited'].get(edit_file, {})
            order         = st.session_state['ea_order'].get(edit_file, [])
            raw_lines     = st.session_state['ea_raw'].get(edit_file, {})

            # Editable dataframe for selected file
            edit_df = pd.DataFrame([
                {'Parameter': k, 'Value': edited_params.get(k, '')}
                for k in order
            ])

            edited = st.data_editor(
                edit_df,
                use_container_width=True,
                hide_index=True,
                height=400,
                column_config={
                    'Parameter': st.column_config.TextColumn('Parameter', disabled=True),
                    'Value'    : st.column_config.TextColumn('Value'),
                },
                key=f"ea_editor_{edit_file}"
            )

            # Save edits back to session state
            st.session_state['ea_edited'][edit_file] = dict(
                zip(edited['Parameter'], edited['Value'].astype(str))
            )

            col1, col2 = st.columns(2)
            with col1:
                # Export single file
                export_bytes = export_set_file(
                    edit_file,
                    st.session_state['ea_edited'][edit_file],
                    raw_lines,
                    order,
                    st.session_state['ea_bytes'][edit_file]
                )
                st.download_button(
                    label     = f"⬇ Export {edit_file}",
                    data      = export_bytes,
                    file_name = edit_file,
                    mime      = 'application/octet-stream',
                    key       = 'ea_export_single'
                )

            with col2:
                # Export all files as zip
                all_exports = []
                for fn in filenames:
                    fb = export_set_file(
                        fn,
                        st.session_state['ea_edited'].get(fn, files_data[fn]),
                        st.session_state['ea_raw'][fn],
                        st.session_state['ea_order'][fn],
                        st.session_state['ea_bytes'][fn]
                    )
                    all_exports.append((fn, fb))
                zip_bytes = create_zip(all_exports)
                st.download_button(
                    label     = "⬇ Export All as ZIP",
                    data      = zip_bytes,
                    file_name = f"ea_settings_{datetime.today().strftime('%Y%m%d')}.zip",
                    mime      = 'application/zip',
                    key       = 'ea_export_all'
                )

    elif len(files_data) == 1:
        st.info("Upload at least 2 files to compare")
    else:
        st.info("Upload .set files above to begin comparison")

# ═══════════════════════════════════════════════════════════════════════════════
# MT5 ANALYSIS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "MT5 Analysis":
    import sys
    sys.path.insert(0, EA)
    from mt5_parser import parse_mt5_report, calc_stats, extract_strategy
    import plotly.graph_objects as go
    import plotly.express as px

    st.title("📊 MT5 Trade Analysis")

    # ── Session state ─────────────────────────────────────────────────────────
    if 'mt5_df' not in st.session_state:
        st.session_state['mt5_df'] = None

    # ── File upload ───────────────────────────────────────────────────────────
    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded = st.file_uploader("Upload MT5 HTML Report", type=['html','htm'])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑 Clear", type="secondary"):
            st.session_state['mt5_df'] = None
            st.rerun()

    if uploaded:
        df_raw = parse_mt5_report(uploaded.read())
        if df_raw is not None:
            st.session_state['mt5_df'] = df_raw
            st.success(f"✓ Loaded {len(df_raw)} trades")
        else:
            st.error("Could not parse report — check file format")

    df_all = st.session_state['mt5_df']

    if df_all is not None and len(df_all) > 0:

        # ── Filters ───────────────────────────────────────────────────────────
        st.divider()
        fc1, fc2, fc3, fc4 = st.columns(4)

        with fc1:
            date_min = df_all['open_time'].min().date()
            date_max = df_all['open_time'].max().date()
            date_from = st.date_input("From", value=date_min, min_value=date_min, max_value=date_max, key='mt5_from')
            date_to   = st.date_input("To",   value=date_max, min_value=date_min, max_value=date_max, key='mt5_to')

        with fc2:
            symbols   = ['All'] + sorted(df_all['symbol'].dropna().unique().tolist())
            sel_symbol= st.multiselect("Symbol", symbols[1:], key='mt5_sym')

        with fc3:
            strategies   = ['All'] + sorted(df_all['strategy'].dropna().unique().tolist())
            sel_strategy = st.multiselect("Strategy / EA", strategies[1:], key='mt5_strat')

        with fc4:
            days      = ['All','Monday','Tuesday','Wednesday','Thursday','Friday']
            sel_days  = st.multiselect("Day of week", days[1:], key='mt5_days')

        # Apply filters
        df = df_all.copy()
        df = df[(df['open_time'].dt.date >= date_from) & (df['open_time'].dt.date <= date_to)]
        if sel_symbol:
            df = df[df['symbol'].isin(sel_symbol)]
        if sel_strategy:
            df = df[df['strategy'].isin(sel_strategy)]
        if sel_days:
            df = df[df['day_of_week'].isin(sel_days)]

        st.caption(f"Showing {len(df)} trades after filters")

        # ── Analysis mode ─────────────────────────────────────────────────────
        mode = st.radio("Analysis mode",
                        ["Overall", "By Strategy", "By Symbol", "By Day of Week"],
                        horizontal=True)

        st.divider()

        # ── Stats card helper ─────────────────────────────────────────────────
        def render_stats(stats, label=""):
            if label:
                st.markdown(f"**{label}**")

            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Net Profit",     f"${stats['net_profit']:,.2f}")
            c2.metric("Win Rate",       f"{stats['win_rate']}%")
            c3.metric("Profit Factor",  f"{stats['profit_factor']}")
            c4.metric("R:R Ratio",      f"{stats['rr_ratio']}")
            c5.metric("Expectancy",     f"${stats['expectancy']:,.2f}")

            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Total Trades",   stats['total_trades'])
            c2.metric("Avg Win",        f"${stats['avg_win']:,.2f}")
            c3.metric("Avg Loss",       f"${stats['avg_loss']:,.2f}")
            c4.metric("Max DD",         f"${stats['max_drawdown']:,.2f}")
            c5.metric("Best Trade",     f"${stats['best_trade']:,.2f}")

            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Max Consec Wins",   stats['max_consec_wins'])
            c2.metric("Max Consec Losses", stats['max_consec_losses'])
            c3.metric("Avg Win Duration",  f"{stats['avg_win_duration']}m")
            c4.metric("Avg Loss Duration", f"{stats['avg_loss_duration']}m")
            c5.metric("Worst Trade",       f"${stats['worst_trade']:,.2f}")

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Long Trades",    stats['long_trades'])
            c2.metric("Long Win Rate",  f"{stats['long_win_rate']}%")
            c3.metric("Short Trades",   stats['short_trades'])
            c4.metric("Short Win Rate", f"{stats['short_win_rate']}%")

        # ── Equity curve helper ───────────────────────────────────────────────
        def render_equity_curve(df_plot, label="Equity Curve"):
            df_sorted = df_plot.sort_values('close_time').copy()
            df_sorted['cumulative'] = df_sorted['net_profit'].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_sorted['close_time'],
                y=df_sorted['cumulative'],
                mode='lines',
                line=dict(color='#00b4d8', width=2),
                fill='tozeroy',
                fillcolor='rgba(0,180,216,0.1)',
                name='Equity'
            ))
            fig.update_layout(
                title=label, height=300,
                plot_bgcolor='rgba(15,15,25,1)',
                paper_bgcolor='rgba(15,15,25,1)',
                font=dict(color='white'),
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix='$'),
                margin=dict(l=60,r=20,t=40,b=40)
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── Day of week bar chart ─────────────────────────────────────────────
        def render_dow_chart(df_plot):
            dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            dow = df_plot.groupby('day_of_week').agg(
                trades     = ('net_profit','count'),
                net_profit = ('net_profit','sum'),
                win_rate   = ('win', lambda x: round(x.mean()*100,1))
            ).reindex([d for d in dow_order if d in df_plot['day_of_week'].unique()])

            wins_by_dow   = df_plot[df_plot['win']==True].groupby('day_of_week')['net_profit'].sum().reindex(dow.index, fill_value=0)
            losses_by_dow = df_plot[df_plot['win']==False].groupby('day_of_week')['net_profit'].sum().reindex(dow.index, fill_value=0)

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=dow.index, y=wins_by_dow,
                name='Profit', marker_color='rgba(45,198,83,0.8)'
            ))
            fig.add_trace(go.Bar(
                x=dow.index, y=losses_by_dow,
                name='Loss', marker_color='rgba(230,57,70,0.8)'
            ))
            fig.update_layout(
                title='Profit & Loss by Day of Week', height=300,
                barmode='relative',
                plot_bgcolor='rgba(15,15,25,1)',
                paper_bgcolor='rgba(15,15,25,1)',
                font=dict(color='white'),
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix='$'),
                legend=dict(bgcolor='rgba(0,0,0,0.3)'),
                margin=dict(l=60,r=20,t=40,b=40)
            )
            st.plotly_chart(fig, use_container_width=True)

            dow_table = dow.reset_index()
            dow_table.columns = ['Day','Trades','Net Profit','Win Rate %']
            dow_table['Net Profit'] = dow_table['Net Profit'].round(2)
            st.dataframe(dow_table, use_container_width=True, hide_index=True)

        # ── Hour of day chart ─────────────────────────────────────────────────
        def render_hour_chart(df_plot):
            hourly = df_plot.groupby('hour').agg(
                trades     = ('net_profit','count'),
                net_profit = ('net_profit','sum'),
                win_rate   = ('win', lambda x: round(x.mean()*100,1))
            )

            wins_by_hour   = df_plot[df_plot['win']==True].groupby('hour')['net_profit'].sum().reindex(hourly.index, fill_value=0)
            losses_by_hour = df_plot[df_plot['win']==False].groupby('hour')['net_profit'].sum().reindex(hourly.index, fill_value=0)

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=wins_by_hour.index, y=wins_by_hour,
                name='Profit', marker_color='rgba(45,198,83,0.8)'
            ))
            fig.add_trace(go.Bar(
                x=losses_by_hour.index, y=losses_by_hour,
                name='Loss', marker_color='rgba(230,57,70,0.8)'
            ))
            fig.update_layout(
                title='Profit & Loss by Hour of Day (Open Time)', height=300,
                barmode='relative',
                plot_bgcolor='rgba(15,15,25,1)',
                paper_bgcolor='rgba(15,15,25,1)',
                font=dict(color='white'),
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title='Hour (UTC)'),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', tickprefix='$'),
                legend=dict(bgcolor='rgba(0,0,0,0.3)'),
                margin=dict(l=60,r=20,t=40,b=40)
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── Render based on mode ──────────────────────────────────────────────
        if mode == "Overall":
            stats = calc_stats(df)
            render_stats(stats, "Overall Statistics")
            render_equity_curve(df)
            col1, col2 = st.columns(2)
            with col1:
                render_dow_chart(df)
            with col2:
                render_hour_chart(df)

        elif mode == "By Strategy":
            strategies_in_df = sorted(df['strategy'].dropna().unique().tolist())
            if len(strategies_in_df) == 0:
                st.info("No strategies found — all trades are manual")
            else:
                # Summary comparison table
                st.subheader("Strategy Comparison")
                summary_rows = []
                for strat in strategies_in_df:
                    s_df   = df[df['strategy'] == strat]
                    s_stat = calc_stats(s_df)
                    summary_rows.append({
                        'Strategy'       : strat,
                        'Trades'         : s_stat['total_trades'],
                        'Net Profit'     : s_stat['net_profit'],
                        'Win Rate %'     : s_stat['win_rate'],
                        'Profit Factor'  : s_stat['profit_factor'],
                        'R:R'            : s_stat['rr_ratio'],
                        'Expectancy'     : s_stat['expectancy'],
                        'Max DD'         : s_stat['max_drawdown'],
                        'Max Consec W'   : s_stat['max_consec_wins'],
                        'Max Consec L'   : s_stat['max_consec_losses'],
                        'Avg Win'        : s_stat['avg_win'],
                        'Avg Loss'       : s_stat['avg_loss'],
                    })
                sum_df = pd.DataFrame(summary_rows).sort_values('Net Profit', ascending=False)

                def colour_profit(val):
                    try:
                        v = float(str(val).replace(',',''))
                        if v > 0: return 'background-color: rgba(0,180,0,0.12)'
                        if v < 0: return 'background-color: rgba(180,0,0,0.12)'
                    except: pass
                    return ''

                st.dataframe(
                    sum_df.style.map(colour_profit, subset=['Net Profit','Expectancy','Max DD']),
                    use_container_width=True, hide_index=True
                )

                # Detail per strategy
                st.divider()
                sel_strat_detail = st.selectbox("Select strategy for detail", strategies_in_df)
                if sel_strat_detail:
                    s_df   = df[df['strategy'] == sel_strat_detail]
                    s_stat = calc_stats(s_df)
                    render_stats(s_stat, sel_strat_detail)
                    render_equity_curve(s_df, f"{sel_strat_detail} — Equity Curve")
                    col1, col2 = st.columns(2)
                    with col1:
                        render_dow_chart(s_df)
                    with col2:
                        render_hour_chart(s_df)

        elif mode == "By Symbol":
            symbols_in_df = sorted(df['symbol'].dropna().unique().tolist())
            summary_rows  = []
            for sym in symbols_in_df:
                s_df   = df[df['symbol'] == sym]
                s_stat = calc_stats(s_df)
                summary_rows.append({
                    'Symbol'         : sym,
                    'Trades'         : s_stat['total_trades'],
                    'Net Profit'     : s_stat['net_profit'],
                    'Win Rate %'     : s_stat['win_rate'],
                    'Profit Factor'  : s_stat['profit_factor'],
                    'R:R'            : s_stat['rr_ratio'],
                    'Expectancy'     : s_stat['expectancy'],
                    'Max DD'         : s_stat['max_drawdown'],
                })
            sum_df = pd.DataFrame(summary_rows).sort_values('Net Profit', ascending=False)

            def colour_profit(val):
                try:
                    v = float(str(val).replace(',',''))
                    if v > 0: return 'background-color: rgba(0,180,0,0.12)'
                    if v < 0: return 'background-color: rgba(180,0,0,0.12)'
                except: pass
                return ''

            st.dataframe(
                sum_df.style.map(colour_profit, subset=['Net Profit','Expectancy','Max DD']),
                use_container_width=True, hide_index=True
            )

            sel_sym_detail = st.selectbox("Select symbol for detail", symbols_in_df)
            if sel_sym_detail:
                s_df   = df[df['symbol'] == sel_sym_detail]
                s_stat = calc_stats(s_df)
                render_stats(s_stat, sel_sym_detail)
                render_equity_curve(s_df, f"{sel_sym_detail} — Equity Curve")
                col1, col2 = st.columns(2)
                with col1:
                    render_dow_chart(s_df)
                with col2:
                    render_hour_chart(s_df)

        elif mode == "By Day of Week":
            render_dow_chart(df)
            render_hour_chart(df)

        # ── Raw trade log ─────────────────────────────────────────────────────
        st.divider()
        with st.expander("Raw Trade Log"):
            show_cols = ['open_time','close_time','symbol','type','strategy',
                         'volume','open_price','close_price','sl','tp',
                         'commission','swap','profit','net_profit','duration_min']
            show_cols = [c for c in show_cols if c in df.columns]

            def colour_net(val):
                try:
                    v = float(val)
                    if v > 0: return 'background-color: rgba(0,180,0,0.12)'
                    if v < 0: return 'background-color: rgba(180,0,0,0.12)'
                except: pass
                return ''

            st.dataframe(
                df[show_cols].style.map(colour_net, subset=['net_profit','profit']),
                use_container_width=True, hide_index=True, height=400
            )

            csv_data = df[show_cols].to_csv(index=False)
            st.download_button(
                label     = "⬇ Download filtered trades CSV",
                data      = csv_data,
                file_name = f"mt5_trades_{date_from}_{date_to}.csv",
                mime      = 'text/csv'
            )

# ═══════════════════════════════════════════════════════════════════════════════
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

            # ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Settings":
    st.title("⚙ Dashboard Settings")
    st.caption("Changes take effect after saving and reloading the page")

    current = load_settings()

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

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save & Reload", type="primary"):
            current['pages'] = updated_pages
            save_settings(current)
            st.success("Settings saved")
            st.rerun()
    with col2:
        if st.button("Reset to defaults", type="secondary"):
            save_settings(DEFAULT_SETTINGS)
            st.success("Reset to defaults")
            st.rerun()