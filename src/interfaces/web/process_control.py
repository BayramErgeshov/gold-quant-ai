"""Live loop process control for the "Live Control" production requirement.

Per the spec: "Buttons: START, STOP, PAUSE, EMERGENCY CLOSE, RESTART,"
extended per the user's explicit request that once started, the live
loop must keep running until deliberately stopped. START/RESTART now
spawn `scripts/run_live_loop_supervisor.py` rather than
`scripts/run_live_loop.py` directly -- the supervisor watches the inner
process and relaunches it immediately on any exit (including a hard
native-extension crash from MT5's local IPC bridge, which bypasses
Python's own exception handling entirely and previously looked like
"the bot just stops"). Tracked via a PID file rather than in-memory
state -- this web UI process and the live loop are already independent
processes (`src.interfaces.web.app`'s own module docstring), and a PID
file survives this web UI process restarting on its own. PAUSE is a
separate, softer control: `RuntimeSettings.paused` (see
`settings_service.py`), which the running live loop process itself
checks every cycle to skip new analysis while still monitoring
already-open positions -- STOP, by contrast, halts that monitoring
entirely, since no process is running at all.

STOP creates `logs/live_loop_stop.flag` *before* terminating anything,
so the supervisor -- even if it is mid-restart at that exact moment --
sees the flag and exits instead of relaunching a new child that would
otherwise outlive the "stopped" state. Termination then walks the whole
process tree (supervisor + its current child) via
`psutil.Process.children(recursive=True)`, since a plain single-PID
`terminate()` on the supervisor alone would leave an orphaned live loop
child still running.

START never trusts `subprocess.Popen(...).pid` as the supervisor's real
identity. Empirically, on this environment, `.venv/Scripts/python.exe`
relaunches into a separate real interpreter process rather than
executing in place -- `Popen.pid` names a short-lived launcher stub,
not the process that actually runs `run_live_loop_supervisor.py`. Since
the supervisor's own `acquire_single_instance_lock` call registers its
own *real* `os.getpid()` into this same PID file, writing the stub's
PID here first would collide with that self-registration and make the
supervisor incorrectly believe another instance already holds the
lock (observed directly: a freshly-started supervisor logging
`already_running` against itself). START instead polls for that
self-registration to appear, which is the only trustworthy source of
the real PID.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time

import psutil

from src.common.logging import get_logger
from src.core.config.yaml_loader import PROJECT_ROOT

logger = get_logger(__name__)

_PID_FILE = PROJECT_ROOT / "logs" / "live_loop_supervisor.pid"
_STOP_FLAG = PROJECT_ROOT / "logs" / "live_loop_stop.flag"
_ENTRYPOINT = PROJECT_ROOT / "scripts" / "run_live_loop_supervisor.py"
_STDOUT_LOG = PROJECT_ROOT / "logs" / "live_loop_web_managed.log"
_TERMINATE_WAIT_SECONDS = 10
_STARTUP_REGISTRATION_TIMEOUT_SECONDS = 20
_STARTUP_POLL_INTERVAL_SECONDS = 0.1


def _read_pid() -> int | None:
    if not _PID_FILE.is_file():
        return None
    try:
        return int(_PID_FILE.read_text().strip())
    except ValueError:
        return None


def is_live_loop_running() -> bool:
    """Check whether the live loop supervisor this web UI last started is still alive.

    Returns:
        True if the PID file names a live process, False otherwise
        (never started, already stopped, or crashed).
    """
    pid = _read_pid()
    return pid is not None and psutil.pid_exists(pid)


def start_live_loop() -> bool:
    """Spawn the live loop supervisor as a new background process, if not already running.

    Returns:
        True once the supervisor has registered its own real PID (within
        `_STARTUP_REGISTRATION_TIMEOUT_SECONDS`), False if one was
        already running, or if it never registered in time.
    """
    if is_live_loop_running():
        return False

    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    # A stale flag from a previous STOP must not make the freshly-started
    # supervisor immediately exit -- it also clears this itself on
    # startup, but clearing it here too avoids a window where a
    # `stop_live_loop()` call racing this one could otherwise leave the
    # flag set after this function already returned "started."
    _STOP_FLAG.unlink(missing_ok=True)
    with _STDOUT_LOG.open("ab") as log_file:
        subprocess.Popen(  # noqa: S603 - fixed, non-shell argv; no user input involved
            [sys.executable, str(_ENTRYPOINT)],
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    deadline = time.monotonic() + _STARTUP_REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if is_live_loop_running():
            logger.info("live_loop_started_by_web_ui", pid=_read_pid())
            return True
        time.sleep(_STARTUP_POLL_INTERVAL_SECONDS)
    logger.error("live_loop_start_timed_out")
    return False


def stop_live_loop() -> bool:
    """Terminate the currently running live loop supervisor and its child, if any.

    Blocks briefly until every process in the tree has actually exited --
    `psutil.Process.terminate()` only sends the kill signal and returns
    immediately, so a caller that started a new process right after this
    one returns could otherwise race a not-yet-dead old process.

    Returns:
        True if a running process was terminated, False if none was running.
    """
    pid = _read_pid()
    if pid is None or not psutil.pid_exists(pid):
        return False
    # Written first: even if the supervisor is between "child just
    # exited" and "spawn the next one" at this exact instant, it checks
    # for this flag before every relaunch and will exit instead.
    _STOP_FLAG.parent.mkdir(parents=True, exist_ok=True)
    _STOP_FLAG.touch()
    try:
        supervisor = psutil.Process(pid)
        processes = [*supervisor.children(recursive=True), supervisor]
        for process in processes:
            with contextlib.suppress(psutil.NoSuchProcess):
                process.terminate()
        _, alive = psutil.wait_procs(processes, timeout=_TERMINATE_WAIT_SECONDS)
        for process in alive:
            with contextlib.suppress(psutil.NoSuchProcess):
                process.kill()
    finally:
        _PID_FILE.unlink(missing_ok=True)
        _STOP_FLAG.unlink(missing_ok=True)
    logger.info("live_loop_stopped_by_web_ui", pid=pid)
    return True


def restart_live_loop() -> None:
    """Stop the current live loop process (if any) and start a fresh one."""
    stop_live_loop()
    start_live_loop()


__all__ = [
    "is_live_loop_running",
    "start_live_loop",
    "stop_live_loop",
    "restart_live_loop",
]
