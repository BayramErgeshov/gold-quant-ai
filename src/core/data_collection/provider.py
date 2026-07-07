"""Abstract base class every data provider adapter implements.

Per DATA_COLLECTION_ENGINE.md: "No AI agent should directly connect to
external APIs. All information must pass through this engine." Every
concrete provider (FRED, NewsAPI, TwelveData, ...) subclasses `DataProvider`
and is only ever invoked through a `FallbackChain` (see `fallback.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.data_collection.models import ProviderTier, SourceCategory


class DataProvider[T](ABC):
    """Base class for a single external data source adapter.

    Attributes:
        name: Human-readable provider name, e.g. "fred".
        category: Data category this provider belongs to.
        tier: Authoritativeness tier used for fallback ordering.
        reliability: Historical reliability score in [0.0, 1.0], used as
            the "reliability" input to `compute_quality_score`. Starts at a
            conservative default and is refined by
            `src/services/statistics` source ranking in a later phase.
    """

    name: str
    category: SourceCategory
    tier: ProviderTier
    reliability: float = 0.8

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything required to make requests.

        Returns:
            False if a required API key/credential is missing — the
            fallback chain skips unconfigured providers rather than
            failing loudly, per FAILSAFE_PROTOCOL.md graceful degradation.
        """

    @abstractmethod
    async def fetch(self, **kwargs: object) -> T:
        """Fetch data from the external source.

        Args:
            **kwargs: Provider-specific query parameters.

        Returns:
            The provider's parsed result.

        Raises:
            src.core.data_collection.exceptions.ProviderError: On any
                failure (network, malformed response, rate limit, ...).
        """
