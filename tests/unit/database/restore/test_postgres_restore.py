"""Unit tests for `src.database.restore.postgres_restore`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.database.restore.postgres_restore import RestoreError, restore_backup
from src.settings import get_settings

pytestmark = pytest.mark.unit


async def test_restore_backup_raises_if_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.dump.gz"

    with pytest.raises(RestoreError, match="not found"):
        await restore_backup(missing, get_settings())


async def test_restore_backup_succeeds(tmp_path: Path) -> None:
    backup_file = tmp_path / "backup.dump.gz"
    backup_file.write_bytes(b"contents")
    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (b"", b"")

    with patch(
        "src.database.restore.postgres_restore.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        await restore_backup(backup_file, get_settings())


async def test_restore_backup_raises_on_nonzero_exit(tmp_path: Path) -> None:
    backup_file = tmp_path / "backup.dump.gz"
    backup_file.write_bytes(b"contents")
    process = AsyncMock()
    process.returncode = 1
    process.communicate.return_value = (b"", b"corrupt archive")

    with (
        patch(
            "src.database.restore.postgres_restore.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        pytest.raises(RestoreError, match="corrupt archive"),
    ):
        await restore_backup(backup_file, get_settings())
