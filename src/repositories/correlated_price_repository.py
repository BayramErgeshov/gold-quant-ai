"""Domain repository for `CorrelatedPrice` entities.

Mirrors `src.repositories.candle_repository.CandleRepository`'s dedup/
range/most-recent query patterns exactly, keyed by `instrument_id` instead
of `symbol_id` — kept as a separate repository rather than a generic base
because the two tables serve deliberately different trust boundaries (see
`src.models.correlated_instrument.CorrelatedInstrument`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.correlated_price import CorrelatedPrice


def _ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class CorrelatedPriceRepository(BaseRepository[CorrelatedPrice]):
    """Repository for correlated-instrument OHLCV prices."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CorrelatedPrice)

    async def insert_new(self, prices: list[CorrelatedPrice]) -> int:
        """Insert prices, skipping any already stored for the same
        instrument/timeframe/timestamp.

        Args:
            prices: Prices to insert; may include ones already stored.

        Returns:
            The number of prices actually inserted (duplicates excluded).
        """
        if not prices:
            return 0

        instrument_id = prices[0].instrument_id
        timeframe = prices[0].timeframe
        existing_timestamps = await self._existing_timestamps(
            instrument_id, timeframe, [price.timestamp for price in prices]
        )

        new_prices = [
            price for price in prices if _ensure_utc(price.timestamp) not in existing_timestamps
        ]
        self.session.add_all(new_prices)
        await self.session.flush()
        return len(new_prices)

    async def _existing_timestamps(
        self, instrument_id: uuid.UUID, timeframe: str, timestamps: list[datetime]
    ) -> set[datetime]:
        statement = select(CorrelatedPrice.timestamp).where(
            CorrelatedPrice.instrument_id == instrument_id,
            CorrelatedPrice.timeframe == timeframe,
            CorrelatedPrice.timestamp.in_(timestamps),
        )
        result = await self.session.execute(statement)
        return {_ensure_utc(timestamp) for timestamp in result.scalars().all()}

    async def list_most_recent(
        self, instrument_id: uuid.UUID, timeframe: str, *, count: int
    ) -> list[CorrelatedPrice]:
        """Fetch the most recent `count` prices for an instrument/timeframe.

        Args:
            instrument_id: Owning instrument id.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            count: Maximum number of most-recent prices to return.

        Returns:
            Matching rows ordered by timestamp ascending (oldest of the
            recent set first, most recent last).
        """
        statement = (
            select(CorrelatedPrice)
            .where(
                CorrelatedPrice.instrument_id == instrument_id,
                CorrelatedPrice.timeframe == timeframe,
            )
            .order_by(CorrelatedPrice.timestamp.desc())
            .limit(count)
        )
        result = await self.session.execute(statement)
        return list(reversed(result.scalars().all()))
