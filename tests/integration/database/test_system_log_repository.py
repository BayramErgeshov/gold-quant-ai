"""Integration tests for `SystemLogRepository` against a real SQL engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.system_log import SystemLog
from src.repositories.system_log_repository import SystemLogRepository


async def test_record_persists_entry_with_context(session: AsyncSession) -> None:
    repo = SystemLogRepository(session)

    entry = await repo.record(
        level="ERROR",
        source="bootstrap",
        event="startup_check",
        context={"check": "postgres", "healthy": False},
    )

    assert entry.id is not None
    assert entry.context == {"check": "postgres", "healthy": False}


async def test_record_defaults_context_to_empty_dict(session: AsyncSession) -> None:
    repo = SystemLogRepository(session)

    entry = await repo.record(level="INFO", source="bootstrap", event="startup_complete")

    assert entry.context == {}


async def test_list_by_source_orders_most_recent_first(session: AsyncSession) -> None:
    # Explicit timestamps avoid flakiness from SQLite's one-second
    # CURRENT_TIMESTAMP resolution (PostgreSQL's `now()` is microsecond
    # precise, but the test must not depend on real wall-clock timing).
    repo = SystemLogRepository(session)
    base_time = datetime.now(UTC)
    await repo.add(SystemLog(level="INFO", source="bootstrap", event="first", created_at=base_time))
    await repo.add(
        SystemLog(
            level="INFO",
            source="bootstrap",
            event="second",
            created_at=base_time + timedelta(seconds=1),
        )
    )
    await repo.add(
        SystemLog(level="INFO", source="other_module", event="unrelated", created_at=base_time)
    )

    entries = await repo.list_by_source("bootstrap")

    assert [entry.event for entry in entries] == ["second", "first"]
