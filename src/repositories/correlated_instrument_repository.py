"""Domain repository for `CorrelatedInstrument` entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.correlated_instrument import CorrelatedInstrument


class CorrelatedInstrumentRepository(BaseRepository[CorrelatedInstrument]):
    """Repository for cross-market reference instruments."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CorrelatedInstrument)

    async def get_by_name(self, name: str) -> CorrelatedInstrument | None:
        """Fetch a correlated instrument by its platform-facing name.

        Args:
            name: Instrument name, e.g. "DXY".

        Returns:
            The matching `CorrelatedInstrument`, or None if it does not exist.
        """
        statement = select(CorrelatedInstrument).where(CorrelatedInstrument.name == name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_enabled_with_mt5_symbol(self) -> list[CorrelatedInstrument]:
        """Fetch every enabled instrument that has a live MT5 data source.

        Returns:
            Enabled `CorrelatedInstrument` rows with a non-null `mt5_symbol`
            — excludes instruments still pending an external data provider.
        """
        statement = select(CorrelatedInstrument).where(
            CorrelatedInstrument.is_enabled.is_(True),
            CorrelatedInstrument.mt5_symbol.is_not(None),
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
