"""Unit tests for `src.core.data_collection.fallback`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.data_collection.exceptions import AllProvidersFailedError, ProviderError
from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider

pytestmark = pytest.mark.unit


class _FakeProvider(DataProvider[dict[str, str]]):
    def __init__(
        self,
        name: str,
        tier: ProviderTier,
        *,
        configured: bool = True,
        result: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.tier = tier
        self.category = SourceCategory.ECONOMIC_DATA
        self.reliability = 0.9
        self._configured = configured
        self._result = result
        self._error = error

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def fetch(self, **kwargs: object) -> dict[str, str]:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


async def test_fetch_returns_first_successful_provider() -> None:
    tier1 = _FakeProvider("tier1", ProviderTier.TIER_1, result={"value": "from_tier1"})
    tier2 = _FakeProvider("tier2", ProviderTier.TIER_2, result={"value": "from_tier2"})
    chain: FallbackChain[dict[str, str]] = FallbackChain(
        [tier2, tier1], category=SourceCategory.ECONOMIC_DATA
    )

    with patch("src.core.data_collection.fallback.set_cached", AsyncMock()):
        result = await chain.fetch(cache_key="test_key")

    assert result.data == {"value": "from_tier1"}
    assert result.metadata.source == "tier1"
    assert result.metadata.is_cached is False


async def test_fetch_skips_unconfigured_providers() -> None:
    unconfigured = _FakeProvider("tier1", ProviderTier.TIER_1, configured=False)
    configured = _FakeProvider("tier2", ProviderTier.TIER_2, result={"value": "ok"})
    chain: FallbackChain[dict[str, str]] = FallbackChain(
        [unconfigured, configured], category=SourceCategory.ECONOMIC_DATA
    )

    with patch("src.core.data_collection.fallback.set_cached", AsyncMock()):
        result = await chain.fetch(cache_key="test_key")

    assert result.metadata.source == "tier2"


async def test_fetch_falls_back_to_next_provider_on_error() -> None:
    failing = _FakeProvider("tier1", ProviderTier.TIER_1, error=ProviderError("boom"))
    working = _FakeProvider("tier2", ProviderTier.TIER_2, result={"value": "ok"})
    chain: FallbackChain[dict[str, str]] = FallbackChain(
        [failing, working], category=SourceCategory.ECONOMIC_DATA
    )

    with patch("src.core.data_collection.fallback.set_cached", AsyncMock()):
        result = await chain.fetch(cache_key="test_key")

    assert result.metadata.source == "tier2"


async def test_fetch_falls_back_to_cache_when_all_providers_fail() -> None:
    failing = _FakeProvider("tier1", ProviderTier.TIER_1, error=ProviderError("boom"))
    chain: FallbackChain[dict[str, str]] = FallbackChain(
        [failing], category=SourceCategory.ECONOMIC_DATA
    )

    with patch(
        "src.core.data_collection.fallback.get_cached",
        AsyncMock(return_value={"value": "cached"}),
    ):
        result = await chain.fetch(cache_key="test_key")

    assert result.data == {"value": "cached"}
    assert result.metadata.source == "cache"
    assert result.metadata.is_cached is True


async def test_fetch_raises_when_all_providers_fail_and_no_cache() -> None:
    failing = _FakeProvider("tier1", ProviderTier.TIER_1, error=ProviderError("boom"))
    chain: FallbackChain[dict[str, str]] = FallbackChain(
        [failing], category=SourceCategory.ECONOMIC_DATA
    )

    with (
        patch("src.core.data_collection.fallback.get_cached", AsyncMock(return_value=None)),
        pytest.raises(AllProvidersFailedError),
    ):
        await chain.fetch(cache_key="test_key")


async def test_fetch_raises_with_empty_provider_list_and_no_cache() -> None:
    chain: FallbackChain[dict[str, str]] = FallbackChain([], category=SourceCategory.NEWS)

    with (
        patch("src.core.data_collection.fallback.get_cached", AsyncMock(return_value=None)),
        pytest.raises(AllProvidersFailedError),
    ):
        await chain.fetch(cache_key="test_key")
