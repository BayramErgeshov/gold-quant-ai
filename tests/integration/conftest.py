"""Shared fixtures for every integration test.

Uses an in-memory SQLite engine rather than a live PostgreSQL container so
repository/engine behavior (real SQL execution, constraints, ordering) is
verified without requiring Docker to be running locally. The Alembic
migration itself is exercised against a real PostgreSQL service container
in CI (`.github/workflows/ci.yml` runs `alembic upgrade head` before the
test suite), since it contains PostgreSQL-specific DDL (e.g. `pgcrypto`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.database.postgres.base import Base

# Import every model so `Base.metadata` is fully populated.
from src.models import (  # noqa: F401
    book,
    book_claim,
    candle,
    concept,
    historical_similarity,
    improvement_proposal,
    market_regime,
    ml_model,
    news_article,
    symbol,
    system_log,
    trade,
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session


@pytest.fixture(autouse=True)
def _mark_integration(request: pytest.FixtureRequest) -> None:
    request.node.add_marker(pytest.mark.integration)
