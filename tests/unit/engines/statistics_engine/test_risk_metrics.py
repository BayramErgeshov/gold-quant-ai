"""Unit tests for distribution-based risk metrics."""

from __future__ import annotations

import pytest

from src.engines.statistics_engine.risk_metrics import (
    average_r_multiple,
    historical_value_at_risk_pct,
    r_multiple,
)

pytestmark = pytest.mark.unit


def test_var_is_zero_for_empty_returns() -> None:
    assert historical_value_at_risk_pct([]) == 0.0


def test_var_raises_for_invalid_confidence_level() -> None:
    with pytest.raises(ValueError, match="confidence_level"):
        historical_value_at_risk_pct([1.0, 2.0], confidence_level=1.0)


def test_var_computes_empirical_tail_loss() -> None:
    returns = [float(value) for value in range(-10, 90)]  # 100 values, -10..89

    var_95 = historical_value_at_risk_pct(returns, confidence_level=0.95)

    assert var_95 == pytest.approx(5.0)


def test_var_is_zero_when_no_losses_exceed_the_threshold() -> None:
    assert historical_value_at_risk_pct([1.0, 2.0, 3.0], confidence_level=0.95) == 0.0


def test_r_multiple_is_zero_for_zero_risk() -> None:
    assert r_multiple(5.0, 0.0) == 0.0


def test_r_multiple_computes_ratio() -> None:
    assert r_multiple(4.0, 2.0) == pytest.approx(2.0)


def test_average_r_multiple_is_zero_for_no_trades() -> None:
    assert average_r_multiple([], []) == 0.0


def test_average_r_multiple_raises_for_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        average_r_multiple([1.0], [1.0, 2.0])


def test_average_r_multiple_computes_mean() -> None:
    result = average_r_multiple([4.0, -1.0], [2.0, 1.0])

    assert result == pytest.approx((2.0 + -1.0) / 2)
