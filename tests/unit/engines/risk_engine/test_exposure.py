"""Unit tests for exposure limit checks."""

from __future__ import annotations

import pytest

from src.engines.risk_engine.exposure import ExposureLimits, ExposureState, check_exposure_limits

pytestmark = pytest.mark.unit

_LIMITS = ExposureLimits(
    max_total_exposure_pct=10.0,
    max_instrument_exposure_pct=5.0,
    max_correlated_exposure_pct=8.0,
    max_session_exposure_pct=6.0,
    max_daily_exposure_pct=9.0,
)


def test_no_breaches_when_within_all_limits() -> None:
    state = ExposureState()

    assert check_exposure_limits(state, 2.0, _LIMITS) == []


def test_reports_total_exposure_breach() -> None:
    state = ExposureState(total_exposure_pct=9.0)

    reasons = check_exposure_limits(state, 2.0, _LIMITS)

    assert any("total_exposure_exceeded" in reason for reason in reasons)


def test_reports_instrument_exposure_breach() -> None:
    state = ExposureState(instrument_exposure_pct=4.0)

    reasons = check_exposure_limits(state, 2.0, _LIMITS)

    assert any("instrument_exposure_exceeded" in reason for reason in reasons)


def test_reports_multiple_breaches_simultaneously() -> None:
    state = ExposureState(
        total_exposure_pct=9.5,
        instrument_exposure_pct=4.5,
        correlated_exposure_pct=7.5,
        session_exposure_pct=5.5,
        daily_exposure_pct=8.5,
    )

    reasons = check_exposure_limits(state, 1.0, _LIMITS)

    assert len(reasons) == 5


def test_exact_limit_is_not_a_breach() -> None:
    state = ExposureState(total_exposure_pct=8.0)

    assert check_exposure_limits(state, 2.0, _LIMITS) == []
