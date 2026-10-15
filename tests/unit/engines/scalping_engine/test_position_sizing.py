"""Unit tests for scalping-specific dynamic position sizing."""

from __future__ import annotations

import pytest

from src.engines.scalping_engine.position_sizing import (
    ScalpingRiskFactors,
    compute_scalping_risk_pct,
)

pytestmark = pytest.mark.unit


def test_full_confidence_no_spread_no_history_uses_full_base_risk() -> None:
    result = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=1.0,
            spread_points=0.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=None,
        ),
    )

    assert result == pytest.approx(1.0)


def test_lower_confidence_scales_risk_down_proportionally() -> None:
    result = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=0.5,
            spread_points=0.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=None,
        ),
    )

    assert result == pytest.approx(0.5)


def test_wide_spread_reduces_risk() -> None:
    tight_spread = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=1.0,
            spread_points=10.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=None,
        ),
    )
    max_spread = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=1.0,
            spread_points=350.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=None,
        ),
    )

    assert max_spread < tight_spread
    assert max_spread == pytest.approx(0.5)  # fully-maxed spread halves the risk


def test_poor_recent_performance_reduces_risk() -> None:
    result = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=1.0,
            spread_points=0.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=0.25,
        ),
    )

    assert result == pytest.approx(0.5)  # 0.25 / 0.5 threshold = 0.5 scale


def test_good_recent_performance_does_not_boost_risk_above_base() -> None:
    result = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=1.0,
            spread_points=0.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=0.9,
        ),
    )

    assert result == pytest.approx(1.0)  # never a fabricated increase


def test_zero_recent_win_rate_reduces_risk_to_zero() -> None:
    result = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=1.0,
            spread_points=0.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=0.0,
        ),
    )

    assert result == pytest.approx(0.0)


def test_result_never_exceeds_base_risk_even_with_out_of_range_confidence() -> None:
    result = compute_scalping_risk_pct(
        1.0,
        ScalpingRiskFactors(
            confidence=5.0,  # a defensively-clamped out-of-range input
            spread_points=0.0,
            max_acceptable_spread_points=350.0,
            recent_win_rate=None,
        ),
    )

    assert result <= 1.0
