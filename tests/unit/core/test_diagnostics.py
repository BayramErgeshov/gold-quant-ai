"""Unit tests for `src.core.diagnostics`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.diagnostics import (
    check_postgres,
    check_qdrant,
    check_redis,
    run_startup_diagnostics,
)
from src.settings import get_settings

pytestmark = pytest.mark.unit


async def test_check_postgres_healthy() -> None:
    connection = AsyncMock()
    connection.fetchval.return_value = "PostgreSQL 16.0"

    with patch("src.core.diagnostics.asyncpg.connect", AsyncMock(return_value=connection)):
        result = await check_postgres(get_settings())

    assert result.healthy is True
    assert result.name == "postgres"
    assert result.critical is True
    assert "PostgreSQL" in result.detail
    connection.close.assert_awaited_once()


async def test_check_postgres_unhealthy_on_connection_error() -> None:
    with patch(
        "src.core.diagnostics.asyncpg.connect",
        AsyncMock(side_effect=OSError("connection refused")),
    ):
        result = await check_postgres(get_settings())

    assert result.healthy is False
    assert "OSError" in result.detail


async def test_check_redis_healthy() -> None:
    client = AsyncMock()

    with patch("src.core.diagnostics.redis.from_url", MagicMock(return_value=client)):
        result = await check_redis(get_settings())

    assert result.healthy is True
    assert result.detail == "PONG"
    client.ping.assert_awaited_once()
    client.aclose.assert_awaited_once()


async def test_check_redis_unhealthy_on_ping_failure() -> None:
    client = AsyncMock()
    client.ping.side_effect = ConnectionError("refused")

    with patch("src.core.diagnostics.redis.from_url", MagicMock(return_value=client)):
        result = await check_redis(get_settings())

    assert result.healthy is False
    assert "ConnectionError" in result.detail
    client.aclose.assert_awaited_once()


async def test_check_qdrant_healthy() -> None:
    client = AsyncMock()
    collections_response = MagicMock()
    collections_response.collections = [MagicMock(), MagicMock()]
    client.get_collections.return_value = collections_response

    with patch("src.core.diagnostics.AsyncQdrantClient", MagicMock(return_value=client)):
        result = await check_qdrant(get_settings())

    assert result.healthy is True
    assert result.detail == "2 collection(s)"
    client.close.assert_awaited_once()


async def test_check_qdrant_unhealthy_on_failure() -> None:
    client = AsyncMock()
    client.get_collections.side_effect = TimeoutError("timed out")

    with patch("src.core.diagnostics.AsyncQdrantClient", MagicMock(return_value=client)):
        result = await check_qdrant(get_settings())

    assert result.healthy is False
    assert "TimeoutError" in result.detail


async def test_run_startup_diagnostics_returns_all_checks() -> None:
    with (
        patch("src.core.diagnostics.check_postgres", AsyncMock()) as mock_postgres,
        patch("src.core.diagnostics.check_redis", AsyncMock()) as mock_redis,
        patch("src.core.diagnostics.check_qdrant", AsyncMock()) as mock_qdrant,
    ):
        await run_startup_diagnostics(get_settings())

    mock_postgres.assert_called_once()
    mock_redis.assert_called_once()
    mock_qdrant.assert_called_once()
