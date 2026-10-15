# ALWAYS turns GOLD QUANT AI on -- Docker (postgres/redis/qdrant),
# web_ui, the live-loop supervisor and its inner process. Idempotent:
# if everything is already running, this just confirms it rather than
# erroring or doing anything surprising.
#
# Deliberately NOT a toggle, per a real incident: a single "one button
# does both" switch is ambiguous the moment the user does not already
# know the current state -- clicking it while already on silently
# turns everything off instead of confirming it is on, which looks
# exactly like "nothing works" with no indication why. Two separate,
# always-does-the-same-thing shortcuts remove that ambiguity entirely.
#
# Does NOT try to launch Docker Desktop itself -- that auto-launch
# path turned out to be the single slowest, least predictable part of
# this script (Docker Desktop's own cold-start time varies from
# seconds to minutes depending on machine state) and makes "one click"
# feel broken rather than fast. If Docker is not already running, this
# says so plainly and exits rather than guessing at a wait time.

# NOT "Stop" -- Windows PowerShell 5.1's documented quirk turns *any*
# stderr line a native command writes (Docker's CLI routinely writes
# routine status/warning lines there, not just real errors) into a
# terminating `NativeCommandError` when this is "Stop", regardless of
# redirection syntax. That silently aborted this script's `docker
# compose up` line mid-run for a long time before being traced here.
# "SilentlyContinue", not "Continue" -- the latter still logs each such
# line as a scary-looking (but harmless) error record.
$ErrorActionPreference = "SilentlyContinue"
. (Join-Path $PSScriptRoot "bot_common.ps1")

$logFile = Join-Path $LogsDir "bot_on_last_run.log"
function Log([string]$Message) {
    "$(Get-Date -Format 'HH:mm:ss') $Message" | Add-Content -Path $logFile
}

"--- bot_on.ps1 started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---" | Set-Content -Path $logFile

if (Test-BotRunning) {
    Log "already running -- nothing to do"
    Show-Balloon "GOLD QUANT AI" "Бот уже включён и работает." "Info"
    exit 0
}

Log "checking Docker"
if (-not (Test-DockerUp)) {
    Log "Docker not up -- aborting"
    Show-Balloon "GOLD QUANT AI" "Docker не запущен. Запустите Docker Desktop и повторите." "Warning"
    exit 1
}
Log "Docker is up"

Log "starting containers: $CoreServices"
docker compose -f $ComposeFile up -d @CoreServices *>> $logFile
Log "containers command finished, exit=$LASTEXITCODE"

New-Item -ItemType File -Force -Path $EnabledFlag | Out-Null
Log "calling start_all.ps1"
& (Join-Path $PSScriptRoot "start_all.ps1") *>> $logFile
Log "start_all.ps1 finished"

Start-Sleep -Seconds 3
if (Test-BotRunning) {
    Log "confirmed running"
    Show-Balloon "GOLD QUANT AI" "Бот включён." "Info"
} else {
    Log "NOT running after start attempt"
    Show-Balloon "GOLD QUANT AI" "Запуск не удался -- проверьте logs\bot_on_last_run.log." "Warning"
    exit 1
}
