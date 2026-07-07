"""Unit tests for Chief AI research request generation."""

from __future__ import annotations

import pytest

from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.research_requests import generate_research_requests
from src.engines.statistics_engine.probability import ProbabilityEstimate

pytestmark = pytest.mark.unit


def _decision(uncertainty_factors: list[str]) -> ChiefAIDecision:
    return ChiefAIDecision(
        state="WAIT",
        probability=ProbabilityEstimate(
            bullish_probability=0.4, bearish_probability=0.4, neutral_probability=0.2
        ),
        confidence_pct=50.0,
        uncertainty_factors=uncertainty_factors,
        reasons=[],
    )


def test_no_requests_when_no_actionable_uncertainty() -> None:
    assert generate_research_requests(_decision([])) == []


def test_no_requests_for_unmapped_factor() -> None:
    assert generate_research_requests(_decision(["critical_news_imminent"])) == []


def test_generates_request_for_unknown_regime() -> None:
    requests = generate_research_requests(_decision(["unknown_market_regime"]))

    assert len(requests) == 1
    assert "market regime" in requests[0].question
    assert requests[0].priority == "P1"


def test_generates_request_for_conflicting_departments() -> None:
    requests = generate_research_requests(_decision(["conflicting_departments"]))

    assert len(requests) == 1
    assert "disagree" in requests[0].question


def test_generates_multiple_requests() -> None:
    requests = generate_research_requests(
        _decision(["unknown_market_regime", "conflicting_departments"])
    )

    assert len(requests) == 2
