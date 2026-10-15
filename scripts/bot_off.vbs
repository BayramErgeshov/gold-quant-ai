' Launches bot_off.ps1 with a guaranteed-invisible window.
' See bot_on.vbs's own comment for why a .vbs wrapper, not PowerShell's
' own "-WindowStyle Hidden", is what actually guarantees this.
Set objShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "\bot_off.ps1"""
objShell.Run cmd, 0, True
