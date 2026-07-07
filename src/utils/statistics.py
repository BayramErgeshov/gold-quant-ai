"""Generic numerical helpers shared across engines that analyze price series.

Kept in one place (rather than duplicated per engine) per CODING_STANDARDS.md
("Never duplicate functionality"). Used by both the Historical Research
Engine's regime classifier and the Technical Department's Trend Agent.
"""

from __future__ import annotations

import math

_MIN_OBSERVATIONS_FOR_STDDEV = 2


def linear_regression_slope_pct(values: list[float]) -> float:
    """Slope of a least-squares fit line through `values`, as %/step of their average.

    Args:
        values: A time-ordered series (e.g. closing prices).

    Returns:
        The regression slope normalized by the series average, as a
        percentage. 0.0 if fewer than 2 values or the average is 0.
    """
    n = len(values)
    if n < _MIN_OBSERVATIONS_FOR_STDDEV:
        return 0.0

    average = sum(values) / n
    if average == 0:
        return 0.0

    x_mean = (n - 1) / 2
    y_mean = average
    numerator = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
    denominator = sum((index - x_mean) ** 2 for index in range(n))
    if denominator == 0:  # pragma: no cover - unreachable: always > 0 for n >= 2
        return 0.0

    slope = numerator / denominator
    return (slope / average) * 100


def log_return_stddev_pct(values: list[float]) -> float:
    """Sample standard deviation of period-over-period log returns, as a percentage.

    Args:
        values: A time-ordered series of strictly positive values (e.g.
            closing prices). Non-positive consecutive pairs are skipped
            rather than raising, since a single bad data point should not
            abort the whole calculation.

    Returns:
        The stddev of log returns, as a percentage. 0.0 if fewer than 2
        valid return observations are available.
    """
    returns = [
        math.log(values[index] / values[index - 1])
        for index in range(1, len(values))
        if values[index - 1] > 0 and values[index] > 0
    ]
    if len(returns) < _MIN_OBSERVATIONS_FOR_STDDEV:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * 100
