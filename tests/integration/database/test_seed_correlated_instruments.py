"""Integration tests for `seed_correlated_instruments`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.seed.seed_correlated_instruments import seed_correlated_instruments
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository


async def test_seed_creates_every_configured_instrument(session: AsyncSession) -> None:
    created = await seed_correlated_instruments(session)

    assert len(created) > 0
    names = {instrument.name for instrument in created}
    assert "EURUSD" in names
    assert "US_10Y_YIELD" in names


async def test_seed_marks_only_instruments_with_an_mt5_symbol_as_enabled(
    session: AsyncSession,
) -> None:
    created = await seed_correlated_instruments(session)

    by_name = {instrument.name: instrument for instrument in created}
    assert by_name["EURUSD"].is_enabled is True
    assert by_name["EURUSD"].mt5_symbol == "EURUSD"
    assert by_name["US_10Y_YIELD"].is_enabled is False
    assert by_name["US_10Y_YIELD"].mt5_symbol is None


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    first = await seed_correlated_instruments(session)
    second = await seed_correlated_instruments(session)

    assert len(first) == len(second)
    repo = CorrelatedInstrumentRepository(session)
    stored = await repo.get_by_name("EURUSD")
    assert stored is not None
