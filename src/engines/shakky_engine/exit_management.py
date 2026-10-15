"""Dynamic Take Profit for Shakky (Classic M5 Strategy Engine).

Replaces the fixed take-profit exit with a trailing target for trades
that entered on a `strong`/`exceptional` Trend Confidence reading (see
`trend_confidence.py`) -- per the user's own analysis, the edge is in
letting a genuinely large move run instead of capping it at a fixed
level. Trades that entered on a `minor`/`normal` reading are untouched:
`evaluate_exit` returns `"hold"` immediately for them, so today's fixed
support/resistance-or-2R target still governs -- this module is an
additional mode, not a replacement of the existing one ("improve it,
don't replace its architecture").

Deliberately fully deterministic, like the rest of
`src.engines.shakky_engine`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.engines.shakky_engine.hold_manager import HoldAssessment
from src.engines.shakky_engine.trend_confidence import (
    Direction,
    TrendConfidenceAssessment,
    TrendConfidenceLevel,
)

ExitAction = Literal["hold", "extend_tp", "close_full", "close_partial"]

# Each extension step reaches this many multiples of the trade's
# original risk distance beyond the *current* price -- the target keeps
# moving out ahead of price as long as continuation is expected, rather
# than being set once and left behind.
_EXTENSION_RISK_MULTIPLE = 1.0

# An opposing candlestick signal while Trend Confidence is still
# strong/exceptional is treated as an early warning, not proof the move
# is over -- de-risk by taking half off rather than abandoning a trade
# the broader trend measure still rates highly.
_PARTIAL_CLOSE_FRACTION = 0.5

_STRONG_LEVELS: frozenset[TrendConfidenceLevel] = frozenset({"strong", "exceptional"})


@dataclass(frozen=True, slots=True)
class ExitDecision:
    """What to do with an open Shakky position this cycle, and why.

    Attributes:
        action: "hold" (no change), "extend_tp" (move the target further
            out), "close_partial" (de-risk on an early warning),
            or "close_full" (trend confirmed exhausted).
        new_take_profit: The new target price, only set for "extend_tp".
        close_volume: Volume to close, only set for "close_partial"/"close_full".
        reasons: Every contributing signal, human-readable.
    """

    action: ExitAction
    new_take_profit: float | None
    close_volume: float | None
    reasons: list[str] = field(default_factory=list)


def _extended_target(direction: Direction, current_price: float, risk_distance: float) -> float:
    distance = risk_distance * _EXTENSION_RISK_MULTIPLE
    return current_price + distance if direction == "buy" else current_price - distance


def evaluate_exit(
    *,
    direction: Direction,
    entry_trend_confidence_level: TrendConfidenceLevel,
    trend_confidence: TrendConfidenceAssessment,
    hold_assessment: HoldAssessment,
    current_price: float,
    current_take_profit: float,
    original_risk_distance: float,
    current_volume: float,
) -> ExitDecision:
    """Decide what to do with an open Shakky position this cycle.

    Args:
        direction: The position's own direction.
        entry_trend_confidence_level: The Trend Confidence level at
            entry time (`Trade.entry_trend_confidence_score`, bucketed).
            Dynamic TP only ever engages for trades that entered
            "strong"/"exceptional" -- everything else keeps today's
            fixed target untouched.
        trend_confidence: This cycle's fresh `assess_trend_confidence()` result.
        hold_assessment: This cycle's fresh `assess_hold()` result.
        current_price: The position's current market price.
        current_take_profit: The position's current take-profit price.
        original_risk_distance: `abs(entry_price - initial_stop_loss)`.
        current_volume: The position's current open volume.

    Returns:
        An `ExitDecision`. The target only ever extends further in the
        position's favor, mirroring the trailing-stop invariant in
        `src.engines.risk_engine.dynamic_stop` (never retreats closer).
    """
    if entry_trend_confidence_level not in _STRONG_LEVELS:
        return ExitDecision(
            action="hold",
            new_take_profit=None,
            close_volume=None,
            reasons=["fixed_tp_mode:entry_confidence_was_not_strong"],
        )
    if original_risk_distance <= 0:
        return ExitDecision(
            action="hold",
            new_take_profit=None,
            close_volume=None,
            reasons=["undefined_risk_distance"],
        )

    if hold_assessment.reversal_expected:
        if trend_confidence.level in _STRONG_LEVELS:
            return ExitDecision(
                action="close_partial",
                new_take_profit=None,
                close_volume=current_volume * _PARTIAL_CLOSE_FRACTION,
                reasons=[*hold_assessment.reasons, "early_reversal_warning_taking_partial_profit"],
            )
        return ExitDecision(
            action="close_full",
            new_take_profit=None,
            close_volume=current_volume,
            reasons=[*hold_assessment.reasons, "trend_exhausted_closing_full_position"],
        )

    if hold_assessment.continuation_expected:
        candidate_tp = _extended_target(direction, current_price, original_risk_distance)
        is_further = (
            candidate_tp > current_take_profit
            if direction == "buy"
            else candidate_tp < current_take_profit
        )
        if is_further:
            return ExitDecision(
                action="extend_tp",
                new_take_profit=candidate_tp,
                close_volume=None,
                reasons=[*hold_assessment.reasons, f"extending_target_to_{candidate_tp:.2f}"],
            )

    return ExitDecision(
        action="hold", new_take_profit=None, close_volume=None, reasons=hold_assessment.reasons
    )
