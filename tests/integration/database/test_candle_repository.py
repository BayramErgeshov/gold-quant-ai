"""Integration tests for `CandleRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.candle import Candle
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.symbol_repository import SymbolRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    # SQLite (used by the `session` fixture) does not round-trip tzinfo;
    # normalize before comparing so assertions work the same on SQLite and
    # PostgreSQL.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _candle(symbol_id: object, offset_hours: int, *, close: float = 3400.0) -> Candle:
    return Candle(
        symbol_id=symbol_id,
        timeframe="H1",
        timestamp=_BASE_TIME + timedelta(hours=offset_hours),
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        source="twelvedata",
    )


async def test_insert_new_inserts_all_when_none_exist(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)

    inserted = await repo.insert_new([_candle(symbol.id, 0), _candle(symbol.id, 1)])

    assert inserted == 2


async def test_insert_new_skips_existing_candles(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)
    await repo.insert_new([_candle(symbol.id, 0)])

    inserted = await repo.insert_new([_candle(symbol.id, 0), _candle(symbol.id, 1)])

    assert inserted == 1
    all_candles = await repo.list_range(symbol.id, "H1")
    assert len(all_candles) == 2


async def test_insert_new_with_empty_list_returns_zero(session: AsyncSession) -> None:
    repo = CandleRepository(session)

    assert await repo.insert_new([]) == 0


async def test_list_range_filters_by_start_and_end(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)
    await repo.insert_new([_candle(symbol.id, offset) for offset in range(5)])

    results = await repo.list_range(
        symbol.id, "H1", start=_BASE_TIME + timedelta(hours=1), end=_BASE_TIME + timedelta(hours=3)
    )

    assert [_utc(c.timestamp) for c in results] == [
        _BASE_TIME + timedelta(hours=1),
        _BASE_TIME + timedelta(hours=2),
        _BASE_TIME + timedelta(hours=3),
    ]


async def test_list_most_recent_returns_the_tail_not_the_head(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)
    await repo.insert_new([_candle(symbol.id, offset) for offset in range(10)])

    results = await repo.list_most_recent(symbol.id, "H1", count=3)

    assert [_utc(c.timestamp) for c in results] == [
        _BASE_TIME + timedelta(hours=7),
        _BASE_TIME + timedelta(hours=8),
        _BASE_TIME + timedelta(hours=9),
    ]


async def test_list_most_recent_returns_everything_when_count_exceeds_history(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)
    await repo.insert_new([_candle(symbol.id, offset) for offset in range(3)])

    results = await repo.list_most_recent(symbol.id, "H1", count=100)

    assert len(results) == 3


async def test_latest_timestamp_returns_none_when_no_candles(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)

    assert await repo.latest_timestamp(symbol.id, "H1") is None


async def test_latest_timestamp_returns_most_recent(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = CandleRepository(session)
    await repo.insert_new([_candle(symbol.id, offset) for offset in range(3)])

    latest = await repo.latest_timestamp(symbol.id, "H1")

    assert latest == _BASE_TIME + timedelta(hours=2)
