"""Unit tests for trading performance statistics."""

from __future__ import annotations

import math

import pytest

from src.engines.statistics_engine.performance import (
    average_loss_pct,
    average_win_pct,
    calmar_ratio,
    expectancy_pct,
    max_consecutive_losses,
    max_consecutive_wins,
    max_drawdown_pct,
    profit_factor,
    recovery_factor,
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


def test_average_win_pct_is_zero_with_no_wins() -> None:
    assert average_win_pct([-1.0, -2.0]) == 0.0


def test_average_win_pct_averages_only_positive_returns() -> None:
    assert average_win_pct([2.0, -1.0, 4.0]) == pytest.approx(3.0)


def test_average_loss_pct_is_zero_with_no_losses() -> None:
    assert average_loss_pct([1.0, 2.0]) == 0.0


def test_average_loss_pct_averages_only_negative_returns_as_a_positive_magnitude() -> None:
    assert average_loss_pct([2.0, -1.0, -3.0]) == pytest.approx(2.0)


def test_max_consecutive_wins_finds_the_longest_streak() -> None:
    assert max_consecutive_wins([1.0, 1.0, -1.0, 1.0, 1.0, 1.0, -1.0]) == 3


def test_max_consecutive_wins_is_zero_with_no_wins() -> None:
    assert max_consecutive_wins([-1.0, -2.0]) == 0


def test_max_consecutive_losses_finds_the_longest_streak() -> None:
    assert max_consecutive_losses([1.0, -1.0, -1.0, -1.0, 1.0, -1.0]) == 3


def test_max_consecutive_losses_is_zero_with_no_losses() -> None:
    assert max_consecutive_losses([1.0, 2.0]) == 0


def test_calmar_ratio_is_zero_without_drawdown() -> None:
    assert calmar_ratio(total_return_pct=20.0, max_drawdown_pct=0.0, days_covered=180) == 0.0


def test_calmar_ratio_is_zero_without_a_covered_period() -> None:
    assert calmar_ratio(total_return_pct=20.0, max_drawdown_pct=5.0, days_covered=0.0) == 0.0


def test_calmar_ratio_annualizes_over_the_actual_period() -> None:
    # 20% return over half a year (~182.6 days) annualizes to ~40%;
    # divided by a 10% max drawdown gives a Calmar ratio of ~4.0.
    result = calmar_ratio(total_return_pct=20.0, max_drawdown_pct=10.0, days_covered=182.625)

    assert result == pytest.approx(4.0, rel=0.01)


def test_recovery_factor_is_zero_without_drawdown() -> None:
    assert recovery_factor(net_profit=500.0, max_drawdown=0.0) == 0.0


def test_recovery_factor_divides_net_profit_by_drawdown() -> None:
    assert recovery_factor(net_profit=500.0, max_drawdown=250.0) == pytest.approx(2.0)
