"""Unit tests for historical replay simulation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.backtesting_engine.simulator import (
    ExecutionCosts,
    Signal,
    run_historical_replay,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="H1",
        timestamp=_BASE_TIME + timedelta(hours=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        source="test_fixture",
    )


def _signal_function_from_script(signals: list[Signal]) -> object:
    iterator = iter(signals)

    def _fn(window: list[Candle]) -> Signal:
        del window
        return next(iterator, "wait")

    return _fn


def test_no_trades_when_insufficient_history() -> None:
    candles = [_candle(0, open_=100, high=101, low=99, close=100)]

    run = run_historical_replay(
        candles, _signal_function_from_script([]), window_size=1, stop_loss_pct=1.0
    )

    assert run.trades == []
    assert run.equity_curve == [10_000.0]


def test_stop_loss_exit_triggers_on_low() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=100, low=90, close=95),
    ]
    signal_function = _signal_function_from_script(["buy", "wait"])

    run = run_historical_replay(candles, signal_function, window_size=1, stop_loss_pct=5.0)

    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(95.0)
    assert trade.return_pct == pytest.approx(-5.0)


def test_take_profit_exit_triggers_on_high() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=110, low=100, close=105),
    ]
    signal_function = _signal_function_from_script(["buy", "wait"])

    run = run_historical_replay(
        candles, signal_function, window_size=1, stop_loss_pct=5.0, take_profit_pct=10.0
    )

    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.return_pct == pytest.approx(10.0)


def test_signal_reversal_closes_position_and_flips() -> None:
    # A "sell" signal while long closes the long (signal_reversed) and
    # immediately opens a short at the same bar's open — a same-bar flip,
    # not merely a flat close.
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=102, high=103, low=101, close=102),
        _candle(3, open_=100, high=101, low=99, close=100),
    ]
    signal_function = _signal_function_from_script(["buy", "sell", "wait"])

    run = run_historical_replay(candles, signal_function, window_size=1, stop_loss_pct=50.0)

    assert len(run.trades) == 2
    assert run.trades[0].direction == "buy"
    assert run.trades[0].exit_reason == "signal_reversed"
    assert run.trades[0].exit_price == pytest.approx(102.0)
    assert run.trades[1].direction == "sell"
    assert run.trades[1].exit_reason == "end_of_data"


def test_end_of_data_closes_open_position_at_last_close() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=101, low=99, close=103),
    ]
    signal_function = _signal_function_from_script(["buy", "wait"])

    run = run_historical_replay(candles, signal_function, window_size=1, stop_loss_pct=50.0)

    assert len(run.trades) == 1
    assert run.trades[0].exit_reason == "end_of_data"
    assert run.trades[0].exit_price == pytest.approx(103.0)


def test_sell_direction_profits_from_price_decline() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=101, low=90, close=95),
    ]
    signal_function = _signal_function_from_script(["sell", "wait"])

    run = run_historical_replay(
        candles, signal_function, window_size=1, stop_loss_pct=50.0, take_profit_pct=5.0
    )

    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade.direction == "sell"
    assert trade.exit_reason == "take_profit"
    assert trade.return_pct == pytest.approx(5.0)


def test_sell_direction_stop_loss_triggers_on_high() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=110, low=100, close=105),
    ]
    signal_function = _signal_function_from_script(["sell", "wait"])

    run = run_historical_replay(candles, signal_function, window_size=1, stop_loss_pct=5.0)

    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(105.0)
    assert trade.return_pct == pytest.approx(-5.0)


def test_execution_costs_reduce_return() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=110, low=100, close=105),
    ]
    signal_function = _signal_function_from_script(["buy", "wait"])
    costs = ExecutionCosts(spread_pct=0.1, slippage_pct=0.1, commission_pct=0.1)

    run = run_historical_replay(
        candles,
        signal_function,
        window_size=1,
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        execution_costs=costs,
    )

    assert len(run.trades) == 1
    assert run.trades[0].return_pct < 10.0


def test_equity_curve_compounds_across_multiple_trades() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100),
        _candle(1, open_=100, high=101, low=99, close=100),
        _candle(2, open_=100, high=110, low=100, close=105),
        _candle(3, open_=105, high=106, low=104, close=105),
        _candle(4, open_=105, high=116, low=105, close=110),
    ]
    signal_function = _signal_function_from_script(["buy", "wait", "buy", "wait"])

    run = run_historical_replay(
        candles, signal_function, window_size=1, stop_loss_pct=5.0, take_profit_pct=10.0
    )

    assert len(run.trades) == 2
    assert len(run.equity_curve) == 3
    assert run.equity_curve[0] == 10_000.0
    assert run.equity_curve[-1] > run.equity_curve[0]
