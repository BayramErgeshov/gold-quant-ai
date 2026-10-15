"""Unit tests for Position Scaling."""

from __future__ import annotations

import pytest

from src.engines.shakky_engine.position_scaling import evaluate_scaling

pytestmark = pytest.mark.unit


def test_scales_a_profitable_buy_when_every_gate_passes() -> None:
    decision = evaluate_scaling(
        direction="buy",
        entry_price=2000.0,
        current_price=2010.0,
        entry_trend_confidence_score=60.0,
        current_trend_confidence_score=75.0,
        market_structure_valid=True,
        exposure_breach_reasons=[],
        base_volume=1.0,
        scale_fraction=0.5,
    )

    assert decision.should_scale is True
    assert decision.additional_volume == pytest.approx(0.5)
    assert "all_gates_passed" in decision.reasons


def test_never_scales_a_losing_position() -> None:
    decision = evaluate_scaling(
        direction="buy",
        entry_price=2000.0,
        current_price=1995.0,
        entry_trend_confidence_score=60.0,
        current_trend_confidence_score=90.0,
        market_structure_valid=True,
        exposure_breach_reasons=[],
        base_volume=1.0,
    )

    assert decision.should_scale is False
    assert decision.additional_volume is None
    assert "gate_failed:position_not_yet_profitable" in decision.reasons


def test_does_not_scale_a_profitable_sell_when_confidence_has_not_increased() -> None:
    decision = evaluate_scaling(
        direction="sell",
        entry_price=2000.0,
        current_price=1990.0,
        entry_trend_confidence_score=70.0,
        current_trend_confidence_score=71.0,
        market_structure_valid=True,
        exposure_breach_reasons=[],
        base_volume=1.0,
    )

    assert decision.should_scale is False
    assert "gate_failed:trend_confidence_has_not_increased" in decision.reasons


def test_does_not_scale_when_market_structure_is_no_longer_valid() -> None:
    decision = evaluate_scaling(
        direction="buy",
        entry_price=2000.0,
        current_price=2010.0,
        entry_trend_confidence_score=60.0,
        current_trend_confidence_score=80.0,
        market_structure_valid=False,
        exposure_breach_reasons=[],
        base_volume=1.0,
    )

    assert decision.should_scale is False
    assert "gate_failed:market_structure_no_longer_valid" in decision.reasons


def test_does_not_scale_when_exposure_limits_would_be_breached() -> None:
    decision = evaluate_scaling(
        direction="buy",
        entry_price=2000.0,
        current_price=2010.0,
        entry_trend_confidence_score=60.0,
        current_trend_confidence_score=80.0,
        market_structure_valid=True,
        exposure_breach_reasons=["total_exposure_exceeded: projected 12.00% > max 10.00%"],
        base_volume=1.0,
    )

    assert decision.should_scale is False
    assert any("total_exposure_exceeded" in reason for reason in decision.reasons)


def test_all_gates_can_fail_simultaneously_without_crashing() -> None:
    decision = evaluate_scaling(
        direction="sell",
        entry_price=2000.0,
        current_price=2010.0,
        entry_trend_confidence_score=60.0,
        current_trend_confidence_score=60.0,
        market_structure_valid=False,
        exposure_breach_reasons=["daily_exposure_exceeded: projected 20% > max 15%"],
        base_volume=1.0,
    )

    assert decision.should_scale is False
    assert len(decision.reasons) == 4
