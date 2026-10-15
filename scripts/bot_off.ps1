# ALWAYS turns GOLD QUANT AI off -- web_ui, the live-loop supervisor
# and its inner process, and the Docker containers (postgres/redis/
# qdrant). Idempotent: if everything is already stopped, this just
# confirms it rather than erroring. See bot_on.ps1's own comment for
# why this is a separate, unambiguous script rather than one shared
# toggle.

# NOT "Stop" -- see bot_on.ps1's own comment: Windows PowerShell 5.1
# turns any stderr line a native command writes into a terminating
# error under "Stop", regardless of redirection syntax, which made
# `docker compose stop` below throw even on a clean, successful stop.
$ErrorActionPreference = "SilentlyContinue"
. (Join-Path $PSScriptRoot "bot_common.ps1")

if (-not (Test-BotRunning) -and -not (Test-Path $EnabledFlag)) {
    Show-Balloon "GOLD QUANT AI" "Бот уже выключен." "Info"
    exit 0
}

& (Join-Path $PSScriptRoot "stop_all.ps1") *> $null
try {
    docker compose -f $ComposeFile stop @CoreServices *> $null
} catch {
    # Docker not running/installed -- nothing to stop, not an error.
}
Remove-Item -Path $EnabledFlag -Force -ErrorAction SilentlyContinue

Show-Balloon "GOLD QUANT AI" "Бот выключен. Ничего не работает в фоне." "Info"
