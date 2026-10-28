"""Income strategy definitions shared by the dashboard, scorer, backtest and MCP.

No network, database initialisation, settings writes or credentials are read here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import math
import os

ROOT = Path(os.environ.get('MARKET_INCOME_CONFIG_DIR', str(Path(__file__).resolve().parent)))
SCHEMA_VERSION = "income-review/1.0"
DEFAULT_EXCLUDED = ["MSTY"]


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False, default=str).encode()).hexdigest()


def _load(path: Path, defaults: dict, merge_weights=False) -> dict:
    effective = copy.deepcopy(defaults)
    state, warnings, supplied = "defaults_missing_file", [], []
    if path.is_file():
        try:
            if path.stat().st_size > 256 * 1024:
                raise ValueError('settings exceed 256 KiB')
            def reject_non_finite(value):
                raise ValueError('non-finite setting')
            raw = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject_non_finite)
            if not isinstance(raw, dict):
                raise ValueError("expected a JSON object")
            for key in defaults:
                if key in raw:
                    if key == "weights" and merge_weights:
                        # Preserve the existing app's merge semantics. Expose only known keys.
                        effective[key].update({k: v for k, v in raw[key].items() if k in defaults[key]})
                    else:
                        effective[key] = raw[key]
                    supplied.append(key)
            state = "saved_with_defaults"
        except (OSError, ValueError, TypeError, AttributeError):
            effective = copy.deepcopy(defaults)
            state = "defaults_invalid_file"
            warnings.append("Settings file is unreadable/invalid; the app falls back to defaults.")
            supplied = []
    return {"effective": effective, "source": path.name, "state": state,
            "saved_keys": supplied, "defaulted_keys": [k for k in defaults if k not in supplied],
            "version": fingerprint(effective), "warnings": warnings}


def load_strategy(path=None) -> dict:
    result = _load(Path(path or ROOT / "etf_settings.json"), {
        "weights": dict(DEFAULT_WEIGHTS), "excluded": list(DEFAULT_EXCLUDED),
        "stop_loss_pct": .20, "buy_zone": 8}, merge_weights=True)
    settings = result["effective"]
    valid = True
    def numeric(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not numeric(settings["stop_loss_pct"]) or not 0 <= settings["stop_loss_pct"] <= 1:
        result["warnings"].append("Invalid saved stop_loss_pct; review cannot assess this threshold.")
        valid = False
    if isinstance(settings["buy_zone"], bool) or not isinstance(settings["buy_zone"], int) or settings["buy_zone"] < 1:
        result["warnings"].append("Invalid saved buy_zone.")
        valid = False
    if not isinstance(settings["excluded"], list) or any(not isinstance(t, str) for t in settings["excluded"]):
        result["warnings"].append("Invalid saved exclusions.")
        valid = False
    weights = settings["weights"]
    if any(not numeric(v) or v < 0 for v in weights.values()):
        result["warnings"].append("Saved weights contain invalid values.")
        valid = False
    elif abs(sum(weights.values()) - 1) > 1e-6:
        result["warnings"].append("Saved weights do not sum to 1; values are exposed without normalising them.")
    result["valid_for_review"] = valid and result["state"] != "defaults_invalid_file"
    return result


def load_backtest(path=None) -> dict:
    return _load(Path(path or ROOT / "backtest_config.json"), BACKTEST_DEFAULTS)

FULL_UNIVERSE = {
    # YieldMax single-stock covered call
    'TSLY': ('YieldMax TSLA', 'TSLA', 'weekly'),
    'NVDY': ('YieldMax NVDA', 'NVDA', 'weekly'),
    'CONY': ('YieldMax COIN', 'COIN', 'weekly'),
    'MSTY': ('YieldMax MSTR', 'MSTR', 'weekly'),
    'AMZY': ('YieldMax AMZN', 'AMZN', 'weekly'),
    'APLY': ('YieldMax AAPL', 'AAPL', 'weekly'),
    'GOOY': ('YieldMax GOOGL', 'GOOGL', 'weekly'),
    'MSFO': ('YieldMax MSFT', 'MSFT', 'weekly'),
    'AMDY': ('YieldMax AMD', 'AMD', 'weekly'),
    'PYPY': ('YieldMax PYPL', 'PYPL', 'weekly'),
    'MRNY': ('YieldMax MRNA', 'MRNA', 'weekly'),
    'AIYY': ('YieldMax AI', 'AI', 'weekly'),
    'ULTY': ('YieldMax Ultra', 'diversified', 'weekly'),
    'YMAX': ('YieldMax Universe FoF', 'diversified', 'weekly'),
    'YMAG': ('YieldMax Mag7 FoF', 'mag7', 'weekly'),
    'XOMO': ('YieldMax XOM', 'XOM', 'weekly'),
    'JPMO': ('YieldMax JPM', 'JPM', 'weekly'),
    # Defiance index income
    'QQQY': ('Defiance Nasdaq Income', 'QQQ', 'weekly'),
    'IWMY': ('Defiance R2K Income', 'IWM', 'weekly'),
    'SPYT': ('Defiance S&P Target Income', 'SPY', 'monthly'),
    # Roundhill
    'QDTE': ('Roundhill Nasdaq 0DTE', 'QQQ', 'weekly'),
    'XDTE': ('Roundhill S&P 0DTE', 'SPY', 'weekly'),
    'RDTE': ('Roundhill R2K 0DTE', 'IWM', 'weekly'),
    # Monthly payers — index covered call / premium income
    'JEPI': ('JPM Equity Premium Income', 'SPX', 'monthly'),
    'JEPQ': ('JPM Nasdaq Premium Income', 'NDX', 'monthly'),
    'QYLD': ('Global X Nasdaq Covered Call', 'NDX', 'monthly'),
    'XYLD': ('Global X S&P Covered Call', 'SPX', 'monthly'),
    'RYLD': ('Global X R2K Covered Call', 'RUT', 'monthly'),
    'DIVO': ('Amplify CWP Enhanced Div', 'diversified', 'monthly'),
    'SVOL': ('Simplify Volatility Premium', 'VIX-short', 'monthly'),
    'SPYI': ('NEOS S&P High Income', 'SPX', 'monthly'),
    'QQQI': ('NEOS Nasdaq High Income', 'NDX', 'monthly'),
}


DEFAULT_WEIGHTS = {
    'nav_3m'       : 0.20,   # 3m price change rank
    'nav_12m'      : 0.10,   # 12m price change rank
    'sharpe'       : 0.15,   # 90d sharpe rank
    'yield_ttm'    : 0.10,   # trailing yield rank (deliberately low — yield alone misleads)
    'dist_slope'   : 0.15,   # distribution trend rank
    'dist_consist' : 0.10,   # distribution consistency rank
    'underlying_rs': 0.20,   # underlying's relative strength vs SPY
}


BACKTEST_DEFAULTS = {'top_n': 5, 'years': 3, 'start_capital': 100000, 'freq_filter': 'all',
            'hedge_enabled': False, 'hedge_pct': 0.10,
            'income_mode': 'reinvest',      # 'reinvest' | 'draw'
            'draw_threshold_pct': 0.10,     # buffer above start capital before drawing
            'bench_ticker': 'JEPI',         # passive income benchmark — same rules, one fund
            'rebal_freq': 'quarterly',      # 'monthly' | 'quarterly' | 'semiannual'
            'stop_loss_pct': 0.0}           # total-return stop from entry, 0 = off
                                            # (price + divs received, NOT raw price — income
                                            #  funds mechanically bleed price via distributions)
