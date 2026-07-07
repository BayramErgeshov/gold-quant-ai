"""Unit tests for `MacroSeriesIngestionService`."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider
from src.engines.macro_engine.ingestion import MacroSeriesIngestionService

pytestmark = pytest.mark.unit


class _FakeFredProvider(DataProvider[list[dict[str, str]]]):
    name = "fake_fred"
    category = SourceCategory.ECONOMIC_DATA
    tier = ProviderTier.TIER_1
    reliability = 0.98

    def __init__(self, observations: list[dict[str, str]]) -> None:
        self._observations = observations

    @property
    def is_configured(self) -> bool:
        return True

    async def fetch(self, **kwargs: object) -> list[dict[str, str]]:
        return self._observations


@pytest.fixture(autouse=True)
def _no_real_redis() -> None:
    with (
        patch("src.core.data_collection.fallback.set_cached", AsyncMock()),
        patch("src.core.data_collection.fallback.get_cached", AsyncMock(return_value=None)),
    ):
        yield


async def test_fetch_series_parses_and_sorts_observations() -> None:
    raw = [
        {"date": "2026-02-01", "value": "3.1"},
        {"date": "2026-01-01", "value": "3.0"},
    ]
    chain: FallbackChain[list[dict[str, str]]] = FallbackChain(
        [_FakeFredProvider(raw)], category=SourceCategory.ECONOMIC_DATA
    )
    service = MacroSeriesIngestionService(fallback_chain=chain)

    observations = await service.fetch_series("CPIAUCSL")

    assert [observation.observed_on for observation in observations] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert observations[0].value == 3.0


async def test_fetch_series_excludes_missing_values() -> None:
    raw = [
        {"date": "2026-01-01", "value": "3.0"},
        {"date": "2026-02-01", "value": "."},
    ]
    chain: FallbackChain[list[dict[str, str]]] = FallbackChain(
        [_FakeFredProvider(raw)], category=SourceCategory.ECONOMIC_DATA
    )
    service = MacroSeriesIngestionService(fallback_chain=chain)

    observations = await service.fetch_series("CPIAUCSL")

    assert len(observations) == 1
    assert observations[0].observed_on == date(2026, 1, 1)
