"""Unit tests for Chief AI alternative scenario generation."""

from __future__ import annotations

import pytest

from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.scenarios import build_scenario_plan
from src.engines.statistics_engine.probability import ProbabilityEstimate

pytestmark = pytest.mark.unit


def _decision(state: str) -> ChiefAIDecision:
    return ChiefAIDecision(
        state=state,  # type: ignore[arg-type]
        probability=ProbabilityEstimate(
            bullish_probability=0.7, bearish_probability=0.2, neutral_probability=0.1
        ),
        confidence_pct=80.0,
        uncertainty_factors=[],
        reasons=[],
    )


def test_buy_scenario_frames_continuation_as_primary() -> None:
    plan = build_scenario_plan(_decision("BUY"), market_regime="bull_trend")

    assert "higher" in plan.primary_scenario
    assert "lower" in plan.alternative_scenario
    assert "bullish" in plan.invalidation
    assert plan.expected_volatility == "bull_trend"


def test_sell_scenario_frames_continuation_as_primary() -> None:
    plan = build_scenario_plan(_decision("SELL"))

    assert "lower" in plan.primary_scenario
    assert "higher" in plan.alternative_scenario
    assert "bearish" in plan.invalidation


def test_wait_scenario_has_no_directional_bias() -> None:
    plan = build_scenario_plan(_decision("WAIT"))

    assert "No directional edge" in plan.primary_scenario
    assert "WAIT" in plan.invalidation
