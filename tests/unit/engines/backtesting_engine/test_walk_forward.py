"""Unit tests for walk-forward validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.backtesting_engine.simulator import Signal
from src.engines.backtesting_engine.walk_forward import run_walk_forward
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _uptrend_signal(window: list[Candle]) -> Signal:
    return "buy" if window[-1].close >= window[0].close else "wait"


def _make_uptrend_candles(n: int, *, start: float = 100.0, step_pct: float = 1.0) -> list[Candle]:
    candles = []
    price = start
    for index in range(n):
        close = price * (1 + step_pct / 100)
        candles.append(
            Candle(
                symbol_id=_SYMBOL_ID,
                timeframe="H1",
                timestamp=_BASE_TIME + timedelta(hours=index),
                open=price,
                high=close + 0.5,
                low=price - 0.5,
                close=close,
                source="test_fixture",
            )
        )
        price = close
    return candles


def _make_flat_candles(n: int, *, price: float = 100.0) -> list[Candle]:
    return [
        Candle(
            symbol_id=_SYMBOL_ID,
            timeframe="H1",
            timestamp=_BASE_TIME + timedelta(hours=index),
            open=price,
            high=price,
            low=price,
            close=price,
            source="test_fixture",
        )
        for index in range(n)
    ]


def test_passes_when_every_window_meets_thresholds() -> None:
    candles = _make_uptrend_candles(40, step_pct=1.0)

    result = run_walk_forward(
        candles,
        _uptrend_signal,
        window_size=1,
        stop_loss_pct=50.0,
        take_profit_pct=2.0,
        n_windows=2,
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
        min_win_rate=0.5,
        min_profit_factor=1.0,
    )

    assert result.passed is True
    assert len(result.window_reports) == 2
    assert all(report.win_rate >= 0.5 for report in result.window_reports)


def test_fails_when_one_window_is_weak() -> None:
    candles = _make_uptrend_candles(20, step_pct=1.0) + _make_flat_candles(20)

    result = run_walk_forward(
        candles,
        _uptrend_signal,
        window_size=1,
        stop_loss_pct=50.0,
        take_profit_pct=2.0,
        n_windows=2,
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
        min_win_rate=0.5,
        min_profit_factor=1.0,
    )

    assert result.passed is False


def test_window_reports_are_versioned_per_window() -> None:
    candles = _make_uptrend_candles(20, step_pct=1.0)

    result = run_walk_forward(
        candles,
        _uptrend_signal,
        window_size=1,
        stop_loss_pct=50.0,
        take_profit_pct=2.0,
        n_windows=2,
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
    )

    versions = {report.strategy_version for report in result.window_reports}
    assert versions == {"1.0.0-window1", "1.0.0-window2"}


def test_raises_for_non_positive_window_count() -> None:
    candles = _make_uptrend_candles(10)

    with pytest.raises(ValueError, match="n_windows"):
        run_walk_forward(
            candles,
            _uptrend_signal,
            window_size=1,
            stop_loss_pct=5.0,
            take_profit_pct=None,
            n_windows=0,
            strategy_name="x",
            strategy_version="1.0.0",
        )
