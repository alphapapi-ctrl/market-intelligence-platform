"""Pure Income page decisions. No holdings, settings or market data are written."""
from __future__ import annotations

import math
import pandas as pd


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def qualified_ranks(rankings: pd.DataFrame) -> dict:
    if rankings is None or rankings.empty:
        return {}
    frame = rankings[rankings["qualified"].eq(True)].sort_values("rank")
    return {str(t).upper(): i + 1 for i, t in enumerate(frame["ticker"])}


def ranking_decision(row: dict | None, qualified_rank: int | None, buy_zone: int) -> dict:
    if row is None:
        return {"signal": "NOT IN UNIVERSE", "reason": "No row in the selected saved ranking.", "qualified_rank": None}
    value = row.get("qualified")
    if value is None or pd.isna(value):
        return {"signal": "not_assessed", "reason": "Qualification is missing.", "qualified_rank": qualified_rank}
    if not bool(value):
        return {"signal": "SELL", "reason": "Disqualified by the stored positive 3-month price-change gate.", "qualified_rank": None}
    if qualified_rank is not None and qualified_rank <= buy_zone:
        return {"signal": "HOLD", "reason": "Inside the top-N qualified buy zone.", "qualified_rank": qualified_rank}
    return {"signal": "REVIEW", "reason": "Qualified but outside the top-N qualified buy zone.", "qualified_rank": qualified_rank}


def stop_decision(total_return: float | None, stop_loss: float) -> dict:
    value = number(total_return)
    if value is None:
        state = "not_assessed"
    elif value <= -stop_loss:
        state = "HIT"
    elif value <= -stop_loss * .75:
        state = "NEAR"
    else:
        state = "OK"
    return {"status": state, "observed_return_fraction": value, "hit_lte": -stop_loss,
            "near_lte": -stop_loss * .75,
            "definition": "(last market close + cash distributions with ex-date strictly after entry) / entry_price - 1",
            "basis": "quote-currency, not reinvested; excludes costs, taxes and FX; ex-dates proxy receipts"}


def holding_total_return(history: pd.DataFrame, entry_price, entry_date) -> float | None:
    """Exact formula formerly embedded in the dashboard's _fetch_holding_tr."""
    entry = number(entry_price)
    if entry is None or entry <= 0 or history is None or history.empty:
        return None
    closes = history["Close"].dropna()
    if closes.empty:
        return None
    divs = float(history.loc[history.index > pd.Timestamp(entry_date), "Dividends"].fillna(0).sum()) if entry_date else 0.
    result = (float(closes.iloc[-1]) + divs) / entry - 1
    return result if math.isfinite(result) else None


def distribution_schedule(history: pd.DataFrame, today=None) -> dict:
    """The page's ex-date cadence estimate; never an announced future payment."""
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize().tz_localize(None)
    distributions = history.loc[(history.index >= today - pd.DateOffset(months=6)) & (history.index <= today), 'Dividends']
    distributions = distributions[distributions > 0]
    if len(distributions) < 2:
        return {'status': 'not_assessed', 'estimated_ex_date': None, 'frequency': None}
    dates = distributions.index[-8:]
    gap = int(dates.to_series().diff().dropna().dt.days.median())
    if gap <= 0:
        return {'status': 'not_assessed', 'estimated_ex_date': None, 'frequency': None}
    nxt = dates[-1] + pd.Timedelta(days=gap)
    while nxt < today:
        nxt += pd.Timedelta(days=gap)
    return {'status': 'estimated', 'estimated_ex_date': nxt.date().isoformat(),
            'frequency': 'weekly' if gap <= 10 else 'monthly' if gap <= 45 else 'quarterly',
            'median_gap_days': gap, 'last_observed_ex_date': dates[-1].date().isoformat(),
            'basis': 'Recent ex-date cadence only; not an announced payment or guaranteed receipt'}


def hedge_signal(vix_close, vix3m_close, on=1.0, off=.95):
    """The page/backtest's existing stateful term-structure hysteresis."""
    vix_close, vix3m_close = vix_close.copy(), vix3m_close.copy()
    vix_close.index, vix3m_close.index = vix_close.index.normalize(), vix3m_close.index.normalize()
    ratio = (vix_close / vix3m_close.reindex(vix_close.index).ffill()).replace([float('inf'), -float('inf')], float('nan')).dropna()
    state, out = False, {}
    for day, value in ratio.items():
        if not state and value >= on:
            state = True
        elif state and value <= off:
            state = False
        out[day] = state
    return pd.Series(out, dtype=bool)


def allocation_preview(rankings: pd.DataFrame, tickers: list[str], aud_balance: float, audusd: float) -> dict:
    """The page's whole-share equal-weight AUD calculator; not a rebalance order list."""
    if number(aud_balance) is None or not 0 <= aud_balance <= 100000000 or number(audusd) is None or not .30 <= audusd <= 1.50:
        raise ValueError("Use the page's input ranges: AUD budget 0–100000000 and USD-per-AUD rate 0.30–1.50")
    if not tickers or len(tickers) != len(set(tickers)):
        raise ValueError("Supply a non-empty, unique buy list")
    usd = aud_balance * audusd
    allocation = usd / len(tickers)
    rows, spend = [], 0.
    for ticker in tickers:
        selected = rankings[rankings["ticker"] == ticker]
        price = number(selected.iloc[0].get("price")) if len(selected) else None
        shares = int(allocation // price) if price and price > 0 else None
        cost = shares * price if shares is not None else None
        if cost is not None:
            spend += cost
        rows.append({"ticker": ticker, "scan_price_usd": price, "hypothetical_whole_shares": shares,
                     "cost_usd": cost, "cost_aud": cost / audusd if cost is not None else None,
                     "hypothetical_weight": 1 / len(tickers)})
    return {"rows": rows, "budget_aud": aud_balance, "usd_per_aud": audusd,
            "per_position_usd": allocation, "spend_usd": spend, "cash_left_usd": usd - spend,
            "execution_ready": False, "persisted_target_allocation": False,
            "limitations": ["Matches the dashboard calculator; not net trades against existing holdings.",
                            "Uses saved scan prices, no fees, taxes, broker FX spread or actual fills."]}
