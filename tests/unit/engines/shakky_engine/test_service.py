"""Unit tests for `ShakkyAnalysisService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.execution.mt5_client import SymbolTick
from src.engines.shakky_engine.service import ShakkyAnalysisService, _is_stop_loss_valid
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _tick(price: float) -> SymbolTick:
    return SymbolTick(bid=price - 0.1, ask=price + 0.1, timestamp=_BASE_TIME)


def _candle(
    offset: int, *, close: float, high: float | None = None, low: float | None = None
) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=5 * offset),
        open=close,
        high=high if high is not None else close + 0.3,
        low=low if low is not None else close - 0.3,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _strong_uptrend(count: int = 80, *, start: float = 1900.0) -> list[Candle]:
    return [_candle(i, close=start + i * i * 0.05) for i in range(count)]


def _strong_downtrend(count: int = 80, *, start: float = 2100.0) -> list[Candle]:
    return [_candle(i, close=start - i * i * 0.05) for i in range(count)]


async def test_analyze_returns_none_with_too_few_m5_candles() -> None:
    service = ShakkyAnalysisService()

    outcome = await service.analyze(
        m5_candles=_strong_uptrend(count=10),
        m15_candles=None,
        h1_candles=None,
        h4_candles=None,
        d1_candles=None,
        dxy_candles=None,
        tick=_tick(1900.0),
    )

    assert outcome.signal is None
    assert outcome.reasons == ["insufficient_m5_history"]


async def test_analyze_produces_a_buy_signal_on_a_strong_uptrend() -> None:
    candles = _strong_uptrend()
    service = ShakkyAnalysisService()

    outcome = await service.analyze(
        m5_candles=candles,
        m15_candles=None,
        h1_candles=None,
        h4_candles=None,
        d1_candles=None,
        dxy_candles=None,
        tick=_tick(candles[-1].close),
    )

    assert outcome.signal is not None
    assert outcome.direction == "buy"
    assert outcome.signal.stop_loss < outcome.signal.entry_price
    assert outcome.signal.take_profit > outcome.signal.entry_price
    assert outcome.confirmation_count >= 3


async def test_analyze_produces_a_sell_signal_on_a_strong_downtrend() -> None:
    candles = _strong_downtrend()
    service = ShakkyAnalysisService()

    outcome = await service.analyze(
        m5_candles=candles,
        m15_candles=None,
        h1_candles=None,
        h4_candles=None,
        d1_candles=None,
        dxy_candles=None,
        tick=_tick(candles[-1].close),
    )

    assert outcome.signal is not None
    assert outcome.direction == "sell"
    assert outcome.signal.stop_loss > outcome.signal.entry_price
    assert outcome.signal.take_profit < outcome.signal.entry_price


async def test_analyze_returns_none_without_enough_confirmations() -> None:
    # A perfectly flat, directionless market should never accumulate 3
    # agreeing confirmations.
    flat = [_candle(i, close=2000.0) for i in range(80)]
    service = ShakkyAnalysisService()

    outcome = await service.analyze(
        m5_candles=flat,
        m15_candles=None,
        h1_candles=None,
        h4_candles=None,
        d1_candles=None,
        dxy_candles=None,
        tick=_tick(2000.0),
    )

    assert outcome.signal is None


async def test_analyze_rejects_a_trade_when_confirmation_timeframes_net_disagree() -> None:
    candles = _strong_uptrend()
    opposing_timeframe = _strong_downtrend(count=80)
    service = ShakkyAnalysisService()

    outcome = await service.analyze(
        m5_candles=candles,
        m15_candles=opposing_timeframe,
        h1_candles=opposing_timeframe,
        h4_candles=opposing_timeframe,
        d1_candles=None,
        dxy_candles=None,
        tick=_tick(candles[-1].close),
    )

    assert outcome.signal is None
    assert "multi_timeframe_net_disagreement" in outcome.reasons


def test_is_stop_loss_valid_rejects_a_sell_stop_below_the_current_price() -> None:
    # Reproduces the exact production incident (retcode 10016 "Invalid
    # stops"): a sell whose candlestick-anchored stop had fallen below
    # the current entry price after the market drifted past it.
    assert (
        _is_stop_loss_valid(direction="sell", entry_price=4020.83, stop_loss=4019.74, atr=1.0)
        is False
    )


def test_is_stop_loss_valid_rejects_a_buy_stop_above_the_current_price() -> None:
    assert (
        _is_stop_loss_valid(direction="buy", entry_price=1999.0, stop_loss=2000.5, atr=1.0) is False
    )


def test_is_stop_loss_valid_accepts_a_normally_placed_sell_stop() -> None:
    assert (
        _is_stop_loss_valid(direction="sell", entry_price=2000.0, stop_loss=2001.5, atr=1.0) is True
    )


def test_is_stop_loss_valid_rejects_a_stop_too_close_to_entry_even_on_the_right_side() -> None:
    # Right side of entry, but the distance has collapsed to a sliver --
    # still not a stop the broker would accept.
    assert (
        _is_stop_loss_valid(direction="sell", entry_price=2000.0, stop_loss=2000.001, atr=1.0)
        is False
    )


async def test_analyze_allows_a_trade_when_confirmation_timeframes_agree() -> None:
    candles = _strong_uptrend()
    agreeing_timeframe = _strong_uptrend(count=80)
    service = ShakkyAnalysisService()

    outcome = await service.analyze(
        m5_candles=candles,
        m15_candles=agreeing_timeframe,
        h1_candles=agreeing_timeframe,
        h4_candles=None,
        d1_candles=None,
        dxy_candles=None,
        tick=_tick(candles[-1].close),
    )

    assert outcome.signal is not None
    assert any("m15_confirms" in reason for reason in outcome.reasons)
