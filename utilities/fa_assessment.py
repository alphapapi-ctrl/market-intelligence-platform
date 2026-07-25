"""
utilities/fa_assessment.py
==========================
Fundamental analysis assessment using local LLM (Ollama/LM Studio) with RAG context.
"""

import os
import requests
import chromadb
from chromadb.utils import embedding_functions

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.path.join(BASE, 'data', 'fa_chromadb')

SYSTEM_PROMPT = """You are a fundamental analyst who thinks through the lens of Michael Burry and Warren Buffett.

Your analytical framework draws from their actual methodology:

BURRY'S FRAMEWORK:
- Tragic Algebra (Omega): True SBC cost = buybacks-to-nowhere + RSU tax withholdings. Replaces GAAP SBC. Typically 1.5-2.5x reported SBC.
- E-delta: Cumulative owners' earnings / cumulative GAAP net income. Shows what shareholders actually receive. NASDAQ 100 benchmark is 83.4%.
- IV15: Price providing 15% CAGR over 15+ years via multi-stage DCF (3-4 stages). NOT a simple P/E ratio.
- Intrinsic value sits around 1.5-2.25x IV15 (typically IV8-IV10). Buybacks below this are accretive, above are dilutive.
- AICT Tiers (AI & Competitive Threat): Fortress > Castle > Chapel > Stone > Wood. Higher tier = more durable moat.
- Shareholder turnover: 3-5x shares outstanding traded since peak typically signals bottoming. Newer companies may need up to 10x.
- Volume swell at lows signals potential bottoming process.
- Tangible book value per share trending upward = "rare and a strong sign."
- Revenue growing while stock crashes 70-80% with stable gross margins = classic value setup.

BUFFETT/MUNGER FRAMEWORK:
- Durable competitive advantage (moat) — can you predict the business in 10-15 years?
- Management quality and capital allocation discipline.
- Circle of competence — is this business understandable?
- Margin of safety — price vs intrinsic value.
- Owner earnings = net income + depreciation - maintenance capex.

YOUR TASK:
When given a ticker, financial data, and current market conditions, provide a concise fundamental perspective as these investors would see it.

Your response MUST use exactly these section headers, in this order. Every section is required — do not skip any:

**BUSINESS QUALITY** — Is the moat durable? What AICT tier?
**SHAREHOLDER TREATMENT** — Management alignment, capital allocation, SBC concerns.
**VALUATION** — Is this cheap relative to business quality? Use the multiples provided.
**VALUE PRICE TARGETS** — MANDATORY, never omit. Estimate intrinsic value per share using owner earnings / DCF logic from the per-share figures provided (fcf_per_share, eps, book_value). State your assumptions (growth rate, discount rate, terminal multiple). Then give three explicit numeric per-share targets:
  - Bear: $X.XX
  - Base: $X.XX
  - Bull: $X.XX
  Compare each to the current price and state the margin of safety (or premium) as a percentage at the base case.
**MACRO POSITIONING** — How does the rate/yield environment affect this business? Sector in or out of favour?
**KEY RISKS** — What could permanently impair the business? Include macro risks.
**VERDICT** — Would this interest a value investor given both fundamentals AND the current environment?

Use the reference documents provided as context for calibration and methodology.
Be direct and specific. Use actual numbers from the data provided. Reference the macro data to contextualise the stock's position. No generic disclaimers.
Keep your response to 600-700 words. If short on space, compress other sections — VALUE PRICE TARGETS must always contain the three numeric targets."""


# ── Value-investor guide ranges (Buffett/Burry heuristics) ──────────────────
# key: (guide text, good threshold, bad threshold, direction)
# direction 'low'  = lower is better (good if <= good_thr, bad if >= bad_thr)
# direction 'high' = higher is better (good if >= good_thr, bad if <= bad_thr)
METRIC_GUIDES = {
    'pe_ratio':         ('<15 value · 15-25 fair · >25 rich',          15,   25,   'low'),
    'forward_pe':       ('<15 value · 15-25 fair · >25 rich',          15,   25,   'low'),
    'pb_ratio':         ('<1.5 classic value · >3 needs high ROE',     1.5,  3,    'low'),
    'ps_ratio':         ('<2 value · >5 rich',                         2,    5,    'low'),
    'gross_margin':     ('>40% moat signal · <20% commodity',          40,   20,   'high'),
    'operating_margin': ('>15% strong · <8% weak',                     15,   8,    'high'),
    'profit_margin':    ('>10% strong · <5% thin',                     10,   5,    'high'),
    'roe':              ('>15% quality · <8% poor',                    15,   8,    'high'),
    'roa':              ('>7% strong · <3% weak',                      7,    3,    'high'),
    'debt_to_equity':   ('<50 conservative · >100 leveraged',          50,   100,  'low'),
    'current_ratio':    ('>1.5 healthy · <1 strained',                 1.5,  1.0,  'high'),
    'revenue_growth':   ('>5% healthy · negative = declining',         5,    0,    'high'),
    'dividend_yield':   ('3-6% income sweet spot',                     None, None, None),
}


def _parse_metric(val):
    """Parse a formatted metric string ('20.00', '45.1%', '$8.14B') to float."""
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str) or val == 'N/A':
        return None
    try:
        return float(val.replace('%', '').replace('$', '').replace(',', '').strip())
    except ValueError:
        return None


def _guide_verdict(key, val):
    """Return (guide_text, verdict_symbol) for a metric, or (None, '')."""
    g = METRIC_GUIDES.get(key)
    if g is None:
        return None, ''
    text, good_thr, bad_thr, direction = g
    v = _parse_metric(val)
    if v is None or direction is None:
        return text, ''
    if direction == 'low':
        verdict = '✅' if v <= good_thr else ('❌' if v >= bad_thr else '➖')
    else:
        verdict = '✅' if v >= good_thr else ('❌' if v <= bad_thr else '➖')
    return text, verdict


def _is_au_ticker(ticker):
    return ticker.upper().endswith('.AX')


def _fetch_rate_series(tickers_map, macro):
    """Download rate/yield tickers and store current + history in macro dict."""
    import yfinance as yf
    import pandas as pd
    data = yf.download(list(tickers_map.keys()), period='3mo', progress=False)
    if data is not None and not data.empty:
        close = data['Close'] if len(tickers_map) > 1 else data[['Close']].rename(columns={'Close': list(tickers_map.keys())[0]})
        # handle single-ticker case where columns aren't multi-level
        if len(tickers_map) == 1:
            tkr = list(tickers_map.keys())[0]
            if tkr not in close.columns:
                close = data[['Close']]
                close.columns = [tkr]
        for tkr, label in tickers_map.items():
            if tkr in close.columns:
                series = close[tkr].dropna()
                if len(series) >= 2:
                    macro[label] = {
                        'current': float(series.iloc[-1]),
                        '1mo_ago': float(series.iloc[-min(21, len(series))]),
                        '3mo_ago': float(series.iloc[0]),
                    }


def _fetch_rba_series(fname, title_match, label, macro):
    """
    Fetch a yield series from an RBA statistical table CSV.
    Yahoo has no working tickers for AU government yields, so we go to the
    source: https://www.rba.gov.au/statistics/tables/csv/<fname>
    The CSVs have metadata rows; we locate the 'Title' row to find the column
    and the 'Series ID' row to find where data starts.
    """
    import csv as _csv
    try:
        resp = requests.get(
            f'https://www.rba.gov.au/statistics/tables/csv/{fname}',
            timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code != 200:
            return
        reader = list(_csv.reader(resp.text.splitlines()))
        title_row = next((r for r in reader if r and r[0].strip().lower() == 'title'), None)
        sid_idx   = next((i for i, r in enumerate(reader)
                          if r and r[0].strip().lower() == 'series id'), None)
        if title_row is None or sid_idx is None:
            return
        col = next((i for i, t in enumerate(title_row)
                    if title_match.lower() in t.lower()), None)
        if col is None:
            return
        vals = []
        for r in reader[sid_idx + 1:]:
            if len(r) > col and r[col].strip():
                try:
                    vals.append(float(r[col]))
                except ValueError:
                    pass
        if len(vals) >= 2:
            macro[label] = {
                'current': vals[-1],
                '1mo_ago': vals[-min(21, len(vals))],
                '3mo_ago': vals[-min(63, len(vals))],
            }
    except Exception:
        pass  # non-fatal — AU yields just won't show


def _fetch_sector_perf(tickers_map, macro, key='sectors'):
    """Download sector ETFs and compute 1mo/3mo returns."""
    import yfinance as yf
    import pandas as pd
    data = yf.download(list(tickers_map.keys()), period='3mo', progress=False)
    if data is not None and not data.empty:
        close = data['Close']
        perf = {}
        for tkr, name in tickers_map.items():
            if tkr in close.columns:
                series = close[tkr].dropna()
                if len(series) >= 2:
                    ret_1mo = float((series.iloc[-1] / series.iloc[-min(21, len(series))] - 1) * 100)
                    ret_3mo = float((series.iloc[-1] / series.iloc[0] - 1) * 100)
                    perf[name] = {'1mo': ret_1mo, '3mo': ret_3mo}
        macro[key] = perf


def _fetch_index(tickers, macro, keys):
    """Download broad market index + volatility index."""
    import yfinance as yf
    import pandas as pd
    data = yf.download(tickers, period='3mo', progress=False)
    if data is not None and not data.empty:
        close = data['Close']
        idx_tkr, vix_tkr = tickers
        idx_key, vix_key = keys
        if idx_tkr in close.columns:
            s = close[idx_tkr].dropna()
            if len(s) >= 2:
                macro[idx_key] = {
                    'current': float(s.iloc[-1]),
                    '1mo_ret': float((s.iloc[-1] / s.iloc[-min(21, len(s))] - 1) * 100),
                    '3mo_ret': float((s.iloc[-1] / s.iloc[0] - 1) * 100),
                }
        if vix_tkr in close.columns:
            v = close[vix_tkr].dropna()
            if len(v) >= 1:
                macro[vix_key] = float(v.iloc[-1])


def fetch_macro_context(ticker=''):
    """Fetch current macro environment data. Includes AU data for .AX tickers."""
    try:
        macro = {}
        is_au = _is_au_ticker(ticker)

        # ── US yields & rates (always included) ──────────────────────────────
        _fetch_rate_series({
            '^IRX': 'us_13w_tbill',
            '^FVX': 'us_5y_yield',
            '^TNX': 'us_10y_yield',
            '^TYX': 'us_30y_yield',
        }, macro)

        # ── AU yields (from RBA tables — Yahoo has no AU yield tickers) ──────
        if is_au:
            _fetch_rba_series('f1-data.csv', 'cash rate target', 'au_cash_rate', macro)
            _fetch_rba_series('f2-data.csv', '10 year', 'au_10y_yield', macro)

        # ── US sectors ───────────────────────────────────────────────────────
        _fetch_sector_perf({
            'XLK': 'Technology', 'XLF': 'Financials', 'XLE': 'Energy',
            'XLV': 'Healthcare', 'XLI': 'Industrials', 'XLP': 'Staples',
            'XLU': 'Utilities',  'XLB': 'Materials',   'XLRE': 'Real Estate',
            'XLC': 'Comms',      'XLY': 'Discretionary',
        }, macro, key='us_sectors')

        # ── AU sectors (ASX sector ETFs) ─────────────────────────────────────
        if is_au:
            _fetch_sector_perf({
                'VAS.AX': 'ASX 300 (Broad)',
                'VAP.AX': 'AU Property',
                'VGS.AX': 'Intl Shares',
                'OZR.AX': 'AU Resources',
                'QFN.AX': 'AU Financials',
                'TECH.AX': 'AU Technology',
                'HLTH.AX': 'AU Healthcare',
                'MVE.AX': 'AU Energy',
            }, macro, key='au_sectors')

        # ── US broad market ──────────────────────────────────────────────────
        _fetch_index(['^GSPC', '^VIX'], macro, ['sp500', 'vix'])

        # ── AU broad market ──────────────────────────────────────────────────
        if is_au:
            _fetch_index(['^AXJO', '^AXVI'], macro, ['asx200', 'au_vix'])
            # AUD/USD
            import yfinance as yf
            import pandas as pd
            aud = yf.download('AUDUSD=X', period='3mo', progress=False)
            if aud is not None and not aud.empty:
                close = aud['Close']
                if isinstance(close, pd.DataFrame):
                    close = close.squeeze()
                if hasattr(close, 'dropna'):
                    s = close.dropna()
                    if len(s) >= 2:
                        macro['audusd'] = {
                            'current': float(s.iloc[-1]),
                            '1mo_ret': float((s.iloc[-1] / s.iloc[-min(21, len(s))] - 1) * 100),
                            '3mo_ret': float((s.iloc[-1] / s.iloc[0] - 1) * 100),
                        }

        macro['_market'] = 'au' if is_au else 'us'
        return macro, None
    except Exception as e:
        return {}, f"Macro fetch warning: {str(e)}"


def _format_yields(macro, lines):
    """Format yield/rate lines."""
    is_au = macro.get('_market') == 'au'

    us_yield_labels = {
        'us_13w_tbill': '13-Week T-Bill (Fed Funds proxy)',
        'us_5y_yield':  '5-Year UST',
        'us_10y_yield': '10-Year UST',
        'us_30y_yield': '30-Year UST',
    }
    au_yield_labels = {
        'au_cash_rate': 'RBA Cash Rate Target',
        'au_10y_yield': 'AU 10-Year Govt Bond',
    }

    def _add_yields(labels, header):
        has = False
        start = len(lines)
        for key, label in labels.items():
            if key in macro:
                d = macro[key]
                current = d['current']
                chg_1mo = current - d['1mo_ago']
                chg_3mo = current - d['3mo_ago']
                arrow = '↑' if chg_1mo > 0 else '↓' if chg_1mo < 0 else '→'
                lines.append(f"  {label}: {current:.2f}%  ({arrow}{abs(chg_1mo):.2f}% 1mo, {'+' if chg_3mo >= 0 else ''}{chg_3mo:.2f}% 3mo)")
                has = True
        if has:
            lines.insert(start, header)
        return has

    has_us = _add_yields(us_yield_labels, "US YIELDS & RATES:")
    if has_us and 'us_10y_yield' in macro and 'us_13w_tbill' in macro:
        spread = macro['us_10y_yield']['current'] - macro['us_13w_tbill']['current']
        lines.append(f"  10Y-3M Spread: {spread:+.2f}% ({'INVERTED — recession signal' if spread < 0 else 'Normal'})")
    if has_us:
        lines.append('')

    if is_au:
        has_au = _add_yields(au_yield_labels, "AU YIELDS & RATES:")
        if has_au:
            lines.append('')


def _format_broad_market(macro, lines):
    """Format broad market index lines."""
    is_au = macro.get('_market') == 'au'

    if 'sp500' in macro or 'vix' in macro:
        lines.append("US BROAD MARKET:")
        if 'sp500' in macro:
            sp = macro['sp500']
            lines.append(f"  S&P 500: {sp['current']:,.0f}  (1mo: {sp['1mo_ret']:+.1f}%, 3mo: {sp['3mo_ret']:+.1f}%)")
        if 'vix' in macro:
            vix = macro['vix']
            vix_label = 'Low volatility' if vix < 15 else 'Moderate' if vix < 20 else 'Elevated' if vix < 30 else 'High fear'
            lines.append(f"  VIX: {vix:.1f} ({vix_label})")
        lines.append('')

    if is_au and ('asx200' in macro or 'au_vix' in macro or 'audusd' in macro):
        lines.append("AU BROAD MARKET:")
        if 'asx200' in macro:
            ax = macro['asx200']
            lines.append(f"  ASX 200: {ax['current']:,.0f}  (1mo: {ax['1mo_ret']:+.1f}%, 3mo: {ax['3mo_ret']:+.1f}%)")
        if 'au_vix' in macro:
            av = macro['au_vix']
            av_label = 'Low volatility' if av < 15 else 'Moderate' if av < 20 else 'Elevated' if av < 30 else 'High fear'
            lines.append(f"  S&P/ASX 200 VIX: {av:.1f} ({av_label})")
        if 'audusd' in macro:
            aud = macro['audusd']
            lines.append(f"  AUD/USD: {aud['current']:.4f}  (1mo: {aud['1mo_ret']:+.1f}%, 3mo: {aud['3mo_ret']:+.1f}%)")
        lines.append('')


def _format_sectors(macro, lines):
    """Format sector performance lines."""
    is_au = macro.get('_market') == 'au'

    def _add_sector_block(key, header):
        if key in macro and macro[key]:
            lines.append(header)
            sorted_s = sorted(macro[key].items(), key=lambda x: x[1]['1mo'], reverse=True)
            for name, perf in sorted_s:
                lines.append(f"  {name:<18s} 1mo: {perf['1mo']:+.1f}%   3mo: {perf['3mo']:+.1f}%")
            top = [s[0] for s in sorted_s[:3]]
            bottom = [s[0] for s in sorted_s[-3:]]
            lines.append(f"  → Leading: {', '.join(top)}")
            lines.append(f"  → Lagging: {', '.join(bottom)}")
            lines.append('')

    if is_au:
        _add_sector_block('au_sectors', 'AU SECTOR PERFORMANCE:')
    _add_sector_block('us_sectors', 'US SECTOR PERFORMANCE (S&P 500):')


def format_macro_context(macro):
    """Format macro data dict into a readable string for the LLM prompt."""
    lines = []
    _format_yields(macro, lines)
    _format_broad_market(macro, lines)
    _format_sectors(macro, lines)
    return '\n'.join(lines)


def get_rag_context(query, n_results=5):
    """Retrieve relevant chunks from the FA reference documents."""
    if not os.path.exists(CHROMA_DIR):
        return None, "Vector store not built — run: python utilities/fa_rag_setup.py"

    try:
        ef = embedding_functions.DefaultEmbeddingFunction()
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_collection('fa_reference', embedding_function=ef)

        results = collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        if results and results['documents'] and results['documents'][0]:
            chunks = results['documents'][0]
            sources = [m['source'] for m in results['metadatas'][0]]
            context = '\n\n---\n\n'.join(
                f"[Source: {src}]\n{chunk}"
                for chunk, src in zip(chunks, sources)
            )
            return context, None
        return None, "No relevant context found"
    except Exception as e:
        return None, f"RAG error: {str(e)}"


def _data_line(k, v):
    """One prompt line for a financial metric, with guide bracket if defined."""
    text, verdict = _guide_verdict(k, v)
    if text:
        return f"  {k}: {v}   [guide: {text}] {verdict}"
    return f"  {k}: {v}"


def _call_llm(system_prompt, user_prompt, llm_url, llm_provider, model,
              max_tokens=2000, num_ctx=8192, api_key=None):
    """
    Send a chat request to the LLM. Returns (text, error).
    Providers: 'ollama' | 'lmstudio' (local) | 'openai' (hosted, needs api_key).
    num_ctx is set explicitly for Ollama — its default (2048-8192 depending
    on version) can silently truncate long RAG prompts from the front.
    """
    try:
        if llm_provider == 'openai':
            if not api_key:
                return None, "OpenAI provider selected but no API key configured (FA Settings)"
            response = requests.post(
                f"{llm_url.rstrip('/')}/v1/chat/completions",
                headers={'Authorization': f'Bearer {api_key}'},
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                    'max_tokens': max_tokens,
                    'temperature': 0.3,
                },
                timeout=180,
            )
            if response.status_code != 200:
                return None, f"OpenAI error {response.status_code}: {response.text[:300]}"
            data = response.json()
            return data['choices'][0]['message']['content'], None

        elif llm_provider == 'ollama':
            response = requests.post(
                f"{llm_url}/api/chat",
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                    'stream': False,
                    'options': {'num_predict': max_tokens, 'num_ctx': num_ctx},
                },
                timeout=180,
            )
            if response.status_code != 200:
                return None, f"Ollama error {response.status_code}: {response.text}"
            data = response.json()
            return data.get('message', {}).get('content', ''), None

        elif llm_provider == 'lmstudio':
            response = requests.post(
                f"{llm_url}/v1/chat/completions",
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                    'max_tokens': max_tokens,
                    'temperature': 0.3,
                },
                timeout=180,
            )
            if response.status_code != 200:
                return None, f"LM Studio error {response.status_code}: {response.text}"
            data = response.json()
            return data['choices'][0]['message']['content'], None

        else:
            return None, f"Unknown LLM provider: {llm_provider}"

    except requests.exceptions.ConnectionError:
        return None, f"Cannot connect to {llm_provider} at {llm_url} — is it running?"
    except requests.exceptions.Timeout:
        return None, "LLM request timed out (180s) — model may be loading or prompt too long"
    except Exception as e:
        return None, f"LLM error: {str(e)}"


def _resolve_llm(settings):
    """Resolve (provider, url, model, api_key) from dashboard settings."""
    fa_cfg = settings.get('fa_features', {})
    provider = fa_cfg.get('provider', 'ollama')
    model = fa_cfg.get('model', 'llama3.1:8b')
    api_key = None
    if provider == 'ollama':
        url = fa_cfg.get('ollama_url', 'http://localhost:11434')
    elif provider == 'openai':
        url = fa_cfg.get('openai_url', 'https://api.openai.com')
        api_key = fa_cfg.get('openai_api_key', '')
    else:
        url = fa_cfg.get('lmstudio_url', 'http://localhost:1234')
    return provider, url, model, api_key


def get_fa_assessment(ticker, financial_data, llm_url='http://localhost:11434',
                      llm_provider='ollama', model='llama3.1:8b', max_tokens=2000,
                      macro=None, api_key=None, system_prompt=None):
    """
    Get fundamental analysis assessment from local LLM with RAG context.

    llm_provider: 'ollama' or 'lmstudio'
    llm_url: base URL for the LLM API
    model: model name/identifier
    macro: pre-fetched macro dict (fetched fresh if None)
    """
    # build the query for RAG retrieval
    rag_query = f"fundamental analysis valuation {ticker} {financial_data.get('sector', '')} {financial_data.get('industry', '')}"
    context, rag_error = get_rag_context(rag_query)

    # fetch macro context (reuse caller's copy if provided)
    if macro is None:
        macro, macro_error = fetch_macro_context(ticker)
    macro_text = format_macro_context(macro) if macro else ''

    # Prompt order matters for small models: reference excerpts FIRST
    # (clearly fenced as background), the subject's data after, and the
    # task restated LAST so it dominates. Appending the excerpts at the
    # end makes 8B models summarise the documents instead of analysing
    # the ticker.
    name = financial_data.get('name', ticker)
    data_summary = '\n'.join(_data_line(k, v) for k, v in financial_data.items())

    parts = []
    if context:
        parts.append(
            "REFERENCE EXCERPTS (background calibration only — these are excerpts "
            "from Burry/Buffett writings and may discuss OTHER companies; do NOT "
            "summarise these documents and do NOT analyse the companies they mention):\n"
            f"<<<REFERENCE START>>>\n{context}\n<<<REFERENCE END>>>"
        )
    parts.append(f"FINANCIAL DATA FOR {ticker} ({name}):\n{data_summary}")
    if macro_text:
        parts.append(f"CURRENT MARKET CONDITIONS:\n{macro_text}")
    parts.append(
        f"TASK: Analyse {ticker} ({name}) from a Burry/Buffett fundamental "
        f"perspective, following the framework in your instructions. Your subject "
        f"is {ticker} ONLY. Use the actual numbers from the financial data above. "
        f"The reference excerpts are calibration material, not the subject of "
        f"your analysis."
    )
    user_prompt = '\n\n'.join(parts)

    return _call_llm(system_prompt or SYSTEM_PROMPT, user_prompt, llm_url, llm_provider,
                     model, max_tokens=max_tokens, api_key=api_key)


def fetch_basic_financials(ticker):
    """Fetch basic financial data for a ticker using yfinance."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or info.get('regularMarketPrice') is None:
            # try with .AX suffix for AU stocks
            if not ticker.endswith('.AX'):
                stock = yf.Ticker(f"{ticker}.AX")
                info = stock.info
            if not info or info.get('regularMarketPrice') is None:
                return None, f"No data found for {ticker}"

        financials = {
            'name': info.get('longName', info.get('shortName', ticker)),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'market_cap': info.get('marketCap', 'N/A'),
            'price': info.get('regularMarketPrice', info.get('currentPrice', 'N/A')),
            'pe_ratio': info.get('trailingPE', 'N/A'),
            'forward_pe': info.get('forwardPE', 'N/A'),
            'pb_ratio': info.get('priceToBook', 'N/A'),
            'ps_ratio': info.get('priceToSalesTrailing12Months', 'N/A'),
            'revenue': info.get('totalRevenue', 'N/A'),
            'revenue_growth': info.get('revenueGrowth', 'N/A'),
            'gross_margin': info.get('grossMargins', 'N/A'),
            'operating_margin': info.get('operatingMargins', 'N/A'),
            'profit_margin': info.get('profitMargins', 'N/A'),
            'roe': info.get('returnOnEquity', 'N/A'),
            'roa': info.get('returnOnAssets', 'N/A'),
            'debt_to_equity': info.get('debtToEquity', 'N/A'),
            'current_ratio': info.get('currentRatio', 'N/A'),
            'free_cash_flow': info.get('freeCashflow', 'N/A'),
            'total_cash': info.get('totalCash', 'N/A'),
            'total_debt': info.get('totalDebt', 'N/A'),
            'shares_outstanding': info.get('sharesOutstanding', 'N/A'),
            'book_value': info.get('bookValue', 'N/A'),
            'dividend_yield': info.get('dividendYield', 'N/A'),
            'beta': info.get('beta', 'N/A'),
            '52w_high': info.get('fiftyTwoWeekHigh', 'N/A'),
            '52w_low': info.get('fiftyTwoWeekLow', 'N/A'),
            '52w_change': info.get('52WeekChange', 'N/A'),
            'avg_volume': info.get('averageVolume', 'N/A'),
            'eps_trailing': info.get('trailingEps', 'N/A'),
            'eps_forward': info.get('forwardEps', 'N/A'),
            'analyst_target_mean': info.get('targetMeanPrice', 'N/A'),
            'analyst_target_low': info.get('targetLowPrice', 'N/A'),
            'analyst_target_high': info.get('targetHighPrice', 'N/A'),
            'analyst_count': info.get('numberOfAnalystOpinions', 'N/A'),
            'analyst_recommendation': info.get('recommendationKey', 'N/A'),
        }

        # Per-share figures for the intrinsic value section — computed here
        # so the LLM doesn't have to divide billions by share count.
        _fcf    = info.get('freeCashflow')
        _shares = info.get('sharesOutstanding')
        if isinstance(_fcf, (int, float)) and isinstance(_shares, (int, float)) and _shares > 0:
            financials['fcf_per_share'] = f"{_fcf / _shares:.2f}"
        _ocf = info.get('operatingCashflow')
        if isinstance(_ocf, (int, float)) and isinstance(_shares, (int, float)) and _shares > 0:
            financials['operating_cf_per_share'] = f"{_ocf / _shares:.2f}"

        # format large numbers
        for key in ['market_cap', 'revenue', 'free_cash_flow', 'total_cash', 'total_debt']:
            val = financials.get(key)
            if isinstance(val, (int, float)) and val != 'N/A':
                if abs(val) >= 1e12:
                    financials[key] = f"${val/1e12:.2f}T"
                elif abs(val) >= 1e9:
                    financials[key] = f"${val/1e9:.2f}B"
                elif abs(val) >= 1e6:
                    financials[key] = f"${val/1e6:.1f}M"

        for key in ['gross_margin', 'operating_margin', 'profit_margin', 'roe', 'roa',
                     'revenue_growth', '52w_change']:
            val = financials.get(key)
            if isinstance(val, (int, float)) and val != 'N/A':
                financials[key] = f"{val*100:.1f}%"

        # dividendYield: newer yfinance returns a percent (3.44), older a
        # fraction (0.0344) — treat values < 1 as fractions
        _dy = financials.get('dividend_yield')
        if isinstance(_dy, (int, float)) and _dy != 'N/A':
            financials['dividend_yield'] = f"{(_dy * 100 if _dy < 1 else _dy):.2f}%"

        for key in ['pe_ratio', 'forward_pe', 'pb_ratio', 'ps_ratio', 'debt_to_equity',
                     'current_ratio', 'beta', 'analyst_target_mean',
                     'analyst_target_low', 'analyst_target_high']:
            val = financials.get(key)
            if isinstance(val, (int, float)) and val != 'N/A':
                financials[key] = f"{val:.2f}"

        if isinstance(financials.get('shares_outstanding'), (int, float)):
            val = financials['shares_outstanding']
            if val >= 1e9:
                financials['shares_outstanding'] = f"{val/1e9:.2f}B"
            elif val >= 1e6:
                financials['shares_outstanding'] = f"{val/1e6:.1f}M"

        return financials, None

    except Exception as e:
        return None, f"Error fetching data for {ticker}: {str(e)}"


def render_fa_assessment(ticker, settings, system_prompt=None):
    """Render the FA assessment widget in Streamlit.

    system_prompt: optional override for SYSTEM_PROMPT (user-edited via AI Settings).
    """
    import streamlit as st

    provider, llm_url, model, api_key = _resolve_llm(settings)

    # fetch financials and macro in parallel-ish (sequential but both under one spinner)
    with st.spinner(f"Fetching financials & market conditions for {ticker}..."):
        financials, error = fetch_basic_financials(ticker)

    if error:
        st.error(error)
        return None

    # show financial summary
    st.markdown("##### Financial Summary")

    def _metric(col, label, key, prefix=''):
        val = financials.get(key, 'N/A')
        col.metric(label, f"{prefix}{val}")
        text, verdict = _guide_verdict(key, val)
        if text:
            col.caption(f"{verdict} {text}")

    col1, col2, col3, col4 = st.columns(4)
    _metric(col1, "Price", 'price', prefix='$')
    _metric(col1, "P/E", 'pe_ratio')
    _metric(col2, "Market Cap", 'market_cap')
    _metric(col2, "P/B", 'pb_ratio')
    _metric(col3, "Gross Margin", 'gross_margin')
    _metric(col3, "ROE", 'roe')
    _metric(col4, "FCF", 'free_cash_flow')
    _metric(col4, "D/E", 'debt_to_equity')

    # full metric table with guides
    with st.expander("📋 All metrics vs value guide", expanded=False):
        rows = []
        for key, val in financials.items():
            text, verdict = _guide_verdict(key, val)
            if text:
                rows.append({'Metric': key, 'Value': val,
                             'Guide': text, 'Read': verdict or '—'})
        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # analyst targets + recommendation trend
    render_analyst_view(ticker)

    # show macro snapshot (fetched once, reused for the LLM prompt)
    macro, _ = fetch_macro_context(ticker)
    if macro:
        with st.expander("📊 Market Conditions (included in assessment)", expanded=False):
            macro_text = format_macro_context(macro)
            st.code(macro_text, language=None)

    # generate assessment
    with st.spinner("Generating Burry/Buffett assessment..."):
        text, error = get_fa_assessment(
            ticker, financials,
            llm_url=llm_url,
            llm_provider=provider,
            model=model,
            macro=macro,
            api_key=api_key,
            system_prompt=system_prompt,
        )

    if error:
        st.error(error)
        return None

    if text:
        html_text = text.replace('\n', '<br>')
        st.markdown(f"""
            <div style="border-left:3px solid #e6a817;padding:12px 16px;
                        border-radius:0 8px 8px 0;margin:8px 0;
                        background:rgba(230,168,23,0.05)">
                <div style="color:#e6a817;font-size:10px;font-weight:bold;
                            letter-spacing:1px;margin-bottom:8px">FUNDAMENTAL ASSESSMENT — BURRY/BUFFETT LENS</div>
                <div style="font-size:13px;line-height:1.7;white-space:pre-wrap">{html_text}</div>
            </div>
        """, unsafe_allow_html=True)
        return text

    return None


# ══════════════════════════════════════════════════════════════════════════
# ANALYST VIEW — price target range + recommendation trend visuals
# ══════════════════════════════════════════════════════════════════════════

def fetch_analyst_view(ticker):
    """Fetch analyst targets and recommendation history for a ticker."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        out = {
            'low':     info.get('targetLowPrice'),
            'mean':    info.get('targetMeanPrice'),
            'median':  info.get('targetMedianPrice'),
            'high':    info.get('targetHighPrice'),
            'count':   info.get('numberOfAnalystOpinions'),
            'rec_key': info.get('recommendationKey', ''),
            'rec_mean': info.get('recommendationMean'),
            'price':   info.get('currentPrice', info.get('regularMarketPrice')),
            'recs':    None,
        }
        try:
            recs = stock.recommendations_summary
            if recs is not None and not recs.empty:
                out['recs'] = recs
        except Exception:
            pass
        return out, None
    except Exception as e:
        return None, f"Analyst data error: {str(e)}"


def render_analyst_view(ticker):
    """Render analyst price target gauge + recommendation trend charts."""
    import streamlit as st
    import plotly.graph_objects as go

    view, err = fetch_analyst_view(ticker)
    if err or view is None:
        return
    if view['mean'] is None and view['recs'] is None:
        return  # no analyst coverage

    st.markdown("##### Analyst View")
    _c1, _c2 = st.columns([3, 2])

    # ── Price target range gauge
    if view['mean'] is not None and view['low'] is not None and view['high'] is not None:
        price = view['price']
        fig_t = go.Figure()
        # range bar
        fig_t.add_trace(go.Scatter(
            x=[view['low'], view['high']], y=[0, 0], mode='lines',
            line=dict(color='#3a4160', width=10), hoverinfo='skip',
            showlegend=False))
        # markers
        _marks = [
            (view['low'],    'Low',     '#ef5350', 'triangle-down'),
            (view['median'], 'Median',  '#4dd0e1', 'circle'),
            (view['mean'],   'Mean',    '#4a9eff', 'diamond'),
            (view['high'],   'High',    '#26a69a', 'triangle-up'),
        ]
        for val, label, color, sym in _marks:
            if val is not None:
                fig_t.add_trace(go.Scatter(
                    x=[val], y=[0], mode='markers+text',
                    marker=dict(color=color, size=13, symbol=sym),
                    text=[f"{label}<br>${val:,.2f}"], textposition='top center',
                    textfont=dict(size=10, color=color), name=label,
                    showlegend=False))
        if price is not None:
            fig_t.add_trace(go.Scatter(
                x=[price], y=[0], mode='markers+text',
                marker=dict(color='#ffeb3b', size=16, symbol='star'),
                text=[f"Price<br>${price:,.2f}"], textposition='bottom center',
                textfont=dict(size=11, color='#ffeb3b'), name='Current',
                showlegend=False))
        _up = (view['mean'] / price - 1) * 100 if price else None
        _title = f"Price Targets — {view['count'] or '?'} analysts"
        if _up is not None:
            _title += f"  ·  {'+' if _up >= 0 else ''}{_up:.1f}% to mean"
        fig_t.update_layout(
            title=dict(text=_title, font=dict(size=13)),
            height=180, margin=dict(l=10, r=10, t=40, b=10),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#ccc'),
            xaxis=dict(gridcolor='#2d3250', tickprefix='$'),
            yaxis=dict(visible=False, range=[-1, 1]),
        )
        _c1.plotly_chart(fig_t, width="stretch", key=f'fa_targets_{ticker}')

    # ── Recommendation trend (stacked bars by month)
    recs = view['recs']
    if recs is not None:
        _rec_colors = {
            'strongBuy':  '#1b8a5a', 'buy':  '#26a69a', 'hold': '#ffca28',
            'sell': '#ef5350', 'strongSell': '#b71c1c',
        }
        _rec_labels = {
            'strongBuy': 'Strong Buy', 'buy': 'Buy', 'hold': 'Hold',
            'sell': 'Sell', 'strongSell': 'Strong Sell',
        }
        recs_plot = recs.iloc[::-1]  # oldest first left-to-right
        periods = recs_plot['period'].astype(str).tolist()
        fig_r = go.Figure()
        for col, color in _rec_colors.items():
            if col in recs_plot.columns:
                fig_r.add_trace(go.Bar(
                    x=periods, y=recs_plot[col], name=_rec_labels[col],
                    marker_color=color))
        _rk = (view['rec_key'] or '').replace('_', ' ').title()
        _rm = f" ({view['rec_mean']:.2f})" if view['rec_mean'] else ''
        fig_r.update_layout(
            barmode='stack',
            title=dict(text=f"Recommendations — consensus: {_rk}{_rm}",
                       font=dict(size=13)),
            height=180, margin=dict(l=10, r=10, t=40, b=10),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#ccc'),
            xaxis=dict(gridcolor='#2d3250'),
            yaxis=dict(gridcolor='#2d3250', title='Analysts'),
            legend=dict(orientation='h', y=-0.25, font=dict(size=9)),
        )
        _c2.plotly_chart(fig_r, width="stretch", key=f'fa_recs_{ticker}')


# ══════════════════════════════════════════════════════════════════════════
# VALUE COMPARISON — small group of tickers, one LLM call picks the winner
# ══════════════════════════════════════════════════════════════════════════

COMPARISON_SYSTEM_PROMPT = """You are a fundamental analyst who thinks through the lens of Michael Burry and Warren Buffett. You are comparing a SMALL group of candidate stocks to decide which is the best value selection. They may be similar setups (e.g. several miners) where the balance sheet and shareholder treatment are the deciders.

Each metric line includes a [guide: ...] bracket showing the value-investor benchmark, with ✅ good / ➖ middling / ❌ poor already marked.

Your response MUST use exactly these section headers, in this order:

**METRIC READ** — For each ticker, the standout strengths and weaknesses. Reference actual numbers and the guide verdicts.
**BALANCE SHEET** — Leverage, liquidity, cash vs debt, FCF durability. Who is strongest, who is riskiest?
**QUALITY VS PRICE** — Margins and returns on capital vs the multiple you pay. Who gives the most quality per dollar?
**VERDICT** — Rank ALL tickers from most to least attractive for a value investor. Name the single best pick and state the deciding factors in 2-3 sentences. If none are attractive at current prices, say so.

Be direct and specific. Use actual numbers. No generic disclaimers. 350-500 words."""


def get_fa_comparison(financials_map, llm_url='http://localhost:11434',
                      llm_provider='ollama', model='llama3.1:8b', max_tokens=1500,
                      api_key=None, system_prompt=None):
    """
    Compare a small group of tickers (2-6) in one LLM call.
    financials_map: {ticker: financials_dict}
    """
    sections = []
    for tkr, fin in financials_map.items():
        name = fin.get('name', tkr)
        data = '\n'.join(_data_line(k, v) for k, v in fin.items())
        sections.append(f"=== {tkr} ({name}) ===\n{data}")

    tickers = ', '.join(financials_map.keys())
    user_prompt = (
        "CANDIDATE FINANCIAL DATA:\n\n" + '\n\n'.join(sections) +
        f"\n\nTASK: Compare {tickers} head-to-head as value candidates, "
        f"following the required section structure. Rank them and pick the "
        f"single best value selection, weighting balance sheet strength "
        f"heavily as the decider between otherwise similar setups."
    )

    return _call_llm(system_prompt or COMPARISON_SYSTEM_PROMPT, user_prompt, llm_url,
                     llm_provider, model, max_tokens=max_tokens, api_key=api_key)


def render_fa_comparison(tickers, settings, system_prompt=None):
    """Render the value comparison widget in Streamlit for a list of tickers."""
    import streamlit as st
    import pandas as pd

    provider, llm_url, model, api_key = _resolve_llm(settings)

    # ── Fetch fundamentals for each ticker
    financials_map = {}
    fetch_errors = []
    progress = st.progress(0.0, text="Fetching fundamentals...")
    for i, tkr in enumerate(tickers):
        progress.progress((i + 1) / len(tickers), text=f"Fetching {tkr}...")
        fin, err = fetch_basic_financials(tkr)
        if err:
            fetch_errors.append(err)
        else:
            financials_map[tkr] = fin
    progress.empty()

    for err in fetch_errors:
        st.warning(err)
    if len(financials_map) < 2:
        st.error("Need at least 2 tickers with data to compare.")
        return None

    # ── Side-by-side table: metrics as rows, one column per ticker
    all_keys = list(next(iter(financials_map.values())).keys())
    rows = []
    for key in all_keys:
        if key == 'name':
            continue
        row = {'Metric': key}
        for tkr, fin in financials_map.items():
            val = fin.get(key, 'N/A')
            _, verdict = _guide_verdict(key, val)
            row[tkr] = f"{val} {verdict}".strip()
        guide = METRIC_GUIDES.get(key)
        row['Guide'] = guide[0] if guide else ''
        rows.append(row)

    st.markdown("##### Side-by-Side Metrics")
    st.caption(" · ".join(f"**{t}** {f.get('name', '')}" for t, f in financials_map.items()))
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 height=min(38 * len(rows) + 40, 600))

    # ── One LLM call to pick the winner
    with st.spinner(f"Comparing {len(financials_map)} candidates (Burry/Buffett lens)..."):
        text, error = get_fa_comparison(
            financials_map,
            llm_url=llm_url,
            llm_provider=provider,
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
        )

    if error:
        st.error(error)
        return None

    if text:
        html_text = text.replace('\n', '<br>')
        st.markdown(f"""
            <div style="border-left:3px solid #4a9eff;padding:12px 16px;
                        border-radius:0 8px 8px 0;margin:8px 0;
                        background:rgba(74,158,255,0.05)">
                <div style="color:#4a9eff;font-size:10px;font-weight:bold;
                            letter-spacing:1px;margin-bottom:8px">VALUE COMPARISON — BURRY/BUFFETT LENS</div>
                <div style="font-size:13px;line-height:1.7;white-space:pre-wrap">{html_text}</div>
            </div>
        """, unsafe_allow_html=True)
        return text

    return None
