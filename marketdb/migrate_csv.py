"""One-off migration of the legacy CSV world into data/market.db.

    python -m marketdb.migrate_csv            # full import (safe to re-run; upserts)
    python -m marketdb.migrate_csv --dry-run  # report only

Imports
  * stocks/watchlist/*.csv            -> securities + security_groups (non-AU/US rows dropped,
                                         listed in stocks/results/migration_dropped_tickers.csv)
  * RRG TICKERS dicts                 -> theme groups rrg_au / rrg_us / rrg_dow + INDEX rows
  * macro / dashboard live tickers    -> role 'macro' rows (GLOBAL region allowed)
  * results/breadth/*_history.csv     -> breadth_daily
  * results/rrg/*_history.csv         -> rrg_history
  * results/{screener,benchmark}/*/*_latest.csv -> study_results (gives delta_rank a baseline)
  * results/substantial_holders       -> asx_holder_notices
  * results/demark/*_demark.csv       -> demark_signals (+ report txt)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import db, universe
from .breadth_format import wide_to_long

STOCKS = db.BASE_DIR / "stocks"
WL     = STOCKS / "watchlist"
RES    = STOCKS / "results"
DROPPED_FILE = db.DATA_DIR / "migration_dropped_tickers.csv"

# Legacy type vocab -> attr
_TYPE_MAP = {"producer": "producer", "explorer": "explorer",
             "royalties_financial_services": "royalty", "ETF": "ETF",
             "Miners & Producers": "producer", "etf": "ETF", "futures": "futures", "index": "index"}

# Macro / dashboard reference symbols (kept in the price store under role 'macro')
MACRO_TICKERS = {
    # macro_data.py
    "GC=F": "Gold", "SI=F": "Silver", "HG=F": "Copper", "CL=F": "WTI Crude", "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100", "IWM": "Russell 2000 ETF", "ITB": "Home Construction ETF",
    "XLY": "Consumer Disc", "XLP": "Consumer Staples", "RSPD": "EW Consumer Disc",
    "RSPS": "EW Consumer Staples", "XLK": "Technology", "XLC": "Communication", "XLU": "Utilities",
    "XLV": "Health Care", "XLF": "Financials", "XLI": "Industrials", "XLB": "Materials",
    "XLE": "Energy", "XLRE": "Real Estate", "^VIX": "VIX", "^VVIX": "VVIX", "^VIX3M": "VIX 3M",
    "DX-Y.NYB": "DXY",
    # dashboard LIVE_TICKERS
    "RSP": "S&P 500 Equal Weight", "^AXJO": "ASX 200", "^AORD": "All Ordinaries", "^N225": "Nikkei 225",
    "^GSPTSE": "TSX", "^FTSE": "FTSE 100", "^GDAXI": "DAX", "^HSI": "Hang Seng", "^KS11": "KOSPI",
    "AUDUSD=X": "AUD/USD", "GBPUSD=X": "GBP/USD", "EURUSD=X": "EUR/USD", "NZDUSD=X": "NZD/USD",
    "JPY=X": "USD/JPY", "CHF=X": "USD/CHF", "^SPGSCI": "GSCI", "PL=F": "Platinum", "PA=F": "Palladium",
    "^SPGSIK": "GSCI Nickel", "NG=F": "Nat Gas", "^TNX": "US 10Y", "^IRX": "US 13W", "^FVX": "US 5Y",
    "^TYX": "US 30Y", "^HGX": "PHLX Housing", "^DJI": "Dow Jones", "^MOVE": "MOVE", "^AXVI": "ASX VIX",
    # credit (consumer_credit.py / au_credit.py)
    "HYG": "HY Corp", "JNK": "HY Corp (JNK)", "LQD": "IG Corp", "TLT": "20Y+ Treasury", "SHY": "1-3Y Treasury",
    "EMB": "EM Bonds", "BX": "Blackstone", "KKR": "KKR", "APO": "Apollo", "CG": "Carlyle", "PSP": "PE ETF",
    "BIZD": "BDC ETF", "ARCC": "Ares Capital", "MAIN": "Main Street Capital", "BKLN": "Leveraged Loans",
    "CRED.AX": "AU Corp Bond", "QPON.AX": "AU Floating Rate", "HBRD.AX": "AU Hybrids", "SUBD.AX": "AU Sub Debt",
    "VGB.AX": "AU Govt Bond", "IAF.AX": "AU Fixed Interest",
}
MACRO_ETF = {"IWM", "ITB", "XLY", "XLP", "RSPD", "RSPS", "XLK", "XLC", "XLU", "XLV", "XLF", "XLI", "XLB",
             "XLE", "XLRE", "RSP", "HYG", "JNK", "LQD", "TLT", "SHY", "EMB", "PSP", "BIZD", "BKLN",
             "CRED.AX", "QPON.AX", "HBRD.AX", "SUBD.AX", "VGB.AX", "IAF.AX"}


def _quote_type(ticker: str, hint: str | None = None) -> str:
    t = ticker.upper()
    if t.startswith("^"):
        return "INDEX"
    if t.endswith("=F"):
        return "FUTURE"
    if t.endswith("=X") or t == "DX-Y.NYB":
        return "CURRENCY"
    if hint:
        return hint
    return "EQUITY"


def _read_wl(name: str) -> pd.DataFrame:
    df = pd.read_csv(WL / name, encoding="utf-8", encoding_errors="replace")
    df.columns = df.columns.str.strip()
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df = df[df["ticker"].ne("") & df["ticker"].ne("nan")]
    if "name" in df.columns:
        df["name"] = df["name"].astype(str).str.strip()
    return df


def _mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


class Migration:
    def __init__(self, con, dry_run=False):
        self.con = con
        self.dry = dry_run
        self.securities: dict[str, dict] = {}
        self.groups: dict[tuple, dict] = {}
        self.dropped: list[dict] = []
        self.today = db.today_str()

    # ── securities / groups accumulation ──────────────────────────────────────
    def add_security(self, ticker: str, **fields):
        region = universe.region_of(ticker)
        if region is None:
            self.dropped.append({"ticker": ticker, "name": fields.get("name"),
                                 "source": fields.get("source"), "reason": "non AU/US listing"})
            return False
        row = self.securities.setdefault(ticker, {"ticker": ticker, "region": region,
                                                  "active": 1, "first_seen": self.today,
                                                  "source": "migration"})
        for k, v in fields.items():
            if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
                continue
            # don't let a later, sparser watchlist overwrite a richer value
            if k in row and row[k] not in (None, "") and k in ("legacy_sector", "legacy_industry", "name", "benchmark"):
                continue
            row[k] = v
        row["quote_type"] = _quote_type(ticker, row.get("quote_type"))
        return True

    def add_group(self, ticker, gtype, gkey, attr=None, source="migration"):
        if ticker not in self.securities:
            return
        self.groups[(ticker, gtype, gkey)] = {"ticker": ticker, "group_type": gtype, "group_key": gkey,
                                              "attr": attr, "source": source, "updated": self.today}

    # ── watchlists ────────────────────────────────────────────────────────────
    def import_watchlists(self):
        # AU total market
        df = _read_wl("asx_all_watchlist.csv"); mt = _mtime(WL / "asx_all_watchlist.csv")
        for r in df.itertuples(index=False):
            is_bench = str(r.benchmark) == "benchmark"
            ok = self.add_security(r.ticker, name=r.name,
                                   legacy_sector=None if is_bench else r.sector,
                                   legacy_industry=None if is_bench else r.industry,
                                   market_cap=None if is_bench else r.market_cap,
                                   benchmark=None if is_bench else r.benchmark,
                                   quote_type="ETF" if is_bench else "EQUITY", mcap_updated=mt,
                                   source="watchlist:asx_all")
            if ok and is_bench:
                self.add_group(r.ticker, "role", "benchmark", "AU Total Market")
        # US total market
        df = _read_wl("us_all_watchlist.csv"); mt = _mtime(WL / "us_all_watchlist.csv")
        for r in df.itertuples(index=False):
            is_bench = str(r.benchmark) == "benchmark"
            ok = self.add_security(r.ticker, name=r.name,
                                   legacy_sector=None if is_bench else r.sector,
                                   legacy_industry=None if is_bench else (r.industry if pd.notna(r.industry) else None),
                                   market_cap=None if is_bench else r.market_cap,
                                   benchmark=None if is_bench else r.benchmark,
                                   quote_type="ETF" if is_bench else "EQUITY", mcap_updated=mt,
                                   source="watchlist:us_all")
            if ok and is_bench:
                self.add_group(r.ticker, "role", "benchmark", "US Total Market")
            elif ok and pd.notna(r.industry) and str(r.industry).strip():
                # legacy "has industry" == S&P 500 / Nasdaq quality layer
                self.add_group(r.ticker, "index", "SP500_LEGACY", "legacy has-industry proxy")
        # Nasdaq 100
        df = _read_wl("nasdaq100.csv")
        for r in df.itertuples(index=False):
            is_bench = str(r.benchmark) == "benchmark"
            ok = self.add_security(r.ticker, name=r.name,
                                   legacy_sector=None if is_bench else r.sector,
                                   legacy_industry=None if is_bench else r.industry,
                                   market_cap=None if is_bench else r.market_cap,
                                   quote_type="INDEX" if is_bench else "EQUITY",
                                   source="watchlist:nasdaq100")
            if ok and is_bench:
                self.add_group(r.ticker, "role", "benchmark", "Nasdaq 100")
            elif ok:
                self.add_group(r.ticker, "index", "NDX100", "legacy watchlist")
        # Commodities
        df = _read_wl("all_major_commodities.csv"); mt = _mtime(WL / "all_major_commodities.csv")
        for r in df.itertuples(index=False):
            is_bench = str(r.benchmark) == "benchmark"
            comm = str(r.commodity).strip().lower()
            ok = self.add_security(r.ticker, name=r.name, market_cap=None if is_bench else r.market_cap,
                                   quote_type="ETF" if is_bench else "EQUITY", mcap_updated=mt,
                                   source="watchlist:commodities")
            if not ok:
                continue
            if is_bench:
                self.add_group(r.ticker, "role", "benchmark", f"{comm} ETF")
                self.add_group(r.ticker, "commodity", comm, "ETF")
            else:
                self.add_group(r.ticker, "commodity", comm, _TYPE_MAP.get(str(r.type).strip(), str(r.type).strip()))
        # Uranium
        df = _read_wl("uranium_watchlist.csv"); mt = _mtime(WL / "uranium_watchlist.csv")
        for r in df.itertuples(index=False):
            is_bench = str(r.benchmark) == "benchmark"
            ok = self.add_security(r.ticker, name=r.name, market_cap=None if is_bench else r.market_cap,
                                   quote_type="ETF" if is_bench else "EQUITY", mcap_updated=mt,
                                   source="watchlist:uranium")
            if ok and is_bench:
                self.add_group(r.ticker, "role", "benchmark", "Uranium ETF")
                self.add_group(r.ticker, "commodity", "uranium", "ETF")
            elif ok:
                self.add_group(r.ticker, "commodity", "uranium",
                               self.groups.get((r.ticker, "commodity", "uranium"), {}).get("attr") or "producer")
        # AU gold miners
        df = _read_wl("au_gold_miners_watchlist.csv"); mt = _mtime(WL / "au_gold_miners_watchlist.csv")
        for r in df.itertuples(index=False):
            is_bench = str(r.benchmark) == "benchmark"
            ok = self.add_security(r.ticker, name=r.name, market_cap=None if is_bench else r.market_cap,
                                   quote_type="ETF" if is_bench else "EQUITY", mcap_updated=mt,
                                   source="watchlist:au_gold")
            if ok and is_bench:
                self.add_group(r.ticker, "role", "benchmark", "Gold miners ETF")
                self.add_group(r.ticker, "commodity", "gold", "ETF")
            elif ok:
                self.add_group(r.ticker, "commodity", "gold", _TYPE_MAP.get(str(r.type).strip(), "producer"))
                self.add_group(r.ticker, "theme", "au_gold_miners", "AU Gold Miners")
        # commodities futures + reference ETF watchlists (macro context)
        for fn, role in [("commodities_watchlist.csv", "macro"), ("etfs_watchlist.csv", "macro")]:
            if not (WL / fn).exists():
                continue
            df = _read_wl(fn)
            for r in df.itertuples(index=False):
                ok = self.add_security(r.ticker, name=r.name, legacy_sector=r.sector,
                                       quote_type=_quote_type(r.ticker, "ETF" if str(r.type).lower() == "etf" else None),
                                       source=f"watchlist:{fn}")
                if ok:
                    self.add_group(r.ticker, "role", role, r.sector)

    # ── RRG dictionaries + macro tickers ──────────────────────────────────────
    def import_rrg_and_macro(self):
        for d in (STOCKS / "legacy", STOCKS):          # RRG dicts live in the legacy scripts now
            if d.exists() and str(d) not in sys.path:
                sys.path.insert(0, str(d))
        for mod, theme, bench in [("rrg_au_data", "rrg_au", "^AXJO"), ("rrg_us_data", "rrg_us", "SPY"),
                                  ("rrg_dow_data", "rrg_dow", "^DJI")]:
            try:
                m = __import__(mod)
            except Exception as e:  # legacy module may have moved
                print(f"  RRG import {mod}: {e}")
                continue
            for t, (name, grp) in m.TICKERS.items():
                qt = "INDEX" if t.startswith("^") else ("EQUITY" if theme == "rrg_dow" else "ETF")
                if self.add_security(t, name=name, quote_type=qt, source=f"rrg:{mod}"):
                    self.add_group(t, "theme", theme, name)
                    self.add_group(t, "theme", f"{theme}:{grp}", name)
            if self.add_security(bench, name=bench, quote_type="INDEX" if bench.startswith("^") else "ETF",
                                 source=f"rrg:{mod}"):
                self.add_group(bench, "role", "benchmark", f"RRG {theme}")
        # RSP for the us_rsp study
        if self.add_security("RSP", name="S&P 500 Equal Weight", quote_type="ETF", source="rrg:us_rsp"):
            self.add_group("RSP", "role", "benchmark", "RRG us_rsp")
        for t, name in MACRO_TICKERS.items():
            qt = "ETF" if t in MACRO_ETF else _quote_type(t)
            if self.add_security(t, name=name, quote_type=qt, source="macro"):
                self.add_group(t, "role", "macro", name)

    # ── write universe tables ─────────────────────────────────────────────────
    def write_universe(self):
        sec = pd.DataFrame(list(self.securities.values()))
        # cap band under the region scheme (commodity universes recompute their own)
        sec["cap_band"] = [("ETF" if qt != "EQUITY" else universe.cap_band_for(mc, reg if reg in ("AU", "US") else "US"))
                           for qt, mc, reg in zip(sec["quote_type"], sec["market_cap"], sec["region"])]
        grp = pd.DataFrame(list(self.groups.values()))
        print(f"  securities: {len(sec)}  (AU {int((sec.region=='AU').sum())}, US {int((sec.region=='US').sum())}, "
              f"GLOBAL {int((sec.region=='GLOBAL').sum())})   groups: {len(grp)}   dropped: {len(self.dropped)}")
        if self.dropped:
            pd.DataFrame(self.dropped).drop_duplicates("ticker").to_csv(DROPPED_FILE, index=False)
            print(f"  dropped tickers listed in {DROPPED_FILE}")
        if self.dry:
            return
        db.upsert_df(sec, "securities", self.con)
        db.upsert_df(grp, "security_groups", self.con)
        self.con.commit()

    # ── results ───────────────────────────────────────────────────────────────
    def import_breadth(self):
        files = {"au_total_market": RES / "breadth/au_total_market/au_total_market_breadth_history.csv",
                 "us_total_market": RES / "breadth/us_total_market/us_total_market_breadth_history.csv",
                 "all_major_commodities": RES / "breadth/all_major_commodities/all_major_commodities_breadth_history.csv"}
        for uni, f in files.items():
            if not f.exists():
                print(f"  breadth {uni}: missing {f}")
                continue
            h = pd.read_csv(f)
            rows = []
            for rec in h.to_dict("records"):
                rows.extend(wide_to_long(rec, uni))
            print(f"  breadth {uni}: {len(h)} days -> {len(rows)} cells")
            if not self.dry:
                self.con.executemany("INSERT OR REPLACE INTO breadth_daily VALUES (?,?,?,?,?,?,?)", rows)
                self.con.commit()

    def import_rrg(self):
        files = {"au": "au_rrg_history.csv", "us": "us_rrg_history.csv",
                 "us_rsp": "us_rrg_rsp_history.csv", "dow": "dow_rrg_history.csv"}
        for study, fn in files.items():
            f = RES / "rrg" / fn
            if not f.exists():
                continue
            h = pd.read_csv(f)
            h["date"] = pd.to_datetime(h["date"]).dt.strftime("%Y-%m-%d")
            h = h.rename(columns={"group": "grp"}).assign(study=study)
            h = h.drop_duplicates(["date", "study", "ticker"], keep="last")
            print(f"  rrg {study}: {len(h)} rows")
            if not self.dry:
                db.upsert_df(h, "rrg_history", self.con)
                self.con.commit()

    def import_latest_results(self):
        mapping = [  # (study, universe, path)
            ("screener",  "au_total_market",       RES / "screener/au_total_market/au_total_market_latest.csv"),
            ("benchmark", "au_total_market",       RES / "benchmark/au_total_market/au_total_market_latest.csv"),
            ("screener",  "us_total_market",       RES / "screener/us_sp500/us_sp500_latest.csv"),
            ("benchmark", "us_total_market",       RES / "benchmark/us_sp500/us_sp500_latest.csv"),
            ("screener",  "nasdaq100",             RES / "screener/nasdaq100/nasdaq100_latest.csv"),
            ("benchmark", "nasdaq100",             RES / "benchmark/us_nasdaq/us_nasdaq_benchmark_latest.csv"),
            ("screener",  "all_major_commodities", RES / "screener/all_major_commodities/all_major_commodities_latest.csv"),
            ("benchmark", "all_major_commodities", RES / "benchmark/all_major_commodities/all_major_commodities_latest.csv"),
            ("screener",  "uranium",               RES / "screener/uranium/uranium_latest.csv"),
            ("benchmark", "uranium",               RES / "benchmark/uranium/uranium_latest.csv"),
            ("screener",  "au_gold_miners",        RES / "screener/au_gold_miners/au_gold_miners_latest.csv"),
            ("benchmark", "au_gold_miners",        RES / "benchmark/au_gold_miners/au_gold_miners_latest.csv"),
        ]
        for study, uni, f in mapping:
            if not f.exists():
                print(f"  results {study}/{uni}: missing")
                continue
            d = pd.read_csv(f)
            d = d.assign(study=study, universe=uni, run_date=_mtime(f))
            d = d[d["ticker"].map(lambda t: universe.region_of(str(t)) is not None)]
            d = d.drop_duplicates(["run_date", "study", "universe", "ticker"])
            # actionable flags as the legacy save_results defined them
            if {"acc_watch", "cap_band", "vol_label", "regime_label"} <= set(d.columns):
                a = ((d["acc_watch"] != "-") & d["cap_band"].isin(["large", "mid"]) &
                     d["vol_label"].isin(["HIGH", "MED"]) & d["regime_label"].isin(["LEADER", "CONTENDER", "TREND+LEAD", "TREND_ONLY"])) | \
                    ((d["vol_label"] == "HIGH") & d["regime_label"].isin(["LEADER", "TREND+LEAD"]))
                d["actionable"] = a.astype(int)
                d["high_conv"] = ((d["vol_label"] == "HIGH") & (d["acc_watch"] != "-") &
                                  (d["score_final"] > 0)).astype(int)
            print(f"  results {study}/{uni}: {len(d)} rows dated {d['run_date'].iloc[0]}")
            if not self.dry:
                db.upsert_df(d, "study_results", self.con)
                self.con.commit()

    def import_holders(self):
        f = RES / "substantial_holders/substantial_holders_history.csv"
        if not f.exists():
            return
        h = pd.read_csv(f, dtype={"ann_id": str})
        core = ["ann_id", "date", "ticker", "form", "title"]
        extra = [c for c in h.columns if c not in core]
        out = h[core].copy()
        out["url"] = h["pdf_url"] if "pdf_url" in h.columns else None
        out["company"] = h["company"] if "company" in h.columns else None
        out["payload"] = [json.dumps({k: (None if pd.isna(v) else v) for k, v in r.items()})
                          for r in h[extra].to_dict("records")]
        out = out.drop_duplicates("ann_id")
        print(f"  substantial holders: {len(out)} notices")
        if not self.dry:
            db.upsert_df(out, "asx_holder_notices", self.con)
            self.con.commit()

    def import_demark(self):
        files = sorted(glob.glob(str(RES / "demark" / "*_demark.csv")))[-5:]
        for f in files:
            date = os.path.basename(f)[:8]
            run_date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
            d = pd.read_csv(f).assign(run_date=run_date)
            d = d.rename(columns={"d_setup": "d_setup_count", "w_setup": "w_setup_count"})
            rep = Path(f.replace("_demark.csv", "_demark_report.txt"))
            if not self.dry:
                db.upsert_df(d, "demark_signals", self.con)
                if rep.exists():
                    self.con.execute("INSERT OR REPLACE INTO demark_reports VALUES (?,?)",
                                     (run_date, rep.read_text(encoding="utf-8", errors="replace")))
                self.con.commit()
        print(f"  demark: {len(files)} scans")

    def import_reports(self):
        """macro/results: dated macro reports, rolling snapshot, consumer/AU credit JSON + txt -> reports."""
        from . import results as R
        MR = db.BASE_DIR / "macro" / "results"
        n = 0
        def iso(d8): return f"{d8[:4]}-{d8[4:6]}-{d8[6:]}"
        for f in sorted(MR.glob("*_macro_report.txt")):
            if not self.dry: R.save_report("macro_report", iso(f.name[:8]), text=f.read_text(encoding="utf-8", errors="replace"), con=self.con)
            n += 1
        for f in sorted(MR.glob("*_cycle_tracker.txt")):
            if not self.dry: R.save_report("cycle_tracker", iso(f.name[:8]), text=f.read_text(encoding="utf-8", errors="replace"), con=self.con)
            n += 1
        snap = MR / "macro_snapshot_prev.json"
        if snap.exists():
            if not self.dry: R.save_report("macro_snapshot", "latest", payload=json.loads(snap.read_text(encoding="utf-8")), con=self.con)
            n += 1
        cc = MR / "consumer_credit"
        for f in sorted(cc.glob("*_consumer_credit.json")):
            payload = json.loads(f.read_text(encoding="utf-8"))
            txt = cc / f"{f.name[:8]}_consumer_credit_report.txt"
            if not self.dry: R.save_report("consumer_credit", iso(f.name[:8]), text=txt.read_text(encoding="utf-8", errors="replace") if txt.exists() else None, payload=payload, con=self.con)
            n += 1
        for f in sorted(cc.glob("*_au_credit.json")):
            if not self.dry: R.save_report("au_credit", iso(f.name[:8]), payload=json.loads(f.read_text(encoding="utf-8")), con=self.con)
            n += 1
        al = MR / "credit_alerts.json"
        if al.exists():
            if not self.dry: R.save_report("credit_alerts", "latest", payload=json.loads(al.read_text(encoding="utf-8")), con=self.con)
            n += 1
        print(f"  macro/credit reports: {n} imported")
        # ETF results + Burry screens
        E = db.BASE_DIR / "etf" / "results"
        m = 0
        for f in sorted((E / "etf_income").glob("*_etf_income.csv")):
            if not self.dry: R.save_frame("etf_income/" + f.name[:8], pd.read_csv(f), con=self.con)
            m += 1
        for f in sorted((E / "backtest").glob("*_summary.json")):
            d = f.name[:8]
            if not self.dry:
                R.save_report("etf_backtest", iso(d), payload=json.loads(f.read_text(encoding="utf-8")), con=self.con)
                for part in ("equity", "quarters"):
                    fp = E / "backtest" / f"{d}_{part}.csv"
                    if fp.exists(): R.save_frame(f"etf_backtest/{d}/{part}", pd.read_csv(fp), con=self.con)
            m += 1
        for f in sorted((STOCKS / "results" / "daily_actionable" / "burry_screen").glob("*_burry_*.csv")):
            if "_tvimport" in f.name: continue
            if not self.dry: R.save_frame("burry/" + f.stem, pd.read_csv(f), con=self.con)
            m += 1
        print(f"  etf / burry frames: {m} imported")
        SC = db.BASE_DIR / "sentiment" / "cache"
        k = 0
        for f in sorted(SC.glob("*.parquet")):
            name = f.stem.replace("aaii_sentiment", "aaii").replace("naaim_exposure", "naaim")
            if not self.dry: R.save_frame("sentiment/" + name, pd.read_parquet(f), con=self.con)
            k += 1
        print(f"  sentiment caches: {k} imported")

    def run(self, import_breadth: bool = True):
        print("Importing watchlists...")
        self.import_watchlists()
        print("Importing RRG + macro tickers...")
        self.import_rrg_and_macro()
        self.write_universe()
        print("Importing results...")
        if import_breadth:
            self.import_breadth()       # legacy vocabulary — bootstrap rebuilds breadth from the store instead
        self.import_rrg()
        self.import_latest_results()
        self.import_holders()
        self.import_demark()
        self.import_reports()
        if not self.dry:
            db.set_meta("migrated_at", db.now_iso(), self.con)
            self.con.commit()
        print("Done.")


def main(argv=None):
    db.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    with db.session() as con:
        Migration(con, dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
