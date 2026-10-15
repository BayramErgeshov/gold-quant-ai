"""Unit tests for `FredEconomicProvider`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.data_collection.exceptions import ProviderError
from src.services.macro.providers.fred_provider import FredEconomicProvider
from src.settings import get_settings

pytestmark = pytest.mark.unit


def _provider() -> FredEconomicProvider:
    return FredEconomicProvider(get_settings())


def test_is_configured_false_without_api_key() -> None:
    assert _provider().is_configured is False


def test_is_configured_true_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    get_settings.cache_clear()

    assert FredEconomicProvider(get_settings()).is_configured is True


async def test_fetch_requires_series_id() -> None:
    with pytest.raises(ProviderError, match="series_id"):
        await _provider().fetch()


async def test_fetch_returns_observations() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"observations": [{"date": "2026-01-01", "value": "3400"}]}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    observations = await provider.fetch(series_id="CPIAUCSL")

    assert observations == [{"date": "2026-01-01", "value": "3400"}]


async def test_fetch_raises_provider_error_on_malformed_response() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"unexpected": "shape"}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    with pytest.raises(ProviderError, match="observations"):
        await provider.fetch(series_id="CPIAUCSL")


async def test_fetch_wraps_http_status_error() -> None:
    provider = _provider()
    request = httpx.Request("GET", "https://api.stlouisfed.org")
    response = httpx.Response(status_code=429, request=request)
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError("rate limited", request=request, response=response)
    )

    with pytest.raises(ProviderError, match="429"):
        await provider.fetch(series_id="CPIAUCSL")


async def test_fetch_wraps_transport_error() -> None:
    provider = _provider()
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(ProviderError, match="failed after retries"):
        await provider.fetch(series_id="CPIAUCSL")


async def test_request_performs_real_http_call_over_mock_transport() -> None:
    """Exercise the real `_request` implementation end-to-end without the network."""
    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["series_id"] == "CPIAUCSL"
        return httpx.Response(200, json={"observations": [{"date": "2026-01-01", "value": "1"}]})

    def fake_async_client(**kwargs: object) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    provider = _provider()
    with patch("src.services.macro.providers.fred_provider.httpx.AsyncClient", fake_async_client):
        observations = await provider.fetch(series_id="CPIAUCSL")

    assert observations == [{"date": "2026-01-01", "value": "1"}]
