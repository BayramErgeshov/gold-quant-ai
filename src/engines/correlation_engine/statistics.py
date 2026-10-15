"""Pure statistical functions for the Market Correlation Engine.

Per the platform's operating instructions: "Do NOT use fixed
correlations... Continuously calculate: rolling correlations, lead-lag
relationships, regime-dependent correlations, volatility transmission,
cointegration, dynamic feature importance." Every function here recomputes
its result from whatever price history it is given — nothing is a
hardcoded constant, and every result carries a sample size so a caller
can judge how much to trust it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.stattools import coint

_MIN_SAMPLES_FOR_CORRELATION = 10
# Cointegration is a claim about a long-run equilibrium relationship, not
# a short-term co-movement -- 30 observations (the generic CLT-style
# floor used elsewhere in this codebase) is too short to distinguish a
# real long-run relationship from noise. 100 is a still-conservative
# middle ground (an institutional audit finding); raising it further is a
# documented future improvement, not a claim that 100 is definitively
# sufficient.
_MIN_SAMPLES_FOR_COINTEGRATION = 100


def log_returns(closes: list[float]) -> list[float]:
    """Compute log returns from a series of closing prices.

    Args:
        closes: Prices ordered oldest first.

    Returns:
        `len(closes) - 1` log returns. Empty if fewer than 2 closes, or
        if any adjacent pair straddles a non-positive price (never a
        fabricated return from an invalid price).
    """
    returns: list[float] = []
    for previous, current in zip(closes, closes[1:], strict=False):
        if previous <= 0 or current <= 0:
            continue
        returns.append(math.log(current / previous))
    return returns


@dataclass(frozen=True, slots=True)
class RollingCorrelationResult:
    """A single rolling-window Pearson correlation measurement.

    Attributes:
        correlation: Pearson correlation coefficient, in [-1.0, 1.0].
        sample_size: Number of paired observations the correlation was
            computed over.
    """

    correlation: float
    sample_size: int


def rolling_correlation(series_a: list[float], series_b: list[float]) -> RollingCorrelationResult:
    """Compute Pearson correlation between two equal-length series.

    Args:
        series_a: First series (e.g. XAUUSD log returns).
        series_b: Second series (e.g. a correlated instrument's log returns),
            already aligned index-for-index with `series_a`.

    Returns:
        A `RollingCorrelationResult`. `correlation=0.0, sample_size=0` if
        there are too few paired observations or either series has zero
        variance — never a fabricated non-zero correlation.
    """
    n = min(len(series_a), len(series_b))
    if n < _MIN_SAMPLES_FOR_CORRELATION:
        return RollingCorrelationResult(correlation=0.0, sample_size=0)

    a = np.asarray(series_a[-n:], dtype=float)
    b = np.asarray(series_b[-n:], dtype=float)
    if np.std(a) == 0 or np.std(b) == 0:
        return RollingCorrelationResult(correlation=0.0, sample_size=0)

    correlation = float(np.corrcoef(a, b)[0, 1])
    if math.isnan(correlation):
        return RollingCorrelationResult(correlation=0.0, sample_size=0)
    return RollingCorrelationResult(correlation=correlation, sample_size=n)


@dataclass(frozen=True, slots=True)
class LeadLagResult:
    """The lag that maximizes correlation between two series.

    Attributes:
        best_lag: Number of bars `series_b` leads `series_a` by. Positive
            means `series_b`'s past values correlate best with
            `series_a`'s current values (`series_b` leads/predicts);
            negative means `series_b` lags `series_a`; zero means they
            move together contemporaneously.
        correlation_at_best_lag: The correlation at `best_lag`.
        sample_size: Paired observations used at `best_lag`.
    """

    best_lag: int
    correlation_at_best_lag: float
    sample_size: int


def lead_lag_correlation(
    series_a: list[float], series_b: list[float], *, max_lag: int = 10
) -> LeadLagResult:
    """Find the lag (in bars) that maximizes |correlation| between two series.

    Args:
        series_a: Reference series (e.g. XAUUSD log returns), oldest first.
        series_b: Candidate leading/lagging series, oldest first, aligned
            index-for-index with `series_a` at lag zero.
        max_lag: Largest lag magnitude to test in either direction.

    Returns:
        A `LeadLagResult` for the lag with the strongest |correlation|.
        Defaults to `best_lag=0` if every lag has too little data.
    """
    best = LeadLagResult(best_lag=0, correlation_at_best_lag=0.0, sample_size=0)
    for lag in range(-max_lag, max_lag + 1):
        if lag > 0:
            # series_b's past (shifted forward) vs series_a's present.
            shifted_a, shifted_b = series_a[lag:], series_b[: len(series_b) - lag]
        elif lag < 0:
            shifted_a, shifted_b = series_a[: len(series_a) + lag], series_b[-lag:]
        else:
            shifted_a, shifted_b = series_a, series_b

        result = rolling_correlation(shifted_a, shifted_b)
        if abs(result.correlation) > abs(best.correlation_at_best_lag):
            best = LeadLagResult(
                best_lag=lag,
                correlation_at_best_lag=result.correlation,
                sample_size=result.sample_size,
            )
    return best


@dataclass(frozen=True, slots=True)
class CointegrationResult:
    """Engle-Granger cointegration test result between two price series.

    Attributes:
        is_cointegrated: Whether the null hypothesis of no cointegration
            is rejected at the 5% level.
        p_value: The test's p-value; lower means stronger evidence of a
            stable long-run relationship.
        sample_size: Number of price observations used.
    """

    is_cointegrated: bool
    p_value: float
    sample_size: int


_COINTEGRATION_SIGNIFICANCE_LEVEL = 0.05


def cointegration_test(
    prices_a: list[float],
    prices_b: list[float],
    *,
    significance_level: float = _COINTEGRATION_SIGNIFICANCE_LEVEL,
) -> CointegrationResult | None:
    """Run the Engle-Granger cointegration test between two price levels.

    Args:
        prices_a: First instrument's price level series (not returns).
        prices_b: Second instrument's price level series, aligned
            index-for-index with `prices_a`.
        significance_level: The p-value threshold for rejecting the null
            hypothesis of no cointegration. Defaults to the conventional
            5%; a caller testing many instruments in the same cycle
            (`src.engines.correlation_engine.analysis`) should pass a
            Bonferroni-corrected level (`0.05 / n_instruments`) instead —
            testing 16 instruments at a fixed 5% each gives a combined
            false-positive rate of `1 - 0.95**16 ≈ 56%`, not 5%.

    Returns:
        A `CointegrationResult`, or None if there are too few paired
        observations to run the test meaningfully — never a fabricated
        result from insufficient data.
    """
    n = min(len(prices_a), len(prices_b))
    if n < _MIN_SAMPLES_FOR_COINTEGRATION:
        return None

    a = np.asarray(prices_a[-n:], dtype=float)
    b = np.asarray(prices_b[-n:], dtype=float)
    _, p_value, _ = coint(a, b)
    return CointegrationResult(
        is_cointegrated=bool(p_value < significance_level),
        p_value=float(p_value),
        sample_size=n,
    )


def volatility_transmission(
    returns_a: list[float], returns_b: list[float], *, max_lag: int = 10
) -> LeadLagResult:
    """Measure lead-lag correlation of realized volatility (|returns|).

    A high correlation of absolute returns at a non-zero lag suggests
    volatility in one market tends to precede volatility in the other,
    independent of direction.

    Args:
        returns_a: Reference series' log returns.
        returns_b: Candidate series' log returns, aligned with `returns_a`.
        max_lag: Largest lag magnitude to test in either direction.

    Returns:
        A `LeadLagResult` computed over `abs()` of each return series.
    """
    return lead_lag_correlation(
        [abs(value) for value in returns_a], [abs(value) for value in returns_b], max_lag=max_lag
    )
