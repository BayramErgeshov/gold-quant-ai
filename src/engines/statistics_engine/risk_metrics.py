"""Distribution-based risk metrics for the Statistics Engine.

Per MACHINE_LEARNING_ENGINE.md "Performance Metrics" and RISK_ENGINE.md
(Phase 11): these functions only *measure* realized/historical risk from a
return series — they never gate or approve a trade. Operational risk
controls (exposure limits, position sizing, trade approval) belong to the
dedicated Risk Engine (Phase 11), which consumes these measurements.
"""

from __future__ import annotations


def historical_value_at_risk_pct(
    returns_pct: list[float], *, confidence_level: float = 0.95
) -> float:
    """Historical-simulation Value at Risk.

    Args:
        returns_pct: Historical returns per period, in percent.
        confidence_level: VaR confidence level, e.g. 0.95 for 95% VaR.

    Returns:
        The loss magnitude (a positive percentage) not expected to be
        exceeded at `confidence_level`, using the empirical return
        distribution. 0.0 if `returns_pct` is empty.

    Raises:
        ValueError: If `confidence_level` is not strictly between 0.0 and 1.0.
    """
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be strictly between 0.0 and 1.0")
    if not returns_pct:
        return 0.0

    sorted_returns = sorted(returns_pct)
    index = min(int((1.0 - confidence_level) * len(sorted_returns)), len(sorted_returns) - 1)
    return max(0.0, -sorted_returns[index])


def r_multiple(realized_pct: float, risk_pct: float) -> float:
    """Express a realized return as a multiple of the risk taken (an "R-multiple").

    Args:
        realized_pct: Realized return, in percent (may be negative).
        risk_pct: The planned risk (distance to stop loss), in percent —
            a positive magnitude.

    Returns:
        `realized_pct / risk_pct`. 0.0 if `risk_pct` is 0 — never a
        fabricated infinite multiple from a zero-risk trade.
    """
    if risk_pct == 0:
        return 0.0
    return realized_pct / risk_pct


def average_r_multiple(realized_pcts: list[float], risk_pcts: list[float]) -> float:
    """Average R-multiple across a sequence of trades.

    Args:
        realized_pcts: Realized return per trade, in percent.
        risk_pcts: Planned risk per trade, in percent (same order/length as `realized_pcts`).

    Returns:
        The mean R-multiple. 0.0 if the lists are empty.

    Raises:
        ValueError: If the two lists have different lengths.
    """
    if len(realized_pcts) != len(risk_pcts):
        raise ValueError("realized_pcts and risk_pcts must be the same length")
    if not realized_pcts:
        return 0.0

    multiples = [
        r_multiple(realized, risk) for realized, risk in zip(realized_pcts, risk_pcts, strict=True)
    ]
    return sum(multiples) / len(multiples)
