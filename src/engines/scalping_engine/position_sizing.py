"""Scalping-specific dynamic position sizing.

Per this platform's operating instructions: "Lot size must NEVER increase
simply because the expected movement is small. Instead implement dynamic
position sizing based on: account equity, maximum allowed risk, historical
performance, current volatility, spread, liquidity, confidence score,
maximum daily drawdown, recent performance of the Scalping Engine."

This module only computes an *adjusted* `risk_per_trade_pct` from those
scalping-specific factors, then delegates the actual equity/stop-distance
sizing formula to `src.engines.risk_engine.position_sizing.
compute_position_size` — reusing it rather than duplicating the sizing
math (CODING_STANDARDS.md "Never duplicate functionality"). The result
can only shrink the baseline risk, never grow it beyond
`base_risk_per_trade_pct`, per "never increase risk after losses" and
"lot size must never increase simply because the expected movement is small."
"""

from __future__ import annotations

from dataclasses import dataclass

_MAX_SPREAD_PENALTY = 0.5  # a maxed-out spread halves the effective risk
_LOW_WIN_RATE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class ScalpingRiskFactors:
    """Every scalping-specific input scaling the baseline risk-per-trade.

    Attributes:
        confidence: The scalping signal's own confidence, in [0.0, 1.0] —
            directly scales risk down for lower-confidence signals.
        spread_points: Current quoted spread.
        max_acceptable_spread_points: Spread at or above which the spread
            penalty is fully applied.
        recent_win_rate: The Scalping Engine's own realized win rate over
            its recent trade history, in [0.0, 1.0], or None if there is
            not yet enough scalping trade history to measure one.
    """

    confidence: float
    spread_points: float
    max_acceptable_spread_points: float
    recent_win_rate: float | None


def compute_scalping_risk_pct(
    base_risk_per_trade_pct: float, factors: ScalpingRiskFactors
) -> float:
    """Scale down the baseline risk-per-trade for scalping-specific conditions.

    Args:
        base_risk_per_trade_pct: The platform's configured baseline risk
            per trade (RISK_ENGINE.md "Position Sizing").
        factors: Every scalping-specific scaling input for this signal.

    Returns:
        An adjusted risk-per-trade percentage, always `<=
        base_risk_per_trade_pct` — never a fabricated increase.
    """
    scale = max(0.0, min(1.0, factors.confidence))

    if factors.max_acceptable_spread_points > 0:
        spread_ratio = min(1.0, factors.spread_points / factors.max_acceptable_spread_points)
        scale *= 1.0 - spread_ratio * _MAX_SPREAD_PENALTY

    if factors.recent_win_rate is not None and factors.recent_win_rate < _LOW_WIN_RATE_THRESHOLD:
        # Linearly taper to zero as the recent win rate approaches 0% —
        # a recently underperforming Scalping Engine trades smaller, never
        # larger, regardless of how confident the current signal looks.
        scale *= factors.recent_win_rate / _LOW_WIN_RATE_THRESHOLD

    return base_risk_per_trade_pct * scale
