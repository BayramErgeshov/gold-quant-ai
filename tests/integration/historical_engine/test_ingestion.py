"""Integration tests for `HistoricalIngestionService`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.data_collection.exceptions import AllProvidersFailedError
from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider
from src.engines.historical_engine.ingestion import HistoricalIngestionService
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.symbol_repository import SymbolRepository


@pytest.fixture(autouse=True)
def _no_real_redis() -> None:
    # This suite tests ingestion logic on top of a working FallbackChain,
    # not the Redis-backed cache itself (already covered in
    # tests/unit/core/data_collection/test_cache.py and test_fallback.py).
    with (
        patch("src.core.data_collection.fallback.set_cached", AsyncMock()),
        patch("src.core.data_collection.fallback.get_cached", AsyncMock(return_value=None)),
    ):
        yield


_SAMPLE_CANDLES = [
    {
        "datetime": "2026-01-03",
        "open": "3410.0",
        "high": "3420.0",
        "low": "3400.0",
        "close": "3415.0",
        "volume": "1000",
    },
    {
        "datetime": "2026-01-02",
        "open": "3400.0",
        "high": "3410.0",
        "low": "3390.0",
        "close": "3408.0",
        "volume": "900",
    },
    {
        "datetime": "2026-01-01",
        "open": "3390.0",
        "high": "3400.0",
        "low": "3380.0",
        "close": "3398.0",
        "volume": "800",
    },
]


class _FakeMarketProvider(DataProvider[list[dict[str, str]]]):
    name = "fake_market_provider"
    category = SourceCategory.MARKET_DATA
    tier = ProviderTier.TIER_2
    reliability = 0.9

    def __init__(self, *, configured: bool = True, error: Exception | None = None) -> None:
        self._configured = configured
        self._error = error

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def fetch(self, **kwargs: object) -> list[dict[str, str]]:
        if self._error is not None:
            raise self._error
        return _SAMPLE_CANDLES


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


async def test_ingest_stores_validated_candles(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    chain: FallbackChain[list[dict[str, str]]] = FallbackChain(
        [_FakeMarketProvider()], category=SourceCategory.MARKET_DATA
    )
    service = HistoricalIngestionService(
        candle_repository=CandleRepository(session), fallback_chain=chain
    )

    result = await service.ingest(symbol.id, provider_symbol="XAU/USD", timeframe="D1")

    assert result.requested == 3
    assert result.valid == 3
    assert result.inserted == 3
    assert result.issues == []

    stored = await CandleRepository(session).list_range(symbol.id, "D1")
    assert len(stored) == 3
    assert stored[0].close == 3398.0


async def test_ingest_is_idempotent_on_repeated_calls(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    chain: FallbackChain[list[dict[str, str]]] = FallbackChain(
        [_FakeMarketProvider()], category=SourceCategory.MARKET_DATA
    )
    service = HistoricalIngestionService(
        candle_repository=CandleRepository(session), fallback_chain=chain
    )

    await service.ingest(symbol.id, provider_symbol="XAU/USD", timeframe="D1")
    second_result = await service.ingest(symbol.id, provider_symbol="XAU/USD", timeframe="D1")

    assert second_result.inserted == 0
    stored = await CandleRepository(session).list_range(symbol.id, "D1")
    assert len(stored) == 3


async def test_ingest_raises_for_unsupported_timeframe(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    service = HistoricalIngestionService(candle_repository=CandleRepository(session))

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        await service.ingest(symbol.id, provider_symbol="XAU/USD", timeframe="BOGUS")


async def test_ingest_propagates_failure_when_no_provider_configured(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    chain: FallbackChain[list[dict[str, str]]] = FallbackChain(
        [_FakeMarketProvider(configured=False)], category=SourceCategory.MARKET_DATA
    )
    service = HistoricalIngestionService(
        candle_repository=CandleRepository(session), fallback_chain=chain
    )

    with pytest.raises(AllProvidersFailedError):
        await service.ingest(symbol.id, provider_symbol="XAU/USD", timeframe="D1")


async def test_ingest_excludes_invalid_candles(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    bad_candles = [
        {
            "datetime": "2026-01-01",
            "open": "3400.0",
            "high": "3390.0",
            "low": "3395.0",
            "close": "3398.0",
            "volume": "800",
        },
    ]

    class _BadProvider(_FakeMarketProvider):
        async def fetch(self, **kwargs: object) -> list[dict[str, str]]:
            return bad_candles

    chain: FallbackChain[list[dict[str, str]]] = FallbackChain(
        [_BadProvider()], category=SourceCategory.MARKET_DATA
    )
    service = HistoricalIngestionService(
        candle_repository=CandleRepository(session), fallback_chain=chain
    )

    result = await service.ingest(symbol.id, provider_symbol="XAU/USD", timeframe="D1")

    assert result.requested == 1
    assert result.valid == 0
    assert result.inserted == 0
    assert any(issue.kind == "invalid_ohlc" for issue in result.issues)
