"""Unit tests for correlation-based concentration control."""

from __future__ import annotations

import pytest

from src.engines.risk_engine.correlation import (
    compute_correlated_exposure_pct,
    is_concentration_excessive,
)

pytestmark = pytest.mark.unit


def test_computes_zero_for_no_exposure() -> None:
    assert compute_correlated_exposure_pct({}, {}) == 0.0


def test_uncorrelated_instrument_contributes_nothing() -> None:
    exposure = {"NASDAQ": 5.0}
    correlations = {"NASDAQ": 0.0}

    assert compute_correlated_exposure_pct(exposure, correlations) == 0.0


def test_missing_correlation_entry_is_treated_as_uncorrelated() -> None:
    exposure = {"COPPER": 5.0}

    assert compute_correlated_exposure_pct(exposure, {}) == 0.0


def test_negative_correlation_still_counts_via_absolute_value() -> None:
    exposure = {"DXY": 4.0}
    correlations = {"DXY": -0.8}

    assert compute_correlated_exposure_pct(exposure, correlations) == pytest.approx(3.2)


def test_sums_across_multiple_correlated_instruments() -> None:
    exposure = {"SILVER": 3.0, "DXY": 2.0}
    correlations = {"SILVER": 0.9, "DXY": -0.5}

    assert compute_correlated_exposure_pct(exposure, correlations) == pytest.approx(
        3.0 * 0.9 + 2.0 * 0.5
    )


def test_is_concentration_excessive_true_when_over_limit() -> None:
    exposure = {"SILVER": 10.0}
    correlations = {"SILVER": 0.9}

    assert is_concentration_excessive(exposure, correlations, max_correlated_exposure_pct=5.0)


def test_is_concentration_excessive_false_when_within_limit() -> None:
    exposure = {"SILVER": 2.0}
    correlations = {"SILVER": 0.9}

    assert not is_concentration_excessive(
        exposure, correlations, max_correlated_exposure_pct=5.0
    )
