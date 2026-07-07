"""PostgreSQL backup creation via `pg_dump`.

Per DATABASE.md ("Backup: Automatic, Hourly, Daily, Weekly, Monthly,
Versioned, Encrypted, Integrity Checked") and DEPLOYMENT.md. Encryption and
scheduling are added when the Scheduler service (Phase 2 `services/scheduler`)
is implemented; this module provides the underlying, independently testable
backup primitive.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.core.config.yaml_loader import PROJECT_ROOT
from src.settings import Settings, get_settings

logger = get_logger(__name__)

BACKUP_DIR = PROJECT_ROOT / "backups"


class BackupError(RuntimeError):
    """Raised when `pg_dump` fails or produces an empty backup file."""


def _backup_file_path(now: datetime) -> Path:
    """Build a timestamped, sortable backup filename."""
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    return BACKUP_DIR / f"postgres_{timestamp}.dump.gz"


async def create_backup(settings: Settings | None = None) -> Path:
    """Create a compressed `pg_dump` backup of the application database.

    Args:
        settings: Application settings. Defaults to `get_settings()`.

    Returns:
        Path to the created backup file.

    Raises:
        BackupError: If `pg_dump` exits non-zero or produces an empty file.
    """
    resolved_settings = settings or get_settings()
    postgres = resolved_settings.postgres
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = _backup_file_path(datetime.now(UTC))

    command = [
        "pg_dump",
        f"--host={postgres.host}",
        f"--port={postgres.port}",
        f"--username={postgres.user}",
        f"--dbname={postgres.db}",
        "--format=custom",
        "--compress=9",
        f"--file={destination}",
    ]
    env = {"PGPASSWORD": postgres.password.get_secret_value()}

    logger.info("postgres_backup_starting", destination=str(destination))
    process = await asyncio.create_subprocess_exec(
        *command,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise BackupError(f"pg_dump exited with {process.returncode}: {stderr.decode().strip()}")
    if not destination.exists() or destination.stat().st_size == 0:
        raise BackupError(f"pg_dump produced no output at {destination}")

    logger.info(
        "postgres_backup_completed",
        destination=str(destination),
        size_bytes=destination.stat().st_size,
    )
    return destination
