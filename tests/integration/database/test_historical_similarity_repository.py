"""Integration tests for `HistoricalSimilarityRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.historical_similarity import HistoricalSimilarity
from src.models.symbol import Symbol
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.symbol_repository import SymbolRepository

_QUERY_TS = datetime(2026, 1, 1, tzinfo=UTC)


async def test_list_for_query_orders_by_similarity_descending(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    repo = HistoricalSimilarityRepository(session)
    await repo.add(
        HistoricalSimilarity(
            symbol_id=symbol.id,
            timeframe="D1",
            query_timestamp=_QUERY_TS,
            matched_timestamp=_QUERY_TS - timedelta(days=1000),
            similarity_score=0.7,
        )
    )
    await repo.add(
        HistoricalSimilarity(
            symbol_id=symbol.id,
            timeframe="D1",
            query_timestamp=_QUERY_TS,
            matched_timestamp=_QUERY_TS - timedelta(days=2000),
            similarity_score=0.95,
        )
    )

    results = await repo.list_for_query(symbol.id, "D1", _QUERY_TS)

    assert [result.similarity_score for result in results] == [0.95, 0.7]


async def test_list_for_query_returns_empty_when_no_matches(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    repo = HistoricalSimilarityRepository(session)

    results = await repo.list_for_query(symbol.id, "D1", _QUERY_TS)

    assert results == []
