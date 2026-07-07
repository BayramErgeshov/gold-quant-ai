"""Domain repository for durable `SystemLog` entries."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.system_log import SystemLog


class SystemLogRepository(BaseRepository[SystemLog]):
    """Repository for durable system log entries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SystemLog)

    async def record(
        self, *, level: str, source: str, event: str, context: dict[str, Any] | None = None
    ) -> SystemLog:
        """Persist a new system log entry.

        Args:
            level: Severity level (DEBUG/INFO/WARNING/ERROR/CRITICAL).
            source: Originating module or component name.
            event: Short machine-readable event name.
            context: Additional structured context for the event.

        Returns:
            The persisted `SystemLog` entity.
        """
        entry = SystemLog(level=level, source=source, event=event, context=context or {})
        return await self.add(entry)

    async def list_by_source(self, source: str, *, limit: int = 100) -> list[SystemLog]:
        """Fetch the most recent log entries for a given source.

        Args:
            source: Originating module or component name to filter by.
            limit: Maximum number of rows to return.

        Returns:
            Matching `SystemLog` rows, most recent first.
        """
        statement = (
            select(SystemLog)
            .where(SystemLog.source == source)
            .order_by(SystemLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
