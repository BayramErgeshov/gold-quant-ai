"""Trade approval pipeline for the Risk Engine.

Per RISK_ENGINE.md "Trade Approval Process" and "Trade Rejection Rules":
"No trade may bypass the Risk Engine... Even if every other department
agrees, the Risk Engine may reject the trade." This module is the final
gate — every check is explicit and every rejection reason is reported,
never a silent approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ConfidenceLevel = Literal[
    "reject", "observation_only", "possible_setup", "high_quality", "institutional_grade"
]

_CONFIDENCE_LEVEL_THRESHOLDS: tuple[tuple[float, ConfidenceLevel], ...] = (
    (86.0, "institutional_grade"),
    (76.0, "high_quality"),
    (61.0, "possible_setup"),
    (41.0, "observation_only"),
)
# Per RISK_ENGINE.md "Confidence Levels": 76-85 "Execution allowed", 86-100
# "Institutional Grade... Still requires complete validation" (execution
# allowed, pending the other checks below). 61-75 "Require stronger
# confirmation" and 41-60 "No execution" are both non-executable by default.
_EXECUTABLE_CONFIDENCE_LEVELS: frozenset[ConfidenceLevel] = frozenset(
    {"high_quality", "institutional_grade"}
)
# Per the "Demo Learning Mode" production requirement ("allow parallel
# trades, aggressive experimentation... maximize statistically useful
# trading experience"): while that mode is enabled, "possible_setup"
# (61-75%) also counts as executable. This tier floor is independent of
# -- and normally stricter than -- any per-strategy `confidence_threshold`
# a user configures in Settings (RuntimeSettings.confidence_threshold/
# scalping_confidence_threshold/swing_confidence_threshold can be set as
# low as they like, but a decision still can never execute below this
# tier system's own floor); Demo Learning Mode is the one explicit,
# user-controlled way to widen that floor, never a silent override.
_DEMO_LEARNING_MODE_EXECUTABLE_CONFIDENCE_LEVELS: frozenset[ConfidenceLevel] = frozenset(
    {"possible_setup", "high_quality", "institutional_grade"}
)


def classify_confidence_level(confidence_pct: float) -> ConfidenceLevel:
    """Map a confidence percentage to a RISK_ENGINE.md "Confidence Levels" tier.

    Args:
        confidence_pct: Overall decision confidence, in [0.0, 100.0].

    Returns:
        One of `ConfidenceLevel`.

    Raises:
        ValueError: If `confidence_pct` is outside [0.0, 100.0].
    """
    if not 0.0 <= confidence_pct <= 100.0:
        raise ValueError("confidence_pct must be between 0.0 and 100.0")
    for threshold, level in _CONFIDENCE_LEVEL_THRESHOLDS:
        if confidence_pct >= threshold:
            return level
    return "reject"


@dataclass(frozen=True, slots=True)
class TradeApprovalRequest:
    """Every input the Risk Engine's approval gate evaluates.

    Attributes:
        confidence_pct: Overall decision confidence, in [0.0, 100.0].
        spread_pips: Current quoted spread.
        max_spread_pips: Maximum acceptable spread.
        is_market_open: Whether the relevant session is currently open.
        exposure_breaches: Exposure-limit breach reasons, e.g. from
            `src.engines.risk_engine.exposure.check_exposure_limits`.
        historical_edge_pct: Measured historical edge for this setup
            (e.g. from `src.engines.statistics_engine.expected_value`).
        min_historical_edge_pct: Minimum required historical edge.
        critical_news_imminent: Whether high-impact news is imminent.
        data_complete: Whether every required input report was available.
        system_health_ok: Whether platform/system health checks passed.
        demo_learning_mode: Per the "Demo Learning Mode" production
            requirement: when True, widens the executable confidence-tier
            floor to also include "possible_setup" (61-75%), not just
            "high_quality"/"institutional_grade" (76+). False (the
            default) preserves the standard RISK_ENGINE.md floor exactly.
    """

    confidence_pct: float
    spread_pips: float
    max_spread_pips: float
    is_market_open: bool
    exposure_breaches: list[str] = field(default_factory=list)
    historical_edge_pct: float = 0.0
    min_historical_edge_pct: float = 0.0
    critical_news_imminent: bool = False
    data_complete: bool = True
    system_health_ok: bool = True
    demo_learning_mode: bool = False


@dataclass(frozen=True, slots=True)
class TradeApprovalDecision:
    """The Risk Engine's final approve/reject decision.

    Attributes:
        approved: True only if every check passed.
        confidence_level: The classified `ConfidenceLevel`.
        rejection_reasons: Every rule that failed. Empty if `approved`.
    """

    approved: bool
    confidence_level: ConfidenceLevel
    rejection_reasons: list[str]


def evaluate_trade(request: TradeApprovalRequest) -> TradeApprovalDecision:
    """Run the RISK_ENGINE.md "Trade Approval Process" / "Trade Rejection Rules".

    Args:
        request: Every input needed to evaluate the trade.

    Returns:
        A `TradeApprovalDecision`. Never approves a trade with any
        outstanding rejection reason, per RISK_ENGINE.md "No trade may
        bypass the Risk Engine."
    """
    confidence_level = classify_confidence_level(request.confidence_pct)
    executable_levels = (
        _DEMO_LEARNING_MODE_EXECUTABLE_CONFIDENCE_LEVELS
        if request.demo_learning_mode
        else _EXECUTABLE_CONFIDENCE_LEVELS
    )
    reasons: list[str] = []

    if confidence_level not in executable_levels:
        reasons.append(f"confidence_level_not_executable: {confidence_level}")
    if request.spread_pips > request.max_spread_pips:
        reasons.append(f"spread_excessive: {request.spread_pips} > max {request.max_spread_pips}")
    if not request.is_market_open:
        reasons.append("market_closed")
    if request.historical_edge_pct < request.min_historical_edge_pct:
        reasons.append(
            f"historical_edge_insufficient: {request.historical_edge_pct} < "
            f"min {request.min_historical_edge_pct}"
        )
    if request.critical_news_imminent:
        reasons.append("critical_news_imminent")
    if not request.data_complete:
        reasons.append("data_incomplete")
    if not request.system_health_ok:
        reasons.append("system_health_degraded")
    reasons.extend(request.exposure_breaches)

    return TradeApprovalDecision(
        approved=not reasons, confidence_level=confidence_level, rejection_reasons=reasons
    )
