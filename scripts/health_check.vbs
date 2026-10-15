' Launches health_check.py with a guaranteed-invisible window, and its
' own stdout/stderr safely redirected to log files (so this keeps using
' the normal console-subsystem python.exe -- whose console this
' launcher's own hidden show-window flag prevents from ever appearing
' -- rather than pythonw.exe, which would otherwise leave
' sys.stdout/sys.stderr as None and crash the moment the script tries
' to log anything).
'
' See bot_on.vbs's own comment for why `WScript.Shell.Run(cmd, 0, ...)`,
' not a Scheduled Task's own "-Hidden" setting (Task Scheduler UI
' listing visibility only, not window visibility) or PowerShell's
' "-WindowStyle Hidden", is what actually guarantees no window ever
' appears -- a Scheduled Task running "only when the user is logged on"
' runs in that user's own visible desktop session, where either of
' those could still flash a console.
'
' Built with Chr(34) for every embedded quote rather than VBScript's
' own `""`-inside-a-string-literal escaping, which is easy to get
' subtly wrong once a command is nested two shells deep (wscript ->
' cmd.exe -> python.exe), each with its own quoting rules.
Set objShell = CreateObject("WScript.Shell")
Set objFso = CreateObject("Scripting.FileSystemObject")
scriptDir = objFso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = objFso.GetParentFolderName(scriptDir)
pythonExe = projectRoot & "\.venv\Scripts\python.exe"
scriptPath = scriptDir & "\health_check.py"
logPath = projectRoot & "\logs\health_check_stdout.log"
errPath = projectRoot & "\logs\health_check_stderr.log"

q = Chr(34)
innerCmd = q & pythonExe & q & " " & q & scriptPath & q & _
    " >> " & q & logPath & q & " 2>> " & q & errPath & q
cmd = "cmd.exe /c " & q & innerCmd & q

' `WScript.Shell.Run` otherwise uses `wscript.exe`'s own current
' directory, not this script's folder, and does not set `PYTHONPATH` --
' `health_check.py` imports `src.*` as an absolute package, which only
' resolves with both the project root as the working directory *and*
' on `PYTHONPATH` (mirrors `PYTHONPATH=.` / `-WorkingDirectory`
' everywhere else this project launches Python, e.g. start_all.ps1).
objShell.CurrentDirectory = projectRoot
objShell.Environment("PROCESS")("PYTHONPATH") = "."
objShell.Run cmd, 0, True
