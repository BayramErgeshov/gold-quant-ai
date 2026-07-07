"""Alembic migration environment for GOLD QUANT AI.

Uses the same async engine configuration as the application
(`src.database.postgres.session`) so migrations always run against the same
database the app connects to — no separate, divergent connection string.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

# Import every ORM model so `Base.metadata` is fully populated before
# Alembic compares it against the live database (autogenerate support).
from src.database.postgres.base import Base
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
from src.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    """Resolve the PostgreSQL DSN from application settings."""
    return get_settings().postgres.dsn


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL without a live connection)."""
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live async connection."""
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable: AsyncEngine = create_async_engine(_get_database_url())

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
