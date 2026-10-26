# Market Intelligence MCP

This server follows the existing Trading Journal MCP deployment on the Windows
machine reached as `mt5tools` (its actual hostname is `ALGOBOSS`). It is a separate
service, with its own environment, task, settings and logs.

| Service | MCP endpoint | Windows login task |
| --- | --- | --- |
| Existing Trading Journal | `http://mt5tools:8765/mcp` | Trading Journal MCP |
| Market Intelligence | `http://mt5tools:8766/mcp` | Market Intelligence MCP |

It uses the same optional MCP SDK version, Streamable HTTP transport, private-LAN
access without authentication, explicit hostname checks, below-normal priority,
and hidden current-user login task as the journal. Do not expose either endpoint
to the public internet. No change to the journal server is required.

## Install on the remote machine

For a transfer without pushing unrelated working changes, run
`python scripts/package_mcp.py` on the development PC. It creates
`data/mcp/market-intelligence-mcp.zip` containing only MCP files and a small
dashboard/ignore-rules patch. Extract into the remote project folder and follow
`MCP_DEPLOY.md`. The package contains no database, API keys or personal settings.

Run these commands **in the existing Market Intelligence project folder on the
remote machine**, under the Windows account that runs the dashboard. Commands use
the current folder, so the remote username and project location need not match
the development PC.

After transferring/pulling this implementation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -ConnectionHost mt5tools -Port 8766 -StartNow
```

The normal project dependencies must already be installed. The server uses this
checkout's `data\market.db`; the database must already exist. MCP startup and
read tools never create, replace or initialise it. For a genuinely fresh project,
follow the README bootstrap instructions first. Macro/credit generation also
needs the existing machine's `macro/config.py` and FRED key. ETF generation uses
that machine's saved ETF settings. Settings and keys are not transferred by Git.

Allow **inbound TCP 8766 on the private network profile**, restricted to the LAN
or intended client PCs, through Windows Firewall. For example, from an elevated
PowerShell on the remote machine:

```powershell
New-NetFirewallRule -DisplayName 'Market Intelligence MCP' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766 -Profile Private -RemoteAddress LocalSubnet
```

The setup script does not change the firewall. The `mt5tools` alias must resolve
to the remote machine from the client PC, as it already does for the journal.
If connecting by IP instead, register that exact IP with `-AllowedHost` and use
`-ConnectionHost` for the address shown in Settings.

Verify on the remote machine:

```powershell
Invoke-RestMethod http://localhost:8766/health
```

Verify on the client PC:

```powershell
Invoke-RestMethod http://mt5tools:8766/health
```

The response must say `market-intelligence-mcp`, show the **remote project's**
database path and hostname, and report `database_exists: true`. Health confirms
the process and configured file; use `market_catalog` to check stored data and
freshness. Check that the journal health endpoint on 8765 still responds.

Connect your MCP client to `http://mt5tools:8766/mcp`. For clients using the same
TOML configuration format as this PC's existing journal connection, add a separate
entry:

```toml
[mcp_servers.market_intelligence]
url = "http://mt5tools:8766/mcp"
```

## Dashboard controls

**Settings → MCP / AI Access** shows process health, database path, hostname
acceptance, startup task state and setup requirements. It offers explicit
install/update, start, stop and refresh actions. Merely opening the tab does not
install a task, start a server, write startup settings or touch market data.

CLI alternatives, from the remote project folder:

```powershell
# Inspect the planned task without writing settings or registering it
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -Preview

# Inspect / start / stop the installed task
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -Action Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -Action Stop

# Foreground troubleshooting (stop the login task first)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\launch_mcp.ps1
```

The task runs 15 seconds after the installing user logs in, without storing a
password. It restarts on failure up to three times at one-minute intervals,
has no execution-time limit, and ignores duplicate starts. It refuses to replace
a task owned by another configuration. Locking the desktop keeps it available;
signing out does not. Stop the task/server before changing its port or database.

Startup preferences live in `data/mcp/settings.json`. Logs and PID records live
beside the database under `mcp/`. They stay machine-local and are ignored by Git
for the standard `data/market.db` location. Do not commit logs or databases if you
choose an alternate path. An existing background instance is adopted only when
its health response identifies this checkout and database.

## Tool map

| Tools | Purpose |
| --- | --- |
| `market_catalog`, `search_securities` | Discover universes, tickers, available report types, dates and recent outcomes |
| `read_prices` | Stored raw OHLCV, adjusted close and corporate actions |
| `read_screener` | Latest or dated screener/benchmark rankings with exact filters |
| `read_breadth`, `read_rrg`, `read_demark`, `read_drawdown` | Stored study results and histories |
| `list_reports`, `read_report` | Macro, credit, ETF and other persisted reports/text/JSON |
| `list_frames`, `read_frame` | Cached sentiment, ETF, Burry and other tables |
| `read_runs` | The dashboard's per-fetch/study audit history |
| `start_update` | Prices and/or screener, benchmark, breadth and RRG jobs; optional universe refresh or breadth rebuild |
| `start_report` | Macro, US/AU credit, ETF scoring or ETF backtest generation |
| `start_demark`, `start_drawdown` | Parameterised scans and saved drawdown comparisons |
| `list_jobs`, `get_job` | Persistent background status, completion, warnings and log chunks |

Read tools use a SQLite **read-only connection** and return bounded pages. They
do not fetch live quotes or refresh caches. Row pages use `next_offset`; report
text/JSON uses character offsets. Job logs use byte offsets. Dates and currencies
are returned with their original data. Stored screener/benchmark returns,
drawdown, persistence and volatility use percentage values (12 means 12%).
Drawdown study return/drawdown fields also use percentage values. Report payloads
and cached frames retain their source-specific units. Breadth is returned in
long form by metric and group.

Stored actionable/high-conviction flags and accumulation labels are study
outputs. Dashboard-only saved/interactive SMA, score and export filters are not
reapplied by MCP; raw MCP results may differ from the currently filtered screen.

## Running jobs

Every start tool requires a `request_id`. Reuse the same ID and identical
arguments for a retry; it returns the existing job instead of running twice.
Use a new ID when requesting a new run. The same ID with changed arguments is an
error. Only one MCP job per database runs at a time; an overlapping request gets
the active job ID. The existing daily-run lock also prevents collisions with
the dashboard's daily runner. Other independent/manual scripts do not all use
that lock, so coordinate those separately.

Examples of tool arguments:

```json
{"request_id":"au-daily-20261026","universes":["au_total_market"],"fetch_prices":true}
```

```json
{"request_id":"studies-20261026","fetch_prices":false,"studies":["screener","benchmark","breadth","rrg"]}
```

```json
{"request_id":"macro-20261026","report":"macro_report"}
```

```json
{"request_id":"drawdown-20261026","universe":"au_total_market","study_name":"au_oct2026","periods":[{"label":"since_july","date":"2026-07-01"}]}
```

`studies: []` runs prices only. Omitted `studies` runs all four study types.
Study-only jobs use stored prices and do not perform an automatic universe
refresh; `refresh_universe: true` explicitly enables that external-data update.
The RRG implementation runs all configured RRG groups, as the existing daily
runner does, even when particular stock universes are selected.
Drawdown studies reuse stored prices but can fetch a missing benchmark, matching
the dashboard's existing drawdown implementation.

Jobs run as separate hidden processes; job history survives MCP restarts.
Stopping MCP is not a reliable way to cancel an update. Windows task shutdown or
sign-out can also terminate workers; the next status check marks those jobs
interrupted. There is no remote cancel or arbitrary shell-execution tool. To stop
a runaway job, inspect its recorded PID and log and manage that process on the
remote machine. Check active jobs before stopping or updating the service.

Poll `get_job` until status is terminal. `completed_with_warnings`, `failed` or
`interrupted` needs investigation. A daily script can exit zero while individual
studies fail or are skipped for poor coverage; the worker checks the audit/log
and surfaces warnings. Always verify relevant run dates, coverage and outcomes
with `read_runs` and the data tools. A named drawdown job replaces that saved
study; choose a new name to keep an older comparison.

Job history is stored separately from market data in `mcp/jobs/<database-id>/`.
Request IDs and logs persist across MCP restarts. Abruptly terminated workers
are marked interrupted when the next job/status request checks them.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_market_mcp.py -v
```

Tests use isolated databases, cover real stdio/HTTP MCP requests, read-only
access, paging/filtering, job deduplication, concurrency, and a detached offline
worker. They do not fetch market data or run reports against personal data.
