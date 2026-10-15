"""Unit tests for `src.core.diagnostics`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from src.core.config.env_settings import MT5EnvSettings, TelegramEnvSettings
from src.core.diagnostics import (
    check_mt5,
    check_postgres,
    check_qdrant,
    check_redis,
    check_telegram,
    run_startup_diagnostics,
)
from src.core.execution.mt5_client import AccountInfo
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


async def test_check_mt5_not_configured() -> None:
    settings = get_settings().model_copy(update={"mt5_env": MT5EnvSettings(login="")})

    result = await check_mt5(settings)

    assert result.healthy is False
    assert "not configured" in result.detail


async def test_check_mt5_unhealthy_when_connect_fails() -> None:
    settings = get_settings().model_copy(
        update={
            "mt5_env": MT5EnvSettings(
                login="109345080", password=SecretStr("x"), server="MetaQuotes_Demo"
            )
        }
    )

    with patch("src.core.diagnostics.RealMT5Client.connect", AsyncMock(return_value=False)):
        result = await check_mt5(settings)

    assert result.healthy is False
    assert "terminal running" in result.detail


async def test_check_mt5_healthy_when_connected() -> None:
    settings = get_settings().model_copy(
        update={
            "mt5_env": MT5EnvSettings(
                login="109345080", password=SecretStr("x"), server="MetaQuotes_Demo"
            )
        }
    )
    account = AccountInfo(
        login=109345080,
        broker="MetaQuotes",
        server="MetaQuotes-Demo",
        balance=10_000.0,
        equity=10_000.0,
        margin=0.0,
        free_margin=10_000.0,
        margin_level=0.0,
        currency="USD",
        leverage=100,
        is_demo=True,
        trading_allowed=True,
    )

    with (
        patch("src.core.diagnostics.RealMT5Client.connect", AsyncMock(return_value=True)),
        patch(
            "src.core.diagnostics.RealMT5Client.get_account_info", AsyncMock(return_value=account)
        ),
    ):
        result = await check_mt5(settings)

    assert result.healthy is True
    assert "109345080" in result.detail
    assert "demo" in result.detail


async def test_check_telegram_not_configured() -> None:
    settings = get_settings().model_copy(
        update={"telegram_env": TelegramEnvSettings(bot_token=SecretStr(""))}
    )

    result = await check_telegram(settings)

    assert result.healthy is False
    assert "not configured" in result.detail


async def test_check_telegram_healthy_when_token_valid() -> None:
    settings = get_settings().model_copy(
        update={"telegram_env": TelegramEnvSettings(bot_token=SecretStr("123:abc"))}
    )

    with patch(
        "src.core.diagnostics.RealTelegramNotifier.verify_connection",
        AsyncMock(return_value="@xauusd_bybob_bot"),
    ):
        result = await check_telegram(settings)

    assert result.healthy is True
    assert "@xauusd_bybob_bot" in result.detail


async def test_run_startup_diagnostics_returns_all_checks() -> None:
    with (
        patch("src.core.diagnostics.check_postgres", AsyncMock()) as mock_postgres,
        patch("src.core.diagnostics.check_redis", AsyncMock()) as mock_redis,
        patch("src.core.diagnostics.check_qdrant", AsyncMock()) as mock_qdrant,
        patch("src.core.diagnostics.check_mt5", AsyncMock()) as mock_mt5,
        patch("src.core.diagnostics.check_telegram", AsyncMock()) as mock_telegram,
    ):
        await run_startup_diagnostics(get_settings())

    mock_postgres.assert_called_once()
    mock_redis.assert_called_once()
    mock_qdrant.assert_called_once()
    mock_mt5.assert_called_once()
    mock_telegram.assert_called_once()
