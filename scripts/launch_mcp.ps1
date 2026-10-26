param(
    [string]$BindAddress = "",
    [ValidateRange(0, 65535)][int]$Port = 0,
    [string[]]$AllowedHost = @(),
    [string[]]$AllowedOrigin = @(),
    [string]$Database = "",
    [string]$ConfigPath = "",
    [switch]$Install,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$marketRoot = Split-Path -Parent $PSScriptRoot
$marketPython = Join-Path $marketRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $marketPython)) {
    throw "Market Intelligence virtual environment missing. Set up the platform's .venv first."
}
if (-not $ConfigPath) { $ConfigPath = Join-Path $marketRoot "data\mcp\settings.json" }
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$configJson = & $marketPython (Join-Path $PSScriptRoot "mcp_config.py") --config $ConfigPath
if ($LASTEXITCODE -ne 0) { throw "Cannot read MCP startup settings." }
$mcpConfig = $configJson | ConvertFrom-Json
if (-not $BindAddress) { $BindAddress = $mcpConfig.bind_address }
if (-not $Port) { $Port = [int]$mcpConfig.port }
if (-not $PSBoundParameters.ContainsKey("AllowedHost")) { $AllowedHost = @($mcpConfig.allowed_hosts) }
if (-not $Database) { $Database = $mcpConfig.database }
if ($Install) {
    & $marketPython -m pip install -r (Join-Path $marketRoot "requirements.txt") -r (Join-Path $marketRoot "requirements-mcp.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}
& $marketPython -c "from mcp.server import MCPServer"
if ($LASTEXITCODE -ne 0) { throw "MCP dependency missing. Run this launcher with -Install once." }

# Check that this endpoint isn't already running; don't spawn duplicate services.
$healthAddress = if ($BindAddress -eq "0.0.0.0") { "127.0.0.1" } else { $BindAddress }
try {
    $health = Invoke-RestMethod -Uri "http://${healthAddress}:$Port/health" -TimeoutSec 2
    if ($health.service -eq "market-intelligence-mcp") {
        Write-Host "Market Intelligence MCP is already running on port $Port."
        exit 0
    }
} catch { }

$marketArgs = @((Join-Path $marketRoot "mcp_server.py"), "--config", $ConfigPath, "--host", $BindAddress, "--port", "$Port")
if ($Database) {
    $Database = [System.IO.Path]::GetFullPath($Database)
    $marketArgs += @("--database", $Database)
}
foreach ($hostName in $AllowedHost) { $marketArgs += @("--allowed-host", $hostName) }
foreach ($origin in $AllowedOrigin) { $marketArgs += @("--allowed-origin", $origin) }
Write-Host "Market Intelligence MCP endpoint: http://<this-machine-LAN-IP>:$Port/mcp"
if ($Background) {
    $logDir = if ($Database) { Join-Path (Split-Path -Parent $Database) "mcp" } else { Join-Path $marketRoot "data\mcp" }
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    # close_fds in the helper prevents the service from keeping this shell's
    # redirected output pipes alive after the launcher exits.
    $launchedProcessId = & $marketPython (Join-Path $PSScriptRoot "start_mcp_background.py") --log-dir $logDir -- @platformArgs
    if ($LASTEXITCODE -ne 0) { throw "Could not launch MCP. Check $logDir." }
    $process = Get-Process -Id ([int]$launchedProcessId)
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        $process.Refresh()
        if ($process.HasExited) { throw "Server exited. See $logDir\server.stderr.log." }
        try {
            $health = Invoke-RestMethod -Uri "http://${healthAddress}:$Port/health" -TimeoutSec 1
            if ($health.service -eq "market-intelligence-mcp") { $ready = $true; break }
        } catch { }
    }
    if (-not $ready) { throw "Startup was not confirmed. Check $logDir\server.stderr.log before retrying." }
    Set-Content -LiteralPath (Join-Path $logDir "server.pid") -Value $health.pid
    Write-Host "Running in background (PID $($health.pid)), below normal priority. Logs: $logDir"
} else {
    & $marketPython @platformArgs
    exit $LASTEXITCODE
}
