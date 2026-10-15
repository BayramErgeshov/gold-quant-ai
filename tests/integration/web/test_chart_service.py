"""Integration tests for the web UI's chart data assembly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.chart_service import get_chart_data
from src.models.candle import Candle
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.candle_repository import CandleRepository
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(symbol_id: object, offset: int, *, close: float) -> Candle:
    return Candle(
        symbol_id=symbol_id,
        timeframe="M15",
        timestamp=_BASE_TIME + timedelta(minutes=15 * offset),
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        source="test_fixture",
    )


async def test_returns_empty_chart_when_no_candles_stored(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))

    result = await get_chart_data(session, symbol_id=symbol.id, timeframe="M15")

    assert result.candles == []
    assert result.trade_markers == []
    assert result.zones == []


async def test_includes_candles_and_trade_markers(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    candle_repository = CandleRepository(session)
    await candle_repository.insert_new([_candle(symbol.id, i, close=2000.0 + i) for i in range(60)])
    await TradeRepository(session).add(
        Trade(
            symbol_id=symbol.id,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2010.0,
            stop_loss=2005.0,
            exit_price=2020.0,
            magic_number=1,
            opened_at=_BASE_TIME + timedelta(minutes=15 * 10),
            closed_at=_BASE_TIME + timedelta(minutes=15 * 20),
            realized_pnl=10.0,
        )
    )

    result = await get_chart_data(session, symbol_id=symbol.id, timeframe="M15")

    assert len(result.candles) == 60
    assert result.candles[0].time < result.candles[-1].time
    marker_kinds = {marker.kind for marker in result.trade_markers}
    assert "entry_buy" in marker_kinds
    assert "exit" in marker_kinds


async def test_detects_fair_value_gaps_from_real_candle_geometry(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    candle_repository = CandleRepository(session)
    # A deliberate 3-bar bullish FVG: bar[0].high < bar[2].low.
    candles = [_candle(symbol.id, i, close=2000.0) for i in range(20)]
    candles[10] = Candle(
        symbol_id=symbol.id,
        timeframe="M15",
        timestamp=_BASE_TIME + timedelta(minutes=15 * 10),
        open=2000.0,
        high=2001.0,
        low=1999.0,
        close=2000.0,
        source="test_fixture",
    )
    candles[11] = Candle(
        symbol_id=symbol.id,
        timeframe="M15",
        timestamp=_BASE_TIME + timedelta(minutes=15 * 11),
        open=2005.0,
        high=2010.0,
        low=2004.0,
        close=2008.0,
        source="test_fixture",
    )
    candles[12] = Candle(
        symbol_id=symbol.id,
        timeframe="M15",
        timestamp=_BASE_TIME + timedelta(minutes=15 * 12),
        open=2012.0,
        high=2013.0,
        low=2012.0,
        close=2012.5,
        source="test_fixture",
    )
    await candle_repository.insert_new(candles)

    result = await get_chart_data(session, symbol_id=symbol.id, timeframe="M15")

    assert any(zone.kind == "fvg_bullish" for zone in result.zones)
