"""Fallback chain orchestration for the Data Collection Engine.

Implements the exact fallback order from DATA_COLLECTION_ENGINE.md:

    Tier 1 -> Tier 2 -> Tier 3 -> Cached Data -> Historical Model

("Historical Model" is provided by the Historical Research Engine, a later
roadmap phase; this chain covers live providers plus cache.)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from src.common.logging import get_logger
from src.core.data_collection.cache import get_cached, set_cached
from src.core.data_collection.exceptions import AllProvidersFailedError, ProviderError
from src.core.data_collection.models import (
    CollectedDataset,
    CollectionMetadata,
    ProviderTier,
    SourceCategory,
)
from src.core.data_collection.provider import DataProvider
from src.core.data_collection.validation import compute_quality_score

logger = get_logger(__name__)

_CACHED_RESULT_RELIABILITY_PENALTY = 0.3


class FallbackChain[T]:
    """Tries each configured provider in tier order, then falls back to cache."""

    def __init__(self, providers: Sequence[DataProvider[T]], *, category: SourceCategory) -> None:
        """Initialize the chain.

        Args:
            providers: Candidate providers, tried in ascending tier order.
            category: Data category this chain serves (for metadata/logging).
        """
        self._providers = sorted(providers, key=lambda provider: provider.tier.value)
        self._category = category

    async def fetch(self, cache_key: str, **kwargs: object) -> CollectedDataset[T]:
        """Fetch data, trying every provider before falling back to cache.

        Args:
            cache_key: Stable cache key identifying this specific query
                (see `src.core.data_collection.cache.build_cache_key`).
            **kwargs: Forwarded to each provider's `fetch`.

        Returns:
            The first successful result, wrapped with provenance/quality
            metadata.

        Raises:
            AllProvidersFailedError: If every provider failed or was
                unconfigured, and no cached value exists either.
        """
        for provider in self._providers:
            if not provider.is_configured:
                logger.warning(
                    "provider_not_configured", provider=provider.name, category=self._category
                )
                continue
            try:
                data = await provider.fetch(**kwargs)
            except ProviderError as exc:
                logger.warning(
                    "provider_fetch_failed",
                    provider=provider.name,
                    category=self._category,
                    error=str(exc),
                )
                continue

            await set_cached(cache_key, data)
            return self._build_result(provider, data, is_cached=False)

        return await self._fetch_from_cache(cache_key)

    async def _fetch_from_cache(self, cache_key: str) -> CollectedDataset[T]:
        cached = await get_cached(cache_key)
        if cached is None:
            raise AllProvidersFailedError(
                f"No provider available and no cached value for key={cache_key!r} "
                f"(category={self._category})"
            )
        logger.warning("serving_stale_cached_data", category=self._category, cache_key=cache_key)
        quality = compute_quality_score(
            freshness=0.0,
            completeness=1.0,
            reliability=max(0.0, 0.5 - _CACHED_RESULT_RELIABILITY_PENALTY),
            consistency=0.5,
            accuracy=0.5,
        )
        fallback_tier = self._providers[-1].tier if self._providers else ProviderTier.TIER_3
        metadata = CollectionMetadata(
            source="cache",
            category=self._category,
            tier=fallback_tier,
            collected_at=datetime.now(UTC),
            quality=quality,
            is_cached=True,
        )
        return CollectedDataset(data=cached, metadata=metadata)

    def _build_result(
        self, provider: DataProvider[T], data: T, *, is_cached: bool
    ) -> CollectedDataset[T]:
        quality = compute_quality_score(
            freshness=1.0,
            completeness=1.0,
            reliability=provider.reliability,
            consistency=1.0,
            accuracy=provider.reliability,
        )
        metadata = CollectionMetadata(
            source=provider.name,
            category=self._category,
            tier=provider.tier,
            collected_at=datetime.now(UTC),
            quality=quality,
            is_cached=is_cached,
        )
        return CollectedDataset(data=data, metadata=metadata)
