"""Unit tests for the "Live Control" START/STOP/RESTART process management.

Uses tiny standalone scripts as stand-ins for
`scripts/run_live_loop_supervisor.py` (which needs a real DB/MT5
connection to run at all) -- only the process-lifecycle mechanics
(spawn, PID-file tracking, terminate) are under test here, not the live
loop itself.

`start_live_loop()` deliberately waits for the spawned process to
self-register its own real PID into `process_control._PID_FILE` (via
`acquire_single_instance_lock`, the same helper the real supervisor
uses) rather than trusting `subprocess.Popen(...).pid` -- this
environment's `.venv/Scripts/python.exe` relaunches into a separate
real interpreter process, so `Popen.pid` never names the process
actually running the entrypoint's code. `self_registering_entrypoint`
below stands in for "the supervisor itself" (self-registers); plain
`sleep_entrypoint` stands in for "the inner live loop the supervisor
spawns" (does not -- in production that inner process registers into a
*different* file, `logs/live_loop.pid`, which `process_control.py`
never tracks).
"""

from __future__ import annotations

import time
from pathlib import Path

import psutil
import pytest

from src.core.config.yaml_loader import PROJECT_ROOT
from src.interfaces.web import process_control

pytestmark = pytest.mark.unit

_SLEEP_SCRIPT = """
import time
time.sleep(30)
"""

_SELF_REGISTERING_SCRIPT_TEMPLATE = """
import sys
sys.path.insert(0, r"{project_root}")
from pathlib import Path
from src.common.process_lock import acquire_single_instance_lock

if not acquire_single_instance_lock(Path(r"{pid_file}")):
    sys.exit(1)

import time
time.sleep(30)
"""


@pytest.fixture
def sleep_entrypoint(tmp_path: Path) -> Path:
    """A plain, non-registering stand-in for the inner live loop process."""
    script = tmp_path / "sleep_forever.py"
    script.write_text(_SLEEP_SCRIPT, encoding="utf-8")
    return script


@pytest.fixture
def self_registering_entrypoint(tmp_path: Path, _isolated_pid_file: None) -> Path:
    """A self-registering stand-in for the supervisor itself (see module docstring).

    Explicitly depends on `_isolated_pid_file` (an autouse fixture) so
    `process_control._PID_FILE` is guaranteed already patched to its
    tmp_path value before this fixture reads it to embed into the
    generated script.
    """
    script = tmp_path / "self_registering.py"
    script.write_text(
        _SELF_REGISTERING_SCRIPT_TEMPLATE.format(
            project_root=PROJECT_ROOT, pid_file=process_control._PID_FILE
        ),
        encoding="utf-8",
    )
    return script


@pytest.fixture(autouse=True)
def _isolated_pid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_control, "_PID_FILE", tmp_path / "live_loop.pid")
    monkeypatch.setattr(process_control, "_STDOUT_LOG", tmp_path / "live_loop.log")
    monkeypatch.setattr(process_control, "_STOP_FLAG", tmp_path / "live_loop_stop.flag")


def _stop_if_running() -> None:
    if process_control.is_live_loop_running():
        process_control.stop_live_loop()


def test_is_live_loop_running_is_false_before_anything_starts() -> None:
    assert process_control.is_live_loop_running() is False


def test_start_live_loop_spawns_a_tracked_process(
    self_registering_entrypoint: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process_control, "_ENTRYPOINT", self_registering_entrypoint)

    started = process_control.start_live_loop()

    try:
        assert started is True
        assert process_control.is_live_loop_running() is True
        pid = int(process_control._PID_FILE.read_text())
        assert psutil.pid_exists(pid)
    finally:
        _stop_if_running()


def test_start_live_loop_does_nothing_when_already_running(
    self_registering_entrypoint: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process_control, "_ENTRYPOINT", self_registering_entrypoint)
    process_control.start_live_loop()

    try:
        started_again = process_control.start_live_loop()
        assert started_again is False
    finally:
        _stop_if_running()


def test_stop_live_loop_terminates_the_process(
    self_registering_entrypoint: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process_control, "_ENTRYPOINT", self_registering_entrypoint)
    process_control.start_live_loop()
    pid = int(process_control._PID_FILE.read_text())

    stopped = process_control.stop_live_loop()

    assert stopped is True
    assert process_control.is_live_loop_running() is False
    assert psutil.pid_exists(pid) is False


def test_stop_live_loop_returns_false_when_nothing_is_running() -> None:
    assert process_control.stop_live_loop() is False


_FAKE_SUPERVISOR_SCRIPT_TEMPLATE = """
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"{project_root}")
from src.common.process_lock import acquire_single_instance_lock

if not acquire_single_instance_lock(Path(r"{pid_file}")):
    sys.exit(1)

stop_flag = Path(r"{stop_flag}")
child_script = Path(r"{child_script}")
children_log = Path(r"{children_log}")

while True:
    if stop_flag.exists():
        break
    proc = subprocess.Popen([sys.executable, str(child_script)])
    with children_log.open("a") as f:
        f.write(str(proc.pid) + "\\n")
    proc.wait()
    if stop_flag.exists():
        break
"""


@pytest.fixture
def fake_supervisor_entrypoint(
    tmp_path: Path, sleep_entrypoint: Path, _isolated_pid_file: None
) -> tuple[Path, Path]:
    """A real-supervisor-shaped stand-in: self-registers, then relaunches
    `sleep_entrypoint` (the plain, non-registering inner-child stand-in)
    until the stop flag appears -- mirrors `run_live_loop_supervisor.py`'s
    own shape exactly, including its own self-registration via
    `acquire_single_instance_lock`.

    Returns:
        `(supervisor_script, children_log)` -- `children_log` records
        every child PID this fake supervisor ever spawns, one per line,
        so a test can confirm no new child appears after stopping.
    """
    children_log = tmp_path / "children.log"
    script = tmp_path / "fake_supervisor.py"
    script.write_text(
        _FAKE_SUPERVISOR_SCRIPT_TEMPLATE.format(
            project_root=PROJECT_ROOT,
            pid_file=process_control._PID_FILE,
            stop_flag=process_control._STOP_FLAG,
            child_script=sleep_entrypoint,
            children_log=children_log,
        ),
        encoding="utf-8",
    )
    return script, children_log


def test_stop_live_loop_prevents_the_supervisor_from_respawning_a_child(
    fake_supervisor_entrypoint: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Reproduces the exact bug this fixes: a plain single-PID terminate()
    # on the supervisor alone could race a mid-restart supervisor into
    # spawning one more orphaned child right after being killed. The
    # stop flag being written *before* termination is what prevents that.
    supervisor_script, children_log = fake_supervisor_entrypoint
    monkeypatch.setattr(process_control, "_ENTRYPOINT", supervisor_script)
    process_control.start_live_loop()
    supervisor_pid = int(process_control._PID_FILE.read_text())

    def _wait_for_first_child(timeout: float = 5.0) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if children_log.is_file() and children_log.read_text().strip():
                return int(children_log.read_text().strip().splitlines()[0])
            time.sleep(0.05)
        raise TimeoutError("fake supervisor never spawned a child")

    first_child_pid = _wait_for_first_child()

    stopped = process_control.stop_live_loop()

    assert stopped is True
    assert psutil.pid_exists(supervisor_pid) is False
    assert psutil.pid_exists(first_child_pid) is False
    assert not process_control._STOP_FLAG.exists()
    logged_children_at_stop = children_log.read_text().splitlines()
    # Give any would-be orphaned respawn a moment to appear.
    time.sleep(1.0)
    assert children_log.read_text().splitlines() == logged_children_at_stop


def test_restart_live_loop_replaces_the_running_process(
    self_registering_entrypoint: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process_control, "_ENTRYPOINT", self_registering_entrypoint)
    process_control.start_live_loop()
    original_pid = int(process_control._PID_FILE.read_text())

    try:
        process_control.restart_live_loop()

        assert process_control.is_live_loop_running() is True
        new_pid = int(process_control._PID_FILE.read_text())
        assert new_pid != original_pid
    finally:
        _stop_if_running()
