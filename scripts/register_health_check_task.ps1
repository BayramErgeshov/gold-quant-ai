# Registers "GoldQuantAI-HealthCheck" -- a Windows Scheduled Task that
# runs scripts/health_check.py every 5 minutes, independently of any
# interactive session or Claude Code being open. Mirrors the existing
# "GoldQuantAI-AutoStart" task's own registration style
# (scripts/start_all.ps1), but on a repeating time trigger instead of
# "at logon" -- a reboot alone does not catch a process that dies hours
# later without the machine restarting.
#
# Run once, interactively, with the permissions needed to register a
# Scheduled Task:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_health_check_task.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TaskName = "GoldQuantAI-HealthCheck"
# `wscript.exe` running `health_check.vbs`, not `python.exe` directly --
# per the user's own report of a flashing console window. A task
# registered without an explicit `-Principal`/`-User` runs "only when
# the user is logged on", i.e. inside that user's own visible desktop
# session, where a console-subsystem `python.exe` can still flash a
# window regardless of the `-Hidden` setting below (that setting only
# controls the task's own visibility in the Task Scheduler UI list, not
# its spawned process's window). `health_check.vbs` wraps the exact
# same `python.exe` call with its output still safely redirected to log
# files, via `WScript.Shell.Run`'s own explicit hidden show-window flag
# -- the one mechanism that reliably suppresses this regardless of
# subsystem type. See bot_on.vbs's own comment for the full reasoning.
$WscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"
$VbsPath = Join-Path $ProjectRoot "scripts\health_check.vbs"

$action = New-ScheduledTaskAction -Execute $WscriptExe -Argument "`"$VbsPath`"" -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Проверяет каждые 5 минут, что web_ui и live_loop_supervisor реально работают (только когда бот включён через GOLD Bot - Включить.lnk); при падении перезапускает через start_all.ps1 и шлёт уведомление в Telegram. Полностью ничего не делает, когда бот выключен. Запускается без единого видимого окна." `
    | Out-Null

Write-Output "Registered scheduled task '$TaskName' (every 5 minutes)."
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
