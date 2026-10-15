"""Unit tests for Market Correlation Engine statistical functions."""

from __future__ import annotations

import math
import random

import pytest

from src.engines.correlation_engine.statistics import (
    cointegration_test,
    lead_lag_correlation,
    log_returns,
    rolling_correlation,
    volatility_transmission,
)

pytestmark = pytest.mark.unit


def test_log_returns_computes_expected_values() -> None:
    returns = log_returns([100.0, 110.0, 99.0])

    assert returns == pytest.approx([math.log(1.1), math.log(99.0 / 110.0)])


def test_log_returns_skips_non_positive_prices() -> None:
    returns = log_returns([100.0, 0.0, 110.0])

    assert returns == []


def test_log_returns_empty_with_fewer_than_two_prices() -> None:
    assert log_returns([100.0]) == []
    assert log_returns([]) == []


def test_rolling_correlation_perfectly_correlated_series() -> None:
    series_a = [float(i) for i in range(50)]
    series_b = [float(i) * 2 + 1 for i in range(50)]

    result = rolling_correlation(series_a, series_b)

    assert result.correlation == pytest.approx(1.0, abs=1e-9)
    assert result.sample_size == 50


def test_rolling_correlation_inversely_correlated_series() -> None:
    series_a = [float(i) for i in range(50)]
    series_b = [-float(i) for i in range(50)]

    result = rolling_correlation(series_a, series_b)

    assert result.correlation == pytest.approx(-1.0, abs=1e-9)


def test_rolling_correlation_returns_zero_with_too_few_samples() -> None:
    result = rolling_correlation([1.0, 2.0], [1.0, 2.0])

    assert result.correlation == 0.0
    assert result.sample_size == 0


def test_rolling_correlation_returns_zero_when_series_has_no_variance() -> None:
    result = rolling_correlation([1.0] * 20, [float(i) for i in range(20)])

    assert result.correlation == 0.0
    assert result.sample_size == 0


def test_rolling_correlation_returns_zero_when_a_series_contains_nan() -> None:
    # A corrupted upstream value (NaN) still has nonzero np.std, so this
    # exercises the correlation-result NaN guard specifically, not the
    # zero-variance guard above it.
    corrupted = [float(i) for i in range(20)]
    corrupted[5] = math.nan

    result = rolling_correlation(corrupted, [float(i) for i in range(20)])

    assert result.correlation == 0.0
    assert result.sample_size == 0


def test_lead_lag_correlation_detects_a_leading_series() -> None:
    random.seed(42)
    base = [random.gauss(0, 1) for _ in range(200)]
    # series_b[t] = base[t + lag]: series_b's value `lag` bars ago equals
    # series_a's value now, i.e. series_b leads series_a by `lag` bars.
    lag = 3
    series_a = base[: len(base) - lag]
    series_b = base[lag:]

    result = lead_lag_correlation(series_a, series_b, max_lag=10)

    assert result.best_lag == lag
    assert result.correlation_at_best_lag == pytest.approx(1.0, abs=1e-9)


def test_lead_lag_correlation_defaults_to_zero_lag_with_no_relationship() -> None:
    random.seed(7)
    series_a = [random.gauss(0, 1) for _ in range(100)]
    series_b = [random.gauss(0, 1) for _ in range(100)]

    result = lead_lag_correlation(series_a, series_b, max_lag=5)

    assert -5 <= result.best_lag <= 5
    assert abs(result.correlation_at_best_lag) <= 1.0


def test_cointegration_test_returns_none_with_too_little_history() -> None:
    assert cointegration_test([1.0, 2.0], [1.0, 2.0]) is None


def test_cointegration_test_detects_cointegrated_series() -> None:
    random.seed(1)
    base = [100.0]
    for _ in range(199):
        base.append(base[-1] + random.gauss(0, 1))
    series_a = base
    series_b = [value * 2 + random.gauss(0, 0.5) for value in base]

    result = cointegration_test(series_a, series_b)

    assert result is not None
    assert result.sample_size == 200
    assert result.is_cointegrated is True
    assert result.p_value < 0.05


def test_cointegration_test_respects_a_stricter_significance_level() -> None:
    random.seed(1)
    base = [100.0]
    for _ in range(199):
        base.append(base[-1] + random.gauss(0, 1))
    series_a = base
    series_b = [value * 2 + random.gauss(0, 0.5) for value in base]

    lenient = cointegration_test(series_a, series_b, significance_level=0.05)
    strict = cointegration_test(series_a, series_b, significance_level=1e-30)

    assert lenient is not None
    assert strict is not None
    assert lenient.p_value == strict.p_value  # same underlying test statistic
    assert lenient.is_cointegrated is True
    # An unreasonably strict (Bonferroni-corrected-to-the-extreme) level
    # must be able to flip the same p-value to "not cointegrated".
    assert strict.is_cointegrated is False


def test_volatility_transmission_uses_absolute_returns() -> None:
    returns_a = [0.01, -0.02, 0.03, -0.01, 0.02] * 10
    returns_b = [0.02, -0.04, 0.06, -0.02, 0.04] * 10

    result = volatility_transmission(returns_a, returns_b, max_lag=2)

    assert result.correlation_at_best_lag == pytest.approx(1.0, abs=1e-9)
