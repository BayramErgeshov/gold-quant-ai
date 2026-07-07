"""Exposure and portfolio-risk limit checks for the Risk Engine.

Per RISK_ENGINE.md "Exposure Control": tracks total/instrument/correlated/
session/daily exposure against configurable maximum limits. Aggregating
live open positions into an `ExposureState` is the Execution Engine's
responsibility (a later roadmap phase); this module only evaluates
whether a proposed trade would breach configured limits.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExposureLimits:
    """Configured maximum exposure percentages (of account equity).

    Attributes:
        max_total_exposure_pct: Maximum total exposure across all instruments.
        max_instrument_exposure_pct: Maximum exposure to a single instrument.
        max_correlated_exposure_pct: Maximum combined exposure across
            instruments correlated with the proposed trade.
        max_session_exposure_pct: Maximum exposure opened within the current session.
        max_daily_exposure_pct: Maximum exposure opened within the current day.
    """

    max_total_exposure_pct: float
    max_instrument_exposure_pct: float
    max_correlated_exposure_pct: float
    max_session_exposure_pct: float
    max_daily_exposure_pct: float


@dataclass(frozen=True, slots=True)
class ExposureState:
    """Current exposure levels before adding a proposed trade."""

    total_exposure_pct: float = 0.0
    instrument_exposure_pct: float = 0.0
    correlated_exposure_pct: float = 0.0
    session_exposure_pct: float = 0.0
    daily_exposure_pct: float = 0.0


def check_exposure_limits(
    state: ExposureState, new_trade_exposure_pct: float, limits: ExposureLimits
) -> list[str]:
    """Check whether adding a proposed trade would breach any exposure limit.

    Args:
        state: Current exposure levels before the proposed trade.
        new_trade_exposure_pct: Exposure the proposed trade would add.
        limits: Configured maximum exposure percentages.

    Returns:
        A list of human-readable breach reasons. Empty if every limit
        would still be respected after adding the trade.
    """
    checks = (
        ("total", state.total_exposure_pct, limits.max_total_exposure_pct),
        ("instrument", state.instrument_exposure_pct, limits.max_instrument_exposure_pct),
        ("correlated", state.correlated_exposure_pct, limits.max_correlated_exposure_pct),
        ("session", state.session_exposure_pct, limits.max_session_exposure_pct),
        ("daily", state.daily_exposure_pct, limits.max_daily_exposure_pct),
    )
    reasons = []
    for name, current, max_allowed in checks:
        projected = current + new_trade_exposure_pct
        if projected > max_allowed:
            reasons.append(
                f"{name}_exposure_exceeded: projected {projected:.2f}% > max {max_allowed:.2f}%"
            )
    return reasons
