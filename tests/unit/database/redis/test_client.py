"""Unit tests for `src.database.redis.client`."""

from __future__ import annotations

import pytest

from src.database.redis.client import get_redis_client

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_redis_client.cache_clear()
    yield
    get_redis_client.cache_clear()


def test_get_redis_client_returns_configured_client() -> None:
    client = get_redis_client()

    assert client.connection_pool.connection_kwargs["host"] == "localhost"
    assert client.connection_pool.connection_kwargs["port"] == 6379


def test_get_redis_client_is_cached() -> None:
    assert get_redis_client() is get_redis_client()
