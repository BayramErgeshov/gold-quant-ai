"""Unit tests for `src.utils.statistics`."""

from __future__ import annotations

import pytest

from src.utils.statistics import (
    forward_return_pct,
    linear_regression_slope_pct,
    log_return_stddev_pct,
)

pytestmark = pytest.mark.unit


def test_linear_regression_slope_pct_zero_for_too_few_values() -> None:
    assert linear_regression_slope_pct([100.0]) == 0.0
    assert linear_regression_slope_pct([]) == 0.0


def test_linear_regression_slope_pct_zero_for_zero_average() -> None:
    assert linear_regression_slope_pct([0.0, 0.0, 0.0]) == 0.0


def test_linear_regression_slope_pct_positive_for_uptrend() -> None:
    values = [100.0 + index * 2 for index in range(10)]

    assert linear_regression_slope_pct(values) > 0


def test_linear_regression_slope_pct_negative_for_downtrend() -> None:
    values = [100.0 - index * 2 for index in range(10)]

    assert linear_regression_slope_pct(values) < 0


def test_linear_regression_slope_pct_zero_for_flat_series() -> None:
    values = [100.0] * 10

    assert linear_regression_slope_pct(values) == pytest.approx(0.0)


def test_log_return_stddev_pct_zero_for_too_few_returns() -> None:
    assert log_return_stddev_pct([100.0]) == 0.0
    assert log_return_stddev_pct([100.0, 105.0]) == 0.0


def test_log_return_stddev_pct_zero_for_constant_series() -> None:
    values = [100.0] * 10

    assert log_return_stddev_pct(values) == pytest.approx(0.0)


def test_log_return_stddev_pct_positive_for_volatile_series() -> None:
    values = [100.0, 110.0, 90.0, 115.0, 85.0]

    assert log_return_stddev_pct(values) > 0


def test_forward_return_pct_computes_percentage_change() -> None:
    assert forward_return_pct(100.0, 110.0) == pytest.approx(10.0)
    assert forward_return_pct(100.0, 90.0) == pytest.approx(-10.0)


def test_forward_return_pct_zero_for_zero_entry_price() -> None:
    assert forward_return_pct(0.0, 100.0) == 0.0


def test_log_return_stddev_pct_skips_non_positive_values() -> None:
    # A zero in the middle must not raise (math domain error on log(0/x)
    # or division by zero); the surrounding valid pairs are still used.
    values = [100.0, 0.0, 105.0, 110.0]

    result = log_return_stddev_pct(values)

    assert result >= 0.0
