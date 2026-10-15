"""Integration tests for `HistoricalSimilarityService`."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.models.candle import Candle
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.symbol_repository import SymbolRepository

_BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)


def _sine_wave_candles(count: int, *, period: int = 20, amplitude: float = 30.0) -> list[float]:
    return [3000.0 + amplitude * math.sin(2 * math.pi * i / period) for i in range(count)]


async def _seed_candles(session: AsyncSession, symbol_id: object, closes: list[float]) -> None:
    candles = [
        Candle(
            symbol_id=symbol_id,
            timeframe="H1",
            timestamp=_BASE_TIME + timedelta(hours=index),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            source="test_fixture",
        )
        for index, close in enumerate(closes)
    ]
    await CandleRepository(session).insert_new(candles)


async def test_search_returns_empty_result_with_insufficient_history(
    session: AsyncSession,
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _seed_candles(session, symbol.id, _sine_wave_candles(5))
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    result = await service.search(symbol.id, "H1", window_size=20)

    assert result.matches == []
    assert result.outcome_statistics.sample_size == 0


async def test_search_finds_repeating_pattern_and_computes_outcomes(
    session: AsyncSession,
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    # A periodic sine wave guarantees earlier windows with a near-identical
    # shape to the most recent one, each followed by enough bars to
    # measure a forward outcome.
    await _seed_candles(session, symbol.id, _sine_wave_candles(200, period=20))
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    result = await service.search(symbol.id, "H1", window_size=20, forward_bars=5, top_n=10)

    assert len(result.matches) > 0
    assert result.matches[0].similarity_score > 0
    assert result.outcome_statistics.sample_size > 0

    # Matches were persisted for future retrieval.
    stored = await HistoricalSimilarityRepository(session).list_all(limit=1000)
    assert len(stored) == result.outcome_statistics.sample_size
    assert all(row.symbol_id == symbol.id and row.timeframe == "H1" for row in stored)


async def test_search_respects_top_n(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _seed_candles(session, symbol.id, _sine_wave_candles(200, period=20))
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    result = await service.search(symbol.id, "H1", window_size=20, forward_bars=5, top_n=3)

    assert len(result.matches) <= 3


async def test_search_skips_matches_without_enough_forward_data(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _seed_candles(session, symbol.id, _sine_wave_candles(200, period=20))
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    # top_n covers almost every candidate window, including ones near the
    # tail of history that don't have `forward_bars` of data after them.
    result = await service.search(symbol.id, "H1", window_size=20, forward_bars=100, top_n=200)

    assert len(result.matches) > result.outcome_statistics.sample_size


async def test_search_enriches_matches_with_outcome_and_adverse_excursion(
    session: AsyncSession,
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _seed_candles(session, symbol.id, _sine_wave_candles(200, period=20))
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    result = await service.search(symbol.id, "H1", window_size=20, forward_bars=5, top_n=10)

    measured = [m for m in result.matches if m.outcome_return_pct is not None]
    assert measured
    for match in measured:
        assert match.adverse_if_long_pct is not None
        assert match.adverse_if_long_pct >= 0.0
        assert match.adverse_if_short_pct is not None
        assert match.adverse_if_short_pct >= 0.0


async def test_search_leaves_outcome_none_for_matches_without_enough_forward_data(
    session: AsyncSession,
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _seed_candles(session, symbol.id, _sine_wave_candles(200, period=20))
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    result = await service.search(symbol.id, "H1", window_size=20, forward_bars=100, top_n=200)

    unmeasured = [m for m in result.matches if m.outcome_return_pct is None]
    assert unmeasured
    for match in unmeasured:
        assert match.adverse_if_long_pct is None
        assert match.adverse_if_short_pct is None


async def test_search_skips_matches_with_zero_entry_price(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    # A degenerate all-zero series: every window is equally (perfectly)
    # similar to the query, but every entry price is 0.0, so no outcome
    # return can be computed — this must not raise a ZeroDivisionError.
    await _seed_candles(session, symbol.id, [0.0] * 60)
    service = HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )

    result = await service.search(symbol.id, "H1", window_size=20, forward_bars=5, top_n=50)

    assert len(result.matches) > 0
    assert result.outcome_statistics.sample_size == 0
