"""Unit tests for `src.core.data_collection.cache`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.data_collection.cache import build_cache_key, get_cached, set_cached

pytestmark = pytest.mark.unit


def test_build_cache_key_is_namespaced() -> None:
    key = build_cache_key("economic_data", "fred:CPIAUCSL")

    assert key == "data_collection:economic_data:fred:CPIAUCSL"


async def test_get_cached_returns_none_when_missing() -> None:
    client = AsyncMock()
    client.get.return_value = None

    with patch("src.core.data_collection.cache.get_redis_client", return_value=client):
        result = await get_cached("some_key")

    assert result is None


async def test_get_cached_deserializes_json() -> None:
    client = AsyncMock()
    client.get.return_value = '{"value": 42}'

    with patch("src.core.data_collection.cache.get_redis_client", return_value=client):
        result = await get_cached("some_key")

    assert result == {"value": 42}


async def test_set_cached_serializes_and_sets_ttl() -> None:
    client = AsyncMock()

    with patch("src.core.data_collection.cache.get_redis_client", return_value=client):
        await set_cached("some_key", {"value": 42}, ttl_seconds=120)

    client.set.assert_awaited_once_with("some_key", '{"value": 42}', ex=120)
