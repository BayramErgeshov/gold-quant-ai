"""Unit tests for improvement proposal construction."""

from __future__ import annotations

import pytest

from src.engines.learning_engine.hypothesis import Hypothesis
from src.engines.learning_engine.proposal import build_proposal_from_hypothesis

pytestmark = pytest.mark.unit


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        question="Does the recurring factor 'stop_too_close' systematically affect outcomes?",
        motivation="'stop_too_close' was identified in 6 reviewed trades.",
        supporting_evidence="6 occurrences across reviewed closed trades.",
        expected_outcome="Confirming or rejecting whether stops should widen.",
        validation_plan="Backtest with and without this factor's influence.",
        success_criteria="Statistically significant improvement in a held-out test period.",
        failure_criteria="No significant difference, or a significant regression.",
        priority="P1",
    )


def test_builds_pending_proposal_from_hypothesis() -> None:
    proposal = build_proposal_from_hypothesis(
        _hypothesis(),
        historical_statistics={"win_rate": 0.42},
        validation_results={"backtest_win_rate": 0.55},
        potential_risk="Wider stops increase loss size if the setup fails.",
    )

    assert proposal.status == "pending"
    assert proposal.title == _hypothesis().question
    assert proposal.historical_statistics == {"win_rate": 0.42}
    assert proposal.validation_results == {"backtest_win_rate": 0.55}
    assert proposal.implementation_difficulty == "medium"
    assert "Backtest with and without" in proposal.recommendation
    assert "Statistically significant" in proposal.recommendation


def test_respects_custom_implementation_difficulty() -> None:
    proposal = build_proposal_from_hypothesis(
        _hypothesis(),
        historical_statistics={},
        validation_results={},
        potential_risk="x",
        implementation_difficulty="high",
    )

    assert proposal.implementation_difficulty == "high"
