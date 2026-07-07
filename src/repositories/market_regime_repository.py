"""Domain repository for `MarketRegime` entities."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.market_regime import MarketRegime


class MarketRegimeRepository(BaseRepository[MarketRegime]):
    """Repository for classified market regime periods."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MarketRegime)

    async def current_regime(
        self, symbol_id: uuid.UUID, timeframe: str, as_of: datetime
    ) -> MarketRegime | None:
        """Fetch the regime period covering a given point in time.

        Args:
            symbol_id: Owning symbol id.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            as_of: The timestamp to find the covering regime period for.

        Returns:
            The `MarketRegime` whose `[start_timestamp, end_timestamp]`
            range contains `as_of`, or None if none is classified yet.
        """
        statement = (
            select(MarketRegime)
            .where(
                MarketRegime.symbol_id == symbol_id,
                MarketRegime.timeframe == timeframe,
                MarketRegime.start_timestamp <= as_of,
                MarketRegime.end_timestamp >= as_of,
            )
            .order_by(MarketRegime.start_timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_symbol(self, symbol_id: uuid.UUID, timeframe: str) -> list[MarketRegime]:
        """Fetch every classified regime period for a symbol/timeframe, in order.

        Args:
            symbol_id: Owning symbol id.
            timeframe: One of `src.models.candle.TIMEFRAMES`.

        Returns:
            Matching `MarketRegime` rows ordered by `start_timestamp`.
        """
        statement = (
            select(MarketRegime)
            .where(MarketRegime.symbol_id == symbol_id, MarketRegime.timeframe == timeframe)
            .order_by(MarketRegime.start_timestamp)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
