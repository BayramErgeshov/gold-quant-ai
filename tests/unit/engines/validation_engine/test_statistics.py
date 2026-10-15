"""Unit tests for Walk-Forward Validation Engine statistics aggregation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.engines.validation_engine.statistics import compute_walk_forward_statistics
from src.engines.validation_engine.walk_forward import WalkForwardOpportunity

pytestmark = pytest.mark.unit

_TIME = datetime(2020, 1, 1, tzinfo=UTC)


def _opportunity(
    *,
    would_have_traded: bool = True,
    realized_return_pct: float | None,
    agreeing_departments: list[str] | None = None,
) -> WalkForwardOpportunity:
    return WalkForwardOpportunity(
        timestamp=_TIME,
        state="BUY" if would_have_traded else "WAIT",
        would_have_traded=would_have_traded,
        direction="buy" if would_have_traded else None,
        realized_return_pct=realized_return_pct,
        agreeing_departments=agreeing_departments or [],
    )


def test_compute_statistics_on_empty_input_never_fabricates_a_rate() -> None:
    statistics = compute_walk_forward_statistics([])

    assert statistics.total_opportunities == 0
    assert statistics.win_rate == 0.0
    assert statistics.average_return_pct == 0.0
    assert statistics.combo_statistics == []
    assert statistics.department_contributions == []


def test_compute_statistics_counts_actionable_and_traded_separately() -> None:
    opportunities = [
        _opportunity(would_have_traded=False, realized_return_pct=None),
        _opportunity(realized_return_pct=1.0, agreeing_departments=["technical"]),
    ]

    statistics = compute_walk_forward_statistics(opportunities)

    assert statistics.total_opportunities == 2
    assert statistics.actionable_opportunities == 1
    assert statistics.traded_opportunities == 1


def test_compute_statistics_win_rate_and_average_return() -> None:
    opportunities = [
        _opportunity(realized_return_pct=2.0, agreeing_departments=["technical"]),
        _opportunity(realized_return_pct=-1.0, agreeing_departments=["technical"]),
    ]

    statistics = compute_walk_forward_statistics(opportunities)

    assert statistics.win_rate == pytest.approx(0.5)
    assert statistics.average_return_pct == pytest.approx(0.5)


def test_compute_statistics_groups_by_agreeing_department_combination() -> None:
    opportunities = [
        _opportunity(realized_return_pct=1.0, agreeing_departments=["historical", "technical"]),
        _opportunity(realized_return_pct=1.5, agreeing_departments=["technical", "historical"]),
        _opportunity(realized_return_pct=-2.0, agreeing_departments=["technical"]),
    ]

    statistics = compute_walk_forward_statistics(opportunities)

    combo_by_departments = {combo.departments: combo for combo in statistics.combo_statistics}
    assert combo_by_departments[("historical", "technical")].sample_size == 2
    assert combo_by_departments[("historical", "technical")].win_rate == pytest.approx(1.0)
    assert combo_by_departments[("technical",)].sample_size == 1
    assert combo_by_departments[("technical",)].win_rate == pytest.approx(0.0)


def test_compute_statistics_department_contribution_rates() -> None:
    opportunities = [
        _opportunity(realized_return_pct=1.0, agreeing_departments=["technical"]),
        _opportunity(realized_return_pct=1.0, agreeing_departments=["historical"]),
        _opportunity(realized_return_pct=-1.0, agreeing_departments=["technical"]),
    ]

    statistics = compute_walk_forward_statistics(opportunities)

    contributions = {c.department_name: c for c in statistics.department_contributions}
    # "technical" agreed with 1 win and 1 loss out of 2 wins/1 loss total.
    assert contributions["technical"].win_contribution_rate == pytest.approx(0.5)
    assert contributions["technical"].loss_contribution_rate == pytest.approx(1.0)
    # "historical" only ever agreed with the single winning opportunity.
    assert contributions["historical"].win_contribution_rate == pytest.approx(0.5)
    assert contributions["historical"].loss_contribution_rate == pytest.approx(0.0)
