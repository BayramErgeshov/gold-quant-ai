"""Swing-specific dynamic position sizing.

Mirrors `src.engines.scalping_engine.position_sizing`'s shape (per
"Lot size must NEVER increase simply because the expected movement is
small" -- the same operating instruction applies to every independent
engine, not just Scalping): only computes an *adjusted*
`risk_per_trade_pct` from swing-specific factors, then delegates the
actual equity/stop-distance sizing formula to
`src.engines.risk_engine.position_sizing.compute_position_size` --
reusing it rather than duplicating the sizing math. Drops the spread
factor scalping applies: swing's much wider ATR-based stop (see
`src.engines.swing_engine.service`) makes the same spread economically
negligible relative to the stop distance, unlike scalping's tight,
spread-sensitive edge.
"""

from __future__ import annotations

from dataclasses import dataclass

_LOW_WIN_RATE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class SwingRiskFactors:
    """Every swing-specific input scaling the baseline risk-per-trade.

    Attributes:
        confidence: The swing signal's own confidence, in [0.0, 1.0] --
            directly scales risk down for lower-confidence signals.
        recent_win_rate: The Swing Engine's own realized win rate over
            its recent trade history, in [0.0, 1.0], or None if there is
            not yet enough swing trade history to measure one.
    """

    confidence: float
    recent_win_rate: float | None


def compute_swing_risk_pct(base_risk_per_trade_pct: float, factors: SwingRiskFactors) -> float:
    """Scale down the baseline risk-per-trade for swing-specific conditions.

    Args:
        base_risk_per_trade_pct: The platform's configured baseline risk
            per trade (RISK_ENGINE.md "Position Sizing").
        factors: Every swing-specific scaling input for this signal.

    Returns:
        An adjusted risk-per-trade percentage, always `<=
        base_risk_per_trade_pct` -- never a fabricated increase.
    """
    scale = max(0.0, min(1.0, factors.confidence))

    if factors.recent_win_rate is not None and factors.recent_win_rate < _LOW_WIN_RATE_THRESHOLD:
        # Linearly taper to zero as the recent win rate approaches 0% -- a
        # recently underperforming Swing Engine trades smaller, never
        # larger, regardless of how confident the current signal looks.
        scale *= factors.recent_win_rate / _LOW_WIN_RATE_THRESHOLD

    return base_risk_per_trade_pct * scale
