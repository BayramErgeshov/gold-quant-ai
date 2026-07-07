"""Domain repository for `Candle` entities."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.candle import Candle


def _ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    SQLite (used in integration tests) does not preserve timezone info on
    read and always returns naive datetimes; PostgreSQL (production)
    returns proper timezone-aware values. Every timestamp in this system
    is UTC by convention (DATA_COLLECTION_ENGINE.md: "Convert all
    timestamps to UTC"), so a naive value is assumed UTC rather than the
    host's local time.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class CandleRepository(BaseRepository[Candle]):
    """Repository for OHLCV candles."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Candle)

    async def insert_new(self, candles: list[Candle]) -> int:
        """Insert candles, skipping any that already exist for the same
        symbol/timeframe/timestamp (DATA_COLLECTION_ENGINE.md: "Never store
        duplicates").

        Deliberately dialect-agnostic (a plain SELECT-then-filter, rather
        than `INSERT ... ON CONFLICT`) so it behaves identically against
        the SQLite engine used in tests and PostgreSQL in production.

        Args:
            candles: Candles to insert; may include ones already stored.

        Returns:
            The number of candles actually inserted (duplicates excluded).
        """
        if not candles:
            return 0

        symbol_id = candles[0].symbol_id
        timeframe = candles[0].timeframe
        existing_timestamps = await self._existing_timestamps(
            symbol_id, timeframe, [candle.timestamp for candle in candles]
        )

        new_candles = [
            candle
            for candle in candles
            if _ensure_utc(candle.timestamp) not in existing_timestamps
        ]
        self.session.add_all(new_candles)
        await self.session.flush()
        return len(new_candles)

    async def _existing_timestamps(
        self, symbol_id: uuid.UUID, timeframe: str, timestamps: list[datetime]
    ) -> set[datetime]:
        statement = select(Candle.timestamp).where(
            Candle.symbol_id == symbol_id,
            Candle.timeframe == timeframe,
            Candle.timestamp.in_(timestamps),
        )
        result = await self.session.execute(statement)
        return {_ensure_utc(timestamp) for timestamp in result.scalars().all()}

    async def list_range(
        self,
        symbol_id: uuid.UUID,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        """Fetch candles for a symbol/timeframe within an optional time range.

        Args:
            symbol_id: Owning symbol id.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            start: Inclusive lower bound on `timestamp`, if given.
            end: Inclusive upper bound on `timestamp`, if given.
            limit: Maximum number of candles to return.

        Returns:
            Matching `Candle` rows ordered by timestamp ascending.
        """
        statement = (
            select(Candle)
            .where(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp)
            .limit(limit)
        )
        if start is not None:
            statement = statement.where(Candle.timestamp >= start)
        if end is not None:
            statement = statement.where(Candle.timestamp <= end)

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def latest_timestamp(self, symbol_id: uuid.UUID, timeframe: str) -> datetime | None:
        """Fetch the most recent candle timestamp for a symbol/timeframe.

        Used to resume historical downloads incrementally
        (DATA_COLLECTION_ENGINE.md: "Only Update Changed Data").

        Args:
            symbol_id: Owning symbol id.
            timeframe: One of `src.models.candle.TIMEFRAMES`.

        Returns:
            The latest stored timestamp, or None if no candles exist yet.
        """
        statement = (
            select(Candle.timestamp)
            .where(Candle.symbol_id == symbol_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        value = result.scalar_one_or_none()
        return _ensure_utc(value) if value is not None else None
