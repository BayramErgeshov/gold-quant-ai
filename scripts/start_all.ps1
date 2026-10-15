# Starts the web UI and the live loop supervisor as independent,
# detached background processes. Registered as a Windows Scheduled Task
# ("GoldQuantAI-AutoStart", trigger: at logon) so both survive a machine
# reboot or a session restart without requiring anyone to notice the
# dashboard is down and manually relaunch it -- PostgreSQL/Redis/Qdrant
# already restart on their own via Docker Desktop's own "restart:
# unless-stopped" policy; this script is the equivalent guarantee for
# the two Python-level processes, which have no such OS-level
# supervision on their own.
#
# Idempotent: if either process is already running (checked via the
# same PID files `src.interfaces.web.process_control` and
# `scripts/run_live_loop.py` themselves maintain), this script does not
# start a second copy.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONPATH = "."

# `pythonw.exe`, not `python.exe` -- per the user's own report that a
# command-line window still flashed on start. `python.exe` is a
# console-subsystem binary: Windows allocates it a console at the OS
# level the instant the process is created, and `-WindowStyle Hidden`
# below only asks for it to be hidden *after* that -- unreliable enough
# in practice (interacts badly with some security/compatibility
# layers, and even a sub-second flash can kick a fullscreen game out of
# exclusive mode) that it is the real cause. `pythonw.exe` is the exact
# same interpreter built for the Windows GUI subsystem -- it never
# allocates a console at all, so there is nothing to flash. Safe here
# specifically because stdout/stderr are redirected to files below
# (`-RedirectStandardOutput`/`-RedirectStandardError`): `pythonw.exe`
# only leaves `sys.stdout`/`sys.stderr` as `None` when nothing
# redirects them, which is not the case here.
$pythonExe = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$logsDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

function Test-PidFileAlive([string]$PidFilePath) {
    if (-not (Test-Path $PidFilePath)) { return $false }
    $processId = Get-Content $PidFilePath -ErrorAction SilentlyContinue
    if (-not $processId) { return $false }
    return $null -ne (Get-Process -Id $processId -ErrorAction SilentlyContinue)
}

$webUiPidFile = Join-Path $logsDir "web_ui.pid"
if (-not (Test-PidFileAlive $webUiPidFile)) {
    $web = Start-Process -FilePath $pythonExe -ArgumentList "scripts\run_web_ui.py" `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsDir "web_ui_stdout.log") `
        -RedirectStandardError (Join-Path $logsDir "web_ui_stderr.log")
    Set-Content -Path $webUiPidFile -Value $web.Id
    Write-Output "Started web_ui (PID $($web.Id))"
} else {
    Write-Output "web_ui already running, skipped"
}

$supervisorPidFile = Join-Path $logsDir "live_loop_supervisor.pid"
if (-not (Test-PidFileAlive $supervisorPidFile)) {
    $loop = Start-Process -FilePath $pythonExe -ArgumentList "scripts\run_live_loop_supervisor.py" `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logsDir "live_loop_stdout.log") `
        -RedirectStandardError (Join-Path $logsDir "live_loop_stderr.log")
    Write-Output "Started live_loop_supervisor (PID $($loop.Id))"
} else {
    Write-Output "live_loop_supervisor already running, skipped"
}
