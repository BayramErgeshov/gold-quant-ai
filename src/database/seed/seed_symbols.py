"""Idempotent seed data for the `symbols` table.

Every fresh database needs the platform's primary symbol to exist before
any research or execution can begin (CONFIGURATION.md: "Primary: XAUUSD").
Safe to run repeatedly — existing rows are left untouched.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.logging import get_logger
from src.models.symbol import Symbol
from src.repositories.symbol_repository import SymbolRepository
from src.settings import Settings, get_settings

logger = get_logger(__name__)


async def seed_primary_symbol(session: AsyncSession, settings: Settings | None = None) -> Symbol:
    """Ensure the configured primary symbol exists in the database.

    Args:
        session: An active `AsyncSession`.
        settings: Application settings. Defaults to `get_settings()`.

    Returns:
        The existing or newly created `Symbol` row for the primary symbol.
    """
    resolved_settings = settings or get_settings()
    primary_name = resolved_settings.platform.symbols.primary
    repository = SymbolRepository(session)

    existing = await repository.get_by_name(primary_name)
    if existing is not None:
        return existing

    created = await repository.add(
        Symbol(name=primary_name, display_name=primary_name, is_primary=True, is_enabled=True)
    )
    logger.info("symbol_seeded", name=primary_name)
    return created
