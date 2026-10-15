"""Unit tests for Dynamic Take Profit (`exit_management`)."""

from __future__ import annotations

import pytest

from src.engines.shakky_engine.exit_management import evaluate_exit
from src.engines.shakky_engine.hold_manager import HoldAssessment
from src.engines.shakky_engine.trend_confidence import TrendConfidenceAssessment

pytestmark = pytest.mark.unit


def _trend(level: str, *, continuation_likely: bool = True) -> TrendConfidenceAssessment:
    return TrendConfidenceAssessment(
        level=level,  # type: ignore[arg-type]
        score=80.0,
        continuation_likely=continuation_likely,
        reasons=["fixture"],
    )


def _hold(
    *, should_hold: bool, continuation_expected: bool, reversal_expected: bool
) -> HoldAssessment:
    return HoldAssessment(
        should_hold=should_hold,
        continuation_expected=continuation_expected,
        reversal_expected=reversal_expected,
        reasons=["fixture"],
    )


def test_fixed_tp_mode_holds_unconditionally_for_non_strong_entries() -> None:
    decision = evaluate_exit(
        direction="buy",
        entry_trend_confidence_level="normal",
        trend_confidence=_trend("exceptional"),
        hold_assessment=_hold(
            should_hold=False, continuation_expected=False, reversal_expected=True
        ),
        current_price=2000.0,
        current_take_profit=2010.0,
        original_risk_distance=5.0,
        current_volume=1.0,
    )

    assert decision.action == "hold"
    assert decision.new_take_profit is None
    assert decision.close_volume is None
    assert "fixed_tp_mode:entry_confidence_was_not_strong" in decision.reasons


def test_extends_target_further_when_continuation_expected_on_a_buy() -> None:
    decision = evaluate_exit(
        direction="buy",
        entry_trend_confidence_level="strong",
        trend_confidence=_trend("strong"),
        hold_assessment=_hold(
            should_hold=True, continuation_expected=True, reversal_expected=False
        ),
        current_price=2010.0,
        current_take_profit=2005.0,
        original_risk_distance=5.0,
        current_volume=1.0,
    )

    assert decision.action == "extend_tp"
    assert decision.new_take_profit == pytest.approx(2015.0)
    assert decision.close_volume is None


def test_does_not_retreat_target_closer_when_candidate_is_not_further() -> None:
    decision = evaluate_exit(
        direction="buy",
        entry_trend_confidence_level="strong",
        trend_confidence=_trend("strong"),
        hold_assessment=_hold(
            should_hold=True, continuation_expected=True, reversal_expected=False
        ),
        current_price=2000.0,
        current_take_profit=2050.0,
        original_risk_distance=5.0,
        current_volume=1.0,
    )

    assert decision.action == "hold"
    assert decision.new_take_profit is None


def test_early_reversal_warning_while_trend_still_strong_closes_half() -> None:
    decision = evaluate_exit(
        direction="buy",
        entry_trend_confidence_level="exceptional",
        trend_confidence=_trend("strong"),
        hold_assessment=_hold(
            should_hold=False, continuation_expected=False, reversal_expected=True
        ),
        current_price=2020.0,
        current_take_profit=2010.0,
        original_risk_distance=5.0,
        current_volume=2.0,
    )

    assert decision.action == "close_partial"
    assert decision.close_volume == pytest.approx(1.0)


def test_confirmed_exhaustion_closes_the_full_position() -> None:
    decision = evaluate_exit(
        direction="sell",
        entry_trend_confidence_level="strong",
        trend_confidence=_trend("minor", continuation_likely=False),
        hold_assessment=_hold(
            should_hold=False, continuation_expected=False, reversal_expected=True
        ),
        current_price=1980.0,
        current_take_profit=1970.0,
        original_risk_distance=5.0,
        current_volume=2.0,
    )

    assert decision.action == "close_full"
    assert decision.close_volume == pytest.approx(2.0)


def test_undefined_risk_distance_is_a_safe_hold() -> None:
    decision = evaluate_exit(
        direction="buy",
        entry_trend_confidence_level="strong",
        trend_confidence=_trend("strong"),
        hold_assessment=_hold(
            should_hold=True, continuation_expected=True, reversal_expected=False
        ),
        current_price=2000.0,
        current_take_profit=2010.0,
        original_risk_distance=0.0,
        current_volume=1.0,
    )

    assert decision.action == "hold"
    assert "undefined_risk_distance" in decision.reasons
