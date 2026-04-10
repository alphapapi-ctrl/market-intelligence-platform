from datetime import datetime
from macro_data import collect_macro_data, fmt, fmt_chg, save_snapshot, load_snapshot, get_change_alerts
from cycle_tracker import cycles, get_current_phase, YEAR
from cycle_classifier import classify_us_business_cycle

TODAY = datetime.today()

# ── VIX Regime ────────────────────────────────────────────────────────────────
def get_vix_regime(vix, vvix, vix_vvix):
    if vix is None or vvix is None or vix_vvix is None:
        return 'UNKNOWN', 'Volatility data unavailable', []

    regime  = ''
    context = ''
    alerts  = []

    if vix < 15 and vix_vvix < 0.17:
        regime  = 'COMPLACENCY WARNING'
        context = 'Market priced for perfection — smart money hedging while surface calm'
        alerts.append('⚠ VIX/VVIX below 0.17 with VIX under 15 — vol spike likely incoming')
        alerts.append('⚠ Reduce risk exposure, tighten stops')

    elif vix < 20 and vix_vvix >= 0.18:
        regime  = 'RISK ON'
        context = 'Low fear confirmed — volatility structure healthy'

    elif vix < 20 and 0.17 <= vix_vvix < 0.18:
        regime  = 'RISK ON — MONITOR'
        context = 'Low fear but VIX/VVIX approaching warning threshold'
        alerts.append('→ Watch VIX/VVIX — approaching 0.17 complacency level')

    elif 20 <= vix <= 25:
        regime  = 'CAUTIOUS'
        context = 'Elevated volatility — selective positioning'

    elif vix > 25 and vix_vvix > 0.25:
        regime  = 'PANIC — POTENTIAL OPPORTUNITY'
        context = 'VIX and VIX/VVIX both spiking — possible capitulation event'
        alerts.append('→ Monitor for exhaustion signal — potential entry opportunity')
        alerts.append('→ Check breadth for washout confirmation')

    elif vix > 25:
        regime  = 'RISK OFF'
        context = 'Elevated fear — focus on defensives and hard assets'

    return regime, context, alerts

# ── Instrument Focus ──────────────────────────────────────────────────────────
def get_focus_instruments(vix_regime):

    asx_risk_on = [
        'XMJ — Materials',
        'XDJ — Consumer Disc',
        'XFJ — Financials',
        'XRE — Real Estate',
        'XEJ — Energy',
        'XIJ — IT',
    ]
    asx_cautious = [
        'XJO — ASX200',
        'XSO — Small Ords',
        'XEJ — Energy',
        'XIJ — IT',
        'XNJ — Industrials',
        'XTJ — Telecom',
    ]
    asx_risk_off = [
        'XHJ — Healthcare',
        'XSJ — Consumer Staples',
        'XUJ — Utilities',
        'AU10Y — Bonds',
        'AUDUSD — Currency',
    ]

    us_risk_on = [
        'SMH — Semiconductors',
        'XLK — Technology',
        'XLY — Consumer Disc',
        'XRT — Retail',
        'IBB — Biotech',
        'KRE — Regional Banks',
        'XLF — Financials',
        'XLI — Industrials',
    ]
    us_cautious = [
        'SPX — S&P500',
        'NDX — Nasdaq100',
        'IWM — Russell2000',
        'DJI — Dow Jones',
    ]
    us_risk_off = [
        'XLP — Consumer Staples',
        'XLU — Utilities',
        'XLV — Healthcare',
        'XLE — Energy',
    ]

    ratios_risk_on = [
        'NDX/SPX — Tech leadership',
        'SMH/NDX — Semi vs Nasdaq',
        'IWM/SPX — Small cap risk appetite',
        'XDJ/XSJ — ASX cyclical vs defensive',
        'XJO/SPY — ASX vs US',
    ]
    ratios_cautious = [
        'IWM/NDX — Small vs large cap',
        'XLF/NDX — Finance vs tech',
        'XDJ/XJO — ASX disc vs market',
        'XEJ/XJO — ASX energy vs market',
    ]
    ratios_risk_off = [
        'Gold/DJI — Hard asset vs equity',
        'Silver/Gold — Industrial demand signal',
        'XLP/SPX — Defensive rotation',
        'XLU/SPX — Utility rotation',
        'DXY — Dollar strength',
        'XLE/XLK — Energy vs tech rotation',
    ]

    metals_risk_off = [
        'Gold (GC=F)',
        'Silver (SI=F)',
        'Copper (HG=F)',
        'DXY — US Dollar Index',
        'AUDUSD — Risk currency proxy',
        'Gold/SPX ratio',
        'Gold/Copper ratio',
    ]

    if 'RISK ON' in vix_regime:
        return {
            'ASX'    : asx_risk_on,
            'US'     : us_risk_on,
            'Ratios' : ratios_risk_on,
            'Metals' : [],
        }
    elif 'CAUTIOUS' in vix_regime:
        return {
            'ASX'    : asx_cautious,
            'US'     : us_cautious,
            'Ratios' : ratios_cautious,
            'Metals' : [],
        }
    elif 'RISK OFF' in vix_regime or 'PANIC' in vix_regime:
        return {
            'ASX'    : asx_risk_off,
            'US'     : us_risk_off,
            'Ratios' : ratios_risk_off,
            'Metals' : metals_risk_off,
        }
    elif 'COMPLACENCY' in vix_regime:
        return {
            'ASX'    : asx_risk_off,
            'US'     : us_risk_off,
            'Ratios' : ratios_risk_off,
            'Metals' : metals_risk_off,
        }
    else:
        return {
            'ASX'    : asx_cautious,
            'US'     : us_cautious,
            'Ratios' : ratios_cautious,
            'Metals' : [],
        }

# ── Live Data Summary ─────────────────────────────────────────────────────────
def format_live_data(data):
    lines = []
    lines.append("─"*70)
    lines.append("  RATES & BONDS")
    lines.append("─"*70)
    lines.append(f"  US10Y:        {fmt(data.get('us10y'))}%   US2Y: {fmt(data.get('us02y'))}%   US3M: {fmt(data.get('us03m'))}%")
    lines.append(f"  Yield Curve:  {fmt(data.get('yield_curve'))}% (10Y-2Y)   Fed Funds: {fmt(data.get('fed_funds'))}%")
    lines.append(f"  AU10Y:        {fmt(data.get('au10y'))}%")

    yc = data.get('yield_curve')
    if yc is not None:
        if yc < 0:
            lines.append("  ⚠ Yield curve INVERTED — recession historically follows 6-18 months")
        elif yc < 0.25:
            lines.append("  → Yield curve flat — watch for re-inversion")
        else:
            lines.append("  ✓ Yield curve positive — un-inverted")

    # Yield curve velocity
    yc_roc_5d  = data.get('yc_roc_5d')
    yc_roc_21d = data.get('yc_roc_21d')
    if yc_roc_5d is not None:
        if yc_roc_5d > 0.1:
            yc_vel = '✓ STEEPENING — risk appetite improving'
        elif yc_roc_5d < -0.1:
            yc_vel = '⚠ FLATTENING — risk appetite deteriorating'
        else:
            yc_vel = '→ STABLE'
        lines.append(f"  Yield Curve Velocity:  {yc_roc_5d:+.3f}% 5d  {yc_roc_21d:+.3f}% 21d  {yc_vel}")

    lines.append("")
    lines.append("─"*70)
    lines.append("  FED & LIQUIDITY")
    lines.append("─"*70)
    bs = data.get('fed_bs')
    bs_str = f"${round(bs/1e6, 2)}T" if bs else 'n/a'
    lines.append(f"  Fed Balance Sheet: {bs_str}   Fed Funds: {fmt(data.get('fed_funds'))}%")
    lines.append(f"  HY Spread: {fmt(data.get('hy_spread'))}%   IG Spread: {fmt(data.get('ig_spread'))}%")

    us10y_trend = data.get('us10y_trend')
    us10y_chg   = data.get('us10y_chg_3m')
    us02y_trend = data.get('us02y_trend')
    us02y_chg   = data.get('us02y_chg_3m')
    if us10y_trend:
        lines.append(f"  US10Y 3M trend: {us10y_trend} ({'+' if us10y_chg > 0 else ''}{us10y_chg}% over 3 months)")
    if us02y_trend:
        lines.append(f"  US2Y  3M trend: {us02y_trend} ({'+' if us02y_chg > 0 else ''}{us02y_chg}% over 3 months)")

    hy = data.get('hy_spread')
    if hy is not None:
        if hy > 6:
            lines.append("  ⚠ HY spreads ELEVATED — credit stress signal")
        elif hy > 4:
            lines.append("  → HY spreads widening — monitor credit conditions")
        else:
            lines.append("  ✓ HY spreads contained — credit conditions healthy")

    lines.append("")
    lines.append("─"*70)
    lines.append("  COMMODITIES")
    lines.append("─"*70)
    lines.append(f"  Gold:    ${fmt(data.get('gold'))}  {fmt_chg(data.get('gold_chg_5d'))} 5d")
    lines.append(f"  Silver:  ${fmt(data.get('silver'))}")
    lines.append(f"  Copper:  ${fmt(data.get('copper'))}  {fmt_chg(data.get('copper_chg_5d'))} 5d")
    lines.append(f"  Oil:     ${fmt(data.get('oil'))}  {fmt_chg(data.get('oil_chg_5d'))} 5d")
    lines.append(f"  Gold/SPX ratio:    {fmt(data.get('gold_spx_ratio'), decimals=4)}")
    lines.append(f"  Gold/Copper ratio: {fmt(data.get('gold_copper_ratio'), decimals=1)}")

    # Copper/Gold ratio ROC
    cu_gold = data.get('cu_gold_ratio')
    cu_5d   = data.get('cu_gold_chg_5d')
    cu_21d  = data.get('cu_gold_chg_21d')
    cu_63d  = data.get('cu_gold_chg_63d')
    if cu_gold is not None:
        if cu_63d is not None:
            if cu_63d > 5:
                cu_status = '✓ RISING — industrial demand expanding, growth signal'
            elif cu_63d < -5:
                cu_status = '⚠ FALLING — industrial demand contracting, recession signal'
            else:
                cu_status = '→ FLAT — neutral growth signal'
        else:
            cu_status = ''
        lines.append(f"  Cu/Gold ratio:     {fmt(cu_gold, decimals=6)}  {fmt_chg(cu_5d)} 5d  {fmt_chg(cu_63d)} 63d  {cu_status}")

    copper_chg = data.get('copper_chg_5d')
    if copper_chg is not None:
        if copper_chg < -5:
            lines.append("  ⚠ Dr Copper down >5% — industrial demand warning")
        elif copper_chg > 3:
            lines.append("  ✓ Dr Copper rising — industrial expansion signal")

    lines.append("")
    lines.append("─"*70)
    lines.append("  EQUITIES & RISK")
    lines.append("─"*70)
    lines.append(f"  SPX:  {fmt(data.get('spx'))}  {fmt_chg(data.get('spx_chg_5d'))} 5d")
    lines.append(f"  NDX:  {fmt(data.get('ndx'))}  {fmt_chg(data.get('ndx_chg_5d'))} 5d")
    lines.append(f"  IWM:  {fmt(data.get('iwm'))}")
    lines.append(f"  DXY:  {fmt(data.get('dxy'))}")

    dxy = data.get('dxy')
    if dxy is not None:
        if dxy > 105:
            lines.append("  ⚠ DXY elevated — headwind for commodities and EM assets")
        elif dxy < 95:
            lines.append("  ✓ DXY weak — tailwind for commodities and gold")

    return lines

# ── Build full report ─────────────────────────────────────────────────────────
def build_report(data):
    vix        = data.get('vix')
    vvix       = data.get('vvix')
    vix_vvix   = data.get('vix_vvix')
    regime, context, vol_alerts = get_vix_regime(vix, vvix, vix_vvix)
    instruments = get_focus_instruments(regime)

    lines = []
    lines.append("═"*70)
    lines.append(f"  DAILY MACRO SNAPSHOT — {TODAY.strftime('%d %b %Y')}")
    lines.append("═"*70)

    # Volatility regime
    lines.append("")
    lines.append(f"  VIX: {fmt(vix)}   VVIX: {fmt(vvix)}   VIX/VVIX: {fmt(vix_vvix, decimals=4)}")
    lines.append(f"  REGIME: {regime}")
    lines.append(f"  {context}")

    if vol_alerts:
        lines.append("")
        for a in vol_alerts:
            lines.append(f"  {a}")

    # Change alerts
    prev_data     = load_snapshot()
    change_alerts = get_change_alerts(data, prev_data)

    if change_alerts:
        lines.append("")
        lines.append("─"*70)
        lines.append("  CHANGE ALERTS — since last run")
        lines.append("─"*70)
        for a in change_alerts:
            lines.append(a)

    # Focus instruments
    lines.append("")
    lines.append("─"*70)
    lines.append("  TODAY'S FOCUS INSTRUMENTS")
    lines.append("─"*70)

    for market, items in instruments.items():
        if items:
            lines.append(f"  {market}:")
            for item in items:
                lines.append(f"    • {item}")

    # Economic regime indicators
    lines.append("")
    lines.append("─"*70)
    lines.append("  ECONOMIC REGIME INDICATORS")
    lines.append("─"*70)

    unemp = data.get('unemployment')
    nfp   = data.get('nfp')
    pmi   = data.get('pmi_manual')

    if unemp is not None:
        if unemp > 5.0:
            unemp_status = '⚠ ELEVATED — recession confirmed'
        elif unemp > 4.5:
            unemp_status = '→ RISING — watch for acceleration'
        elif unemp > 4.0:
            unemp_status = '→ TICKING UP — late cycle signal'
        else:
            unemp_status = '✓ LOW — labour market healthy'
        lines.append(f"  Unemployment:  {fmt(unemp)}%  {unemp_status}")

    if pmi is not None:
        if pmi < 45:
            pmi_status = '⚠ CONTRACTION — significant slowdown'
        elif pmi < 50:
            pmi_status = '→ CONTRACTION — sub 50, slowing'
        elif pmi < 55:
            pmi_status = '✓ EXPANSION — moderate growth'
        else:
            pmi_status = '✓ STRONG EXPANSION'
        lines.append(f"  PMI Mfg:       {fmt(pmi)}  {pmi_status}")

    if nfp is not None:
        lines.append(f"  Non-Farm Pay:  {int(nfp):,} (000s)")

    sentiment = data.get('consumer_sentiment')
    if sentiment is not None:
        if sentiment < 60:
            sent_status = '⚠ VERY LOW — recession level pessimism'
        elif sentiment < 75:
            sent_status = '→ WEAK — below historical average'
        elif sentiment < 90:
            sent_status = '✓ MODERATE'
        else:
            sent_status = '✓ STRONG — risk on environment'
        lines.append(f"  Consumer Sent:  {fmt(sentiment)}  {sent_status}")

    # Consumer cycle ratios
    lines.append("")
    lines.append("─"*70)
    lines.append("  CONSUMER CYCLE INDICATORS")
    lines.append("─"*70)

    xly_xlp = data.get('xly_xlp')
    if xly_xlp is not None:
        chg_5d  = data.get('xly_xlp_chg_5d')
        chg_63d = data.get('xly_xlp_chg_63d')
        if chg_63d is not None:
            if chg_63d < -5:
                cons_status = '⚠ RISK OFF — defensives outperforming 3 months'
            elif chg_63d < 0:
                cons_status = '→ WEAKENING — disc losing ground to staples'
            else:
                cons_status = '✓ RISK ON — discretionary leading'
        else:
            cons_status = ''
        lines.append(f"  XLY/XLP ratio:     {fmt(xly_xlp, decimals=4)}  {fmt_chg(chg_5d)} 5d  {fmt_chg(chg_63d)} 63d  {cons_status}")

    rspd_rsps = data.get('rspd_rsps')
    if rspd_rsps is not None:
        chg_5d  = data.get('rspd_rsps_chg_5d')
        chg_63d = data.get('rspd_rsps_chg_63d')
        if chg_63d is not None:
            if chg_63d < -5:
                eq_status = '⚠ RISK OFF — equal weight confirms defensive rotation'
            elif chg_63d < 0:
                eq_status = '→ WEAKENING — equal weight disc fading'
            else:
                eq_status = '✓ RISK ON — equal weight disc leading'
        else:
            eq_status = ''
        lines.append(f"  RSPD/RSPS ratio:   {fmt(rspd_rsps, decimals=4)}  {fmt_chg(chg_5d)} 5d  {fmt_chg(chg_63d)} 63d  {eq_status}")

    risk_ratio = data.get('risk_ratio')
    if risk_ratio is not None:
        chg_5d  = data.get('risk_ratio_chg_5d')
        chg_10d = data.get('risk_ratio_chg_10d')
        if chg_10d is not None:
            if chg_10d < -3:
                risk_status = '⚠ RISK OFF — defensives accelerating'
            elif chg_10d < 0:
                risk_status = '→ WEAKENING — defensive rotation building'
            elif chg_10d > 3:
                risk_status = '✓ RISK ON — growth sectors accelerating'
            else:
                risk_status = '→ NEUTRAL — no clear rotation'
        else:
            risk_status = ''
        lines.append(f"  Sector Groups Risk On/Off ratio: {fmt(risk_ratio, decimals=4)}  {fmt_chg(chg_5d)} 5d  {fmt_chg(chg_10d)} 10d  {risk_status}")

    # A/D Line divergence
    ad_div = data.get('ad_divergence')
    ad_trend = data.get('ad_trend')
    if ad_div:
        flag = '⚠' if 'BEARISH' in ad_div else '✓' if 'BULLISH' in ad_div else '→'
        lines.append(f"  A/D Line:          {flag} {ad_div}")

    # Valuation & leverage
    lines.append("")
    lines.append("─"*70)
    lines.append("  VALUATION & LEVERAGE")
    lines.append("─"*70)

    spx_m2 = data.get('spx_m2')
    if spx_m2 is not None:
        if spx_m2 > 0.25:
            val_status = '⚠ EXTREME — dot-com bubble levels'
        elif spx_m2 > 0.20:
            val_status = '→ ELEVATED — above historical average'
        else:
            val_status = '✓ MODERATE'
        lines.append(f"  SPX/M2 ratio:      {fmt(spx_m2, decimals=4)}  {val_status}")

    margin_m2 = data.get('margin_m2')
    if margin_m2 is not None:
        if margin_m2 > 1.5:
            lev_status = '⚠ EXTREME — forced deleveraging risk'
        elif margin_m2 > 1.0:
            lev_status = '→ ELEVATED — leverage building'
        else:
            lev_status = '✓ CONTAINED'
        lines.append(f"  Margin/M2 ratio:   {fmt(margin_m2, decimals=4)}  {lev_status}")

        margin_1m = data.get('margin_chg_1m')
        margin_3m = data.get('margin_chg_3m')
        from_peak = data.get('margin_from_peak')

        if margin_1m is not None and margin_3m is not None:
            if margin_1m < 0 and margin_3m < 0:
                lines.append(f"  ⚠ MARGIN DECLINING — {fmt_chg(margin_1m)} 1m  {fmt_chg(margin_3m)} 3m — deleveraging signal")
            elif margin_1m < 0:
                lines.append(f"  → Margin dipping 1m {fmt_chg(margin_1m)} — watch for confirmation")
            else:
                lines.append(f"  ✓ Margin stable/rising — {fmt_chg(margin_1m)} 1m  {fmt_chg(margin_3m)} 3m")

        if from_peak is not None:
            if from_peak == 0.0 or abs(from_peak) < 0.5:
                lines.append(f"  ⚠ Margin AT or NEAR ALL TIME HIGH — peak deleveraging risk")
            elif from_peak < -10:
                lines.append(f"  ⚠ Margin {fmt(from_peak)}% from peak — significant deleveraging underway")
            elif from_peak < -5:
                lines.append(f"  → Margin {fmt(from_peak)}% from peak — watch closely")
            else:
                lines.append(f"  Margin {fmt(from_peak)}% from peak")

    # Margin debt acceleration
    margin_accel = data.get('margin_acceleration')
    if margin_accel is not None:
        if margin_accel > 0.5:
            ma_status = '⚠ ACCELERATING — leverage building fast'
        elif margin_accel < -0.5:
            ma_status = '✓ DECELERATING — deleveraging in progress'
        else:
            ma_status = '→ STABLE'
        lines.append(f"  Margin Debt Accel:     {margin_accel:+.3f}%  {ma_status}")

    buffett = data.get('buffett')
    if buffett is not None:
        if buffett > 200:
            buf_status = '⚠ EXTREME — significantly above historical average of 100%'
        elif buffett > 150:
            buf_status = '→ ELEVATED — above fair value zone'
        elif buffett > 100:
            buf_status = '→ MODERATELY ELEVATED'
        else:
            buf_status = '✓ FAIR VALUE'
        lines.append(f"  Buffett Indicator: {fmt(buffett)}%  {buf_status}")

    cape = data.get('cape_manual')
    if cape is not None:
        if cape > 35:
            cape_status = '⚠ EXTREME — dot-com bubble territory'
        elif cape > 25:
            cape_status = '→ ELEVATED — above historical average of 16'
        else:
            cape_status = '✓ MODERATE'
        lines.append(f"  Shiller CAPE:      {fmt(cape)}  {cape_status}  (manual — update monthly)")

    # Cycle positions
    lines.append("")
    lines.append("═"*70)
    lines.append("  MACRO CYCLE POSITIONS")
    lines.append("═"*70)

    cycle_keys = ['land_cycle', 'rate_cycle', 'commodity_equity_cycle',
                  'presidential_cycle', 'business_cycle', 'fed_cycle']

    for key in cycle_keys:
        c = cycles[key]
        lines.append("")
        lines.append(f"  {'─'*66}")
        lines.append(f"  {c['name'].upper()}")
        lines.append(f"  {'─'*66}")

        if key in ['land_cycle', 'rate_cycle', 'commodity_equity_cycle', 'presidential_cycle']:
            phase, desc, years = get_current_phase(key)
            lines.append(f"  Phase:    {phase}")
            lines.append(f"  Context:  {desc}")
            lines.append(f"  Years in: {round(years, 1)}")

        if key == 'land_cycle':
            itb     = data.get('itb')
            itb_63  = data.get('itb_chg_63d')
            itb_126 = data.get('itb_chg_126d')
            if itb is not None:
                lines.append(f"  ITB Housing ETF:  ${fmt(itb)}  {fmt_chg(itb_63)} 63d  {fmt_chg(itb_126)} 126d")
                if itb_126 is not None:
                    if itb_126 < -20:
                        lines.append("  ⚠ ITB down >20% over 6 months — property price decline likely in 12-18 months")
                    elif itb_126 < -10:
                        lines.append("  → ITB down >10% over 6 months — housing stress building")
                    elif itb_126 > 10:
                        lines.append("  ✓ ITB rising — housing construction healthy")

        if key == 'commodity_equity_cycle':
            lines.append(f"  Supercycle: {c['supercycle_phase']}")
            lines.append("  Metals rotation:")
            for m in c['metals_rotation']:
                lines.append(f"    → {m}")

        if key == 'rate_cycle':
            lines.append(f"  US10Y now: {fmt(data.get('us10y'))}%")
            lines.append(f"  Key levels: Structural={c['key_levels']['structural_shift']}% | Mid={c['key_levels']['mid_cycle']}% | Peak={c['key_levels']['cycle_peak']}%")

        if key == 'presidential_cycle':
            hist_avg = {1: 9.88, 2: 8.47, 3: 17.64, 4: 10.19}
            hist_dd  = {1: -14.0, 2: -18.0, 3: -14.0, 4: -14.0}

            cyc_year   = data.get('pres_cycle_year', 1)
            cyc_ret    = data.get('pres_cycle_ret')
            cyc_dd     = data.get('pres_cycle_dd')
            cyc_dd_now = data.get('pres_cycle_dd_now')
            cyc_high   = data.get('pres_cycle_high')
            cyc_days   = data.get('pres_cycle_days')

            avg_ret = hist_avg.get(cyc_year, 9.88)
            avg_dd  = hist_dd.get(cyc_year, -14.0)

            lines.append(f"  Cycle start: Nov 2024 (Trump Term 2)  Day {cyc_days}")
            lines.append(f"  Current year of cycle: Year {cyc_year}")
            lines.append(f"  {'─'*52}")
            lines.append(f"  {'Metric':<30} {'Current':>10} {'Hist Avg':>10}")
            lines.append(f"  {'─'*52}")
            lines.append(f"  {'SPX return since Nov 2024':<30} {fmt(cyc_ret)}%{'':4} {fmt(avg_ret)}%")
            lines.append(f"  {'Max drawdown this cycle':<30} {fmt(cyc_dd)}%{'':4} {fmt(avg_dd)}%")
            lines.append(f"  {'Current DD from cycle high':<30} {fmt(cyc_dd_now)}%")
            lines.append(f"  {'Cycle high (SPX)':<30} {fmt(cyc_high)}")

            if cyc_ret is not None:
                vs_avg = cyc_ret - avg_ret
                if vs_avg > 5:
                    lines.append(f"  ✓ Running {fmt(vs_avg)}% ahead of historical average")
                elif vs_avg < -10:
                    lines.append(f"  ⚠ Running {fmt(abs(vs_avg))}% behind historical average")
                else:
                    lines.append(f"  → Tracking {fmt(vs_avg)}% vs historical average")

            if cyc_dd_now is not None and cyc_dd_now < -10:
                lines.append(f"  ⚠ Currently {fmt(cyc_dd_now)}% off cycle high — significant drawdown")
            elif cyc_dd_now is not None and cyc_dd_now < -5:
                lines.append(f"  → {fmt(cyc_dd_now)}% off cycle high — watch for support")

        if key == 'business_cycle':
            bc_phase, bc_score, bc_signals, bc_alerts = classify_us_business_cycle(data)
            lines.append(f"  Phase:    {bc_phase}  (signal score: {bc_score})")
            if bc_signals:
                lines.append("  Sector signals:")
                for s in bc_signals:
                    lines.append(f"    • {s}")
            if bc_alerts:
                lines.append("  Alerts:")
                for a in bc_alerts:
                    lines.append(f"    {a}")

        if key == 'fed_cycle':
            lines.append(f"  Phase:    {c['current']}")
            lines.append(f"  Fed Funds: {fmt(data.get('fed_funds'))}%")
            bs = data.get('fed_bs')
            bs_str = f"${round(bs/1e6, 2)}T" if bs else 'n/a'
            lines.append(f"  Balance sheet: {bs_str}")

        lines.append("  Watch for next phase:")
        for s in c['next_signals']:
            lines.append(f"    → {s}")

    # Live market data
    lines.append("")
    lines.append("═"*70)
    lines.append("  LIVE MARKET READINGS")
    lines.append("═"*70)
    lines.extend(format_live_data(data))

    lines.append("")
    lines.append("═"*70)
    return "\n".join(lines)

# ── Save report ───────────────────────────────────────────────────────────────
def save_report(output):
    import os
    os.makedirs('results', exist_ok=True)
    filename = f"results/{TODAY.strftime('%Y%m%d')}_macro_report.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"Report saved to {filename}")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    data   = collect_macro_data()
    report = build_report(data)
    print(report)
    save_report(report)
    save_snapshot(data)