"""Unit tests for `NewsApiProvider`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.data_collection.exceptions import ProviderError
from src.services.news.providers.newsapi_provider import NewsApiProvider
from src.settings import get_settings

pytestmark = pytest.mark.unit


def _provider() -> NewsApiProvider:
    return NewsApiProvider(get_settings())


def test_is_configured_false_without_api_key() -> None:
    assert _provider().is_configured is False


def test_is_configured_true_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSAPI_API_KEY", "test-key")
    get_settings.cache_clear()

    assert NewsApiProvider(get_settings()).is_configured is True


async def test_fetch_requires_query() -> None:
    with pytest.raises(ProviderError, match="query"):
        await _provider().fetch()


async def test_fetch_returns_articles() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"articles": [{"title": "Gold rallies"}]}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    articles = await provider.fetch(query="gold OR XAUUSD")

    assert articles == [{"title": "Gold rallies"}]


async def test_fetch_raises_provider_error_on_malformed_response() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"unexpected": "shape"}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    with pytest.raises(ProviderError, match="articles"):
        await provider.fetch(query="gold")


async def test_fetch_wraps_http_status_error() -> None:
    provider = _provider()
    request = httpx.Request("GET", "https://newsapi.org")
    response = httpx.Response(status_code=401, request=request)
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError("unauthorized", request=request, response=response)
    )

    with pytest.raises(ProviderError, match="401"):
        await provider.fetch(query="gold")


async def test_fetch_wraps_transport_error() -> None:
    provider = _provider()
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(ProviderError, match="failed after retries"):
        await provider.fetch(query="gold")


async def test_request_performs_real_http_call_over_mock_transport() -> None:
    """Exercise the real `_request` implementation end-to-end without the network."""
    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == ""
        assert request.url.params["q"] == "gold"
        return httpx.Response(200, json={"articles": [{"title": "Gold rallies"}]})

    def fake_async_client(**kwargs: object) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    provider = _provider()
    with patch(
        "src.services.news.providers.newsapi_provider.httpx.AsyncClient", fake_async_client
    ):
        articles = await provider.fetch(query="gold")

    assert articles == [{"title": "Gold rallies"}]
