"""Unit tests for swing-specific dynamic position sizing."""

from __future__ import annotations

import pytest

from src.engines.swing_engine.position_sizing import SwingRiskFactors, compute_swing_risk_pct

pytestmark = pytest.mark.unit


def test_full_confidence_no_history_uses_full_base_risk() -> None:
    result = compute_swing_risk_pct(1.0, SwingRiskFactors(confidence=1.0, recent_win_rate=None))

    assert result == pytest.approx(1.0)


def test_lower_confidence_scales_risk_down_proportionally() -> None:
    result = compute_swing_risk_pct(1.0, SwingRiskFactors(confidence=0.5, recent_win_rate=None))

    assert result == pytest.approx(0.5)


def test_poor_recent_performance_reduces_risk() -> None:
    result = compute_swing_risk_pct(1.0, SwingRiskFactors(confidence=1.0, recent_win_rate=0.25))

    assert result == pytest.approx(0.5)  # 0.25 / 0.5 threshold = 0.5 scale


def test_good_recent_performance_does_not_boost_risk_above_base() -> None:
    result = compute_swing_risk_pct(1.0, SwingRiskFactors(confidence=1.0, recent_win_rate=0.9))

    assert result == pytest.approx(1.0)  # never a fabricated increase


def test_zero_recent_win_rate_reduces_risk_to_zero() -> None:
    result = compute_swing_risk_pct(1.0, SwingRiskFactors(confidence=1.0, recent_win_rate=0.0))

    assert result == pytest.approx(0.0)


def test_result_never_exceeds_base_risk_even_with_out_of_range_confidence() -> None:
    result = compute_swing_risk_pct(1.0, SwingRiskFactors(confidence=5.0, recent_win_rate=None))

    assert result <= 1.0
