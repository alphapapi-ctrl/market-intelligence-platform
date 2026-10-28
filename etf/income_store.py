"""Append-only Income outputs alongside the existing daily dashboard stores."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from uuid import uuid4

from .income_config import SCHEMA_VERSION, fingerprint


def clean(value):
    """JSON-safe pandas/numpy values without allowing non-finite numbers."""
    import pandas as pd
    return json.loads(pd.Series([value], dtype=object).to_json(orient="values", date_format="iso"))[0]


def _frame(con, name, frame, created, immutable=False):
    buf = io.BytesIO()
    frame.to_parquet(buf, index=False)
    verb = "INSERT" if immutable else "INSERT OR REPLACE"
    con.execute(f"{verb} INTO frames(name,updated,n_rows,blob) VALUES(?,?,?,?)",
                (name, created, len(frame), buf.getvalue()))


def save_generation(kind: str, frames: dict, configuration: dict, *, summary=None, sources=None) -> dict:
    """Persist exact-run frames + config, and keep the existing daily keys compatible."""
    if kind not in ("etf_income", "etf_backtest"):
        raise ValueError("Unknown Income output kind")
    from marketdb import db
    from market_mcp.version import code_version
    stamp = datetime.now(timezone.utc)
    run_id = stamp.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:12]
    created, day = stamp.isoformat(), datetime.today().strftime("%Y%m%d")
    manifest = {label: f"{kind}_runs/{run_id}/{label}" for label in frames}
    payload = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "kind": kind,
               "strategy_id": "etf_income", "portfolio_id": None, "created_at": created, "code_version": code_version(),
               "job_id": os.environ.get("MARKET_MCP_JOB_ID"), "run_date": datetime.today().date().isoformat(), "configuration": configuration,
               "configuration_version": fingerprint(configuration), "frames": manifest,
               "row_counts": {label: len(frame) for label, frame in frames.items()},
               "summary": summary, "sources": sources or {}, "holdings_inferred": False}
    with db.session() as con:
        for label, frame in frames.items():
            _frame(con, manifest[label], frame, created, immutable=True)
            legacy = f"{kind}/{day}" if kind == "etf_income" else f"{kind}/{day}/{label}"
            _frame(con, legacy, frame, db.now_iso())
        # A unique immutable report retains every run, including multiple runs in one day.
        con.execute("INSERT INTO reports(kind,date,text,payload,created) VALUES(?,?,?,?,?)",
                    (kind + "_run", run_id, None, json.dumps(clean(payload), allow_nan=False), created))
        daily_payload = summary if kind == "etf_backtest" else payload
        con.execute("INSERT OR REPLACE INTO reports(kind,date,text,payload,created) VALUES(?,?,?,?,?)",
                    (kind, datetime.today().strftime("%Y-%m-%d"), None, json.dumps(clean(daily_payload), allow_nan=False), db.now_iso()))
        con.commit()
    return payload


def save_review(snapshot: dict) -> dict:
    """Write a content-addressed review once; never overwrite another review."""
    from marketdb import db
    review_id = snapshot["review_id"]
    text = json.dumps(snapshot, sort_keys=True, allow_nan=False)
    with db.session() as con:
        previous = con.execute("SELECT payload FROM reports WHERE kind='etf_income_review' AND date=?", (review_id,)).fetchone()
        if previous:
            if json.loads(previous[0]) != snapshot:
                raise ValueError("Review identity collision; existing snapshot has been preserved")
        else:
            con.execute("INSERT INTO reports(kind,date,text,payload,created) VALUES('etf_income_review',?,?,?,?)",
                        (review_id, None, text, datetime.now(timezone.utc).isoformat()))
            con.commit()
    return {"kind": "etf_income_review", "review_id": review_id, "report_date": review_id,
            "configuration_version": snapshot["configuration"]["version"],
            "warnings": snapshot["warnings"]}
