"""Integration tests for `CorrelatedInstrumentRepository`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.correlated_instrument import CorrelatedInstrument
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository


async def test_get_by_name_returns_none_when_missing(session: AsyncSession) -> None:
    repo = CorrelatedInstrumentRepository(session)

    assert await repo.get_by_name("EURUSD") is None


async def test_get_by_name_returns_existing_instrument(session: AsyncSession) -> None:
    repo = CorrelatedInstrumentRepository(session)
    await repo.add(
        CorrelatedInstrument(
            name="EURUSD", display_name="Euro vs US Dollar", mt5_symbol="EURUSD", category="fx"
        )
    )

    found = await repo.get_by_name("EURUSD")

    assert found is not None
    assert found.mt5_symbol == "EURUSD"


async def test_list_enabled_with_mt5_symbol_excludes_disabled_and_symbolless(
    session: AsyncSession,
) -> None:
    repo = CorrelatedInstrumentRepository(session)
    await repo.add(
        CorrelatedInstrument(
            name="EURUSD",
            display_name="Euro vs US Dollar",
            mt5_symbol="EURUSD",
            category="fx",
            is_enabled=True,
        )
    )
    await repo.add(
        CorrelatedInstrument(
            name="US_10Y_YIELD",
            display_name="US 10-Year Treasury Yield",
            mt5_symbol=None,
            category="rates",
            is_enabled=False,
        )
    )
    await repo.add(
        CorrelatedInstrument(
            name="DISABLED_FX",
            display_name="Disabled FX pair",
            mt5_symbol="GBPUSD",
            category="fx",
            is_enabled=False,
        )
    )

    results = await repo.list_enabled_with_mt5_symbol()

    assert [instrument.name for instrument in results] == ["EURUSD"]
