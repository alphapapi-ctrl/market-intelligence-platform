# marketdb — consolidated data layer design

Status: implemented 2026-08-22 (see "Migration notes" at the end for what changed).

## Why

Before this change the daily run ("Run ALL") executed 16 independent scripts. Each one
re-downloaded its whole universe from Yahoo — the AU screener alone pulled the 1,760-ticker
ASX universe three times (12m close, 24m close, volume), the benchmark did the same, breadth
once more. Across AU + US + Nasdaq + commodities + uranium + gold miners that was **30+
full-universe `yf.download` calls per day**, which is exactly what triggers Yahoo throttling and
the partial frames that produced the false "breadth collapse" rows.

Every script also carried its own copy of the per-ticker metric block (returns, max DD,
persistence, vol_63, MQS, SMAs, rel_vol, acc_watch, regime), and wrote its own CSV tree —
~200 MB under `stocks/results/`, 1,086-column-wide breadth files, and watchlist CSVs that were
simultaneously input config and mutable state (the market-cap scripts rewrote them in place).

## Shape of the new layer

```
marketdb/                     shared package — used by scripts AND the dashboard
  db.py                       SQLite connection, schema creation, read/write helpers
  schema.sql                  DDL (idempotent)
  universe.py                 securities + groups: resolve a universe key -> ticker frame
  fetch.py                    the ONLY place that calls yfinance for daily bars
  prices.py                   get_prices()/get_volumes() wide frames from the DB
  metrics.py                  the shared per-ticker metric block (one implementation)
  studies.py                  screener / benchmark / breadth / rrg calculators
  results.py                  write + read study results ("latest", dated, actionable, formatted)
  refresh_universe.py         monthly: Yahoo screener -> securities; index memberships; flags
  migrate_csv.py              one-off import of the old watchlists + results history
  run_daily.py                single daily entrypoint: update prices -> run every study
data/market.db                the database (gitignored)
```

Database: **SQLite** (stdlib, single file, WAL mode). No new dependencies. Pandas reads straight
from it. If it ever outgrows SQLite the schema is plain SQL and moves to DuckDB/Postgres unchanged.

## Schema

### `securities` — one row per Yahoo symbol, AU and US only
| column | notes |
|---|---|
| ticker (PK) | Yahoo symbol: `BHP.AX`, `AAPL`, `^AXJO`, `GDX` |
| name, region (`AU`/`US`), exchange, quote_type (`EQUITY`/`ETF`/`INDEX`/`FUTURE`/`CURRENCY`) | |
| sector, industry | **Yahoo taxonomy** — the same vocabulary for AU and US (see "Sector taxonomy") |
| legacy_sector, legacy_industry | what the old watchlists said (kept for reference) |
| market_cap, cap_band | cap_band thresholds per region in `universe_config.json` |
| benchmark | default RS benchmark (`VAS.AX`, `SPY`, `GDX`, …) |
| active, first_seen, last_seen, delisted_at | lifecycle — set by the monthly refresh and the fetch log |

### `security_groups` — many-to-many flags `(ticker, group_type, group_key, attr)`
| group_type | group_key examples | attr |
|---|---|---|
| `index` | `ASX200`, `ASX300`, `ALLORDS`, `SP500`, `NDX100`, `DJIA`, `R1000`, `R2000` | |
| `commodity` | `gold`, `silver`, `copper`, `uranium`, `lithium`, `platinum`, `palladium` | `producer` / `explorer` / `royalty` / `ETF` |
| `theme` | `au_gold_miners`, `rrg_au_sector`, `rrg_us_sector`, … | display name |
| `role` | `benchmark`, `macro`, `rrg` | keeps non-equity tickers (indices, sector ETFs, futures) in the price store |

A ticker can carry any number of flags, so a copper/gold producer is in both groups; the flag with
`priority = 0` is the **primary** exposure (its peer group for RS and the commodity it is listed
under), set from the Commodities → 🪨 Exposures tab (`universe.set_exposure`). Commodity flags
come from three sources, in priority order: manual overrides (`stocks/universe_overrides.json`),
the legacy watchlists (migrated), and Yahoo industry mapping (Gold, Silver, Copper, Uranium, and the
six Oil & Gas industries → `oil_gas` typed producer/services/midstream/refining; lithium, PGMs,
iron ore and nickel have no Yahoo industry so they rely on the first two plus name keywords).
`commodity_groups` in `universe_config.json` (Metals / Energy / Other, each with a default
benchmark ETF) drive the Commodities page tabs; new commodities are registered from the same tab
via `universe.add_commodity()`.

A fourth flag source, `summary` (`marketdb/summary_scan.py`, 2026-08-23), reads each flagged
stock's Yahoo `longBusinessSummary` — stored in `securities.business_summary` and refreshed at most
every 180 days, so the scan itself is offline after the first run — and word-matches a keyword table
(`universe_config.json` → `summary_scan.keywords`) after removing the company name (so "Silver Lake
Resources" does not flag silver). By default only precious-metals stocks are scanned (the user's
stated interest: lithium crossover and multi-precious-metal producers); `--all` widens it. Hits the
stock is not yet flagged with are written to `reports(kind='summary_scan')` and reviewed on the
Exposures tab; applying them inserts secondary flags (priority 9) after pinning the existing primary
at priority 0, and rejecting them records `remove_groups` overrides that later scans honour. Summary
flags persist across the monthly refresh like every other commodity flag (only index groups are
rebuilt). Known noise: small explorers list every metal they "explore for", so the review UI
filters by cap band and mention count.

### `universes` — study universes are *queries*, not CSV files
`universe_config.json` defines each universe as a filter over `securities` + `security_groups`:

| key | definition | peer key | benchmark |
|---|---|---|---|
| au_total_market | region=AU, EQUITY, active | sector | VAS.AX |
| us_total_market | region=US, EQUITY, active | sector | SPY |
| nasdaq100 | index=NDX100 | sector | ^NDX |
| all_major_commodities | any commodity flag, region AU/US | commodity | per-commodity map |
| uranium | commodity=uranium | commodity | URA |
| au_gold_miners | commodity=gold, region=AU | commodity | GDX |

Adding a universe (e.g. `asx200`, `sp500_only`, `copper_miners`) is a config entry, not a script.

### `prices` — `(ticker, date)` → open, high, low, close, adj_close, volume, dividend, split
Unadjusted OHLCV plus Yahoo's adjusted close and corporate actions. Studies use `adj_close`
(identical to what `auto_adjust=True` returned before) and raw `volume`.

### `fetch_log` — per ticker: last fetch time, first/last bar date, row count, status, consecutive failures
Drives incremental fetching and delisting detection.

### Results
| table | grain |
|---|---|
| `study_results` | `(run_date, study ∈ {screener, benchmark}, universe, ticker)` → every metric column the old CSVs had + `delta_rank`, `actionable`, `high_conv` |
| `breadth_daily` | **long**: `(date, universe, layer, group_type, group_key, metric)` → count. Layers `all` / `sp` / `rus` (US); group types `all`, `cap`, `sector`, `industry`. The dashboard loader pivots back to the old wide `sec_<key>_<metric>` names |
| `rrg_history` | `(date, study, ticker)` → rs_ratio, rs_momentum, close |
| `demark_signals` | `(run_date, ticker)` |
| `drawdown_results` | `(study, period_label, ticker)` |
| `asx_holder_notices` | substantial-holder announcements |
| `runs` | audit of every fetch/study run: timing, coverage, status |

## Fetch layer (`marketdb/fetch.py`)

1. **One ticker set per day.** The daily runner unions every universe, every benchmark, the RRG
   index/ETF lists and the macro tickers into one list (~3,500 symbols) and fetches each once.
2. **Incremental.** A ticker with history in the DB is fetched from `last_date − 10 days`; a new
   ticker is back-filled 3 years. After the first run a daily update is a handful of bars per ticker.
3. **Chunked + throttled.** Chunks of 150 symbols, `threads=True` inside a chunk, a pause between
   chunks, exponential back-off retry (3 attempts) on exceptions/empty frames.
4. **Adjustment drift detection.** The 10-day overlap is compared with stored `adj_close`; a
   >0.1 % mismatch means a dividend/split happened → that ticker's full history is re-fetched.
   This is what makes incremental fetching safe with adjusted prices.
5. **Coverage guards** (ported from the breadth scripts): a run records fetched/expected; each
   study refuses to write if its universe coverage is below 80 %, and breadth drops any day whose
   `total` is below 90 % of the trailing-60-day median.
6. **Delisting.** 10 consecutive empty fetches → `fetch_log.status='stale'`; the monthly refresh
   marks `securities.active=0` when Yahoo no longer lists the symbol.

`get_prices(tickers, start, end)` returns the same wide `DataFrame` the old `fetch_prices()`
did, so the study code is unchanged in spirit — it just never touches the network.

## Studies (`marketdb/studies.py`)

`metrics.ticker_metrics(prices, prices_24m, volumes)` is the single implementation of the
per-ticker block. `screener()` layers peer RS (sector or commodity peers), `benchmark()` layers
RS vs a benchmark (per-ticker for commodities), both score with the `rank_settings.json` block
for that universe. `breadth()` reuses the same block per day. `rrg()` is the existing formula.

Deliberate changes from the old scripts (the 15 copies had drifted from each other —
`tests/test_metrics_parity.py` shows exact parity everywhere except these):
- Benchmark `rs_trend` uses the time-ordered `[rs_63, rs_21, rs_5]` sequence everywhere. The AU
  benchmark script alone appended the 12-month `rs_ratio` as a fourth step; US/Nasdaq and every
  screener did not. Effect: a few AU benchmark rows move one trend grade (score ±0.5).
- Benchmark lead bonus is awarded when `rs_ratio > 1` (five of the six scripts); the AU script
  alone required the 200-SMA trend as well. Default bonus sizes are 1.0/1.0 (five of six); AU keeps
  its 0.5/0.5 because those values are set explicitly in `rank_settings.json`.
- `vol_63` for tickers with fewer than 63 bars uses the bars available (AU/US rule) instead of
  `None` (commodity/uranium/gold rule), so very new listings get an MQS and a full score.
- Breadth is computed as one vectorised panel over all days (`studies.breadth_panel`): prices
  forward-filled across no-trade days, rolling SMAs, a rolling 252-bar 12-month return (first-bar
  base for younger listings), and a ticker leaves the counts 10 bars after its last real print.
  The old scripts anchored the "12-month" base on the first bar of whatever 400-day window they
  happened to fetch. The full history was rebuilt with this engine on 2026-08-22 (from mid-2024),
  including delisted names while they traded, on the Yahoo sector taxonomy throughout — so every
  sector series is continuous and there is no "Unknown" bucket. `run_daily --rebuild-breadth`
  repeats that.
- All six universes now honour `rank_settings.json` (uranium/gold previously ignored it).

Added 2026-08-23 (no legacy equivalent, so outside the parity test): `rsi_14`, `rsi_div` and
`obv_div` on every screener/benchmark row. RSI is Wilder's (ewm alpha = 1/14, TradingView's
`ta.rsi`). `rsi_div` follows TradingView's built-in divergence indicator: pivots are found on the
RSI line (5 bars each side), price is compared at the same two bars, only the last two consecutive
pivots count, the newer must be confirmed within 20 bars of the last bar, and the label is void
once price has closed through that pivot — BULL / BEAR regular, HID_BULL / HID_BEAR hidden
(continuation). `obv_div` compares the least-squares direction of price and OBV over 21 bars:
CONV_UP / CONV_DOWN when volume confirms, BEAR_DIV (price up, OBV down), BULL_DIV (price down,
OBV up), ACCUM / DISTRIB when price is flat (< 2 %) and OBV is not (≥ 3 average-volume days).
Thresholds live in `universe_config.json` → `divergence` and are passed into `ticker_metrics`.
Both labels feed `score_final` as additive bonuses (`studies.divergence_bonus`, applied in screener
and benchmark mode before the volume multiplier): regular RSI divergence and OBV divergence ±1.0,
hidden / confirming / flat-price signals ±0.5 — the same scale as the `rs_trend` bonus. Weights are
`studies.DIVERGENCE_DEFAULTS`, overridable per universe in `rank_settings.json` and edited on the
Settings → Rank page; the parity test zeroes them. They do not affect the actionable flags.
Schema: `study_results.rsi_14 REAL, rsi_div TEXT, obv_div TEXT`, added by `db._migrate()` on
existing databases.
- TradingView export exchanges come from `securities.exchange` (NASDAQ/NYSE/AMEX/ASX) instead
  of the old hard-coded 5-megacap list.
- Actionable / high-conviction are stored as flags on the result rows; the dashboard derives the
  export lists and TV strings from the DB instead of dated files.

## Daily run (`marketdb/run_daily.py`)

```
python -m marketdb.run_daily                # fetch + every study
python -m marketdb.run_daily --universe au_total_market --skip-fetch
python -m marketdb.run_daily --studies breadth rrg
```
The dashboard's Run Scripts page and `launcher.py` call this. Macro/credit/ETF scripts are
unchanged as entrypoints; `macro_data.py` now reads its ~30 tickers from the price store.

## Monthly universe refresh (`marketdb/refresh_universe.py`)

Source: Yahoo's screener endpoint (`yf.screen` / `EquityQuery`) — 250 rows per call, filtered by
region × industry, returning symbol, name, exchange, quoteType, marketCap. Two regions ×
~145 industries ≈ 300 small calls gives the complete AU + US listed universe **with sector,
industry and market cap in one consistent taxonomy** and no per-ticker `.info` calls at all.

Steps:
1. Pull AU (exchange ASX) and US (NMS/NYQ/NGM/NCM/ASE/PCX — listed only, no OTC) equities.
   Apply the per-region market-cap floor from `universe_config.json`.
2. Upsert `securities`: new symbols get `first_seen`; symbols missing from Yahoo get `active=0`
   and `delisted_at`. Names, sector, industry, market_cap, cap_band refresh every month.
3. Index memberships from isolated providers — S&P 500 (Wikipedia table), Nasdaq-100 (Nasdaq's
   own list API), ASX 20/50/200 (Wikipedia tables), Dow 30 (the RRG Dow list; Wikipedia's
   components table is not in the served HTML). Russell 1000/2000 have no free machine-readable
   source, so the US breadth "Russell proxy" layer is defined as *not in S&P 500 / Nasdaq-100*.
   If one provider breaks the others still update and the old membership is kept.
   US issuers whose financials are not reported in USD (Yahoo `financialCurrency`) are excluded —
   that is the cleanest available signal for ADRs / foreign cross-listings. Preferred shares,
   warrants, units and ASX codes longer than four characters (hybrids, bonds, deferred-settlement
   lines) are excluded by `is_odd_line()`.
4. Commodity flags from Yahoo industry + overrides + legacy, as above.
5. Write `universe_history(refresh_date, universe, ticker)` so point-in-time membership is kept.
6. Anything not AU/US is never inserted; the one-off migration wrote the dropped tickers to
   `stocks/results/migration_dropped_tickers.csv`.

Scheduling: `run_daily.py` checks `meta.last_universe_refresh` and runs the refresh itself when
it is older than 31 days (`auto_monthly_refresh` in `universe_config.json`), so no OS scheduler
is required. It can also be run on demand from the Run Scripts page, from `launcher.py` (`M`), or
from Windows Task Scheduler (command in the README).

## Sector taxonomy

The old watchlists used three incompatible vocabularies (AU: FactSet-style "Non-energy
minerals"; US: GICS with drift such as `Communication` vs `Communication Services`; Nasdaq-100:
a third). The refresh cannot extend those, so the **Yahoo taxonomy (11 sectors, ~145 industries)
is now the working `sector`/`industry` for every ticker**, and the old labels are kept in
`legacy_sector`/`legacy_industry`. Breadth history is stored long-format keyed by group name, so
old sector series simply end on the migration date and the Yahoo-named series start there.

## Migration notes (what the one-off `migrate_csv.py` did)

- Watchlists → `securities` + `security_groups` (commodity/type/benchmark/index flags), non-AU/US
  rows dropped and listed in `stocks/results/migration_dropped_tickers.csv`.
- Breadth history CSVs → `breadth_daily` (wide → long).
- RRG history CSVs → `rrg_history`.
- Latest screener/benchmark CSVs → `study_results` (so `delta_rank` has a previous run).
- Substantial-holder history → `asx_holder_notices`.
- The old CSV trees were left on disk untouched; nothing writes to them any more. The old
  per-universe scripts, `data_fetch/`, `config/` and the six market-cap scripts were moved to
  `stocks/legacy/` (they still run, but against the CSVs they always used).
