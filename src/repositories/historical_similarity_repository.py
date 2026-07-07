"""Domain repository for `HistoricalSimilarity` entities."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.historical_similarity import HistoricalSimilarity


class HistoricalSimilarityRepository(BaseRepository[HistoricalSimilarity]):
    """Repository for cached historical analogue search results."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HistoricalSimilarity)

    async def list_for_query(
        self, symbol_id: uuid.UUID, timeframe: str, query_timestamp: datetime
    ) -> list[HistoricalSimilarity]:
        """Fetch cached similarity matches for a specific reference point.

        Args:
            symbol_id: Owning symbol id.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            query_timestamp: The reference point previously analyzed.

        Returns:
            Matching `HistoricalSimilarity` rows, most similar first.
        """
        statement = (
            select(HistoricalSimilarity)
            .where(
                HistoricalSimilarity.symbol_id == symbol_id,
                HistoricalSimilarity.timeframe == timeframe,
                HistoricalSimilarity.query_timestamp == query_timestamp,
            )
            .order_by(HistoricalSimilarity.similarity_score.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
