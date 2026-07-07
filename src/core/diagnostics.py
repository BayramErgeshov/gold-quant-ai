"""Startup diagnostics for GOLD QUANT AI.

Implements the "Startup Workflow" from WORKFLOW_ENGINE.md: verify every
critical infrastructure dependency before the platform begins research or
trading. If a critical dependency is unhealthy, the platform must not trade
but should continue running remaining diagnostics and stay observable
(FAILSAFE_PROTOCOL.md Level 2/3 behavior) rather than crash outright.

`check_mt5`/`check_telegram` must be run from the same local Windows
session as a running MT5 terminal / with a real bot token configured —
`MetaTrader5.initialize()` communicates via local IPC, so it cannot
succeed from a different machine or an isolated remote session than the
one running the terminal. External data providers (FRED/NewsAPI/
TwelveData) are checked per-request by their own `FallbackChain`
(DATA_COLLECTION_ENGINE.md), not here at startup.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncpg
import redis.asyncio as redis
from qdrant_client import AsyncQdrantClient

from src.core.execution.mt5_client import RealMT5Client
from src.core.notifications.telegram_client import RealTelegramNotifier
from src.settings import Settings


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of a single startup diagnostic check.

    Attributes:
        name: Human-readable check name.
        healthy: Whether the dependency responded successfully.
        detail: Short human-readable status or error message.
        duration_ms: How long the check took, in milliseconds.
        critical: Whether failure of this check should prevent trading.
    """

    name: str
    healthy: bool
    detail: str
    duration_ms: float
    critical: bool = True


async def _timed(name: str, critical: bool, probe: Callable[[], Awaitable[str]]) -> CheckResult:
    """Run a single probe coroutine and capture its timing and outcome.

    Args:
        name: Human-readable check name.
        critical: Whether failure should be treated as trading-blocking.
        probe: Coroutine factory returning a success detail message, or
            raising an exception on failure.

    Returns:
        The resulting `CheckResult`.
    """
    started_at = time.perf_counter()
    try:
        detail = await probe()
        healthy = True
    except Exception as exc:  # noqa: BLE001 - any dependency failure must be captured, not raised
        detail = f"{type(exc).__name__}: {exc}"
        healthy = False
    duration_ms = (time.perf_counter() - started_at) * 1000
    return CheckResult(name=name, healthy=healthy, detail=detail, duration_ms=duration_ms,
                        critical=critical)


async def check_postgres(settings: Settings) -> CheckResult:
    """Verify PostgreSQL is reachable and accepting connections."""

    async def probe() -> str:
        connection = await asyncpg.connect(
            host=settings.postgres.host,
            port=settings.postgres.port,
            user=settings.postgres.user,
            password=settings.postgres.password.get_secret_value(),
            database=settings.postgres.db,
            timeout=5,
        )
        try:
            version = await connection.fetchval("SELECT version()")
        finally:
            await connection.close()
        return str(version)

    return await _timed("postgres", critical=True, probe=probe)


async def check_redis(settings: Settings) -> CheckResult:
    """Verify Redis is reachable and responding to PING."""

    async def probe() -> str:
        client = redis.from_url(settings.redis.url, socket_timeout=5)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return "PONG"

    return await _timed("redis", critical=True, probe=probe)


async def check_qdrant(settings: Settings) -> CheckResult:
    """Verify Qdrant is reachable and responding to health/collections calls."""

    async def probe() -> str:
        client = AsyncQdrantClient(
            host=settings.qdrant.host,
            port=settings.qdrant.port,
            api_key=settings.qdrant.api_key.get_secret_value() or None,
            timeout=5,
        )
        try:
            collections = await client.get_collections()
        finally:
            await client.close()
        return f"{len(collections.collections)} collection(s)"

    return await _timed("qdrant", critical=True, probe=probe)


async def check_mt5(settings: Settings) -> CheckResult:
    """Verify the MT5 terminal is running, reachable and authenticated.

    Per MT5_ENGINE.md "Connection Validation": before any operation,
    confirm the terminal is running and the account is authenticated.
    Reports a clear "not configured" detail rather than a confusing IPC
    error when `MT5_LOGIN` has not been set yet.
    """

    async def probe() -> str:
        if not settings.mt5_env.login:
            raise RuntimeError("MT5_LOGIN not configured")
        client = RealMT5Client(settings)
        if not await client.connect():
            raise ConnectionError(
                "MetaTrader5.initialize() failed - is the terminal running on this machine?"
            )
        account = await client.get_account_info()
        mode = "demo" if account.is_demo else "LIVE"
        return f"account {account.login} on {account.server} ({mode})"

    return await _timed("mt5", critical=True, probe=probe)


async def check_telegram(settings: Settings) -> CheckResult:
    """Verify the configured Telegram bot token is valid.

    Reports a clear "not configured" detail rather than a confusing API
    error when `TELEGRAM_BOT_TOKEN` has not been set yet.
    """

    async def probe() -> str:
        if not settings.telegram_env.bot_token.get_secret_value():
            raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
        username = await RealTelegramNotifier(settings).verify_connection()
        return f"bot {username}"

    return await _timed("telegram", critical=True, probe=probe)


async def run_startup_diagnostics(settings: Settings) -> list[CheckResult]:
    """Run every registered startup check concurrently.

    Args:
        settings: Resolved application settings.

    Returns:
        One `CheckResult` per registered check, in registration order.
    """
    checks = (
        check_postgres(settings),
        check_redis(settings),
        check_qdrant(settings),
        check_mt5(settings),
        check_telegram(settings),
    )
    return list(await asyncio.gather(*checks))
