"""Integration tests for `SymbolRepository` against a real SQL engine."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.symbol import Symbol
from src.repositories.symbol_repository import SymbolRepository


async def test_add_and_get_by_id(session: AsyncSession) -> None:
    repo = SymbolRepository(session)
    created = await repo.add(Symbol(name="XAUUSD", display_name="Gold vs US Dollar"))

    fetched = await repo.get_by_id(created.id)

    assert fetched is not None
    assert fetched.name == "XAUUSD"
    assert fetched.created_at is not None


async def test_get_by_name_returns_none_when_missing(session: AsyncSession) -> None:
    repo = SymbolRepository(session)

    assert await repo.get_by_name("DOES_NOT_EXIST") is None


async def test_get_primary_returns_the_flagged_symbol(session: AsyncSession) -> None:
    repo = SymbolRepository(session)
    await repo.add(Symbol(name="EURUSD", display_name="Euro vs US Dollar", is_primary=False))
    await repo.add(Symbol(name="XAUUSD", display_name="Gold vs US Dollar", is_primary=True))

    primary = await repo.get_primary()

    assert primary is not None
    assert primary.name == "XAUUSD"


async def test_list_enabled_excludes_disabled_symbols(session: AsyncSession) -> None:
    repo = SymbolRepository(session)
    await repo.add(Symbol(name="XAUUSD", display_name="Gold", is_enabled=True))
    await repo.add(Symbol(name="RETIRED", display_name="Retired symbol", is_enabled=False))

    enabled = await repo.list_enabled()

    assert {symbol.name for symbol in enabled} == {"XAUUSD"}


async def test_delete_removes_entity(session: AsyncSession) -> None:
    repo = SymbolRepository(session)
    created = await repo.add(Symbol(name="XAUUSD", display_name="Gold"))

    await repo.delete(created)

    assert await repo.get_by_id(created.id) is None


async def test_list_all_respects_limit(session: AsyncSession) -> None:
    repo = SymbolRepository(session)
    for index in range(5):
        await repo.add(Symbol(name=f"SYM{index}", display_name=f"Symbol {index}"))

    page = await repo.list_all(limit=2)

    assert len(page) == 2
