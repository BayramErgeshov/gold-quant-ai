"""Integration tests for `src.database.seed.seed_symbols`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.seed.seed_symbols import seed_primary_symbol
from src.repositories.symbol_repository import SymbolRepository
from src.settings import get_settings


async def test_seed_primary_symbol_creates_row_when_missing(session: AsyncSession) -> None:
    symbol = await seed_primary_symbol(session, get_settings())

    assert symbol.name == get_settings().platform.symbols.primary
    assert symbol.is_primary is True


async def test_seed_primary_symbol_is_idempotent(session: AsyncSession) -> None:
    first = await seed_primary_symbol(session, get_settings())
    second = await seed_primary_symbol(session, get_settings())

    assert first.id == second.id
    repository = SymbolRepository(session)
    all_symbols = await repository.list_all()
    assert len([s for s in all_symbols if s.name == first.name]) == 1
