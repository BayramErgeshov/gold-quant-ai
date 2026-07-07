"""Unit tests for parameter grid search."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.backtesting_engine.optimization import (
    ParameterCombination,
    run_parameter_grid_search,
)
from src.engines.backtesting_engine.simulator import Signal
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


def test_ranks_results_by_robustness_score_descending() -> None:
    candles = _make_uptrend_candles(40, step_pct=1.0)
    combinations = [
        ParameterCombination(stop_loss_pct=50.0, take_profit_pct=2.0),
        ParameterCombination(stop_loss_pct=1.0, take_profit_pct=0.5),
    ]

    results = run_parameter_grid_search(
        candles,
        _uptrend_signal,
        window_size=1,
        parameter_combinations=combinations,
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
    )

    assert len(results) == 2
    assert results[0].robustness_score >= results[1].robustness_score


def test_returns_one_result_per_combination() -> None:
    candles = _make_uptrend_candles(20, step_pct=1.0)
    combinations = [ParameterCombination(stop_loss_pct=5.0, take_profit_pct=None)]

    results = run_parameter_grid_search(
        candles,
        _uptrend_signal,
        window_size=1,
        parameter_combinations=combinations,
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
    )

    assert len(results) == 1
    assert results[0].parameters == combinations[0]


def test_robustness_score_falls_back_to_expectancy_for_infinite_profit_factor() -> None:
    # A pure uptrend with a small target and a huge stop never loses, so
    # profit_factor is infinite; the robustness score must still be finite.
    candles = _make_uptrend_candles(40, step_pct=1.0)
    combinations = [ParameterCombination(stop_loss_pct=90.0, take_profit_pct=0.5)]

    results = run_parameter_grid_search(
        candles,
        _uptrend_signal,
        window_size=1,
        parameter_combinations=combinations,
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
    )

    assert results[0].report.profit_factor == float("inf")
    assert results[0].robustness_score != float("inf")


def test_handles_empty_parameter_list() -> None:
    candles = _make_uptrend_candles(10)

    results = run_parameter_grid_search(
        candles,
        _uptrend_signal,
        window_size=1,
        parameter_combinations=[],
        strategy_name="xauusd_uptrend",
        strategy_version="1.0.0",
    )

    assert results == []
