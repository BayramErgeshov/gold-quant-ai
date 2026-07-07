"""Async SQLAlchemy engine/session management for PostgreSQL.

Per CODING_STANDARDS.md: async-first, dependency injection, repository
pattern. No module outside this one may construct an `AsyncEngine` directly.
Repositories accept an `AsyncSession` via constructor injection (see
`src/database/repositories/base.py`) rather than calling `get_session()`
themselves, so they remain trivially unit-testable against any session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.settings import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Build (and cache) the process-wide async PostgreSQL engine.

    Returns:
        A cached `AsyncEngine` connected via connection pooling, configured
        from `get_settings()`.
    """
    settings = get_settings()
    return create_async_engine(
        settings.postgres.dsn,
        echo=settings.platform.database.echo_sql,
        pool_size=settings.postgres.pool_min_size,
        max_overflow=max(settings.postgres.pool_max_size - settings.postgres.pool_min_size, 0),
        pool_pre_ping=True,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to the process-wide engine.

    Returns:
        An `async_sessionmaker` producing `AsyncSession` instances.
    """
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a transactional `AsyncSession`, committing on clean exit.

    Yields:
        An `AsyncSession` that commits on clean exit and rolls back on
        exception.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
