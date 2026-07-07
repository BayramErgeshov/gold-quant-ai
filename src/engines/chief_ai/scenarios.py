"""Alternative scenario generation for Chief AI decisions.

Per DECISION_ENGINE.md "Alternative Scenario": "Every decision must
include Primary Scenario, Alternative Scenario, Invalidation, Maximum
Risk, Expected Duration, Expected Volatility, Historical Analogue." Built
entirely from already-computed decision evidence — never a fabricated
forecast without supporting inputs. Maximum Risk / Expected Duration /
Historical Analogue require Position Sizing (Phase 11) and Historical
Similarity (Phase 5) outputs specific to the candidate trade and are
attached by the caller once those are available, rather than guessed here.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engines.chief_ai.decision import ChiefAIDecision


@dataclass(frozen=True, slots=True)
class ScenarioPlan:
    """Primary/alternative scenario framing for a decision.

    Attributes:
        primary_scenario: The scenario matching `decision.state`.
        alternative_scenario: What happens if the opposite direction prevails.
        invalidation: The condition that would prove the primary scenario wrong.
        expected_volatility: Expected volatility label, if a market regime is known.
    """

    primary_scenario: str
    alternative_scenario: str
    invalidation: str
    expected_volatility: str | None


def build_scenario_plan(
    decision: ChiefAIDecision, *, market_regime: str | None = None
) -> ScenarioPlan:
    """Build the primary/alternative scenario framing for a decision.

    Args:
        decision: The Chief AI decision to build scenarios for.
        market_regime: Current classified regime, if known, used as a
            proxy for expected volatility framing.

    Returns:
        A `ScenarioPlan` derived from `decision`'s own probability split.
    """
    if decision.state == "BUY":
        primary = (
            f"Price continues higher "
            f"(bullish probability {decision.probability.bullish_probability:.0%})."
        )
        alternative = (
            f"Price reverses lower "
            f"(bearish probability {decision.probability.bearish_probability:.0%})."
        )
        invalidation = (
            "A confirmed break of the bullish market structure invalidates this scenario."
        )
    elif decision.state == "SELL":
        primary = (
            f"Price continues lower "
            f"(bearish probability {decision.probability.bearish_probability:.0%})."
        )
        alternative = (
            f"Price reverses higher "
            f"(bullish probability {decision.probability.bullish_probability:.0%})."
        )
        invalidation = (
            "A confirmed break of the bearish market structure invalidates this scenario."
        )
    else:
        primary = "No directional edge identified this cycle; remain flat."
        alternative = "A change in the underlying evidence could favor either direction."
        invalidation = f"N/A while the decision remains {decision.state}."

    return ScenarioPlan(
        primary_scenario=primary,
        alternative_scenario=alternative,
        invalidation=invalidation,
        expected_volatility=market_regime,
    )
