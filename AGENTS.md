# Market Intelligence: agent entry points

Read `README.md` and `docs/marketdb_design.md` for the platform and data model.
Preserve existing unrelated working-tree changes.

## MCP

- Read `docs/mcp_setup.md` for the remote setup, tool map, units, freshness,
  background-job lifecycle and dashboard-filter limitations.
- `mcp_server.py` runs the optional server. Dependencies: `requirements-mcp.txt`.
- `market_mcp/operations.py` provides bounded read-only database access.
- `market_mcp/jobs.py` admits idempotent jobs; `market_mcp/worker.py` runs fixed
  existing study/report entry points. No arbitrary shell/SQL tool is exposed.
- `scripts/setup_mcp_task.ps1` installs the separate Windows login task.
- `market_mcp/settings_ui.py` renders Settings → MCP / AI Access.
- `tests/test_market_mcp.py` uses isolated databases and no market downloads.
- `docs/etf_income_mcp.md` and `docs/etf_income_tools.schema.json` describe Income
  review/configuration/results tools, proxy-NAV limits and deployment verification.
- Keep Income, Growth and AU Stocks separate. Monthly Income risk review does
  not adopt a full rebalance cadence. No Income settings/holdings/journal writes
  are authorised by a read, preview or deployment check.

Reuse the existing `marketdb` calculations and scripts so MCP and dashboard
results agree. Read tools must not initialise, migrate or write the market
database. Do not infer job success solely from process exit zero: inspect
per-study run outcomes, warnings and output dates. Do not commit machine-local
startup preferences, job logs, databases, API keys or dashboard settings.
