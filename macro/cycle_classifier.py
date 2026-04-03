def classify_us_business_cycle(data):

    # Get 63d trend for each ratio — positive = outperforming
    xle_spx  = data.get('cyc_xle_spx_chg_63d', 0)
    xlk_spx  = data.get('cyc_xlk_spx_chg_63d', 0)
    xlf_xlu  = data.get('cyc_xlf_xlu_chg_63d', 0)
    xly_xlp  = data.get('cyc_xly_xlp_chg_63d', 0)
    xli_spx  = data.get('cyc_xli_spx_chg_63d', 0)
    xlb_spx  = data.get('cyc_xlb_spx_chg_63d', 0)
    xlp_spx  = data.get('cyc_xlp_spx_chg_63d', 0)
    xlu_spx  = data.get('cyc_xlu_spx_chg_63d', 0)
    xlv_spx  = data.get('cyc_xlv_spx_chg_63d', 0)
    iwm_spx  = data.get('cyc_iwm_spx_chg_63d', 0)
    xlf_spx  = data.get('cyc_xlf_spx_chg_63d', 0)

    # also use 20d for momentum confirmation
    xle_spx_20  = data.get('cyc_xle_spx_chg_20d', 0)
    xly_xlp_20  = data.get('cyc_xly_xlp_chg_20d', 0)
    xlk_spx_20  = data.get('cyc_xlk_spx_chg_20d', 0)
    xlp_spx_20  = data.get('cyc_xlp_spx_chg_20d', 0)
    xlu_spx_20  = data.get('cyc_xlu_spx_chg_20d', 0)

    # Signal flags
    energy_lead      = xle_spx > 10
    tech_lead        = xlk_spx > 5
    fin_lead         = xlf_xlu > 5 and xlf_spx > 0
    disc_lead        = xly_xlp > 5
    industrial_lead  = xli_spx > 5
    material_lead    = xlb_spx > 5
    defensive_bid    = (xlp_spx > 3 or xlu_spx > 3) and xly_xlp < 0
    healthcare_lead  = xlv_spx > 5
    small_cap_lead   = iwm_spx > 5

    # Score each phase
    scores = {
        'EARLY EXPANSION'    : 0,
        'MID EXPANSION'      : 0,
        'LATE EXPANSION'     : 0,
        'LATE CYCLE'         : 0,
        'EARLY CONTRACTION'  : 0,
        'RECESSION'          : 0,
        'EARLY RECOVERY'     : 0,
    }

    # Early Expansion signals
    if disc_lead:           scores['EARLY EXPANSION']   += 2
    if fin_lead:            scores['EARLY EXPANSION']   += 2
    if small_cap_lead:      scores['EARLY EXPANSION']   += 1
    if tech_lead:           scores['EARLY EXPANSION']   += 1

    # Mid Expansion signals
    if tech_lead:           scores['MID EXPANSION']     += 2
    if industrial_lead:     scores['MID EXPANSION']     += 2
    if material_lead:       scores['MID EXPANSION']     += 1
    if fin_lead:            scores['MID EXPANSION']     += 1

    # Late Expansion signals
    if energy_lead:         scores['LATE EXPANSION']    += 2
    if material_lead:       scores['LATE EXPANSION']    += 1
    if not tech_lead:       scores['LATE EXPANSION']    += 1

    # Late Cycle signals
    if energy_lead:         scores['LATE CYCLE']        += 2
    if defensive_bid:       scores['LATE CYCLE']        += 2
    if not disc_lead:       scores['LATE CYCLE']        += 1
    if not fin_lead:        scores['LATE CYCLE']        += 1

    # Early Contraction signals
    if defensive_bid:       scores['EARLY CONTRACTION'] += 2
    if not energy_lead:     scores['EARLY CONTRACTION'] += 1
    if healthcare_lead:     scores['EARLY CONTRACTION'] += 1
    if xly_xlp < -5:        scores['EARLY CONTRACTION'] += 2

    # Recession signals
    if healthcare_lead:     scores['RECESSION']         += 2
    if xlu_spx > 5:         scores['RECESSION']         += 2
    if xlp_spx > 5:         scores['RECESSION']         += 2
    if not energy_lead:     scores['RECESSION']         += 1

    # Early Recovery signals
    if fin_lead and not energy_lead:  scores['EARLY RECOVERY'] += 2
    if disc_lead and not tech_lead:   scores['EARLY RECOVERY'] += 1
    if small_cap_lead:                scores['EARLY RECOVERY'] += 1

    phase   = max(scores, key=scores.get)
    score   = scores[phase]

    # Build signal list
    signals = []
    if energy_lead:     signals.append(f'XLE/SPX +{xle_spx:.1f}% 63d — Energy leading')
    if tech_lead:       signals.append(f'XLK/SPX +{xlk_spx:.1f}% 63d — Tech leading')
    if fin_lead:        signals.append(f'XLF/XLU +{xlf_xlu:.1f}% 63d — Financials vs Utilities rising')
    if disc_lead:       signals.append(f'XLY/XLP +{xly_xlp:.1f}% 63d — Discretionary leading Staples')
    if industrial_lead: signals.append(f'XLI/SPX +{xli_spx:.1f}% 63d — Industrials leading')
    if material_lead:   signals.append(f'XLB/SPX +{xlb_spx:.1f}% 63d — Materials leading')
    if defensive_bid:   signals.append(f'XLY/XLP {xly_xlp:.1f}% 63d — Defensives outperforming')
    if healthcare_lead: signals.append(f'XLV/SPX +{xlv_spx:.1f}% 63d — Healthcare leading')
    if small_cap_lead:  signals.append(f'IWM/SPX +{iwm_spx:.1f}% 63d — Small caps leading')

    # Alerts
    alerts = []
    if xly_xlp < -10:
        alerts.append(f'⚠ XLY/XLP {xly_xlp:.1f}% — severe defensive rotation')
    if xlf_xlu < -10:
        alerts.append(f'⚠ XLF/XLU {xlf_xlu:.1f}% — financials collapsing vs utilities')
    if xle_spx > 30:
        alerts.append(f'→ XLE/SPX +{xle_spx:.1f}% — energy dominance, late cycle peak risk')

    return phase, score, signals, alerts