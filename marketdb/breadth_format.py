"""Convert breadth rows between the old wide CSV layout (one column per
group × metric, e.g. ``sec_financials_above200``) and the long table
``breadth_daily(date, universe, layer, group_type, group_key, metric, value)``.

The two functions are exact inverses for every column name the legacy
breadth scripts produced, so the dashboard can keep using the wide names.
"""
from __future__ import annotations

import re

import pandas as pd

# longest first so 'above_200' wins over 'above_20', 'high_vol' over 'vol'
METRICS = ["acc_progress", "acc_early", "acc_shift", "above_200", "above_20", "above_50",
           "above200", "above20", "above50", "high_vol", "contender", "laggard",
           "leaders", "leader", "total", "weak"]
_METRIC_RE = re.compile(r"(?:^|_)(" + "|".join(re.escape(m) for m in METRICS) + r")$")
LAYERS = ("sp", "rus")
GROUP_PREFIX = {"sec": "sector", "ind": "industry", "comm": "commodity", "type": "type"}
CAP_BANDS = ("large", "mid", "small")


def parse_column(col: str) -> tuple[str, str, str, str] | None:
    """'rus_sec_financials_above20' -> ('rus', 'sector', 'financials', 'above20').
    Returns None for 'date' or anything unrecognised."""
    if col == "date":
        return None
    layer = "all"
    rest = col
    for l in LAYERS:
        if rest.startswith(l + "_"):
            layer = l
            rest = rest[len(l) + 1:]
            break
    m = _METRIC_RE.search(rest)
    if not m:
        return None
    metric = m.group(1)
    head = rest[: m.start()]            # '' | 'sec_financials' | 'large' | 'comm_uranium_producer'
    if head == "":
        return layer, "all", "", metric
    if head in CAP_BANDS:
        return layer, "cap", head, metric
    for pfx, gtype in GROUP_PREFIX.items():
        if head.startswith(pfx + "_"):
            return layer, gtype, head[len(pfx) + 1:], metric
    return layer, "other", head, metric


def build_column(layer: str, group_type: str, group_key: str, metric: str) -> str:
    if group_type == "all":
        body = metric
    elif group_type == "cap":
        body = f"{group_key}_{metric}"
    elif group_type == "other":
        body = f"{group_key}_{metric}"
    else:
        pfx = {v: k for k, v in GROUP_PREFIX.items()}[group_type]
        body = f"{pfx}_{group_key}_{metric}"
    return body if layer == "all" else f"{layer}_{body}"


def wide_to_long(row: dict, universe: str) -> list[tuple]:
    """One wide breadth row (dict with 'date') -> list of breadth_daily tuples."""
    date = str(row["date"])[:10]
    out = []
    for col, val in row.items():
        p = parse_column(col)
        if p is None:
            continue
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        layer, gtype, gkey, metric = p
        out.append((date, universe, layer, gtype, gkey, metric, float(val)))
    return out


def long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """breadth_daily rows (any universe, already filtered) -> wide frame sorted by date,
    with the legacy column names. Missing combinations become NaN exactly as the CSV had."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date"])
    cols = [build_column(l, t, k, m) for l, t, k, m in
            zip(df["layer"], df["group_type"], df["group_key"], df["metric"])]
    tmp = pd.DataFrame({"date": df["date"].values, "col": cols, "value": df["value"].values})
    wide = tmp.pivot_table(index="date", columns="col", values="value", aggfunc="first")
    wide = wide.reset_index().sort_values("date").reset_index(drop=True)
    wide.columns.name = None
    # legacy files had the core columns first; keep a stable, readable order
    core = ["date", "total", "leader", "contender", "laggard", "weak", "above_20", "above_50",
            "above_200", "high_vol", "acc_early", "acc_progress", "acc_shift"]
    ordered = [c for c in core if c in wide.columns] + [c for c in wide.columns if c not in core]
    return wide[ordered]
