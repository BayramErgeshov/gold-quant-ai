"""FRED (Federal Reserve Economic Data) provider adapter.

Tier 1 economic data source per DATA_COLLECTION_ENGINE.md / NEWS_ENGINE.md.
Requires `FRED_API_KEY`; when absent, `is_configured` is False and the
fallback chain skips this provider rather than making an unauthenticated
request that would only fail.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.data_collection.exceptions import ProviderError
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider
from src.settings import Settings, get_settings

_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
_TIMEOUT_SECONDS = 10.0


class FredEconomicProvider(DataProvider[list[dict[str, Any]]]):
    """Fetches economic time series observations from FRED.

    Example series ids: "CPIAUCSL" (CPI), "DFF" (Fed Funds Rate), "DGS10"
    (10-Year Treasury Yield).
    """

    name = "fred"
    category = SourceCategory.ECONOMIC_DATA
    tier = ProviderTier.TIER_1
    reliability = 0.98

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.data_providers.fred_api_key.get_secret_value())

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, params: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
            return response

    async def fetch(self, **kwargs: object) -> list[dict[str, Any]]:
        """Fetch observations for a single FRED series.

        Args:
            series_id: FRED series identifier, e.g. "CPIAUCSL".

        Returns:
            A list of `{"date": ..., "value": ...}` observation dicts.

        Raises:
            ProviderError: If the request is malformed, the API responds
                with an error, or the network request fails after retries.
        """
        series_id = kwargs.get("series_id")
        if not isinstance(series_id, str):
            raise ProviderError("fetch() requires a 'series_id' string argument")

        params = {
            "series_id": series_id,
            "api_key": self._settings.data_providers.fred_api_key.get_secret_value(),
            "file_type": "json",
        }

        try:
            response = await self._request(params)
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"FRED returned HTTP {exc.response.status_code}") from exc
        except httpx.TransportError as exc:
            raise ProviderError(f"FRED request failed after retries: {exc}") from exc

        payload = response.json()
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise ProviderError("FRED response missing 'observations' array")
        return observations
