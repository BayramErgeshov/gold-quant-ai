# Stops every GOLD QUANT AI process started by `start_all.ps1` --
# `web_ui`, the live-loop supervisor, and its inner `run_live_loop.py`
# child. A standalone counterpart to `src.interfaces.web.process_control
# .stop_live_loop()` that does not depend on `web_ui`'s own API being up
# (it is one of the things being stopped), so it can run from
# `scripts/bot_off.ps1` even when nothing is currently running.
#
# Writes `logs/live_loop_stop.flag` *before* killing anything, mirroring
# `process_control.stop_live_loop()`: if the supervisor is caught
# between "child just exited" and "spawn the next one" at this exact
# instant, it checks for this flag before every relaunch and exits
# instead of fighting this script.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $ProjectRoot "logs"
$stopFlag = Join-Path $logsDir "live_loop_stop.flag"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
New-Item -ItemType File -Force -Path $stopFlag | Out-Null

function Stop-ByPidFile([string]$Name, [string]$PidFilePath) {
    if (-not (Test-Path $PidFilePath)) {
        Write-Output "$Name already stopped (no PID file)"
        return
    }
    $processId = Get-Content $PidFilePath -ErrorAction SilentlyContinue
    if ($processId) {
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Output "Stopped $Name (PID $processId)"
        } else {
            Write-Output "$Name already stopped (stale PID file)"
        }
    }
    Remove-Item -Path $PidFilePath -Force -ErrorAction SilentlyContinue
}

# Inner loop first, then its supervisor, so the supervisor cannot
# relaunch a fresh child in the gap between the two.
Stop-ByPidFile "live_loop" (Join-Path $logsDir "live_loop.pid")
Stop-ByPidFile "live_loop_supervisor" (Join-Path $logsDir "live_loop_supervisor.pid")
Stop-ByPidFile "web_ui" (Join-Path $logsDir "web_ui.pid")

Remove-Item -Path $stopFlag -Force -ErrorAction SilentlyContinue
Write-Output "All GOLD QUANT AI processes stopped."
