"""Atomic single-instance PID-file lock, shared by `scripts/run_live_loop.py`
and `scripts/run_live_loop_supervisor.py`.

This environment's process launchers are known to spawn several
near-simultaneous OS processes for what looks like a single logical
launch. A plain "read PID file, then write PID file" check is not
atomic, so two near-simultaneous processes could both observe an
absent/stale lock and both proceed. `os.O_CREAT | os.O_EXCL` is used
instead: the OS guarantees only one caller can ever win the file
creation, even under a race, so only one process passes per lock cycle.
"""

from __future__ import annotations

import os
from pathlib import Path

import psutil


def acquire_single_instance_lock(pid_file: Path) -> bool:
    """Refuse to proceed if another live process already holds this lock file.

    Args:
        pid_file: The PID file to atomically create/inspect. Reused by
            whichever caller needs "exactly one of me running" semantics
            -- a different path per distinct process kind (the inner
            live loop vs. its outer supervisor) keeps their locks
            independent.

    Returns:
        True if this process may proceed (no other live process holds
        the lock, or the recorded PID belongs to this same process).
        False if another live process is already running under this lock file.
    """
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()
    while True:
        try:
            fd = os.open(pid_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                existing_pid = int(pid_file.read_text().strip())
            except (ValueError, OSError):
                existing_pid = None
            if (
                existing_pid is not None
                and existing_pid != current_pid
                and psutil.pid_exists(existing_pid)
            ):
                return False
            pid_file.unlink(missing_ok=True)
            continue
        else:
            with os.fdopen(fd, "w") as f:
                f.write(str(current_pid))
            return True
