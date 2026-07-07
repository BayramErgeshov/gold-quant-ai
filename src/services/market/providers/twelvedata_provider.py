"""TwelveData market data provider adapter.

Tier 2 market data source per DATA_COLLECTION_ENGINE.md (MT5 itself is
Tier 1 once the MT5 Engine is implemented; TwelveData provides an
independent cross-check and a fallback when MT5 is unavailable). Requires
`TWELVEDATA_API_KEY`.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.data_collection.exceptions import ProviderError
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider
from src.settings import Settings, get_settings

_BASE_URL = "https://api.twelvedata.com/time_series"
_TIMEOUT_SECONDS = 10.0


class TwelveDataMarketProvider(DataProvider[list[dict[str, Any]]]):
    """Fetches OHLCV candles from TwelveData."""

    name = "twelvedata"
    category = SourceCategory.MARKET_DATA
    tier = ProviderTier.TIER_2
    reliability = 0.85

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.data_providers.twelvedata_api_key.get_secret_value())

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
        """Fetch OHLCV candles for a symbol/timeframe.

        Args:
            symbol: Instrument symbol, e.g. "XAU/USD".
            interval: Candle interval, e.g. "5min", "1h", "1day".
            output_size: Number of most recent candles to return.

        Returns:
            A list of candle dicts (datetime/open/high/low/close/volume).

        Raises:
            ProviderError: If the request is malformed, the API responds
                with an error, or the network request fails after retries.
        """
        symbol = kwargs.get("symbol")
        interval = kwargs.get("interval")
        if not isinstance(symbol, str) or not isinstance(interval, str):
            raise ProviderError("fetch() requires 'symbol' and 'interval' string arguments")

        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": kwargs.get("output_size", 100),
            "apikey": self._settings.data_providers.twelvedata_api_key.get_secret_value(),
        }

        try:
            response = await self._request(params)
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"TwelveData returned HTTP {exc.response.status_code}") from exc
        except httpx.TransportError as exc:
            raise ProviderError(f"TwelveData request failed after retries: {exc}") from exc

        payload = response.json()
        if payload.get("status") == "error":
            raise ProviderError(f"TwelveData error: {payload.get('message', 'unknown error')}")

        candles = payload.get("values")
        if not isinstance(candles, list):
            raise ProviderError("TwelveData response missing 'values' array")
        return candles
