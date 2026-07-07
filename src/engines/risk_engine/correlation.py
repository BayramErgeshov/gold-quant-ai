"""Correlation-based concentration control for the Risk Engine.

Per RISK_ENGINE.md "Correlation Control": detect excessive concentration
across correlated instruments (Gold, Silver, DXY, US10Y, VIX, S&P500,
NASDAQ, Oil, Copper) rather than treating every instrument's exposure as
independent.
"""

from __future__ import annotations


def compute_correlated_exposure_pct(
    open_exposure_by_instrument: dict[str, float], correlations: dict[str, float]
) -> float:
    """Compute the correlation-weighted exposure across related instruments.

    Args:
        open_exposure_by_instrument: Current exposure percentage per
            instrument, keyed by instrument name.
        correlations: Correlation coefficient (-1.0 to 1.0) of each
            instrument to the proposed trade's instrument, keyed by the
            same instrument names. Instruments missing a correlation entry
            are treated as uncorrelated (0.0) rather than assumed risky.

    Returns:
        Sum of `exposure * abs(correlation)` across every instrument —
        high absolute correlation (long or short) still represents
        concentrated risk.
    """
    return sum(
        exposure * abs(correlations.get(instrument, 0.0))
        for instrument, exposure in open_exposure_by_instrument.items()
    )


def is_concentration_excessive(
    open_exposure_by_instrument: dict[str, float],
    correlations: dict[str, float],
    *,
    max_correlated_exposure_pct: float,
) -> bool:
    """Check whether correlated exposure exceeds the configured maximum.

    Args:
        open_exposure_by_instrument: Current exposure percentage per instrument.
        correlations: Each instrument's correlation to the proposed trade's instrument.
        max_correlated_exposure_pct: Maximum allowed correlation-weighted exposure.

    Returns:
        True if the correlation-weighted exposure exceeds the maximum.
    """
    return (
        compute_correlated_exposure_pct(open_exposure_by_instrument, correlations)
        > max_correlated_exposure_pct
    )
