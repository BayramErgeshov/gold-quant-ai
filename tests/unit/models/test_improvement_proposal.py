"""Unit tests for the `ImprovementProposal` ORM model."""

from __future__ import annotations

import pytest

from src.models.improvement_proposal import ImprovementProposal

pytestmark = pytest.mark.unit


def test_repr_includes_title_and_status() -> None:
    proposal = ImprovementProposal(
        title="Widen stops in high volatility regimes",
        problem="Stops are hit prematurely during high volatility.",
        evidence="12 losing trades identified stop_too_close.",
        expected_benefit="Fewer premature stop-outs.",
        potential_risk="Larger losses per trade if wrong.",
        implementation_difficulty="medium",
        recommendation="Backtest wider stops in high-volatility regimes.",
        status="pending",
    )

    assert repr(proposal) == (
        "ImprovementProposal(title='Widen stops in high volatility regimes', status='pending')"
    )
