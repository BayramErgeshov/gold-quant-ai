"""Before Market Close position assessment (production requirement).

Per the spec: "30 minutes before market close, analyze every open
position; send a Telegram report per position with recommendation,
confidence, reasons, expected weekend risk, keep/close recommendation."
Reuses the same cycle's already-computed `ChiefAIDecision` and classified
market regime as "current market context" -- never re-fabricates a
separate opinion, and never invents a numeric weekend-gap probability
this platform cannot actually measure (no historical Friday-close ->
Monday-open gap dataset exists yet); the weekend note is a factual,
regime-grounded statement instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.core.execution.mt5_client import OpenPosition
from src.engines.chief_ai.decision import ChiefAIDecision
from src.models.trade import Trade

# Below this confidence, the current cycle's decision is too weak to
# either confirm or override the position's own direction -- fall back to
# the position's own floating P&L as the deciding factor.
_MEANINGFUL_CONFIDENCE_PCT = 60.0

_ELEVATED_WEEKEND_RISK_REGIMES = frozenset({"high_volatility", "transition"})


@dataclass(frozen=True, slots=True)
class PositionPreCloseAssessment:
    """One open position's "Before Market Close" assessment.

    Attributes:
        trade_id: The journaled trade's id.
        market: Symbol name, e.g. "XAUUSD".
        recommendation: "keep" or "close".
        confidence_pct: The current cycle's Chief AI confidence used to
            derive this recommendation.
        reasons: Why this recommendation was chosen.
        weekend_risk: A factual, regime-grounded weekend gap risk note,
            only populated when the weekly close is approaching.
    """

    trade_id: str
    market: str
    recommendation: Literal["keep", "close"]
    confidence_pct: float
    reasons: list[str] = field(default_factory=list)
    weekend_risk: str | None = None


def _weekend_risk_note(market_regime: str | None) -> str:
    if market_regime in _ELEVATED_WEEKEND_RISK_REGIMES:
        return (
            f"Elevated weekend gap risk: current regime is {market_regime!r} "
            "-- gold has historically produced larger open-price gaps after "
            "the weekly close in unstable regimes."
        )
    return (
        f"No elevated weekend gap risk signal from the current regime "
        f"({market_regime or 'unclassified'!r})."
    )


def assess_position_before_close(
    *,
    trade: Trade,
    position: OpenPosition,
    current_decision: ChiefAIDecision,
    market_regime: str | None,
    weekend_approaching: bool,
) -> PositionPreCloseAssessment:
    """Assess one open position ahead of the session close.

    Args:
        trade: The journaled `Trade` for this position.
        position: The broker's current view of the open position.
        current_decision: This cycle's primary Chief AI decision --
            reused as the "current market view," never a separate
            fabricated re-analysis.
        market_regime: This cycle's classified market regime, if known.
        weekend_approaching: Whether today's close is also the weekly close.

    Returns:
        The `PositionPreCloseAssessment` for this position.
    """
    position_bias: Literal["BUY", "SELL"] = "BUY" if position.direction == "buy" else "SELL"
    reasons: list[str] = []

    if current_decision.state == position_bias:
        recommendation: Literal["keep", "close"] = "keep"
        reasons.append(
            f"current_decision_agrees:{current_decision.state}"
            f"@{current_decision.confidence_pct:.0f}%"
        )
    elif (
        current_decision.state in ("BUY", "SELL")
        and current_decision.confidence_pct >= _MEANINGFUL_CONFIDENCE_PCT
    ):
        recommendation = "close"
        reasons.append(
            f"current_decision_opposes:{current_decision.state}"
            f"@{current_decision.confidence_pct:.0f}%"
        )
    else:
        recommendation = "keep" if position.profit >= 0 else "close"
        reasons.append("no_strong_directional_signal_this_cycle")
        reasons.append("position_in_profit" if position.profit >= 0 else "position_in_loss")

    return PositionPreCloseAssessment(
        trade_id=str(trade.id),
        market=position.symbol,
        recommendation=recommendation,
        confidence_pct=current_decision.confidence_pct,
        reasons=reasons,
        weekend_risk=_weekend_risk_note(market_regime) if weekend_approaching else None,
    )
