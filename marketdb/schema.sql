-- marketdb schema. Idempotent: every statement is CREATE ... IF NOT EXISTS.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

-- ── Universe ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS securities (
    ticker          TEXT PRIMARY KEY,          -- Yahoo symbol
    name            TEXT,
    region          TEXT NOT NULL,             -- AU | US | GLOBAL (indices/futures/FX only)
    exchange        TEXT,                      -- ASX, NMS, NYQ, NGM, NCM, ASE, PCX, ...
    quote_type      TEXT,                      -- EQUITY | ETF | INDEX | FUTURE | CURRENCY | MUTUALFUND
    sector          TEXT,                      -- working taxonomy (Yahoo)
    industry        TEXT,
    legacy_sector   TEXT,                      -- from the pre-migration watchlists
    legacy_industry TEXT,
    market_cap      REAL,
    cap_band        TEXT,                      -- large | mid | small | ETF
    currency        TEXT,
    benchmark       TEXT,                      -- default RS benchmark ticker
    active          INTEGER NOT NULL DEFAULT 1,
    first_seen      TEXT,
    last_seen       TEXT,
    delisted_at     TEXT,
    mcap_updated    TEXT,
    source          TEXT,                      -- 'migration' | 'yahoo_screener' | 'manual'
    business_summary TEXT,                     -- Yahoo longBusinessSummary (summary_scan.py)
    summary_updated TEXT
);
CREATE INDEX IF NOT EXISTS ix_securities_region ON securities(region, active, quote_type);
CREATE INDEX IF NOT EXISTS ix_securities_sector ON securities(sector);

CREATE TABLE IF NOT EXISTS security_groups (
    ticker      TEXT NOT NULL,
    group_type  TEXT NOT NULL,                 -- index | commodity | theme | role
    group_key   TEXT NOT NULL,                 -- ASX200, gold, rrg_au_sector, benchmark, ...
    attr        TEXT,                          -- producer/explorer/royalty/services/ETF, display name, ...
    source      TEXT,
    updated     TEXT,
    priority    INTEGER NOT NULL DEFAULT 9,    -- commodity flags: 0 = primary exposure (peer group for RS)
    PRIMARY KEY (ticker, group_type, group_key)
);
CREATE INDEX IF NOT EXISTS ix_groups_key ON security_groups(group_type, group_key);

CREATE TABLE IF NOT EXISTS universe_history (
    refresh_date TEXT NOT NULL,
    universe     TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    PRIMARY KEY (refresh_date, universe, ticker)
);

-- ── Prices ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,                 -- YYYY-MM-DD
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    adj_close   REAL,
    volume      REAL,
    dividend    REAL,
    split       REAL,
    PRIMARY KEY (ticker, date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_prices_date ON prices(date);

CREATE TABLE IF NOT EXISTS fetch_log (
    ticker          TEXT PRIMARY KEY,
    last_fetch_at   TEXT,
    first_date      TEXT,
    last_date       TEXT,
    n_rows          INTEGER,
    status          TEXT,                      -- ok | empty | error | stale
    error           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    full_refetch_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,                 -- fetch | screener | benchmark | breadth | rrg | refresh | demark
    universe    TEXT,
    started     TEXT NOT NULL,
    finished    TEXT,
    status      TEXT,                          -- ok | partial | aborted | error
    n_expected  INTEGER,
    n_fetched   INTEGER,
    notes       TEXT
);

-- ── Study results ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS study_results (
    run_date      TEXT NOT NULL,
    study         TEXT NOT NULL,               -- screener | benchmark
    universe      TEXT NOT NULL,
    rank          INTEGER,
    delta_rank    INTEGER,
    ticker        TEXT NOT NULL,
    name          TEXT,
    sector        TEXT,
    industry      TEXT,
    commodity     TEXT,
    type          TEXT,
    cap_band      TEXT,
    close         REAL,
    peer_rs_score REAL,
    rs_ratio      REAL,
    rs_5          REAL,
    rs_21         REAL,
    rs_63         REAL,
    rs_trend      TEXT,
    ret_6m        REAL,
    ret_12m       REAL,
    ret_24m       REAL,
    max_dd        REAL,
    persist_frac  REAL,
    vol_63        REAL,
    rel_vol       REAL,
    vol_label     TEXT,
    acc_watch     TEXT,
    sma20         REAL,
    sma50         REAL,
    sma200        REAL,
    pass_trend    INTEGER,
    mqs           REAL,
    rsi_14        REAL,                        -- Wilder RSI(14) on adjusted close
    rsi_div       TEXT,                        -- BULL | BEAR | HID_BULL | HID_BEAR | -
    obv_div       TEXT,                        -- CONV_UP | CONV_DOWN | BULL_DIV | BEAR_DIV | ACCUM | DISTRIB | -
    regime_label  TEXT,
    score_final   REAL,
    actionable    INTEGER NOT NULL DEFAULT 0,
    high_conv     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_date, study, universe, ticker)
);
CREATE INDEX IF NOT EXISTS ix_study_latest ON study_results(study, universe, run_date);

CREATE TABLE IF NOT EXISTS breadth_daily (
    date        TEXT NOT NULL,
    universe    TEXT NOT NULL,
    layer       TEXT NOT NULL DEFAULT 'all',   -- all | sp | rus
    group_type  TEXT NOT NULL DEFAULT 'all',   -- all | cap | sector | industry | commodity | type
    group_key   TEXT NOT NULL DEFAULT '',
    metric      TEXT NOT NULL,                 -- total, leader, above_20, ... (old column stems)
    value       REAL,
    PRIMARY KEY (date, universe, layer, group_type, group_key, metric)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_breadth_universe ON breadth_daily(universe, date);

CREATE TABLE IF NOT EXISTS rrg_history (
    date        TEXT NOT NULL,
    study       TEXT NOT NULL,                 -- au | us | us_rsp | dow
    ticker      TEXT NOT NULL,
    name        TEXT,
    grp         TEXT,
    rs_ratio    REAL,
    rs_momentum REAL,
    close       REAL,
    PRIMARY KEY (date, study, ticker)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS demark_signals (
    run_date        TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    name            TEXT,
    sector          TEXT,
    market_cap      REAL,
    close           REAL,
    d_setup9_buy    INTEGER, d_setup9_sell INTEGER,
    w_setup9_buy    INTEGER, w_setup9_sell INTEGER,
    d_cd13_buy      INTEGER, d_cd13_sell   INTEGER,
    w_cd13_buy      INTEGER, w_cd13_sell   INTEGER,
    d_setup_count   INTEGER, w_setup_count INTEGER,
    PRIMARY KEY (run_date, ticker)
);
CREATE TABLE IF NOT EXISTS demark_reports (
    run_date    TEXT PRIMARY KEY,
    report      TEXT
);

CREATE TABLE IF NOT EXISTS drawdown_results (
    study         TEXT NOT NULL,
    period_label  TEXT NOT NULL,
    start_date    TEXT,
    ticker        TEXT NOT NULL,
    rank          INTEGER,
    payload       TEXT,                        -- JSON of the full result row
    created       TEXT,
    PRIMARY KEY (study, period_label, ticker)
);
CREATE TABLE IF NOT EXISTS drawdown_summaries (
    study         TEXT PRIMARY KEY,
    universe      TEXT,
    periods       TEXT,                        -- JSON list of {label, start}
    summary       TEXT,
    created       TEXT
);

CREATE TABLE IF NOT EXISTS asx_holder_notices (
    ann_id      TEXT PRIMARY KEY,
    date        TEXT,
    ticker      TEXT,
    company     TEXT,
    form        TEXT,
    title       TEXT,
    url         TEXT,
    payload     TEXT                           -- JSON of any extra columns
);
CREATE INDEX IF NOT EXISTS ix_holder_ticker ON asx_holder_notices(ticker, date);

-- ── Generic stores for the non-stocks modules (macro, ETF, sentiment, Burry) ──
CREATE TABLE IF NOT EXISTS reports (
    kind        TEXT NOT NULL,                 -- macro_report | macro_snapshot | consumer_credit | au_credit | cycle_tracker | ...
    date        TEXT NOT NULL,                 -- YYYY-MM-DD ('latest' for rolling snapshots)
    text        TEXT,                          -- human-readable report
    payload     TEXT,                          -- JSON
    created     TEXT,
    PRIMARY KEY (kind, date)
);
CREATE TABLE IF NOT EXISTS frames (
    name        TEXT PRIMARY KEY,              -- e.g. 'etf_income/2026-08-22', 'sentiment/aaii', 'burry/2026-08-22/au_total_market'
    updated     TEXT,
    n_rows      INTEGER,
    blob        BLOB                           -- parquet bytes
);
