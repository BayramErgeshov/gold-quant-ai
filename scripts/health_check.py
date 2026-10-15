"""Periodic system health watchdog -- the "is it actually running" check.

Per the user's explicit request after the platform silently went down
(both `web_ui` and `live_loop_supervisor` not running at all, nothing
left to notice or recover on its own): `scripts/run_live_loop_supervisor.py`
only restarts its *own* inner process on crash -- it cannot restart
itself, and there was previously nothing that periodically verified the
top-level processes were running at all (e.g. after a reboot where the
"at logon" Scheduled Task did not fire, or an external event killed both
processes outright).

This script is the outer-outer safety net, meant to run on its own
schedule (a Windows Scheduled Task, registered once via
`scripts/register_health_check_task.ps1`) independently of whether
Claude Code or any interactive session is open:

1. Checks `web_ui` (PID + a real HTTP call to `/api/control/status`) and
   `live_loop_supervisor` (PID, mirroring
   `src.interfaces.web.process_control.is_live_loop_running`).
2. Checks that the live loop is actually *completing cycles*, not just
   that its process exists: queries the latest `shakky_scan_snapshot` /
   `swing_scan_snapshot` rows in `system_logs` and flags staleness. This
   is the check that (1) above structurally cannot do -- a production
   incident on 2026-10-07 had `gqa_postgres` crash and stay down for five
   days straight while `live_loop_supervisor` kept respawning its child
   every few seconds (each child instantly died trying to reach the
   unreachable database, exit code 1, no traceback ever written anywhere
   since the crash happens before logging is even configured) -- `psutil`
   saw a live PID the entire time and `web_ui` kept answering
   `/api/control/status` with `running: true`, so nothing before this
   check would have ever noticed. A fresh row in `system_logs` is proof
   the loop ran a real, successful, database-backed cycle -- not just
   that *a* process is alive.
3. If anything is down or stale, runs `scripts/start_all.ps1` (already
   idempotent -- safe even if some of it is already up) *and* brings the
   core Docker containers back up (`docker compose up -d postgres redis
   qdrant`, equally idempotent) -- step (1) alone never restarts a dead
   Postgres container, which is exactly what let the 2026-10-07 incident
   run undetected and unrepaired for five days. Re-checks once after a
   short wait.
4. Sends a Telegram alert whenever something was found down, stating
   whether the automatic recovery attempt succeeded -- the one case this
   cannot paper over (the MT5 terminal itself being unreachable, or a
   genuine Postgres data problem) still needs a human, and this never
   hides that behind a silent retry loop.

Respects the master on/off switch (`scripts/bot_on.ps1` /
`scripts/bot_off.ps1` / `logs/bot_enabled.flag`): when the user has
turned the bot off, this exits immediately and does nothing at all --
it must never relaunch something the user deliberately stopped.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/health_check.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import psutil

from src.common.logging import configure_logging, get_logger
from src.core.config.yaml_loader import PROJECT_ROOT
from src.core.notifications.telegram_client import RealTelegramNotifier
from src.database.postgres.session import get_session
from src.repositories.system_log_repository import SystemLogRepository
from src.settings import get_settings

logger = get_logger(__name__)

_ENABLED_FLAG = PROJECT_ROOT / "logs" / "bot_enabled.flag"
_WEB_UI_PID_FILE = PROJECT_ROOT / "logs" / "web_ui.pid"
_SUPERVISOR_PID_FILE = PROJECT_ROOT / "logs" / "live_loop_supervisor.pid"
_START_ALL_SCRIPT = PROJECT_ROOT / "scripts" / "start_all.ps1"
_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
_CORE_SERVICES = ("postgres", "redis", "qdrant")
_HEALTH_URL = "http://127.0.0.1:8420/api/control/status"
_HTTP_TIMEOUT_SECONDS = 10.0
# Long enough for a freshly-recovered Postgres container to accept
# connections *and* for the already-running supervisor's next child to
# finish a first real scan cycle (observed ~10-40s end-to-end) -- a short
# wait here would otherwise report "recovery failed" on a database-outage
# case that is, in fact, actively recovering right on schedule.
_RECOVERY_WAIT_SECONDS = 75.0
# Every scan-producing engine's own `next_scan_minutes` is 1-5 minutes
# (`config/risk.yaml`); ten minutes of total silence from either source
# is well past any normal jitter/startup delay but still catches a crash
# loop (whose child dies in seconds, not minutes) quickly.
_MAX_SNAPSHOT_STALENESS = dt.timedelta(minutes=10)
_SCAN_SNAPSHOT_SOURCES = ("shakky_scan_snapshot", "swing_scan_snapshot")


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.is_file():
        return None
    try:
        return int(pid_file.read_text().strip())
    except ValueError:
        return None


def _process_alive(pid_file: Path) -> bool:
    pid = _read_pid(pid_file)
    return pid is not None and psutil.pid_exists(pid)


def _web_ui_responds() -> bool:
    try:
        with urllib.request.urlopen(_HEALTH_URL, timeout=_HTTP_TIMEOUT_SECONDS):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


async def _check_scan_freshness() -> list[str]:
    """Verify the live loop is completing real, database-backed cycles.

    Returns one problem string per stale/missing source, plus a single
    "database unreachable" problem (and nothing else) if the database
    itself cannot be reached at all.
    """
    try:
        async with get_session() as session:
            repo = SystemLogRepository(session)
            problems = []
            now = dt.datetime.now(dt.UTC)
            for source in _SCAN_SNAPSHOT_SOURCES:
                rows = await repo.list_by_source(source, limit=1)
                if not rows:
                    problems.append(f"{source}: ни одного цикла ещё не было записано")
                    continue
                age = now - rows[0].created_at
                if age > _MAX_SNAPSHOT_STALENESS:
                    minutes = int(age.total_seconds() // 60)
                    problems.append(f"{source}: нет новых циклов уже {minutes} мин")
            return problems
    except Exception:
        logger.exception("health_check_database_unreachable")
        return ["database: Postgres недоступен (цикл не может ничего сделать)"]


def _check_once() -> list[str]:
    """Return every process-level problem found this check."""
    problems = []
    if not _process_alive(_WEB_UI_PID_FILE):
        problems.append("web_ui: процесс не запущен")
    elif not _web_ui_responds():
        problems.append("web_ui: процесс есть, но API не отвечает")
    if not _process_alive(_SUPERVISOR_PID_FILE):
        problems.append("live_loop_supervisor: процесс не запущен")
    return problems


def _run_start_all() -> None:
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_START_ALL_SCRIPT),
        ],
        cwd=str(PROJECT_ROOT),
        timeout=60,
        check=False,
    )


def _run_docker_recovery() -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(_COMPOSE_FILE), "up", "-d", *_CORE_SERVICES],
        cwd=str(PROJECT_ROOT),
        timeout=90,
        check=False,
    )


async def _send_alert(text: str) -> None:
    settings = get_settings()
    chat_id = settings.telegram_env.trading_group_id
    if not chat_id:
        logger.warning("health_check_alert_skipped_no_telegram_chat_configured")
        return
    try:
        await RealTelegramNotifier(settings).send_message(chat_id, text)
    except Exception:
        logger.exception("health_check_telegram_alert_failed")


async def main() -> int:
    # Per the user's explicit request: when the bot is turned off via
    # the master switch (`scripts/bot_off.ps1`, which removes this
    # flag), this watchdog must take -- and log, and notify about --
    # absolutely nothing. Checked before even `configure_logging`, so a
    # disabled run leaves no trace at all, not even a log line, and
    # critically never fights the user's own "off" choice by relaunching
    # anything.
    if not _ENABLED_FLAG.is_file():
        return 0
    configure_logging(get_settings())
    problems = _check_once() + await _check_scan_freshness()
    if not problems:
        logger.info("health_check_ok")
        return 0

    logger.warning("health_check_found_problems", problems=problems)
    _run_docker_recovery()
    _run_start_all()
    await asyncio.sleep(_RECOVERY_WAIT_SECONDS)
    remaining = _check_once() + await _check_scan_freshness()

    if not remaining:
        logger.info("health_check_recovered", original_problems=problems)
        await _send_alert(
            "⚠️ Проверка системы: обнаружена проблема, восстановлено автоматически.\n"
            + "\n".join(f"• {p}" for p in problems)
        )
        return 0

    logger.error("health_check_recovery_failed", remaining_problems=remaining)
    await _send_alert(
        "🔴 Проверка системы: автоматическое восстановление НЕ помогло.\n"
        + "\n".join(f"• {p}" for p in remaining)
        + "\n\nНужна ручная проверка."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
