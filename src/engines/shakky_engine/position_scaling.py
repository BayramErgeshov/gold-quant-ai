"""Position Scaling for Shakky (Classic M5 Strategy Engine).

Adds volume to an already-open Shakky position when the move has grown
even stronger -- per the user's own requirement, this must never average
a losing position. Every gate below is a hard requirement; all must pass
(`should_scale=False` otherwise), which structurally makes averaging a
loser impossible rather than merely discouraged.

Deliberately fully deterministic, like the rest of
`src.engines.shakky_engine`. Reuses the existing portfolio exposure
check (`src.engines.risk_engine.exposure.check_exposure_limits`) rather
than a second, parallel risk-limit implementation -- the caller computes
the breach list for the proposed additional volume and passes it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.engines.shakky_engine.trend_confidence import Direction

# A trivial wobble in the score should not count as "Trend Confidence
# increased" -- only a real, meaningful improvement qualifies.
_MIN_TREND_CONFIDENCE_INCREASE = 5.0

DEFAULT_SCALE_FRACTION = 0.5


@dataclass(frozen=True, slots=True)
class ScalingDecision:
    """Whether to add volume to an already-open Shakky position this cycle.

    Attributes:
        should_scale: Whether to place an additional order this cycle.
        additional_volume: The volume to add, only set when `should_scale`.
        reasons: Every gate's own pass/fail reason, human-readable.
    """

    should_scale: bool
    additional_volume: float | None
    reasons: list[str] = field(default_factory=list)


def evaluate_scaling(
    *,
    direction: Direction,
    entry_price: float,
    current_price: float,
    entry_trend_confidence_score: float,
    current_trend_confidence_score: float,
    market_structure_valid: bool,
    exposure_breach_reasons: list[str],
    base_volume: float,
    scale_fraction: float = DEFAULT_SCALE_FRACTION,
) -> ScalingDecision:
    """Decide whether to add volume to an already-open Shakky position.

    Args:
        direction: The open position's own direction.
        entry_price: The position's original entry price.
        current_price: The position's current market price.
        entry_trend_confidence_score: Trend Confidence score recorded at
            entry (`Trade.entry_trend_confidence_score`).
        current_trend_confidence_score: This cycle's fresh
            `assess_trend_confidence().score`.
        market_structure_valid: Whether market structure still supports
            `direction` this cycle (the caller passes `not
            HoldAssessment.reversal_expected`).
        exposure_breach_reasons: Output of
            `src.engines.risk_engine.exposure.check_exposure_limits` for
            the proposed additional volume -- empty means risk remains
            acceptable.
        base_volume: The position's current open volume, used to size the add-on.
        scale_fraction: Fraction of `base_volume` to add when every gate passes.

    Returns:
        A `ScalingDecision`. `should_scale` is True only if every gate
        (profitable, Trend Confidence increased, structure still valid,
        exposure still acceptable) passes.
    """
    reasons: list[str] = []

    is_profitable = (
        current_price > entry_price if direction == "buy" else current_price < entry_price
    )
    if not is_profitable:
        reasons.append("gate_failed:position_not_yet_profitable")

    confidence_increased = (
        current_trend_confidence_score
        >= entry_trend_confidence_score + _MIN_TREND_CONFIDENCE_INCREASE
    )
    if not confidence_increased:
        reasons.append("gate_failed:trend_confidence_has_not_increased")

    if not market_structure_valid:
        reasons.append("gate_failed:market_structure_no_longer_valid")

    if exposure_breach_reasons:
        reasons.extend(f"gate_failed:{reason}" for reason in exposure_breach_reasons)

    should_scale = not reasons
    if should_scale:
        reasons.append("all_gates_passed")

    return ScalingDecision(
        should_scale=should_scale,
        additional_volume=base_volume * scale_fraction if should_scale else None,
        reasons=reasons,
    )
