"""Unit tests for Walk-Forward Validation Engine recommendation generation."""

from __future__ import annotations

import pytest

from src.engines.validation_engine.recommendations import generate_recommendations
from src.engines.validation_engine.statistics import (
    DepartmentComboStatistics,
    WalkForwardStatistics,
)

pytestmark = pytest.mark.unit


def _statistics(combo_statistics: list[DepartmentComboStatistics]) -> WalkForwardStatistics:
    return WalkForwardStatistics(
        total_opportunities=1000,
        actionable_opportunities=500,
        traded_opportunities=500,
        win_rate=0.5,
        average_return_pct=0.1,
        combo_statistics=combo_statistics,
    )


def test_generate_recommendations_skips_combinations_below_minimum_sample_size() -> None:
    statistics = _statistics(
        [
            DepartmentComboStatistics(
                departments=("technical",), sample_size=5, win_rate=0.9, average_return_pct=2.0
            )
        ]
    )

    proposals = generate_recommendations(statistics, symbol_name="XAUUSD", timeframe="M15")

    assert proposals == []


def test_generate_recommendations_skips_combinations_with_a_middling_win_rate() -> None:
    statistics = _statistics(
        [
            DepartmentComboStatistics(
                departments=("technical",), sample_size=100, win_rate=0.5, average_return_pct=0.1
            )
        ]
    )

    proposals = generate_recommendations(statistics, symbol_name="XAUUSD", timeframe="M15")

    assert proposals == []


def test_generate_recommendations_proposes_for_a_strong_combination() -> None:
    statistics = _statistics(
        [
            DepartmentComboStatistics(
                departments=("historical", "technical"),
                sample_size=50,
                win_rate=0.72,
                average_return_pct=1.8,
            )
        ]
    )

    proposals = generate_recommendations(statistics, symbol_name="XAUUSD", timeframe="M15")

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.status == "pending"
    assert "historical, technical" in proposal.title
    assert proposal.historical_statistics["win_rate"] == pytest.approx(0.72)


def test_generate_recommendations_proposes_for_a_weak_combination() -> None:
    statistics = _statistics(
        [
            DepartmentComboStatistics(
                departments=("news",), sample_size=30, win_rate=0.15, average_return_pct=-1.5
            )
        ]
    )

    proposals = generate_recommendations(statistics, symbol_name="XAUUSD", timeframe="M15")

    assert len(proposals) == 1
    assert proposals[0].status == "pending"
    assert "lower" in proposals[0].title or "excluded" in proposals[0].title


def test_generate_recommendations_never_sets_a_non_pending_status() -> None:
    statistics = _statistics(
        [
            DepartmentComboStatistics(
                departments=(), sample_size=100, win_rate=0.8, average_return_pct=3.0
            ),
            DepartmentComboStatistics(
                departments=("ml",), sample_size=100, win_rate=0.1, average_return_pct=-2.0
            ),
        ]
    )

    proposals = generate_recommendations(statistics, symbol_name="XAUUSD", timeframe="M15")

    assert len(proposals) == 2
    assert all(proposal.status == "pending" for proposal in proposals)
