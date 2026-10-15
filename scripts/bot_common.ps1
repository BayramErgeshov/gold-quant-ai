# Shared helpers for bot_on.ps1 / bot_off.ps1. Dot-sourced, never run directly.

$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:LogsDir = Join-Path $ProjectRoot "logs"
$script:EnabledFlag = Join-Path $LogsDir "bot_enabled.flag"
$script:ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$script:DockerWaitSeconds = 150
# Only the three containers the native (non-containerized) web_ui/
# live_loop processes actually talk to. `docker-compose.yml` also
# defines postgres-exporter/redis-exporter/prometheus/grafana/app (a
# *second*, containerized copy of this same app, unused -- this project
# always runs web_ui/live_loop_supervisor directly via the venv, never
# that container) -- starting those every time would mean building/
# pulling images this setup never needs and a much slower "on" than
# the bot itself requires.
$script:CoreServices = @("postgres", "redis", "qdrant")

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Show-Balloon([string]$Title, [string]$Text, [string]$Icon = "Info") {
    $notify = New-Object System.Windows.Forms.NotifyIcon
    try {
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.Visible = $true
        $notify.ShowBalloonTip(6000, $Title, $Text, [System.Windows.Forms.ToolTipIcon]::$Icon)
        Start-Sleep -Seconds 6
    } finally {
        $notify.Dispose()
    }
}

function Test-DockerUp {
    # Checks the actual text of `docker info`'s stdout, not
    # `$LASTEXITCODE`. Root cause of a real incident that cost a long
    # debugging session: `docker info` writes a harmless platform
    # notice ("WARNING: No blkio throttle ...") to stderr even on a
    # perfectly healthy daemon. Windows PowerShell 5.1 has a documented
    # quirk where *any* stderr line from a native command becomes a
    # terminating `NativeCommandError` once `$ErrorActionPreference`
    # is "Stop" -- true regardless of redirection syntax (`2>&1`,
    # `2>$null`, or none at all), so this script's own top-level
    # `$ErrorActionPreference = "Stop"` made every single call here
    # throw and get caught below as "Docker not up", even when Docker
    # was completely healthy. A function-local override (shadows the
    # caller's "Stop" only for the lifetime of this function, per
    # PowerShell scoping -- no `$script:`/`$global:`) is the fix.
    $ErrorActionPreference = "Continue"
    try {
        $output = docker info 2>$null | Out-String
        return $output -match "Server Version:"
    } catch {
        return $false
    }
}

function Start-DockerDesktopIfInstalled {
    $candidates = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )
    $exe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) { return $false }
    Start-Process -FilePath $exe -WindowStyle Hidden
    return $true
}

function Test-PidFileAlive([string]$PidFilePath) {
    if (-not (Test-Path $PidFilePath)) { return $false }
    $procId = Get-Content $PidFilePath -ErrorAction SilentlyContinue
    if (-not $procId) { return $false }
    return $null -ne (Get-Process -Id $procId -ErrorAction SilentlyContinue)
}

function Test-BotRunning {
    (Test-PidFileAlive (Join-Path $LogsDir "web_ui.pid")) -or `
        (Test-PidFileAlive (Join-Path $LogsDir "live_loop_supervisor.pid"))
}
