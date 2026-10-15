"""Integration tests for `CorrelatedPriceRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.correlated_instrument import CorrelatedInstrument
from src.models.correlated_price import CorrelatedPrice
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    # SQLite (used by the `session` fixture) does not round-trip tzinfo.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _make_instrument(session: AsyncSession) -> CorrelatedInstrument:
    return await CorrelatedInstrumentRepository(session).add(
        CorrelatedInstrument(
            name="EURUSD", display_name="Euro vs US Dollar", mt5_symbol="EURUSD", category="fx"
        )
    )


def _price(instrument_id: object, offset_hours: int, *, close: float = 1.1) -> CorrelatedPrice:
    return CorrelatedPrice(
        instrument_id=instrument_id,
        timeframe="H1",
        timestamp=_BASE_TIME + timedelta(hours=offset_hours),
        open=close - 0.001,
        high=close + 0.002,
        low=close - 0.002,
        close=close,
        source="mt5",
    )


async def test_insert_new_inserts_all_when_none_exist(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    repo = CorrelatedPriceRepository(session)

    inserted = await repo.insert_new([_price(instrument.id, 0), _price(instrument.id, 1)])

    assert inserted == 2


async def test_insert_new_skips_existing_prices(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    repo = CorrelatedPriceRepository(session)
    await repo.insert_new([_price(instrument.id, 0)])

    inserted = await repo.insert_new([_price(instrument.id, 0), _price(instrument.id, 1)])

    assert inserted == 1


async def test_insert_new_with_empty_list_returns_zero(session: AsyncSession) -> None:
    repo = CorrelatedPriceRepository(session)

    assert await repo.insert_new([]) == 0


async def test_list_most_recent_returns_the_tail_not_the_head(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    repo = CorrelatedPriceRepository(session)
    await repo.insert_new([_price(instrument.id, offset) for offset in range(10)])

    results = await repo.list_most_recent(instrument.id, "H1", count=3)

    assert [_utc(price.timestamp) for price in results] == [
        _BASE_TIME + timedelta(hours=7),
        _BASE_TIME + timedelta(hours=8),
        _BASE_TIME + timedelta(hours=9),
    ]
