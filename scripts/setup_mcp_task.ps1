<#
.SYNOPSIS
Installs or inspects the platform's quiet, current-user MCP login task.
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_mcp_task.ps1 -AllowedHost mt5tools -StartNow
#>
[CmdletBinding()]
param(
    [ValidateSet("Install", "Status", "Start", "Stop")][string]$Action = "Install",
    [string]$TaskName = "",
    [string]$AllowedHost = "",
    [string]$ConnectionHost = "",
    [ValidateRange(0, 65535)][int]$Port = 0,
    [string]$BindAddress = "",
    [string]$Database = "",
    [string]$ConfigPath = "",
    [switch]$StartNow,
    [switch]$Preview,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$marketRoot = Split-Path -Parent $PSScriptRoot
$marketPython = Join-Path $marketRoot ".venv\Scripts\python.exe"
$marketPythonw = Join-Path $marketRoot ".venv\Scripts\pythonw.exe"
$runner = Join-Path $PSScriptRoot "run_mcp_scheduled.py"
$configHelper = Join-Path $PSScriptRoot "mcp_config.py"
if (-not $ConfigPath) { $ConfigPath = Join-Path $marketRoot "data\mcp\settings.json" }
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
if (-not (Test-Path -LiteralPath $marketPython)) { throw "Market Intelligence .venv missing. Create it and install requirements.txt and requirements-mcp.txt first." }

$patch = @{}
if ($TaskName) { $patch.task_name = $TaskName }
if ($ConnectionHost) { $patch.connection_host = $ConnectionHost }
if ($PSBoundParameters.ContainsKey("AllowedHost")) { $patch.allowed_hosts = @($AllowedHost.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
if ($Port) { $patch.port = $Port }
if ($BindAddress) { $patch.bind_address = $BindAddress }
if ($Database) { $patch.database = $Database }
$configJson = ($patch | ConvertTo-Json -Compress) | & $marketPython $configHelper --config $ConfigPath --patch-stdin
if ($LASTEXITCODE -ne 0) { throw "Invalid MCP settings. No scheduled task was changed." }
$config = $configJson | ConvertFrom-Json
$TaskName = $config.task_name
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '"' + $runner + '" --config "' + $ConfigPath + '"'
$description = "Market Intelligence MCP login service. Managed by $marketRoot"

function Get-OwnedTask {
    # Enumerate the root folder: a missing task is different from a permission/service error.
    $found = @(Get-ScheduledTask -TaskPath "\" -ErrorAction Stop | Where-Object { $_.TaskName -eq $TaskName })
    if (-not $found.Count) { return $null }
    $task = $found[0]
    $owned = ($task.Description -eq $description -and @($task.Actions).Count -eq 1 -and
        $task.Actions[0].Execute -eq $marketPythonw -and $task.Actions[0].Arguments -eq $arguments)
    if (-not $owned) { throw "A task named '$TaskName' belongs to another configuration. Choose a different task name; it has been left unchanged." }
    return $task
}

if ($Preview) {
    # No task registration, startup, config writes or platform database access.
    [ordered]@{ task_name = $TaskName; user = $identity; execute = $marketPythonw; arguments = $arguments;
        working_directory = $marketRoot; trigger = "AtLogOn"; delay = "PT15S"; logon_type = "Interactive";
        run_level = "Limited"; execution_time_limit = "PT0S"; restart_minutes = 1; restart_count = 3;
        multiple_instances = "IgnoreNew"; config_path = $ConfigPath; config = $config } | ConvertTo-Json -Depth 5
    exit 0
}

Import-Module ScheduledTasks -ErrorAction Stop
$task = Get-OwnedTask
switch ($Action) {
    "Install" {
        if (-not (Test-Path -LiteralPath $marketPythonw)) { throw "pythonw.exe missing from platform .venv; recreate the virtual environment." }
        & $marketPython -c "from mcp.server import MCPServer"
        if ($LASTEXITCODE -ne 0) { throw "MCP dependency missing. Run .venv\Scripts\python.exe -m pip install -r requirements-mcp.txt first." }
        if ($task -and "$($task.State)" -eq "Running") { throw "Stop the login task before updating its settings." }
        $taskAction = New-ScheduledTaskAction -Execute $marketPythonw -Argument $arguments -WorkingDirectory $marketRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
        $trigger.Delay = "PT15S"
        $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3 -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName $TaskName -TaskPath "\" -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description $description -Force | Out-Null
        $configJson | & $marketPython $configHelper --config $ConfigPath --patch-stdin --save | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Task registered but settings could not be saved. Fix folder permissions and rerun before starting." }
        if ($StartNow) { Start-ScheduledTask -TaskName $TaskName -TaskPath "\" }
    }
    "Start" {
        if (-not $task) { throw "Install the MCP login task first." }
        Start-ScheduledTask -TaskName $TaskName -TaskPath "\"
    }
    "Stop" {
        if (-not $task) { throw "MCP login task is not installed." }
        Stop-ScheduledTask -TaskName $TaskName -TaskPath "\"
        # Also covers an existing background server adopted by the supervisor.
        & (Join-Path $PSScriptRoot "stop_mcp.ps1") -Database $config.database 6>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not stop the recorded MCP server." }
    }
}
$task = Get-OwnedTask
$result = [ordered]@{ installed = [bool]$task; task_name = $TaskName; user = $identity; state = "Not installed" }
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath "\"
    $result.state = "$($task.State)"
    $result.user = $task.Principal.UserId
    $result.last_run = $info.LastRunTime.ToString("s")
    $result.last_result = $info.LastTaskResult
}
if ($Json) { $result | ConvertTo-Json } else {
    Write-Host "MCP login task: $($result.task_name) - $($result.state)"
    Write-Host "Windows account: $($result.user) (runs at this user's login; no password stored)"
    Write-Host "Connection host: $($config.connection_host), port $($config.port). See Settings > MCP / AI Access for health and setup."
}
