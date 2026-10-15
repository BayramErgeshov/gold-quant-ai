"""Domain repository for the single `RuntimeSettings` row."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.runtime_settings import DEFAULT_RUNTIME_SETTINGS_ID, RuntimeSettings


class RuntimeSettingsRepository(BaseRepository[RuntimeSettings]):
    """Repository for the platform's live-editable runtime settings."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RuntimeSettings)

    async def get_or_create_default(self) -> RuntimeSettings:
        """Fetch the singleton settings row, creating it with defaults if absent.

        Returns:
            The existing or newly-created `RuntimeSettings` row.
        """
        existing = await self.session.get(RuntimeSettings, DEFAULT_RUNTIME_SETTINGS_ID)
        if existing is not None:
            return existing
        return await self.add(RuntimeSettings(id=DEFAULT_RUNTIME_SETTINGS_ID))
