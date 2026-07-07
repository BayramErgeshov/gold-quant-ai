"""Explanation generation for Chief AI decisions.

Per DECISION_ENGINE.md "Explanation": "Every recommendation explains Why
now, Why this direction, Why not opposite direction, What confirms, What
invalidates, Historical evidence, Macro evidence, Technical evidence, Risk
assessment." Always built from the same `ChiefAIDecision` produced by
`src.engines.chief_ai.decision.evaluate` — never freeform generated text,
per NEWS_ENGINE.md's "Chief AI Interface" principle applied consistently:
"Structured... Never raw text."
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engines.chief_ai.decision import ChiefAIDecision


@dataclass(frozen=True, slots=True)
class DecisionExplanation:
    """A structured explanation of a Chief AI decision."""

    why_now: str
    why_this_direction: str
    why_not_opposite: str
    confirming_evidence: list[str]
    invalidating_evidence: list[str]
    confidence_summary: str
    uncertainty_summary: str


def _probability_for(decision: ChiefAIDecision, direction: str) -> float:
    return (
        decision.probability.bullish_probability
        if direction == "bullish"
        else decision.probability.bearish_probability
    )


def explain_decision(decision: ChiefAIDecision) -> DecisionExplanation:
    """Build a structured explanation for a Chief AI decision.

    Args:
        decision: The decision to explain.

    Returns:
        A `DecisionExplanation` derived entirely from `decision`'s own
        fields — no additional freeform text generation.
    """
    if decision.state in ("BUY", "SELL"):
        direction = "bullish" if decision.state == "BUY" else "bearish"
        opposite = "bearish" if decision.state == "BUY" else "bullish"
        why_now = (
            f"{direction.capitalize()} probability "
            f"({_probability_for(decision, direction):.0%}) exceeds {opposite} probability "
            f"({_probability_for(decision, opposite):.0%}) with confidence "
            f"{decision.confidence_pct:.1f}% at or above threshold."
        )
        why_this_direction = f"Evidence favors a {direction} bias: " + (
            "; ".join(decision.reasons) or "no specific reasons recorded"
        )
        why_not_opposite = (
            f"The {opposite} case was outweighed by the combined cross-department vote."
        )
    else:
        why_now = f"No trade: {'; '.join(decision.reasons) or 'insufficient evidence'}."
        why_this_direction = "No directional bias met the approval threshold."
        why_not_opposite = "Neither direction had sufficient support this cycle."

    return DecisionExplanation(
        why_now=why_now,
        why_this_direction=why_this_direction,
        why_not_opposite=why_not_opposite,
        confirming_evidence=decision.supporting_evidence,
        invalidating_evidence=decision.opposing_evidence,
        confidence_summary=f"{decision.confidence_pct:.1f}% overall confidence",
        uncertainty_summary=(
            "; ".join(decision.uncertainty_factors) if decision.uncertainty_factors else "none"
        ),
    )
