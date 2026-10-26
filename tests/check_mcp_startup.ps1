<# Opt-in integration check: install/start/stop a uniquely named temporary login task. #>
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$setup = Join-Path $projectRoot "scripts\setup_mcp_task.ps1"
$testName = "Market Intelligence MCP Test " + [guid]::NewGuid().ToString("N")
$testRoot = Join-Path $projectRoot ("data\mcp\startup-test-" + [guid]::NewGuid().ToString("N"))
$testRoot = [System.IO.Path]::GetFullPath($testRoot)
$configPath = Join-Path $testRoot "settings.json"
$testDatabase = Join-Path $testRoot "market.db"
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$testPort = $listener.LocalEndpoint.Port
$listener.Stop()
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    & $projectPython -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('CREATE TABLE smoke_test (value INTEGER)'); c.close()" $testDatabase
    if ($LASTEXITCODE -ne 0) { throw "Cannot create isolated test database" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup -ConfigPath $configPath -TaskName $testName -ConnectionHost localhost -BindAddress 127.0.0.1 -Port $testPort -Database $testDatabase -StartNow -Json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Temporary login task installation failed" }
    $ready = $false
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$testPort/health" -TimeoutSec 1
            if ($health.service -eq "market-intelligence-mcp") { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw "Temporary server did not become ready; inspect $testRoot" }
    if ($health.database -ne $testDatabase -or $health.app_root -ne $projectRoot) { throw "Server identity mismatch" }
    $aliasHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$testPort/health" -Headers @{ Host = "localhost:$testPort" } -TimeoutSec 2
    if ($aliasHealth.pid -ne $health.pid) { throw "Hostname alias reached another process" }
    # A second launch must detect the same instance instead of creating a server.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "scripts\launch_mcp.ps1") -ConfigPath $configPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Duplicate prevention check failed" }
    $again = Invoke-RestMethod -Uri "http://127.0.0.1:$testPort/health" -TimeoutSec 2
    if ($again.pid -ne $health.pid) { throw "A duplicate MCP process was started" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup -Action Stop -ConfigPath $configPath -Json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Temporary task stop failed" }
    $stopped = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 200
        try { $null = Invoke-RestMethod -Uri "http://127.0.0.1:$testPort/health" -TimeoutSec 1 }
        catch { $stopped = $true; break }
    }
    if (-not $stopped) { throw "Server remained running after task stop" }
    Write-Host "PASS: hidden login task, correct database, alias, duplicate prevention and stop."
} finally {
    $task = Get-ScheduledTask -TaskName $testName -ErrorAction SilentlyContinue
    if ($task -and $task.Description -eq "Market Intelligence MCP login service. Managed by $projectRoot") {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup -Action Stop -ConfigPath $configPath -Json 2>$null | Out-Null
        Unregister-ScheduledTask -TaskName $testName -Confirm:$false
    }
    # Validate the absolute target before recursively deleting this check's files.
    $allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "data\mcp")) + "\"
    if (-not $testRoot.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Cleanup target outside test workspace" }
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
