"""Supervisor for `scripts/run_live_loop.py` -- restarts it on any crash or exit.

Per the user's explicit request: once started, the live loop must keep
running until the user deliberately stops it. `src.core.execution.mt5_client`'s
own module docstring documents that MT5's local IPC channel occasionally
fails in ways severe enough to take down the whole Python interpreter
outright (a native-extension failure, not a catchable Python exception)
-- no amount of internal `try`/`except` inside `run_live_loop.py` can
protect against that from the inside. This supervisor is the outer
safety net: it watches the inner process and relaunches it immediately
whenever it exits, for any reason, unless `logs/live_loop_stop.flag`
is present -- created by `src.interfaces.web.process_control.stop_live_loop()`
(the web UI's STOP/RESTART buttons) or a manual stop -- in which case it
exits without respawning.

Holds its own single-instance lock (`logs/live_loop_supervisor.pid`,
separate from the inner script's own `logs/live_loop.pid`) so exactly
one supervisor ever runs, no matter how many times it is launched.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/run_live_loop_supervisor.py
"""

from __future__ import annotations

import subprocess
import sys
import time

from src.common.logging import configure_logging, get_logger
from src.common.process_lock import acquire_single_instance_lock
from src.core.config.yaml_loader import PROJECT_ROOT
from src.settings import get_settings

logger = get_logger(__name__)

_SUPERVISOR_PID_FILE = PROJECT_ROOT / "logs" / "live_loop_supervisor.pid"
_ENTRYPOINT = PROJECT_ROOT / "scripts" / "run_live_loop.py"
_STOP_FLAG = PROJECT_ROOT / "logs" / "live_loop_stop.flag"
# Backs off restarts slightly so a persistently-failing child (bad
# config, DB unreachable) does not spin the CPU with instant relaunches
# every fraction of a second -- still resumes trading within seconds of
# any transient crash, matching "must not stop until I stop it."
_RESTART_DELAY_SECONDS = 5


def main() -> int:
    settings = get_settings()
    configure_logging(settings)

    if not acquire_single_instance_lock(_SUPERVISOR_PID_FILE):
        logger.error("live_loop_supervisor_startup_failed", reason="already_running")
        return 1

    _STOP_FLAG.unlink(missing_ok=True)
    restart_count = 0

    while True:
        if _STOP_FLAG.exists():
            logger.info("live_loop_supervisor_stopped", restart_count=restart_count)
            _STOP_FLAG.unlink(missing_ok=True)
            return 0

        logger.info("live_loop_supervisor_launching_child", restart_count=restart_count)
        process = subprocess.Popen(  # noqa: S603 - fixed, non-shell argv; no user input involved
            [sys.executable, str(_ENTRYPOINT)], cwd=str(PROJECT_ROOT)
        )
        exit_code = process.wait()
        logger.warning("live_loop_child_exited", exit_code=exit_code, restart_count=restart_count)

        if _STOP_FLAG.exists():
            logger.info("live_loop_supervisor_stopped", restart_count=restart_count)
            _STOP_FLAG.unlink(missing_ok=True)
            return 0

        restart_count += 1
        time.sleep(_RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
