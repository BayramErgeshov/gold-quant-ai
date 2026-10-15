# Creates two Desktop shortcuts -- "GOLD Bot - Включить.lnk" and
# "GOLD Bot - Выключить.lnk" -- each running its own script
# (bot_on.vbs / bot_off.vbs) with a guaranteed-invisible window. Two
# separate, unambiguous shortcuts on purpose: a single toggle shortcut
# is confusing the moment the user does not already know the bot's
# current state, since clicking it then does the opposite of what they
# expect. Removes any stale shortcut from an earlier version of this
# script (the single-toggle one, and the one pointing straight at
# powershell.exe -- see bot_on.vbs's own comment for why that alone
# was not reliably invisible).
#
# Run this once:
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\create_bot_shortcut.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
# `wscript.exe` explicitly, not just the .vbs file's own extension
# association -- a GUI-subsystem binary with nothing to show, and this
# way it is never at the mercy of a `cscript.exe` (console-subsystem)
# association some other tool might have set as the default .vbs handler.
$wscriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"

function New-BotShortcut([string]$Name, [string]$VbsFile, [string]$Description) {
    $shortcutPath = Join-Path $desktop "$Name.lnk"
    $targetVbs = Join-Path $ProjectRoot "scripts\$VbsFile"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $wscriptExe
    $shortcut.Arguments = "`"$targetVbs`""
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.IconLocation = "$PSHOME\powershell.exe,0"
    $shortcut.Description = $Description
    $shortcut.Save()
    Write-Output "Создан ярлык: $shortcutPath"
}

$staleShortcuts = @(
    "GOLD Bot.lnk",
    "GOLD Bot - Включить.lnk",
    "GOLD Bot - Выключить.lnk"
)
foreach ($name in $staleShortcuts) {
    Remove-Item -Path (Join-Path $desktop $name) -Force -ErrorAction SilentlyContinue
}

New-BotShortcut "GOLD Bot - Включить" "bot_on.vbs" "Включить GOLD QUANT AI (один клик, без окон)"
New-BotShortcut "GOLD Bot - Выключить" "bot_off.vbs" "Выключить GOLD QUANT AI (один клик, без окон)"
