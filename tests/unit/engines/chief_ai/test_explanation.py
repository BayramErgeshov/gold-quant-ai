"""Unit tests for Chief AI decision explanation."""

from __future__ import annotations

import pytest

from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.explanation import explain_decision
from src.engines.statistics_engine.probability import ProbabilityEstimate

pytestmark = pytest.mark.unit


def _decision(state: str, **overrides: object) -> ChiefAIDecision:
    defaults: dict[str, object] = {
        "state": state,
        "probability": ProbabilityEstimate(
            bullish_probability=0.8, bearish_probability=0.1, neutral_probability=0.1
        ),
        "confidence_pct": 80.0,
        "uncertainty_factors": [],
        "reasons": ["bullish_probability_exceeds_bearish"],
        "supporting_evidence": ["structure_bullish"],
        "opposing_evidence": ["dxy_strength"],
    }
    defaults.update(overrides)
    return ChiefAIDecision(**defaults)  # type: ignore[arg-type]


def test_explains_buy_decision() -> None:
    explanation = explain_decision(_decision("BUY"))

    assert "Bullish" in explanation.why_now
    assert "bearish" in explanation.why_not_opposite
    assert explanation.confirming_evidence == ["structure_bullish"]
    assert explanation.invalidating_evidence == ["dxy_strength"]
    assert "80.0%" in explanation.confidence_summary


def test_explains_sell_decision() -> None:
    explanation = explain_decision(
        _decision(
            "SELL",
            probability=ProbabilityEstimate(
                bullish_probability=0.1, bearish_probability=0.8, neutral_probability=0.1
            ),
            reasons=["bearish_probability_exceeds_bullish"],
        )
    )

    assert "Bearish" in explanation.why_now
    assert "bullish" in explanation.why_not_opposite


def test_explains_wait_decision_with_reasons() -> None:
    explanation = explain_decision(
        _decision("WAIT", reasons=["confidence_below_threshold: 40.0 < 70.0"])
    )

    assert "No trade" in explanation.why_now
    assert "confidence_below_threshold" in explanation.why_now


def test_explains_wait_decision_with_no_reasons() -> None:
    explanation = explain_decision(_decision("WAIT", reasons=[]))

    assert "insufficient evidence" in explanation.why_now


def test_uncertainty_summary_reflects_factors() -> None:
    explanation = explain_decision(
        _decision("WAIT", uncertainty_factors=["critical_news_imminent"])
    )

    assert explanation.uncertainty_summary == "critical_news_imminent"


def test_uncertainty_summary_is_none_when_empty() -> None:
    explanation = explain_decision(_decision("WAIT"))

    assert explanation.uncertainty_summary == "none"
