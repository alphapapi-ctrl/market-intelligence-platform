"""Package only the MCP addition, excluding local data, secrets and unrelated edits."""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import zipfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def integration_patch() -> str:
    changes = []
    name = "dashboard.py"
    current = (ROOT / name).read_text(encoding="utf-8")
    previous = current.replace(
        "_stab_gen, _stab_mcp = st.tabs([", "_stab_gen = st.tabs([", 1
    ).replace('        "MCP / AI Access",\n', "", 1).replace(
        '    with _stab_mcp:\n        from market_mcp.settings_ui import show as show_mcp_settings\n        show_mcp_settings()\n\n', "", 1
    )
    if previous == current or "_stab_mcp" in previous:
        raise ValueError("Cannot isolate the MCP dashboard addition; review the integration manually")
    changes.extend(difflib.unified_diff(previous.splitlines(True), current.splitlines(True),
                                       fromfile="a/dashboard.py", tofile="b/dashboard.py"))
    current = (ROOT / ".gitignore").read_text(encoding="utf-8")
    previous = current.replace("\n# Machine-local MCP startup settings, logs and job history\ndata/mcp/\n", "", 1).replace(
        "\n# MCP configuration code contains defaults and validation, not machine settings\n!market_mcp/config.py\n", "", 1)
    if previous == current:
        raise ValueError("Cannot isolate MCP ignore rules")
    changes.extend(difflib.unified_diff(previous.splitlines(True), current.splitlines(True),
                                       fromfile="a/.gitignore", tofile="b/.gitignore"))
    return "".join(changes)


def main():
    destination = ROOT / "data/mcp/market-intelligence-mcp.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / "mcp_server.py", ROOT / "requirements-mcp.txt", ROOT / "docs/mcp_setup.md",
             ROOT / "docs/etf_income_mcp.md", ROOT / "docs/etf_income_tools.schema.json",
             ROOT / "tests/test_market_mcp.py", ROOT / "tests/test_income_mcp.py", ROOT / "tests/check_mcp_startup.ps1"]
    files += [ROOT / "etf" / name for name in ('income_config.py', 'income_rules.py', 'income_store.py',
               'etf_income_data.py', 'etf_backtest.py', 'etf_prices.py')]
    files += sorted((ROOT / "market_mcp").glob("*.py"))
    files += [ROOT / "scripts" / name for name in ("launch_mcp.ps1", "setup_mcp_task.ps1", "run_mcp_scheduled.py",
               "stop_mcp.ps1", "mcp_config.py", "start_mcp_background.py", "package_mcp.py", "check_income_mcp.py")]
    entries = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in files}
    entries["mcp-integration.patch"] = integration_patch().encode("utf-8")
    baseline = subprocess.check_output(['git', 'show', 'e29ba40:dashboard.py'], cwd=ROOT).decode('utf-8')
    current = (ROOT / 'dashboard.py').read_text(encoding='utf-8')
    start, end = baseline.index('elif page == "ETF Income":'), baseline.index('elif page == "DeMark Signals":')
    a, b = current.index('elif page == "ETF Income":'), current.index('elif page == "DeMark Signals":')
    if baseline[:start] + current[a:b] + baseline[end:] != current:
        raise ValueError('Dashboard has unrelated changes since the 1.1.0 base; review before packaging')
    entries['income-dashboard.patch'] = ''.join(difflib.unified_diff(baseline.splitlines(True), current.splitlines(True),
        fromfile='a/dashboard.py', tofile='b/dashboard.py')).encode('utf-8')
    entries["MCP_DEPLOY.md"] = b"""# Market Intelligence MCP 1.1.0 source update

The recommended upgrade is git pull using docs/etf_income_mcp.md. This optional
source package contains no market database, ETF settings, holdings, API keys or
journal files. Finish active jobs and STOP the existing Market Intelligence MCP
task before extracting it into the existing project folder. Preserve remote
source edits; inspect/merge them first. Do not install a duplicate task.

For the existing 1.0.0 instance, after extracting:

```powershell
git apply --check income-dashboard.patch
git apply income-dashboard.patch
powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\setup_mcp_task.ps1 -Action Start
```

After a few seconds:

```powershell
.\\.venv\\Scripts\\python.exe scripts/check_income_mcp.py --url http://localhost:8766 --expected-root "$PWD" --expected-database "$PWD\\data\\market.db"
```

Restart the dashboard. If a patch check fails, do not force it; review the small
patch, or skip it only if its exact changes are already applied. The extra
mcp-integration.patch is for initial installation without the existing MCP
Settings tab/ignore rules; do not reapply that patch on an existing instance.

Read docs/etf_income_mcp.md for source/version checks, limitations, schemas,
preserved history and plugin handoff. Leave Trading Journal and port 8765 alone.
Do not generate live reviews/holdings/journal entries to demonstrate deployment.
SHA256SUMS.json records this archive's source files.

## Original first-install reference (only if no service/task exists)

Extract this archive into the existing Market Intelligence project folder on
mt5tools. It contains only MCP files and a small integration patch; no market
database, personal settings, API keys or unrelated application changes.

In PowerShell, from that project folder:

```powershell
# Check and apply the dashboard tab + local-file ignore rules.
git apply --check mcp-integration.patch
git apply mcp-integration.patch

.\\.venv\\Scripts\\python.exe -m pip install -r requirements-mcp.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\setup_mcp_task.ps1 -ConnectionHost mt5tools -Port 8766 -StartNow
Invoke-RestMethod http://localhost:8766/health
```

If the patch check fails, do not force it. If these exact additions were already
installed, skip the patch; otherwise review the short patch against the remote
dashboard/.gitignore. The MCP server can run without the dashboard tab.

Restart the dashboard to see Settings > MCP / AI Access. Allow inbound TCP 8766
on the private LAN in Windows Firewall (see docs/mcp_setup.md for the command),
and verify http://mt5tools:8766/health from the client PC.

Connect your AI client to http://mt5tools:8766/mcp. The existing Trading Journal
MCP stays on 8765. Health must identify the remote project/database.

This archive does not install anything until you run the commands. Standard
project dependencies and an existing data/market.db are required. Use the remote
machine's existing macro/config.py for report generation.

See docs/mcp_setup.md for the full tool map, job lifecycle, logs and setup.
SHA256SUMS.json records the contents of this package.
"""
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr("SHA256SUMS.json", json.dumps(manifest, indent=2))
    print(destination)
    print(f"{len(entries)} files; {destination.stat().st_size:,} bytes; no databases or settings included")


if __name__ == "__main__":
    main()
