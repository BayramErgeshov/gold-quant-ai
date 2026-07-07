"""FRED macro data ingestion service.

Fetches a single named economic series from FRED (Phase 3's
`FredEconomicProvider`, via the standard `FallbackChain`) and converts it
into `MacroObservation`s for the Macro Department agents to analyze.
Activates automatically once `FRED_API_KEY` is set in `.env`; adding a
higher-tier or additional provider later is a matter of extending the
`FallbackChain`'s provider list, per DATA_COLLECTION_ENGINE.md.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.core.data_collection.cache import build_cache_key
from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import SourceCategory
from src.core.macro_analysis.agent import MacroObservation
from src.services.macro.providers.fred_provider import FredEconomicProvider
from src.settings import Settings, get_settings

_DATA_CATEGORY = SourceCategory.ECONOMIC_DATA
_MISSING_VALUE_MARKER = "."


def _parse_observation(raw: dict[str, Any]) -> MacroObservation | None:
    """Parse a single FRED observation record.

    Args:
        raw: A single observation dict as returned by `FredEconomicProvider`.

    Returns:
        The parsed `MacroObservation`, or None if the value is FRED's
        missing-value marker (".") — never fabricated as 0.0 or similar.
    """
    raw_value = raw.get("value", _MISSING_VALUE_MARKER)
    if raw_value == _MISSING_VALUE_MARKER:
        return None
    return MacroObservation(observed_on=date.fromisoformat(raw["date"]), value=float(raw_value))


class MacroSeriesIngestionService:
    """Fetches and parses a single FRED economic series."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        fallback_chain: FallbackChain[list[dict[str, Any]]] | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            settings: Application settings. Defaults to `get_settings()`.
            fallback_chain: Provider chain to fetch series from. Defaults
                to a chain containing only `FredEconomicProvider`;
                injectable for testing and for adding higher-tier
                providers later.
        """
        resolved_settings = settings or get_settings()
        self._fallback_chain = fallback_chain or FallbackChain(
            [FredEconomicProvider(resolved_settings)], category=_DATA_CATEGORY
        )

    async def fetch_series(self, series_id: str) -> list[MacroObservation]:
        """Fetch and parse a FRED economic series.

        Args:
            series_id: FRED series identifier, e.g. "CPIAUCSL".

        Returns:
            Observations ordered by date ascending, with missing values
            excluded rather than fabricated.
        """
        cache_key = build_cache_key(_DATA_CATEGORY.value, f"fred:{series_id}")
        dataset = await self._fallback_chain.fetch(cache_key, series_id=series_id)

        observations = [
            observation
            for raw in dataset.data
            if (observation := _parse_observation(raw)) is not None
        ]
        observations.sort(key=lambda observation: observation.observed_on)
        return observations
