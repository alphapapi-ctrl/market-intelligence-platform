# Market Intelligence Platform

A local market intelligence dashboard for tracking relative strength, breadth and macro conditions across AU/US equities and commodities.

Provides actionable reports for screeners and trading view watchlist to easily import them into tradingview.

Drawdown Analysis Tool:
Choose up to 3 priods of time to conduct a drawdown analysis and relative strength comparison on all of the existing watchlist.  AU/US stocks, major commodities, AU gold mining, Uranium.

RRG Relative Rotation Graphs - relative strength vs relative momentum with adjustable tails up to 63 trading days.  Separate graphs for AU and US sectors.  Useful for monitoring rotation across all sectors and major metals.

Additional tools: Seasonality, DeMark 9/13 scanner, Sentiment (AAII/NAAIM/COT), Debt Markets, ETF
Income strategy, Fundamental Analysis (local LLM + RAG).

## Data layer (marketdb)

All AU/US price data and study results live in one SQLite database, `data/market.db`, managed by
the `marketdb` package (design: `docs/marketdb_design.md`):

- `securities` / `security_groups` — the universe: every AU and US listing with Yahoo sector &
  industry, market cap, cap band, index membership (ASX 20/50/200, S&P 500, Nasdaq-100, Dow) and
  commodity flags (gold, silver, copper, platinum, palladium, iron ore, nickel, uranium, lithium,
  oil & gas — many per stock, one marked primary; edited on the Commodities → Exposures tab). Universes such as
  `au_total_market` or `au_gold_miners` are *queries* over these tables, defined in
  `marketdb/universe_config.json`. Manual tweaks go in `stocks/universe_overrides.json`.
- `prices` — daily OHLCV + adjusted close for ~5,000 symbols, fetched **once** per day,
  incrementally (only the new bars), in throttled chunks with retries and corporate-action
  drift detection.
- `study_results`, `breadth_daily`, `rrg_history`, `demark_signals`, `drawdown_results`,
  `asx_holder_notices` — what the dashboard reads.

```bash
python -m marketdb.run_daily                  # daily: update prices, run every study
python -m marketdb.run_daily --universe au_total_market --studies screener
python -m marketdb.refresh_universe           # monthly: new listings, delistings, sectors, caps, indices
python -m marketdb.refresh_universe --dry-run # preview the monthly changes
python -m marketdb.run_daily --repair-splits   # one-off: back-adjust splits Yahoo left unadjusted (runs after every fetch anyway)
```

The daily run performs the monthly refresh automatically when the universe is more than 31 days
old (`refresh.auto_monthly_refresh` in `universe_config.json`). To schedule the daily run from
Windows Task Scheduler instead of the dashboard button:

```bash
schtasks /Create /TN "MarketDB Daily" /SC DAILY /ST 07:45 /TR "C:\Users\pc\Project\.venv\Scripts\python.exe -m marketdb.run_daily" /F
```

### First run on a fresh clone (or a new machine)

The database is not in git (it is ~500 MB and rebuilds itself). After `pip install -r requirements.txt`:

```bash
python -m marketdb.bootstrap
```

≈ 15 minutes: seeds the universe from the tracked `stocks/watchlist/*.csv`, runs the Yahoo
universe refresh, back-fills three years of prices for ~5,000 symbols, rebuilds the breadth
history from those prices, runs every screener/benchmark/RRG and a DeMark scan, and — if
`macro/config.py` is in place — the macro and credit reports too (otherwise it prints the
setup steps and the Macro / Debt Markets pages show the same notice until you run
`python launcher.py 1 16 17`). From then on `python launcher.py A` (macro report + market
data) or `python -m marketdb.run_daily` (market data only) is all that is needed.
Alternatively copy `data/market.db` from another machine and go straight to the daily run.

Pulling this change onto an existing checkout of the old layout needs the same one-off
bootstrap; the old `stocks/results/` CSV trees are no longer read or written.

## Requirements
- Python 3.10+
- See `requirements.txt` for all dependencies

## Installation

1. Clone the repo
2. Create and activate a virtual environment:

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac

3. Install dependencies:
pip install -r requirements.txt

4. Set up the FRED API key (the Macro and Debt Markets pages need it):
   - Copy `macro/config_template.py` to `macro/config.py`
   - Add your FRED API key (free at fred.stlouisfed.org/docs/api/api_key.html)
   - `config.py` is gitignored, so repeat this on every machine. Without it those pages show a
     notice explaining exactly this, and the macro scripts exit with the same instructions.

## Launch
streamlit run dashboard.py

## Full Documentation
See `Market_Intelligence_Platform_Guide_v1.4.docx` in "docs" folder for complete installation, usage and technical reference.

Upload to your own AI to allow it to understand how all scripts work and calculations to allow for modification/additions.

## Dashboard Pages
- **Macro** — VIX regime, live market readings, macro cycle positioning
- **AU/US Market** — breadth (5-panel chart + tables), benchmark RS, sector peer screener;
  tables filter by regime, sector, acc-watch, volume, cap band and RSI divergence, and carry
  RSI(14) divergence (`rsi_div`) and OBV-vs-price divergence/convergence (`obv_div`) columns
- **Commodities** — *All | Metals | Energy | Exposures* tabs over gold, silver, copper,
  platinum, palladium, iron ore, nickel (Metals) and uranium, lithium, oil & gas (Energy);
  country / commodity / type / cap-band / volume filters; per-stock multi-exposure editor with a
  primary exposure, "add a new commodity", and a business-summary scan that proposes secondary
  exposures (e.g. a gold miner's lithium or copper project) for one-click review
- **RRG Charts** — relative rotation graphs with downloadable PNG
- **Breadth RRG** — sector breadth participation rotation graph (Ab20/50/200)
- **DeMark Signals** — TD Setup 9 and Countdown 13 scanner, daily and weekly, US market
- **Drawdown Analysis** — period-based performance analysis vs benchmark and peers
- **Screeners & Exports** — actionable lists per market with a page-level regime / volume /
  cap-band / acc-watch / RSI-divergence filter row; TradingView and CSV exports contain exactly the rows shown
- **Seasonality / Sentiment / Debt Markets / ETF Income / Fundamental Analysis** — see the pages
- **Run Scripts** — daily marketdb run, per-market runs, monthly universe refresh, maintenance
- **Settings** — toggle pages on/off