"""Unit tests for `OpenAIEmbeddingProvider`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.data_collection.exceptions import ProviderError
from src.core.embeddings.openai_provider import OpenAIEmbeddingProvider

pytestmark = pytest.mark.unit


def _provider(api_key: str = "test-key") -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(model="text-embedding-3-large", dimension=3072, api_key=api_key)


def test_dimension_returns_configured_value() -> None:
    assert _provider().dimension == 3072


async def test_embed_raises_without_api_key() -> None:
    provider = _provider(api_key="")

    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        await provider.embed(["hello"])


async def test_embed_raises_on_empty_input() -> None:
    with pytest.raises(ProviderError, match="non-empty"):
        await _provider().embed([])


async def test_embed_returns_vectors_in_order() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]
    }
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    vectors = await provider.embed(["hello", "world"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_raises_on_malformed_response() -> None:
    provider = _provider()
    fake_response = MagicMock()
    fake_response.json.return_value = {"unexpected": "shape"}
    provider._request = AsyncMock(return_value=fake_response)  # type: ignore[method-assign]

    with pytest.raises(ProviderError, match="data"):
        await provider.embed(["hello"])


async def test_embed_wraps_http_status_error() -> None:
    provider = _provider()
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(status_code=401, request=request)
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError("unauthorized", request=request, response=response)
    )

    with pytest.raises(ProviderError, match="401"):
        await provider.embed(["hello"])


async def test_embed_wraps_transport_error() -> None:
    provider = _provider()
    provider._request = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(ProviderError, match="failed after retries"):
        await provider.embed(["hello"])


async def test_request_performs_real_http_call_over_mock_transport() -> None:
    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"data": [{"embedding": [0.5]}]})

    def fake_async_client(**kwargs: object) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    provider = _provider()
    with patch("src.core.embeddings.openai_provider.httpx.AsyncClient", fake_async_client):
        vectors = await provider.embed(["hello"])

    assert vectors == [[0.5]]
