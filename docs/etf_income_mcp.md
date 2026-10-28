# ETF Income MCP coverage — service 1.1.0 / income-review/1.0

This extends the existing Market Intelligence service on port 8766. No new MCP
connection or service is installed. Growth, Income and AU Stocks remain separate;
these tools do not call TradingJournal, import its stock grading/risk policy,
execute trades or reconcile portfolio data.

## What is shared with the app

- `etf/income_config.py`: unchanged universe, weights, exclusions, buy zone,
  live stop defaults and backtest defaults, with a whitelisted read-only loader.
- `etf/etf_income_data.py`: the existing metrics/percentile scorer, used by live
  scoring and the backtest. A generation captures the configuration actually used.
- `etf/income_rules.py`: HOLD/REVIEW/SELL by qualified rank; the live total-return
  formula and HIT/NEAR/OK thresholds; ex-date cadence estimate; VIX hysteresis;
  and the page's whole-share, equal-weight AUD calculator. The dashboard and MCP
  call these same functions. The backtest shares scorer and VIX calculations;
  its independent simulation/stop settings remain distinct.

No investment threshold/default was changed. A 0 live stop retains the page's
literal rule (HIT at return <= 0); the simulator separately defines 0 as disabled.
Floating-point boundary behaviour is retained, not silently rounded into a
different trade decision. Missing/unreadable configuration is reported along with
the effective defaults. Invalid saved thresholds prevent assessment/generation
rather than being silently replaced. Credentials and unknown settings are omitted.

## NAV, price, distributions, currency and time

The page calls `chg_3m` and `chg_12m` NAV change, but computes them from market
close. The strict qualifier is **chg_3m > 0**, after at least 63 price bars. This
is a price-trend proxy, **not verified fund NAV**. No independent fund NAV series
or NAV deterioration rule exists here; `true_nav_deterioration` is not_assessed.
The integration does not manufacture that capability or claim distributions
prove return of capital.

The live stop formula is `(last close + cash distributions after entry) /
entry_price - 1`, with distributions strictly after the entry date. It is not a
raw price stop, reinvested return, account-currency return, or verified receipt
ledger. Amounts use ex-date observations and instrument quote currency; costs,
taxes and FX are excluded. Return thresholds are fractions (0.20 means 20%);
ranking changes/yields are percentages. The scorer/backtest retain their existing
raw-price/dividend input conventions; underlying RS uses adjusted close.

Read previews use only stored prices, dividends and split events, with no fetch,
schema migration or market-database write. Missing entry dates/prices/currency,
incomplete coverage, stale prices or a split crossing entry produce an unknown
stop, while returning the app-formula proxy separately for inspection. Split
adjustments are not independently reconciled; no split adjustment is applied
twice. Existing simulator limitations for splits, costs and FX remain explicit.

The freshness diagnostic uses the existing ETF adapter's 5-calendar-day window.
It is a data-quality rule, not a new investment/turnover threshold. Generation
records retain per-ticker first/last observations, missing tickers and source
basis. Legacy cached frames do not have that provenance: it remains unknown.
Naive legacy store timestamps have unspecified timezone. `as_of` for a review
requires an offset; historical previews use prices through its date, with current
review settings labelled separately from captured generation settings. Current
saved holdings are not a reconstructed historical holdings ledger.

## Cadence and portfolio identity

The confirmed conversation context is **monthly risk checks**, with **full
rebalance cadence undecided**. That context is returned separately from saved
app settings. The existing app has no saved live review/full-rebalance schedule;
`backtest_config.json.rebal_freq` (default quarterly) is an experiment parameter,
not an adopted user policy. No schedule or monitor is created.

`etf/holdings.json` exists as an app concept, but has no verified external demo
portfolio identity, cash ledger or journal/broker reconciliation. Null holdings
reads it with that warning; an absent/invalid file is **unavailable**, not an empty
account. An explicit `holdings: []` means empty only for that preview. Every
preview/review requires a stable Income `portfolio_id`; the tool never imports
screenshots, guesses share counts, or treats rankings as current positions.

There is no persisted target allocation or working rebalance manager. Optional
allocation inputs reproduce the existing AUD calculator only. They require an
explicit buy list, budget and FX quote/source/time; they do not compute net orders
against a verified portfolio or change holdings. Exact quantities, costs, cash,
corporate actions, FX and fills remain required before any later execution work.

## New native tools and input schemas

Exact native MCP input schemas are in
[`etf_income_tools.schema.json`](etf_income_tools.schema.json). All tools return
`schema_version: income-review/1.0`. Holdings and allocation objects forbid extra
fields. There are no settings-write tools; writes are unnecessary for this phase.

| Tool | Inputs | Output |
| --- | --- | --- |
| `etf_income_config` | none | effective strategy/backtest config, source hashes/defaults, universe, actual rule definitions, cadence distinction and capabilities |
| `read_etf_income_results` | `run_id?` OR `ranking_date?: YYYY-MM-DD`, `limit=50` (1–100), `offset=0` | complete ranking page, shared decisions/rule evidence, score contributions when retained, source/config provenance and warnings |
| `preview_etf_income_review` | `portfolio_id`, `holdings?`, `run_id?` OR `ranking_date?`, `as_of?`, `allocation?`, `limit=25`, `offset=0` | read-only content-addressed snapshot with paged holdings, independent ranking/stop evidence, ex-date/VIX diagnostics and optional calculator preview |
| `start_etf_income_review` | same review inputs without pagination, plus `request_id` | existing durable job ID; saves an immutable review when explicitly requested |
| `read_etf_income_review` | `review_id`, `limit=25` (1–100), `offset=0` | persisted snapshot whose content hash is verified before returning it |

Holding object: `ticker` required; optional `shares`, `entry_price`, `entry_date`
(YYYY-MM-DD), `quote_currency` (uppercase ISO code). Missing values stay unknown.
There is at most one supplied aggregate holding per ticker, maximum 100. Costs
and multi-lot tax accounting are not implemented by the existing app.

Allocation object: required `tickers`, `budget_aud`, `usd_per_aud`, `fx_source`,
`fx_observed_at` (offset timestamp). Matches page ranges: budget 0–100000000 AUD,
FX 0.30–1.50 USD per AUD. FX is never inferred from account capital/screenshots.

Examples (synthetic input contracts, not seeded user holdings):

```json
{"portfolio_id":"income-demo","holdings":[{"ticker":"JEPI","shares":10,"entry_price":100,"entry_date":"2026-10-01","quote_currency":"USD"}],"as_of":"2026-10-28T10:00:00+10:00"}
```

```json
{"request_id":"income-review-20261028-01","portfolio_id":"income-demo","holdings":[],"as_of":"2026-10-28T10:00:00+10:00"}
```

For stable preview pagination, reuse the same `as_of` and explicit inputs. Use a
saved review ID for immutable export/history. Source changes are reflected in the
snapshot's content identity; it is not a fabricated journal entry.

## Generation, discovery, jobs and history

Existing `start_report(report="etf_income"|"etf_backtest", request_id=...)` remains
the generation interface. No generation is triggered by reads or deployment checks.

| Output | Existing compatible daily store | New immutable history |
| --- | --- | --- |
| Income ranking | frame `etf_income/YYYYMMDD`; report kind `etf_income`, date YYYY-MM-DD (manifest) | report kind `etf_income_run`, date = unique run ID; frame `etf_income_runs/<run_id>/rankings` |
| Backtest | frames `etf_backtest/YYYYMMDD/equity` and `/quarters`; kind `etf_backtest`, date YYYY-MM-DD (unchanged summary shape) | kind `etf_backtest_run`, unique run ID; frames `etf_backtest_runs/<run_id>/equity` and `/quarters`, captured config and summary |
| Review snapshot | no holdings/journal changes | kind `etf_income_review`, date = SHA-256 review ID |

Multiple same-day generations retain distinct immutable outputs. Older daily-only
frames remain readable and are not backfilled with invented configuration. An
empty old `list_reports(kind="etf_income")` does not mean an empty screener cache.
`market_catalog.etf_income` and the new results reader make this explicit.

Jobs reuse the existing single-active-job admission and stable request IDs. An
exact retry returns the same job; changed inputs with that ID are rejected.
`get_job.outcome.steps` records saved run/review IDs, frame references and warnings.
Successful exit without an artifact belonging to that job is not accepted as
successful ETF generation. Missing tickers/partial data and review warnings are
surfaced as completed_with_warnings. Job history gets one additive `outcome`
column in its separate job database; there is no new market schema.

Discover versions with `list_reports(kind="etf_income_run"|"etf_backtest_run"|
"etf_income_review")`. Retrieve any manifest/summary/export using `read_report`
with `section="payload"`, `report_date=<run/review ID>` and character pagination;
retrieve named tables via `read_frame` row pagination. A saved review includes
portfolio/strategy identity, settings/code/source versions, evaluation timestamp,
evidence and warnings suitable for a **later** journal entry. This phase creates
no live review, journal record, holdings, trade close or reconciliation data.

## Upgrade the existing remote instance

The last verified remote instance is still service 1.0.0 at
`C:\Users\Algo\MarketIntelligence`, database `data\market.db`, endpoint
`http://mt5tools:8766/mcp`. Inspect its current health/configuration before
upgrading; do not install another service or change the journal task on 8765.

After current update jobs finish, run on the remote PC in that existing folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -Action Stop
git pull --ff-only origin master
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -Action Start
```

Allow a few seconds for startup, then run the read-only acceptance check:

```powershell
.\.venv\Scripts\python.exe scripts/check_income_mcp.py --url http://localhost:8766 --expected-root "$PWD" --expected-database "$PWD\data\market.db"
```

Restart the dashboard to load its shared helper functions. No dependency upgrade,
new task, database replacement, settings edit or data import is required. Stop
before pulling; a stopped service alone is not proof that detached jobs finished.
Keep machine-local ETF JSON settings/holdings and the existing database in place.

From the development PC the same script can check the LAN endpoint with the
recorded expected remote root/database. It verifies health/version, normalized
running source fingerprint, live tools/list, actual config/result reads and an
existing stock screener read. **Implementation/test completion is not deployment
verification**: only this check against the running intended instance establishes
that version 1.1.0 is active. The journal service should continue responding on
8765. Reload the Codex MCP connection after the server upgrade for new tools.

## Stock Trading plugin handoff

- Rediscover the five new tools after deployment. Consult `etf_income_config`
  first, then use the new results/review readers rather than inferring portfolio
  state from raw ranking frames.
- Keep `strategy_id=etf_income` and the explicit demo Income identity separate
  from Growth and AU Stocks. Do not apply stock grades/fixed-balance sizing here.
- Preserve monthly risk-review versus undecided full-rebalance semantics, even
  when the historical journal playbook or saved backtest says quarterly.
- Treat missing holdings/NAV/entry/currency/split evidence as not_assessed; do not
  close/import journal trades or claim an allocation is executable.
- A future journal workflow can consume an explicitly requested saved review's
  immutable ID and provenance. Journal reconciliation remains a separate phase.

Validation: `python -m unittest discover -s tests -p '*mcp.py' -v` runs synthetic
fixtures, including ordinary HOLD/REVIEW/SELL, stop/distribution and split cases,
missing/stale data, cadence separation, unknown external holdings, same/conflicting
retries, a real background review, preserved generation/review history, scorer
and simulator parity, and the original HTTP/stdio/stock-reader regressions.
