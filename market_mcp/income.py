"""Read-only Income configuration/results/previews and explicit review snapshots.

This module never imports the network price adapter or TradingJournal.
"""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import re
from typing_extensions import TypedDict, NotRequired
from typing import Annotated
from pydantic import Field

import pandas as pd

from etf import income_config as IC
from etf.income_rules import (allocation_preview, holding_total_return, number,
                              qualified_ranks, ranking_decision, stop_decision, distribution_schedule, hedge_signal)
from . import operations as op

MAX_AGE_DAYS = 5  # the existing ETF price adapter's freshness window, not a trading threshold
CONTEXT = {"source": "user clarification, 2026-10-28; conversation context, not saved app configuration",
           "risk_review_frequency": "monthly", "risk_review_checks": ["NAV deterioration", "stop-loss rules"],
           "full_rebalance_cadence": "undecided", "quarterly_idea_adopted": False,
           "automatic_execution_authorised": False, "recurring_monitor_installed": False}


class HoldingInput(TypedDict):
    __pydantic_config__ = {'extra': 'forbid'}
    ticker: str
    shares: NotRequired[Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)] | None]
    entry_price: NotRequired[Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)] | None]
    entry_date: NotRequired[Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$')] | None]
    quote_currency: NotRequired[Annotated[str, Field(pattern=r'^[A-Z]{3}$')] | None]


class AllocationInput(TypedDict):
    __pydantic_config__ = {'extra': 'forbid'}
    tickers: list[str]
    budget_aud: Annotated[float, Field(strict=True, ge=0, le=100000000, allow_inf_nan=False)]
    usd_per_aud: Annotated[float, Field(strict=True, ge=.30, le=1.50, allow_inf_nan=False)]
    fx_source: str
    fx_observed_at: str


def _moment(as_of=None):
    value = datetime.now(timezone.utc) if as_of is None else datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("as_of must be an ISO timestamp with a UTC offset")
    if value > datetime.now(timezone.utc) + pd.Timedelta(minutes=5):
        raise ValueError("as_of cannot be in the future")
    return value


def _holdings_source():
    path = IC.ROOT / "holdings.json"
    if not path.exists():
        return {"status": "unavailable", "source": "etf/holdings.json", "updated": None,
                "holdings": [], "warnings": ["No saved holdings source. Rankings are not actual holdings."]}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        holdings = validate_holdings(raw["holdings"])
        return {"status": "saved_app_data_unverified", "source": "etf/holdings.json",
                "updated": raw.get("updated"), "holdings": holdings,
                "version": IC.fingerprint(holdings), "historical_holdings_verified": False, "warnings": [
                    "Saved app holdings have no verified external portfolio identity, cost/FX reconciliation or broker link."]}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "invalid", "source": "etf/holdings.json", "updated": None,
                "holdings": [], "warnings": ["Saved holdings are unreadable or invalid; not interpreted as an empty portfolio."]}


def etf_income_config() -> dict:
    """Read only Income settings/capabilities with source hashes and defaults. Monthly risk review is user context; the saved backtest cadence is not an adopted live rebalance policy. No credentials or settings writes."""
    strategy, backtest, holdings = IC.load_strategy(), IC.load_backtest(), _holdings_source()
    settings = strategy["effective"]
    excluded = settings["excluded"] if isinstance(settings["excluded"], list) else []
    active = {ticker: {"name": details[0], "underlying": details[1], "distribution_frequency": details[2]}
              for ticker, details in IC.FULL_UNIVERSE.items() if ticker not in excluded}
    from .version import code_version
    return {"schema_version": IC.SCHEMA_VERSION, "code_version": code_version(), "strategy_id": "etf_income", "strategy": strategy,
        "backtest": backtest, "version": IC.fingerprint({"strategy": strategy, "backtest": backtest}),
        "universe": active, "full_universe_count": len(IC.FULL_UNIVERSE),
        "rules": {"qualification": {"metric": "chg_3m", "operator": ">", "threshold": 0,
                   "units": "percent", "window": "last 63 observed closes, minimum 63 bars",
                   "true_nav": False, "basis": "market-price proxy, distributions excluded from this gate"},
                  "score": "Same etf_income_data.compute_metrics/score_universe as the app and simulator; percentile weighted sum × 100.",
                  "selection": "HOLD inside top-N qualified (buy_zone); REVIEW outside; SELL if disqualified; separate stop status.",
                  "live_stop": stop_decision(None, settings["stop_loss_pct"]) if strategy["valid_for_review"] else None,
                  "backtest_stop": {"threshold_fraction": backtest["effective"].get("stop_loss_pct"), "zero_disables": True},
                  "vix_hedge_banner": {"ratio": "VIX/VIX3M", "on_gte": 1., "off_lte": .95,
                                        "stateful": True, "live_banner_lookback": "6 months", "trade_execution": False},
                  "live_stop_zero": "Existing live page treats zero literally (HIT at return <= 0); only the backtest defines zero as disabled."},
        "cadence": {"conversation_context": dict(CONTEXT), "saved_live_review_cadence": None,
                    "saved_live_full_rebalance_cadence": None,
                    "saved_backtest_rebalance_cadence": backtest["effective"].get("rebal_freq"),
                    "note": "Backtest configuration and app quarterly wording are not an adopted policy for this demo experiment."},
        "holdings_source": {k: v for k, v in holdings.items() if k != "holdings"},
        "capabilities": {"saved_holdings_read": holdings["status"] == "saved_app_data_unverified",
            "explicit_holdings_preview": True, "verified_external_portfolio": False,
            "persisted_target_allocations": False, "cash_ledger": False, "rebalance_manager": False,
            "equal_weight_aud_calculator_preview": True, "verified_fund_nav": False,
            "trade_execution": False, "settings_write": False, "journal_write": False},
        "input_contract": {"portfolio_id": "Explicit Income portfolio identity; never inferred from universe or a screenshot.",
            "holdings": "Optional exact list of ticker, shares, entry_price, entry_date (YYYY-MM-DD), quote_currency. Null uses saved unverified app holdings; [] explicitly means empty for this preview.",
            "allocation": "Optional {tickers, budget_aud, usd_per_aud, fx_source, fx_observed_at}. Reproduces the page's calculator only; not net trades.",
            "missing_for_execution": ["verified exact current quantities and portfolio identity", "account cash", "costs and taxes", "broker FX and fill prices", "corporate-action reconciliation"]},
        "warnings": strategy["warnings"] + backtest["warnings"]}


def validate_holdings(holdings):
    if not isinstance(holdings, list) or len(holdings) > 100:
        raise ValueError("Supply at most 100 holdings")
    result, seen = [], set()
    fields = {"ticker", "shares", "entry_price", "entry_date", "quote_currency"}
    for holding in holdings:
        if not isinstance(holding, dict) or set(holding) - fields:
            raise ValueError("Holding fields: ticker, shares, entry_price, entry_date, quote_currency")
        ticker = str(holding.get("ticker", "")).strip().upper()
        if not re.fullmatch(r"[A-Z0-9.^=-]{1,30}", ticker) or ticker in seen:
            raise ValueError("Holdings require unique exact tickers")
        seen.add(ticker)
        value = {"ticker": ticker}
        for key in ("shares", "entry_price"):
            raw = holding.get(key)
            if raw is not None and (number(raw) is None or number(raw) < 0):
                raise ValueError(f"{ticker}: {key} must be a finite non-negative number or null")
            value[key] = number(raw)
        entry_date = holding.get("entry_date") or None
        op.valid_date(entry_date)
        value["entry_date"] = entry_date
        currency = holding.get("quote_currency") or None
        if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
            raise ValueError("quote_currency must be an uppercase ISO currency code or null")
        value["quote_currency"] = currency
        result.append(value)
    return result


def validate_request(portfolio_id, holdings, run_id, ranking_date, as_of, allocation):
    if not isinstance(portfolio_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", portfolio_id):
        raise ValueError("Supply a stable explicit Income portfolio_id (1–100 letters/digits/._-)")
    if portfolio_id.lower() in ("growth", "etf_growth", "au_stocks", "stocks_swing"):
        raise ValueError("This interface is only for the separate ETF Income strategy")
    if holdings is not None:
        validate_holdings(holdings)
    if run_id and (not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9TZ.-]{1,100}", run_id)):
        raise ValueError("Invalid generation run_id")
    op.valid_date(ranking_date)
    _moment(as_of)
    if allocation is not None:
        keys = {"tickers", "budget_aud", "usd_per_aud", "fx_source", "fx_observed_at"}
        if not isinstance(allocation, dict) or set(allocation) != keys:
            raise ValueError("allocation requires tickers, budget_aud, usd_per_aud, fx_source, fx_observed_at")
        if not isinstance(allocation["tickers"], list) or not 1 <= len(allocation["tickers"]) <= 100:
            raise ValueError("Supply 1–100 allocation tickers")
        if any(not isinstance(t, str) or t not in IC.FULL_UNIVERSE for t in allocation["tickers"]):
            raise ValueError("Allocation tickers must be exact Income universe symbols")
        if not isinstance(allocation["fx_source"], str) or not allocation["fx_source"].strip() or len(allocation["fx_source"]) > 200:
            raise ValueError("An explicit bounded FX source is required")
        _moment(allocation["fx_observed_at"])
        allocation_preview(pd.DataFrame(columns=["ticker", "price"]), allocation["tickers"], allocation["budget_aud"], allocation["usd_per_aud"])


def _frame(con, name):
    row = con.execute("SELECT updated,blob,length(blob) FROM frames WHERE name=?", (name,)).fetchone()
    if row is None:
        raise ValueError("Income frame not found")
    if row[2] > 32 * 1024 * 1024:
        raise ValueError("Income frame exceeds the read limit")
    return pd.read_parquet(io.BytesIO(row[1])), row[0]


def _rankings(con, run_id=None, ranking_date=None, cutoff=None):
    if run_id and ranking_date:
        raise ValueError("Select run_id or ranking_date, not both")
    latest_legacy = con.execute("SELECT MAX(name) FROM frames WHERE name GLOB 'etf_income/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'").fetchone()[0]
    latest_legacy_day = datetime.strptime(latest_legacy.split('/')[1], '%Y%m%d').date().isoformat() if latest_legacy else None
    sql, parameters = "SELECT date,payload FROM reports WHERE kind='etf_income_run'", []
    if run_id:
        sql += ' AND date=?'
        parameters.append(run_id)
    if ranking_date:
        sql += " AND json_extract(payload,'$.run_date')=?"
        parameters.append(ranking_date)
    if cutoff:
        sql += " AND json_extract(payload,'$.created_at')<=?"
        parameters.append(cutoff.astimezone(timezone.utc).isoformat())
    if not run_id and not ranking_date and latest_legacy_day and (not cutoff or latest_legacy_day <= cutoff.date().isoformat()):
        sql += " AND json_extract(payload,'$.run_date')>=?"
        parameters.append(latest_legacy_day)
    runs = con.execute(sql + ' ORDER BY created DESC,date DESC LIMIT 1', parameters).fetchall()
    for row in runs:
        if run_id and row[0] != run_id:
            continue
        payload = json.loads(row[1])
        stamp = datetime.fromisoformat(payload["created_at"])
        # Generation day follows the captured source frame key, not the client's timezone.
        day = payload.get("run_date", stamp.date().isoformat())
        if not run_id and not ranking_date and latest_legacy_day and day < latest_legacy_day and (not cutoff or latest_legacy_day <= cutoff.date().isoformat()):
            continue
        if ranking_date and day != ranking_date:
            continue
        if cutoff and stamp > cutoff:
            continue
        frame, updated = _frame(con, payload["frames"]["rankings"])
        return frame, {"run_id": row[0], "frame": payload["frames"]["rankings"],
            "run_date": day, "updated": updated, "generation_configuration": payload["configuration"],
            "sources": payload.get("sources", {}), "content_version": IC.fingerprint(_rows(frame)),
            "configuration_known": True, "legacy": False}
    if run_id:
        raise ValueError("Income run not found/available at the requested as_of")
    sql = "SELECT name,updated FROM frames WHERE name GLOB 'etf_income/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'"
    parameters = []
    if ranking_date:
        sql += ' AND name=?'
        parameters.append('etf_income/' + ranking_date.replace('-', ''))
    if cutoff:
        sql += ' AND name<=?'
        parameters.append('etf_income/' + cutoff.date().strftime('%Y%m%d'))
    legacy = con.execute(sql + ' ORDER BY name DESC LIMIT 1', parameters).fetchall()
    for row in legacy:
        day = datetime.strptime(row[0].split("/")[1], "%Y%m%d").date()
        if ranking_date and day.isoformat() != ranking_date:
            continue
        if cutoff and day > cutoff.date():
            continue
        frame, updated = _frame(con, row[0])
        return frame, {"run_id": None, "frame": row[0], "run_date": day.isoformat(), "updated": updated,
            "generation_configuration": None, "sources": {}, "configuration_known": False,
            "content_version": IC.fingerprint(_rows(frame)), "legacy": True}
    return pd.DataFrame(), {"frame": None, "run_id": None, "run_date": None, "updated": None,
                            "generation_configuration": None, "configuration_known": False, "sources": {}, "legacy": True}


def _rows(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _diagnostics(row, rank, buy_zone, weights=None):
    observed = number(row.get("chg_3m"))
    score_parts = {}
    for column, weight in {'r_nav3': 'nav_3m', 'r_nav12': 'nav_12m', 'r_sharpe': 'sharpe',
                           'r_yield': 'yield_ttm', 'r_slope': 'dist_slope', 'r_consist': 'dist_consist', 'r_und': 'underlying_rs'}.items():
        percentile = number(row.get(column))
        applied_weight = number((weights or {}).get(weight))
        score_parts[weight] = {'percentile': percentile, 'generation_weight': applied_weight,
                              'contribution': percentile * applied_weight * 100 if percentile is not None and applied_weight is not None else None}
    return {"ranking": ranking_decision(row, rank, buy_zone),
            "qualification_consistent_with_observed_gate": None if observed is None or row.get('qualified') is None else bool(row['qualified']) == (observed > 0),
            "price_trend_gate": {"observed_pct": observed, "threshold_gt_pct": 0,
                                  "status": "not_assessed" if observed is None else "pass" if observed > 0 else "fail"},
            "true_nav_deterioration": {"status": "not_assessed", "reason": "No verified fund NAV series or independent NAV rule in this app; chg_3m is a market-price proxy."},
            "score_components": score_parts,
            "stop_loss": {"status": "not_assessed", "reason": "Requires an exact holding/entry and dated price/distribution history; rankings alone are not holdings."}}


def read_etf_income_results(run_id: str | None = None, ranking_date: str | None = None,
                            limit: int = 50, offset: int = 0) -> dict:
    """Read complete latest/dated Income rankings with rule evidence, captured config and price-vs-NAV limits. Legacy frames remain readable even if no etf_income report exists. No refresh/re-scoring or holdings inference."""
    op.bounds(limit, offset, 100)
    op.valid_date(ranking_date)
    with op.connection() as con:
        frame, source = _rankings(con, run_id, ranking_date)
    config = etf_income_config()
    ranks = qualified_ranks(frame)
    rows = _rows(frame.iloc[offset:offset + limit])
    for row in rows:
        weights = ((source.get('generation_configuration') or {}).get('strategy') or {}).get('effective', {}).get('weights')
        row["diagnostics"] = _diagnostics(row, ranks.get(row["ticker"]), config["strategy"]["effective"]["buy_zone"], weights) if config["strategy"]["valid_for_review"] else {"status": "not_assessed", "reason": "Invalid current settings"}
    now = _moment()
    warnings = _source_warnings(source, now)
    sources = source.get('sources', {})
    if sources.get('missing_tickers'):
        warnings.append('Generation skipped some universe tickers; inspect source.missing_tickers.')
    if sources.get('missing_underlying_rs'):
        warnings.append('Some underlying RS values used the existing neutral fallback; inspect source.missing_underlying_rs.')
    return {"schema_version": IC.SCHEMA_VERSION, "strategy_id": "etf_income", "portfolio_id": None,
            "source": source, "current_review_configuration": config, "rows": rows, "total_rows": len(frame),
            "offset": offset, "next_offset": offset + limit if len(frame) > offset + limit else None,
            "warnings": warnings, "holdings_inferred": False}


def _source_warnings(source, moment):
    warnings = []
    if not source.get("frame"):
        warnings.append("No Income ranking source is available.")
    elif (moment.date() - datetime.fromisoformat(source["run_date"]).date()).days > MAX_AGE_DAYS:
        warnings.append("Income ranking is stale under the 5-calendar-day source freshness window.")
    if not source.get("configuration_known"):
        warnings.append("Legacy cached ranking has no captured generation configuration or per-ticker source timestamps; current settings cannot be attributed to that historical run.")
    warnings.append("Market price trend is a NAV proxy only; true fund NAV deterioration is not assessed.")
    return warnings


def _holding_evidence(con, holding, moment, stop_loss):
    ticker, warnings = holding["ticker"], []
    entries = con.execute("SELECT date,close,dividend,split FROM prices WHERE ticker=? AND date<=? ORDER BY date",
                          (ticker, moment.date().isoformat())).fetchall()
    sec = con.execute("SELECT currency FROM securities WHERE ticker=?", (ticker,)).fetchone()
    currency = sec[0] if sec else None
    history = pd.DataFrame([dict(r) for r in entries])
    basis = {"source": "marketdb.prices.close/dividend/split", "instrument_currency": currency,
             "entry_quote_currency": holding["quote_currency"], "fx_conversion": "none",
             "price_basis": "stored market close; upstream splits may have rescaled history; not independently verified fund NAV",
             "distributions": "cash per-share amounts on ex-date, not verified receipt/tax/fee records"}
    total_return, latest, dividends, splits, first = None, None, None, [], None
    schedule = {'status': 'not_assessed', 'estimated_ex_date': None, 'frequency': None}
    if not history.empty:
        history.index = pd.to_datetime(history["date"])
        history = history.rename(columns={"close": "Close", "dividend": "Dividends"})
        schedule = distribution_schedule(history, moment.date())
        closes = history["Close"].dropna()
        if not closes.empty:
            latest, first = closes.index[-1].date().isoformat(), closes.index[0].date().isoformat()
        if holding["entry_date"]:
            relevant = history[history.index > pd.Timestamp(holding["entry_date"])]
            dividends = number(relevant["Dividends"].fillna(0).sum())
            splits = relevant[relevant["split"].notna() & ~relevant["split"].isin([0, 1])][["date", "split"]].to_dict("records")
        total_return = holding_total_return(history, holding["entry_price"], holding["entry_date"])
    if not holding["entry_date"]:
        warnings.append("Missing exact entry date; received-distribution window is unknown.")
    elif holding["entry_date"] > moment.date().isoformat():
        warnings.append("Entry is later than this review.")
    elif first and holding["entry_date"] < first:
        warnings.append("Price/distribution coverage does not reach the entry date.")
    if not holding["entry_price"]:
        warnings.append("Missing exact positive entry price.")
    if not latest:
        warnings.append("No stored price history.")
    elif (moment.date() - datetime.fromisoformat(latest).date()).days > MAX_AGE_DAYS:
        warnings.append("Stored holding prices are stale.")
    if splits:
        warnings.append("Split/corporate action crosses the entry window; entry and distribution per-share bases need reconciliation.")
    if not currency or not holding["quote_currency"] or currency != holding["quote_currency"]:
        warnings.append("Entry versus instrument quote-currency basis is missing or mismatched; no FX inference.")
    if total_return is None:
        warnings.append('A finite app-formula return could not be calculated from the supplied entry and stored history.')
    stop = stop_decision(total_return if not warnings else None, stop_loss)
    stop["app_formula_proxy_return_fraction"] = total_return
    stop["reason"] = "; ".join(warnings) if warnings else "Same total-return formula and thresholds as the Income page; source data was checked for coverage/currency/splits."
    return {"stop_loss": stop, "sources": {**basis, "first_price_date": first, "last_price_date": latest,
            "cash_distributions_ps_after_entry": dividends, "split_events": splits,
            "history_content_version": IC.fingerprint(_rows(history.reset_index(drop=True)))},
            "distribution_schedule": schedule,
            "warnings": warnings, "quantity_status": "provided" if holding["shares"] and holding["shares"] > 0 else "missing_or_placeholder"}


def _hedge_evidence(con, moment):
    start = (pd.Timestamp(moment.date()) - pd.DateOffset(months=6)).date().isoformat()
    data = {}
    for ticker in ('^VIX', '^VIX3M'):
        rows = con.execute("SELECT date,close FROM prices WHERE ticker=? AND date>=? AND date<=? AND close>0 ORDER BY date",
                           (ticker, start, moment.date().isoformat())).fetchall()
        data[ticker] = pd.Series([row[1] for row in rows], index=pd.to_datetime([row[0] for row in rows]), dtype=float)
    result = {'status': 'not_assessed', 'source': 'stored ^VIX and ^VIX3M close; no live fetch', 'on_gte': 1., 'off_lte': .95,
              'execution_authorised': False, 'lookback': '6 months', 'warnings': []}
    if any(series.empty for series in data.values()):
        result['warnings'] = ['Missing stored VIX/VIX3M history; banner is not assessed.']
        return result
    aligned = data['^VIX3M'].reindex(data['^VIX'].index).ffill()
    ratios = (data['^VIX'] / aligned).dropna()
    state = hedge_signal(data['^VIX'], data['^VIX3M'])
    if ratios.empty or state.empty:
        return result
    last = min(data['^VIX'].index[-1], data['^VIX3M'].index[-1]).date()
    stale = (moment.date() - last).days > MAX_AGE_DAYS
    result.update({'status': 'not_assessed' if stale else 'ON' if bool(state.iloc[-1]) else 'OFF',
                   'observed_ratio': number(ratios.iloc[-1]), 'last_source_date': last.isoformat(),
                   'initial_state': False, 'window_start': start,
                   'warnings': ['VIX source data is stale.'] if stale else []})
    return result


def build_snapshot(portfolio_id, holdings=None, run_id=None, ranking_date=None, as_of=None, allocation=None):
    validate_request(portfolio_id, holdings, run_id, ranking_date, as_of, allocation)
    moment, config = _moment(as_of), etf_income_config()
    if holdings is None:
        source_holdings = _holdings_source()
        selected = source_holdings.pop("holdings")
    else:
        selected = validate_holdings(holdings)
        source_holdings = {"status": "explicit_preview_inputs", "source": "caller supplied; not saved or broker verified",
                           "version": IC.fingerprint(selected), "warnings": []}
    warnings = list(config["warnings"]) + list(source_holdings["warnings"])
    with op.connection() as con:
        con.execute("BEGIN")  # one consistent read snapshot, with no migration or network calls
        frame, source = _rankings(con, run_id, ranking_date, moment)
        hedge = _hedge_evidence(con, moment)
        ranks = qualified_ranks(frame)
        rows = _rows(frame)
        by_ticker = {str(row["ticker"]).upper(): row for row in rows}
        assessed = []
        valid = config["strategy"]["valid_for_review"]
        settings = config["strategy"]["effective"]
        for holding in selected:
            row = by_ticker.get(holding["ticker"])
            weights = ((source.get('generation_configuration') or {}).get('strategy') or {}).get('effective', {}).get('weights')
            diag = _diagnostics(row, ranks.get(holding["ticker"]), settings["buy_zone"], weights) if row is not None and valid else {
                "ranking": ranking_decision(None, None, 1), "true_nav_deterioration": {"status": "not_assessed"}}
            if valid:
                evidence = _holding_evidence(con, holding, moment, settings["stop_loss_pct"])
            else:
                evidence = {"stop_loss": {"status": "not_assessed", "reason": "Invalid saved strategy settings"}, "warnings": [], "quantity_status": "unknown"}
            diag['stop_loss'] = evidence['stop_loss']
            assessed.append({"holding": holding, "stored_ranking": row, "rule_evidence": diag, **evidence})
        proposed_allocation = allocation_preview(frame, allocation["tickers"], allocation["budget_aud"], allocation["usd_per_aud"]) if allocation else None
    warnings += _source_warnings(source, moment)
    if not source.get("configuration_known"):
        warnings.append("Ranking signals apply the current buy zone to legacy stored qualification; this is what the app does, not a reconstructed historical strategy.")
    source_stale = not source.get("run_date") or (moment.date() - datetime.fromisoformat(source["run_date"]).date()).days > MAX_AGE_DAYS
    for row in assessed:
        gate = row['rule_evidence'].get('price_trend_gate', {})
        row["recommendation_usable"] = bool(valid and not source_stale and gate.get('status') in ('pass', 'fail') and row['rule_evidence'].get('qualification_consistent_with_observed_gate') is True and row["rule_evidence"]["ranking"]["signal"] in ("HOLD", "SELL", "REVIEW"))
        if not row["recommendation_usable"]:
            row["recommendation_status"] = "not_assessed"
        else:
            row["recommendation_status"] = "app_ranking_signal_only; stop evidence separate, no execution"
    candidates = [r for r in rows if ranks.get(str(r["ticker"]).upper(), 10**9) <= settings["buy_zone"] and r["ticker"] not in {h["ticker"] for h in selected}] if valid else []
    if source_holdings["status"] in ("unavailable", "invalid"):
        warnings.append("Candidate membership against actual holdings is not assessed; holdings are unavailable.")
        candidates = []
    if proposed_allocation:
        proposed_allocation.update({"fx_source": allocation["fx_source"], "fx_observed_at": allocation["fx_observed_at"],
                                   "ranking_source": source["frame"], "ranking_stale": source_stale})
    snapshot = {"schema_version": IC.SCHEMA_VERSION, "kind": "etf_income_review", "strategy_id": "etf_income",
        "portfolio_id": portfolio_id, "evaluated_at": moment.isoformat(), "job_id": None,
        "configuration": config, "ranking_source": source, "holdings_source": source_holdings,
        "holdings": assessed, "buy_zone_candidates": candidates, "allocation_preview": proposed_allocation, "vix_hedge_banner": hedge,
        "warnings": list(dict.fromkeys(warnings)), "true_fund_nav_assessed": False,
        "execution_authorised": False, "journal_written": False,
        "source_versions": {"rankings": source.get("content_version"), "holdings": source_holdings.get("version"),
                            "configuration": config["version"]}}
    snapshot["review_id"] = IC.fingerprint(snapshot)
    return snapshot


def snapshot_page(snapshot, limit=25, offset=0, persisted=False):
    op.bounds(limit, offset, 100)
    rows = snapshot["holdings"]
    return {**{k: v for k, v in snapshot.items() if k != "holdings"}, "persisted": persisted,
            "holdings": rows[offset:offset + limit], "total_holdings": len(rows), "offset": offset,
            "next_offset": offset + limit if len(rows) > offset + limit else None}


def preview_etf_income_review(portfolio_id: str, holdings: list[HoldingInput] | None = None,
        run_id: str | None = None, ranking_date: str | None = None, as_of: str | None = None,
        allocation: AllocationInput | None = None, limit: int = 25, offset: int = 0) -> dict:
    """Read-only Income review preview; never saves holdings/settings/journal data or fetches prices. portfolio_id is explicit Income identity. Holdings use exact ticker/shares/entry_price/entry_date/quote_currency; null reads unverified app holdings. Separate monthly review from undecided full rebalance. Unknown NAV, stale data and unreconciled splits stay not_assessed."""
    return snapshot_page(build_snapshot(portfolio_id, holdings, run_id, ranking_date, as_of, allocation), limit, offset)


def read_etf_income_review(review_id: str, limit: int = 25, offset: int = 0) -> dict:
    """Read a previously saved immutable Income review with captured settings/source versions and paged holdings. Review IDs are listed by list_reports(kind='etf_income_review'); raw JSON export uses read_report(section='payload', report_date=review_id)."""
    op.bounds(limit, offset, 100)
    if not re.fullmatch(r"[a-f0-9]{64}", review_id):
        raise ValueError("Invalid review_id")
    with op.connection() as con:
        row = con.execute("SELECT payload FROM reports WHERE kind='etf_income_review' AND date=?", (review_id,)).fetchone()
    if row is None:
        raise ValueError("Income review not found")
    snapshot = json.loads(row[0])
    if IC.fingerprint({k: v for k, v in snapshot.items() if k != "review_id"}) != review_id:
        raise ValueError("Stored review content does not match its immutable identity")
    return snapshot_page(snapshot, limit, offset, persisted=True)
