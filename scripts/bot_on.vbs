' Launches bot_on.ps1 with a guaranteed-invisible window.
'
' Per the user's own report: a console window still flashed even with
' PowerShell's own "-WindowStyle Hidden". `powershell.exe` is itself a
' console-subsystem binary -- Windows allocates it a console at process
' creation before "-WindowStyle Hidden" has any say, which is
' unreliable enough in practice to kick a fullscreen game out of
' exclusive mode for a single frame. `WScript.Shell.Run(cmd, 0, ...)`
' passes an explicit hidden show-window flag straight to the Win32
' CreateProcess call itself (via the Shell API), which is the
' consistently reliable way to launch something with zero visible
' window on Windows -- and `wscript.exe`, which runs this file, is
' itself a GUI-subsystem binary with nothing to show in the first place.
Set objShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptDir & "\bot_on.ps1"""
objShell.Run cmd, 0, True
