"""Unit tests for `src.database.postgres.integrity`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.postgres.integrity import (
    check_migration_integrity,
    get_latest_local_revision,
)

pytestmark = pytest.mark.unit


def test_get_latest_local_revision_finds_a_migration_head() -> None:
    # Not hardcoded to a specific revision id: new migrations are added
    # over time, so this only asserts a head resolves at all and looks
    # like one of this project's revision ids (YYYYMMDDNNNN).
    revision = get_latest_local_revision()

    assert revision is not None
    assert revision.isdigit()
    assert len(revision) == 12


async def test_check_migration_integrity_healthy_when_revisions_match() -> None:
    current_head = get_latest_local_revision()
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = current_head
    session.execute.return_value = execute_result

    result = await check_migration_integrity(session)

    assert result.healthy is True
    assert result.database_revision == current_head
    assert result.expected_revision == current_head


async def test_check_migration_integrity_unhealthy_when_revisions_differ() -> None:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "some_old_revision"
    session.execute.return_value = execute_result

    result = await check_migration_integrity(session)

    assert result.healthy is False
    assert "out of date" in result.detail


async def test_check_migration_integrity_reports_database_errors() -> None:
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("relation does not exist")

    result = await check_migration_integrity(session)

    assert result.healthy is False
    assert result.database_revision is None
    assert "RuntimeError" in result.detail
