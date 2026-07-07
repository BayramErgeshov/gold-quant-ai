"""PostgreSQL restore from a `pg_dump` custom-format backup, via `pg_restore`.

Per DATABASE.md ("Restore" is a first-class, tested capability, not an
afterthought) and DEPLOYMENT.md ("Automatic Restore Test").
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.common.logging import get_logger
from src.settings import Settings, get_settings

logger = get_logger(__name__)


class RestoreError(RuntimeError):
    """Raised when `pg_restore` fails or the backup file is missing."""


async def restore_backup(backup_path: Path, settings: Settings | None = None) -> None:
    """Restore the application database from a `pg_dump` custom-format backup.

    Args:
        backup_path: Path to a backup file created by `create_backup`.
        settings: Application settings. Defaults to `get_settings()`.

    Raises:
        RestoreError: If the backup file does not exist or `pg_restore` fails.
    """
    if not backup_path.exists():
        raise RestoreError(f"Backup file not found: {backup_path}")

    resolved_settings = settings or get_settings()
    postgres = resolved_settings.postgres

    command = [
        "pg_restore",
        f"--host={postgres.host}",
        f"--port={postgres.port}",
        f"--username={postgres.user}",
        f"--dbname={postgres.db}",
        "--clean",
        "--if-exists",
        "--no-owner",
        str(backup_path),
    ]
    env = {"PGPASSWORD": postgres.password.get_secret_value()}

    logger.info("postgres_restore_starting", source=str(backup_path))
    process = await asyncio.create_subprocess_exec(
        *command,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise RestoreError(
            f"pg_restore exited with {process.returncode}: {stderr.decode().strip()}"
        )

    logger.info("postgres_restore_completed", source=str(backup_path))
