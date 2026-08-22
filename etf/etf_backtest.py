"""
etf/etf_backtest.py
===================
Quarterly-rebalance backtest for the income ETF strategy.

At each quarter start, scores the universe using ONLY data available at that
date (same formulas as the live scorer via compute_metrics), selects the
top-N qualified ETFs, and equal-weights them. Distributions accumulate as
cash and are redeployed at the next rebalance. Benchmarked against SPY
total return.

Config (optional): etf/backtest_config.json
    {"top_n": 5, "years": 3, "start_capital": 100000, "freq_filter": "all"}

Usage:
    python etf/etf_backtest.py
"""

import os
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

from etf_income_data import (UNIVERSE, score_universe, compute_metrics,
                             resolve_underlying, underlying_rs_from_series)

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE, 'results', 'backtest')
CONFIG_FILE = os.path.join(BASE, 'backtest_config.json')

DEFAULTS = {'top_n': 5, 'years': 3, 'start_capital': 100000, 'freq_filter': 'all',
            'hedge_enabled': False, 'hedge_pct': 0.10,
            'income_mode': 'reinvest',      # 'reinvest' | 'draw'
            'draw_threshold_pct': 0.10,     # buffer above start capital before drawing
            'bench_ticker': 'JEPI',         # passive income benchmark — same rules, one fund
            'rebal_freq': 'quarterly',      # 'monthly' | 'quarterly' | 'semiannual'
            'stop_loss_pct': 0.0}           # total-return stop from entry, 0 = off
                                            # (price + divs received, NOT raw price — income
                                            #  funds mechanically bleed price via distributions)

REBAL_FREQ_MAP = {'monthly': 'MS', 'quarterly': 'QS', 'semiannual': '6MS'}

HEDGE_TICKER = 'VIXY'    # long VIX short-term futures ETF
HEDGE_ON_RATIO = 1.00    # VIX/VIX3M >= 1.0 — term structure inverted (backwardation)
HEDGE_OFF_RATIO = 0.95   # exit below this — hysteresis to avoid whipsaw


def load_config():
    cfg = DEFAULTS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


import etf_prices as _px


def fetch_history(tickers, years):
    """Unadjusted close + dividends per ticker from the marketdb store. One extra
    year for the 12m scoring lookback at the first rebalance."""
    _px.prefetch(list(tickers))
    data = {}
    for t in tickers:
        try:
            hist = _px.history(t, years + 1)
            if hist is None or hist.empty:
                continue
            data[t] = hist[['Close', 'Dividends']].dropna(subset=['Close'])
        except Exception as e:
            print(f"  {t}: fetch error — {e}")
    return data


def fetch_adj(tickers, years):
    """Adjusted close only — used for underlying RS so total-return comparison
    matches the live scorer."""
    _px.prefetch(list(tickers))
    data = {}
    for t in tickers:
        try:
            s = _px.adj_close(t, years + 1)
            if s is None or s.empty:
                continue
            data[t] = s.to_frame('Close')
        except Exception as e:
            print(f"  {t}: fetch error — {e}")
    return data


def compute_hedge_signal(vix_close, vix3m_close, on=HEDGE_ON_RATIO, off=HEDGE_OFF_RATIO):
    """Stateful VIX term-structure signal with hysteresis.

    ON when VIX/VIX3M rises to `on` (backwardation = stress),
    OFF when it falls back below `off`. Returns a bool Series by date.
    """
    vix_close = vix_close.copy()
    vix3m_close = vix3m_close.copy()
    vix_close.index = vix_close.index.normalize()
    vix3m_close.index = vix3m_close.index.normalize()
    ratio = (vix_close / vix3m_close.reindex(vix_close.index).ffill()).dropna()
    state = False
    out = {}
    for d, r in ratio.items():
        if not state and r >= on:
            state = True
        elif state and r <= off:
            state = False
        out[d] = state
    return pd.Series(out)


def score_at(date, history, freq_filter, und_history=None, spy=None):
    """Score the universe using the trailing 12m window ending at `date`.

    und_history: {underlying_label: close DataFrame} for point-in-time RS vs SPY.
    """
    metrics = {}
    win_start = date - pd.Timedelta(days=365)

    # point-in-time underlying RS per unique underlying label
    und_rs = {}
    if und_history and spy is not None:
        spy_win = spy['Close'][(spy.index > win_start) & (spy.index <= date)]
        for label, uh in und_history.items():
            uwin = uh['Close'][(uh.index > win_start) & (uh.index <= date)]
            und_rs[label] = underlying_rs_from_series(uwin, spy_win)

    for ticker, (name, underlying, freq) in UNIVERSE.items():
        if freq_filter != 'all' and freq != freq_filter:
            continue
        if ticker not in history:
            continue
        h = history[ticker]
        win = h[(h.index > win_start) & (h.index <= date)]
        if len(win) < 63:
            continue
        divs = win['Dividends'][win['Dividends'] > 0]
        m = compute_metrics(win['Close'], divs)
        if m is None:
            continue
        m['name'] = name
        m['freq'] = freq
        m['underlying_rs'] = und_rs.get(underlying)
        metrics[ticker] = m
    if not metrics:
        return pd.DataFrame()
    return score_universe(metrics)


def build_cash_rate(cal, years):
    """Daily interest factor for idle cash from the 13-week T-bill yield (^IRX).

    ^IRX quotes an annualised percent (e.g. 5.2). Returns a Series of daily
    accrual rates aligned to the trading calendar; 0 where unavailable.
    """
    irx = fetch_adj(['^IRX'], years).get('^IRX')
    if irx is None:
        return pd.Series(0.0, index=cal)
    rate = irx['Close'].reindex(cal, method='ffill')
    return (rate.clip(lower=0).fillna(0.0) / 100.0) / 252.0


def sim_passive(bench_hist, cal, rebal_dates, capital, income_mode, maintain_level,
                cash_rate=None):
    """Buy-and-hold one income fund under the SAME money-flow rules as the
    strategy: distributions pool as cash, redeployed at each quarterly
    rebalance; prop-style draws in draw mode. This is the honest benchmark —
    if the rotation machinery can't beat one lazy fund, the complexity
    isn't paying.
    """
    def _p(day):
        s = bench_hist['Close'][bench_hist.index <= day]
        return float(s.iloc[-1]) if len(s) else None

    sh, cash, wd, inc = 0.0, capital, 0.0, 0.0
    vals = []
    nri = 0
    for day in cal:
        if cash_rate is not None and cash > 0:
            cash += cash * float(cash_rate.get(day, 0.0))
        if nri < len(rebal_dates) and day >= rebal_dates[nri]:
            px = _p(day)
            if px:
                val = sh * px + cash
                if income_mode == 'draw' and val > maintain_level:
                    wd += val - maintain_level
                    val = maintain_level
                sh = val / px
                cash = 0.0
            nri += 1
        if day in bench_hist.index:
            div = float(bench_hist.loc[day, 'Dividends'])
            if div > 0:
                cash += sh * div
                inc += sh * div
        px = _p(day)
        vals.append(round((sh * px if px else 0.0) + cash, 2))
    return vals, wd, inc


def run_backtest():
    cfg = load_config()
    top_n = int(cfg['top_n'])
    years = int(cfg['years'])
    capital = float(cfg['start_capital'])
    freq_filter = cfg.get('freq_filter', 'all')
    hedge_enabled = bool(cfg.get('hedge_enabled', False))
    hedge_pct = float(cfg.get('hedge_pct', 0.10))
    income_mode = cfg.get('income_mode', 'reinvest')
    draw_threshold = float(cfg.get('draw_threshold_pct', 0.10))
    maintain_level = capital * (1 + draw_threshold)   # draw down to this at rebalance
    stop_loss = float(cfg.get('stop_loss_pct', 0.0))  # 0 = disabled

    os.makedirs(RESULTS_DIR, exist_ok=True)
    today = datetime.today().strftime('%Y%m%d')

    print(f"Backtest: top {top_n}, {years}y, ${capital:,.0f}, freq={freq_filter}, "
          f"rebalance={cfg.get('rebal_freq', 'quarterly')}")
    print(f"Fetching {len(UNIVERSE)} ETFs + SPY...")
    history = fetch_history(list(UNIVERSE.keys()), years)
    spy = fetch_history(['SPY'], years).get('SPY')
    if spy is None or not history:
        print("Insufficient data")
        return

    # underlying histories for point-in-time RS (one fetch per unique proxy)
    und_map = {}   # underlying label -> proxy ticker
    for _, underlying, _ in UNIVERSE.values():
        t = resolve_underlying(underlying)
        if t and underlying not in und_map:
            und_map[underlying] = t
    print(f"Fetching {len(und_map)} underlyings for RS...")
    und_raw = fetch_adj(list(set(und_map.values())), years)
    und_history = {label: und_raw[t] for label, t in und_map.items() if t in und_raw}
    spy_adj = fetch_adj(['SPY'], years).get('SPY')

    # hedge data: VIX term structure signal + VIXY prices
    hedge_signal = None
    vixy = None
    if hedge_enabled:
        print("Fetching VIX term structure + VIXY for hedge...")
        vol_data = fetch_adj(['^VIX', '^VIX3M', HEDGE_TICKER], years)
        vix, vix3m, vixy = (vol_data.get('^VIX'), vol_data.get('^VIX3M'),
                            vol_data.get(HEDGE_TICKER))
        if vix is None or vix3m is None or vixy is None:
            print("  Hedge data unavailable — running unhedged")
            hedge_enabled = False
        else:
            hedge_signal = compute_hedge_signal(vix['Close'], vix3m['Close'])

    # Rebalance dates: first trading day of each period
    rebal_freq = cfg.get('rebal_freq', 'quarterly')
    freq_code = REBAL_FREQ_MAP.get(rebal_freq, 'QS')
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years)
    rebal_dates = pd.date_range(start=start, end=end, freq=freq_code)
    rebal_dates = [d for d in rebal_dates if d >= start]

    # Trading calendar from SPY
    cal = spy.index[(spy.index >= start) & (spy.index <= end)]

    cash = capital
    shares = {}           # ticker -> shares held
    equity_rows = []      # daily portfolio value
    quarter_rows = []     # per-quarter log
    income_total = 0.0
    income_at_rebal = 0.0
    next_rebal_idx = 0

    hedge_shares = 0.0    # VIXY position
    hedge_basis = 0.0     # cost of current hedge position
    hedge_pnl = 0.0       # realised hedge P&L
    hedge_days = 0

    withdrawn_total = 0.0   # cumulative cash drawn out (income_mode == 'draw')
    interest_total = 0.0    # T-bill interest earned on idle cash
    cash_rate = build_cash_rate(cal, years)

    entry_px = {}           # ticker -> entry price (for total-return stop)
    divs_since = {}         # ticker -> per-share distributions received since entry
    stop_events = []        # (date, ticker, tr%) log of stops hit

    def _px(hist_df, day):
        s = hist_df['Close'][hist_df.index <= day]
        return float(s.iloc[-1]) if len(s) else None

    if hedge_enabled:
        sig_series = hedge_signal.reindex(cal, method='ffill').fillna(False)
    else:
        sig_series = pd.Series(False, index=cal)

    for day in cal:
        # idle cash earns the T-bill rate
        if cash > 0:
            _acc = cash * float(cash_rate.get(day, 0.0))
            cash += _acc
            interest_total += _acc

        # rebalance if we've reached the next scheduled date
        if next_rebal_idx < len(rebal_dates) and day >= rebal_dates[next_rebal_idx]:
            # close out the previous quarter's income
            if quarter_rows:
                quarter_rows[-1]['income'] = round(income_total - income_at_rebal, 2)
            income_at_rebal = income_total

            # liquidate at today's close (incl. any hedge position)
            for t, sh in shares.items():
                h = history[t]
                px = h['Close'][h.index <= day]
                if len(px):
                    cash += sh * float(px.iloc[-1])
            shares = {}
            if hedge_shares > 0:
                vp = _px(vixy, day)
                if vp:
                    proceeds = hedge_shares * vp
                    cash += proceeds
                    hedge_pnl += proceeds - hedge_basis
                hedge_shares = 0.0
                hedge_basis = 0.0

            # prop-style withdrawal: draw the excess above the maintain level,
            # leave the buffer working. Below threshold — no draw, rebuild.
            qtr_withdrawal = 0.0
            if income_mode == 'draw' and cash > maintain_level:
                qtr_withdrawal = cash - maintain_level
                cash = maintain_level
                withdrawn_total += qtr_withdrawal

            ranked = score_at(day, history, freq_filter, und_history, spy_adj)
            picks = []
            if not ranked.empty:
                q = ranked[ranked['qualified'] == True]
                picks = list(q.head(top_n).index)

            # hedge first if the signal is on
            if hedge_enabled and bool(sig_series.get(day, False)) and cash > 0:
                vp = _px(vixy, day)
                if vp:
                    hedge_basis = cash * hedge_pct
                    hedge_shares = hedge_basis / vp
                    cash -= hedge_basis

            entry_px = {}
            divs_since = {}
            if picks:
                alloc = cash / len(picks)
                for t in picks:
                    h = history[t]
                    px = h['Close'][h.index <= day]
                    if len(px):
                        p = float(px.iloc[-1])
                        shares[t] = alloc / p
                        entry_px[t] = p
                        divs_since[t] = 0.0
                cash = 0.0

            quarter_rows.append({
                'date'     : day.strftime('%Y-%m-%d'),
                'holdings' : ', '.join(picks) if picks else 'CASH',
                'n_picks'  : len(picks),
                'income'   : 0.0,   # filled at next rebalance / end of run
                'withdrawn': round(qtr_withdrawal, 2),
                'hedged'   : hedge_shares > 0,
            })
            next_rebal_idx += 1

        # daily hedge entry/exit on the VIX term-structure signal
        if hedge_enabled:
            sig_today = bool(sig_series.get(day, False))
            if sig_today and hedge_shares == 0 and shares:
                # trim every position proportionally to fund the hedge
                vp = _px(vixy, day)
                if vp:
                    hedge_cash = 0.0
                    for t in list(shares):
                        p = _px(history[t], day)
                        if p:
                            sell_sh = shares[t] * hedge_pct
                            shares[t] -= sell_sh
                            hedge_cash += sell_sh * p
                    hedge_cash += cash * hedge_pct
                    cash -= cash * hedge_pct
                    if hedge_cash > 0:
                        hedge_basis = hedge_cash
                        hedge_shares = hedge_cash / vp
            elif not sig_today and hedge_shares > 0:
                # signal off — exit hedge to cash (redeployed next rebalance)
                vp = _px(vixy, day)
                if vp:
                    proceeds = hedge_shares * vp
                    cash += proceeds
                    hedge_pnl += proceeds - hedge_basis
                    hedge_shares = 0.0
                    hedge_basis = 0.0
            if hedge_shares > 0:
                hedge_days += 1

        # collect distributions paid today
        day_income = 0.0
        for t, sh in shares.items():
            h = history[t]
            if day in h.index:
                div = float(h.loc[day, 'Dividends'])
                if div > 0:
                    day_income += sh * div
                    if t in divs_since:
                        divs_since[t] += div
        cash += day_income
        income_total += day_income

        # total-return stop: cut holdings whose price + received distributions
        # have fallen more than stop_loss below entry — cash until next rebalance
        if stop_loss > 0:
            for t in list(shares):
                if t not in entry_px:
                    continue
                p = _px(history[t], day)
                if p is None:
                    continue
                tr = (p + divs_since.get(t, 0.0)) / entry_px[t] - 1
                if tr < -stop_loss:
                    cash += shares[t] * p
                    stop_events.append({'date': day.strftime('%Y-%m-%d'),
                                        'ticker': t, 'tr': round(tr * 100, 1)})
                    del shares[t]
                    del entry_px[t]

        # mark portfolio to market
        pos_value = 0.0
        for t, sh in shares.items():
            h = history[t]
            px = h['Close'][h.index <= day]
            if len(px):
                pos_value += sh * float(px.iloc[-1])
        hedge_value = 0.0
        if hedge_shares > 0:
            vp = _px(vixy, day)
            if vp:
                hedge_value = hedge_shares * vp
        value = pos_value + cash + hedge_value
        equity_rows.append({
            'date'         : day.strftime('%Y-%m-%d'),
            'value'        : round(value, 2),
            'positions'    : round(pos_value, 2),
            'cash'         : round(cash, 2),
            'hedge'        : round(hedge_value, 2),
            'income_cum'   : round(income_total, 2),
            'withdrawn_cum': round(withdrawn_total, 2),
        })

    # close out the final (partial) quarter's income
    if quarter_rows:
        quarter_rows[-1]['income'] = round(income_total - income_at_rebal, 2)

    eq = pd.DataFrame(equity_rows)

    # SPY reference: growth opportunity-cost footnote, not the objective
    spy_win = spy[(spy.index >= start) & (spy.index <= end)]
    spy_shares = capital / float(spy_win['Close'].iloc[0])
    spy_cash = 0.0
    spy_vals = []
    for day, row in spy_win.iterrows():
        if spy_cash > 0:
            spy_cash += spy_cash * float(cash_rate.get(day, 0.0))
        spy_cash += spy_shares * float(row['Dividends'])
        spy_vals.append(round(spy_shares * float(row['Close']) + spy_cash, 2))
    eq['spy'] = pd.Series(spy_vals[:len(eq)]).values if len(spy_vals) >= len(eq) else np.nan

    # Passive income benchmark: one fund, same money-flow rules
    bench_ticker = cfg.get('bench_ticker', 'JEPI')
    bench_hist = history.get(bench_ticker)
    if bench_hist is None:
        bench_fetch = fetch_history([bench_ticker], years)
        bench_hist = bench_fetch.get(bench_ticker)
    bench_wd = bench_inc = 0.0
    bench_all_in_ret = None
    if bench_hist is not None:
        bench_vals, bench_wd, bench_inc = sim_passive(
            bench_hist, cal, rebal_dates, capital, income_mode, maintain_level,
            cash_rate=cash_rate)
        eq['bench'] = bench_vals
        bench_final = bench_vals[-1]
        bench_all_in_ret = ((bench_final + bench_wd) / capital - 1) * 100

    # Stats — computed on the all-in curve (capital base + cumulative withdrawals)
    # so a withdrawal is not counted as a drawdown. Identical to `value` in
    # reinvest mode where withdrawn_cum is always 0.
    eq['all_in'] = eq['value'] + eq['withdrawn_cum']
    final = float(eq['value'].iloc[-1])
    final_all_in = float(eq['all_in'].iloc[-1])
    total_ret = (final_all_in / capital - 1) * 100
    n_years = max((pd.to_datetime(eq['date'].iloc[-1]) - pd.to_datetime(eq['date'].iloc[0])).days / 365.25, 0.1)
    cagr = ((final_all_in / capital) ** (1 / n_years) - 1) * 100
    roll_max = eq['all_in'].cummax()
    max_dd = float(((eq['all_in'] - roll_max) / roll_max).min() * 100)
    spy_final = float(eq['spy'].dropna().iloc[-1]) if eq['spy'].notna().any() else capital
    spy_ret = (spy_final / capital - 1) * 100

    # settle any open hedge P&L at final mark for reporting
    open_hedge_pnl = 0.0
    if hedge_shares > 0 and vixy is not None:
        vp = _px(vixy, cal[-1])
        if vp:
            open_hedge_pnl = hedge_shares * vp - hedge_basis

    summary = {
        'run_date'      : today,
        'config'        : cfg,
        'final_value'   : round(final, 2),
        'total_return'  : round(total_ret, 2),
        'cagr'          : round(cagr, 2),
        'max_drawdown'  : round(max_dd, 2),
        'income_total'  : round(income_total, 2),
        'income_avg_qtr': round(income_total / max(len(quarter_rows), 1), 2),
        'spy_return'    : round(spy_ret, 2),
        'excess_return' : round(total_ret - spy_ret, 2),
        'bench_ticker'  : bench_ticker,
        'bench_return'  : round(bench_all_in_ret, 2) if bench_all_in_ret is not None else None,
        'bench_income'  : round(bench_inc, 2),
        'bench_withdrawn': round(bench_wd, 2),
        'excess_vs_bench': round(total_ret - bench_all_in_ret, 2) if bench_all_in_ret is not None else None,
        'n_quarters'    : len(quarter_rows),
        'rebal_freq'    : rebal_freq,
        'stop_loss_pct' : stop_loss,
        'stops_hit'     : len(stop_events),
        'stop_events'   : stop_events,
        'hedge_enabled' : hedge_enabled,
        'hedge_days'    : hedge_days,
        'hedge_days_pct': round(hedge_days / max(len(cal), 1) * 100, 1),
        'hedge_pnl'     : round(hedge_pnl + open_hedge_pnl, 2),
        'income_mode'   : income_mode,
        'interest_total': round(interest_total, 2),
        'withdrawn_total': round(withdrawn_total, 2),
        'withdrawn_avg_qtr': round(withdrawn_total / max(len(quarter_rows), 1), 2),
        'maintain_level': round(maintain_level, 2) if income_mode == 'draw' else None,
    }

    from marketdb import results as _mr
    _mr.save_frame(f"etf_backtest/{today}/equity", eq)
    _mr.save_frame(f"etf_backtest/{today}/quarters", pd.DataFrame(quarter_rows))
    _mr.save_report('etf_backtest', f"{today[:4]}-{today[4:6]}-{today[6:]}", payload=summary)
    print(f"Saved: marketdb etf_backtest/{today}")

    print(f"\n{'═' * 50}")
    if income_mode == 'draw':
        print(f"  Mode        : DRAW — maintain ${maintain_level:,.0f} "
              f"(${capital:,.0f} + {draw_threshold:.0%} buffer)")
        print(f"  Withdrawn   : ${withdrawn_total:,.0f} total  "
              f"(${summary['withdrawn_avg_qtr']:,.0f}/qtr avg)")
    print(f"  Final value : ${final:,.0f}  (all-in {total_ret:+.1f}% incl. withdrawals)")
    print(f"  CAGR        : {cagr:+.1f}%")
    print(f"  Max DD      : {max_dd:.1f}%")
    print(f"  Income      : ${income_total:,.0f}  (${summary['income_avg_qtr']:,.0f}/qtr avg)")
    print(f"  Cash interest: ${interest_total:,.0f}  (T-bill rate on idle cash)")
    if bench_all_in_ret is not None:
        print(f"  {bench_ticker} passive: {bench_all_in_ret:+.1f}% all-in, "
              f"income ${bench_inc:,.0f}  (strategy excess: {total_ret - bench_all_in_ret:+.1f}%)")
    print(f"  SPY (ref)   : {spy_ret:+.1f}%  — growth opportunity cost, not the objective")
    if hedge_enabled:
        print(f"  Hedge       : VIXY {hedge_pct:.0%} on term-structure inversion — "
              f"{hedge_days} days hedged ({summary['hedge_days_pct']}%), "
              f"P&L {summary['hedge_pnl']:+,.0f}")
    if stop_loss > 0:
        print(f"  Stop loss   : {stop_loss:.0%} total-return from entry — {len(stop_events)} hit")
        for ev in stop_events:
            print(f"    {ev['date']}: {ev['ticker']} cut at {ev['tr']:+.1f}%")
    print(f"{'═' * 50}")
    for r in quarter_rows:
        print(f"  {r['date']}: {r['holdings']}")
    print(f"\nSaved to {RESULTS_DIR}")
    return summary


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run_backtest()
