"""Research request generation for Chief AI.

Per RESEARCH_FRAMEWORK.md "Hypothesis Generation" and DECISION_ENGINE.md's
"RESEARCH MORE" decision state: when the evidence gap is a specific,
addressable research need (rather than routine low confidence), Chief AI
raises a structured request instead of silently waiting.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engines.chief_ai.decision import ChiefAIDecision

_REQUEST_BY_FACTOR: dict[str, tuple[str, str]] = {
    "unknown_market_regime": (
        "What is the current XAUUSD market regime?",
        "Regime classification failed or was unavailable this cycle, reducing decision "
        "confidence.",
    ),
    "conflicting_departments": (
        "Why do departments disagree on direction this cycle?",
        "Bullish and bearish probabilities are nearly equal, indicating conflicting "
        "independent evidence.",
    ),
}


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    """A structured research request.

    Per RESEARCH_FRAMEWORK.md "Hypothesis Generation": every hypothesis
    contains (at minimum) a Question, Motivation and Priority.
    """

    question: str
    motivation: str
    priority: str


def generate_research_requests(decision: ChiefAIDecision) -> list[ResearchRequest]:
    """Generate research requests for addressable uncertainty factors.

    Args:
        decision: The Chief AI decision to inspect.

    Returns:
        One `ResearchRequest` per matching uncertainty factor, in the
        order they appear on `decision.uncertainty_factors`. Empty if no
        actionable research gap was identified this cycle.
    """
    requests = []
    for factor in decision.uncertainty_factors:
        template = _REQUEST_BY_FACTOR.get(factor)
        if template is not None:
            question, motivation = template
            requests.append(
                ResearchRequest(question=question, motivation=motivation, priority="P1")
            )
    return requests
