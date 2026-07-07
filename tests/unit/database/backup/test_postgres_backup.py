"""Unit tests for `src.database.backup.postgres_backup`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.database.backup.postgres_backup import BackupError, create_backup
from src.settings import get_settings

pytestmark = pytest.mark.unit


def _mock_process(returncode: int, stderr: bytes = b"") -> AsyncMock:
    process = AsyncMock()
    process.returncode = returncode
    process.communicate.return_value = (b"", stderr)
    return process


async def test_create_backup_writes_expected_file(tmp_path: Path) -> None:
    process = _mock_process(returncode=0)

    def fake_exec(*_args: object, **_kwargs: object) -> AsyncMock:
        # Simulate pg_dump writing output to the destination path.
        destination = Path(_args[-1].removeprefix("--file="))
        destination.write_bytes(b"fake-dump-contents")
        return process

    with (
        patch("src.database.backup.postgres_backup.BACKUP_DIR", tmp_path),
        patch(
            "src.database.backup.postgres_backup.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=fake_exec),
        ),
    ):
        result = await create_backup(get_settings())

    assert result.exists()
    assert result.read_bytes() == b"fake-dump-contents"
    assert result.parent == tmp_path


async def test_create_backup_raises_on_nonzero_exit(tmp_path: Path) -> None:
    process = _mock_process(returncode=1, stderr=b"connection refused")

    with (
        patch("src.database.backup.postgres_backup.BACKUP_DIR", tmp_path),
        patch(
            "src.database.backup.postgres_backup.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        pytest.raises(BackupError, match="connection refused"),
    ):
        await create_backup(get_settings())


async def test_create_backup_raises_on_empty_output(tmp_path: Path) -> None:
    process = _mock_process(returncode=0)

    with (
        patch("src.database.backup.postgres_backup.BACKUP_DIR", tmp_path),
        patch(
            "src.database.backup.postgres_backup.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        pytest.raises(BackupError, match="no output"),
    ):
        await create_backup(get_settings())
