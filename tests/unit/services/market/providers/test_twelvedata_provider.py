"""Unit tests for `TwelveDataMarketProvider`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.data_collection.exceptions import ProviderError
from src.services.market.providers.twelvedata_provider import TwelveDataMarketProvider
from src.settings import get_settings

pytestmark = pytest.mark.unit


def _provider() -> TwelveDataMarketProvider:
    return TwelveDataMarketProvider(get_settings())


def test_is_configured_false_without_api_key() -> None:
    assert _provider().is_configured is False


def test_is_configured_true_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWELVEDATA_API_KEY", "test-key")
    get_settings.cache_clear()

    assert TwelveDataMarketProvider(get_settings()).is_configured is True


async def test_fetch_requires_symbol_and_interval() -> None:
    with pytest.raises(ProviderError, match="symbol"):
        await _provider().fetch()

    with pytest.raises(ProviderError, match="symbol"):
        await _provider().fetch(symbol="XAU/USD")


async def test_fetch_returns_candles() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "status": "ok",
        "values": [{"datetime": "2026-01-01 00:00:00", "close": "3400.0"}],
    }
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    candles = await provider.fetch(symbol="XAU/USD", interval="5min")

    assert candles == [{"datetime": "2026-01-01 00:00:00", "close": "3400.0"}]


async def test_fetch_raises_on_api_error_status() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"status": "error", "message": "invalid symbol"}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    with pytest.raises(ProviderError, match="invalid symbol"):
        await provider.fetch(symbol="BOGUS", interval="5min")


async def test_fetch_raises_provider_error_on_malformed_response() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"status": "ok", "unexpected": "shape"}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    with pytest.raises(ProviderError, match="values"):
        await provider.fetch(symbol="XAU/USD", interval="5min")


async def test_fetch_wraps_http_status_error() -> None:
    provider = _provider()
    request = httpx.Request("GET", "https://api.twelvedata.com")
    response = httpx.Response(status_code=403, request=request)
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError("forbidden", request=request, response=response)
    )

    with pytest.raises(ProviderError, match="403"):
        await provider.fetch(symbol="XAU/USD", interval="5min")


async def test_fetch_wraps_transport_error() -> None:
    provider = _provider()
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(ProviderError, match="failed after retries"):
        await provider.fetch(symbol="XAU/USD", interval="5min")


async def test_request_performs_real_http_call_over_mock_transport() -> None:
    """Exercise the real `_request` implementation end-to-end without the network."""

    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "XAU/USD"
        assert request.url.params["interval"] == "5min"
        return httpx.Response(
            200,
            json={"status": "ok", "values": [{"datetime": "2026-01-01 00:00:00", "close": "1"}]},
        )

    def fake_async_client(**kwargs: object) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    provider = _provider()
    with patch(
        "src.services.market.providers.twelvedata_provider.httpx.AsyncClient",
        fake_async_client,
    ):
        candles = await provider.fetch(symbol="XAU/USD", interval="5min")

    assert candles == [{"datetime": "2026-01-01 00:00:00", "close": "1"}]
