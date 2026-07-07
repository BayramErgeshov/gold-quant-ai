"""Unit tests for trading performance statistics."""

from __future__ import annotations

import math

import pytest

from src.engines.statistics_engine.performance import (
    expectancy_pct,
    max_drawdown_pct,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)

pytestmark = pytest.mark.unit


def test_win_rate_is_zero_for_no_trades() -> None:
    assert win_rate([]) == 0.0


def test_win_rate_computes_fraction_of_positive_returns() -> None:
    assert win_rate([1.0, -1.0, 2.0, -0.5]) == pytest.approx(0.5)


def test_profit_factor_is_zero_for_no_trades() -> None:
    assert profit_factor([]) == 0.0


def test_profit_factor_is_infinite_when_no_losses() -> None:
    assert profit_factor([1.0, 2.0]) == math.inf


def test_profit_factor_is_zero_when_no_wins() -> None:
    assert profit_factor([-1.0, -2.0]) == 0.0


def test_profit_factor_computes_gross_ratio() -> None:
    assert profit_factor([4.0, -2.0]) == pytest.approx(2.0)


def test_expectancy_is_zero_for_no_trades() -> None:
    assert expectancy_pct([]) == 0.0


def test_expectancy_computes_mean_return() -> None:
    assert expectancy_pct([1.0, 2.0, 3.0]) == pytest.approx(2.0)


def test_sharpe_ratio_is_zero_for_insufficient_data() -> None:
    assert sharpe_ratio([1.0]) == 0.0


def test_sharpe_ratio_is_zero_for_constant_returns() -> None:
    assert sharpe_ratio([1.0, 1.0, 1.0]) == 0.0


def test_sharpe_ratio_is_positive_for_consistently_positive_returns() -> None:
    assert sharpe_ratio([1.0, 2.0, 1.5, 1.8, 1.2]) > 0


def test_sortino_ratio_is_zero_for_insufficient_data() -> None:
    assert sortino_ratio([1.0]) == 0.0


def test_sortino_ratio_is_zero_when_no_downside() -> None:
    assert sortino_ratio([1.0, 2.0, 3.0]) == 0.0


def test_sortino_ratio_is_positive_for_positive_mean_with_downside() -> None:
    assert sortino_ratio([2.0, -1.0, 3.0, -0.5]) > 0


def test_max_drawdown_is_zero_for_insufficient_data() -> None:
    assert max_drawdown_pct([100.0]) == 0.0


def test_max_drawdown_is_zero_for_monotonic_growth() -> None:
    assert max_drawdown_pct([100.0, 110.0, 120.0]) == 0.0


def test_max_drawdown_computes_peak_to_trough_decline() -> None:
    equity_curve = [100.0, 120.0, 90.0, 130.0, 65.0]

    # Worst decline: peak 130 -> trough 65 = 50%.
    assert max_drawdown_pct(equity_curve) == pytest.approx(50.0)
