"""Unit tests for `src.core.macro_analysis.trend_mapping`."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.core.macro_analysis.agent import MacroObservation
from src.core.macro_analysis.trend_mapping import TrendGoldMapping, analyze_series_trend

pytestmark = pytest.mark.unit

_MAPPING = TrendGoldMapping(
    rising_bias="bearish",
    falling_bias="bullish",
    rising_rationale="rising rationale",
    falling_rationale="falling rationale",
)
_BASE_DATE = date(2026, 1, 1)


def _observations(values: list[float]) -> list[MacroObservation]:
    return [
        MacroObservation(observed_on=_BASE_DATE + timedelta(days=30 * index), value=value)
        for index, value in enumerate(values)
    ]


def test_analyze_series_trend_reports_neutral_for_too_few_observations() -> None:
    report = analyze_series_trend(
        "test_agent",
        _observations([1.0, 2.0]),
        _MAPPING,
        trend_threshold_pct=0.5,
        caveat="caveat",
    )

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_series_trend_detects_rising_trend() -> None:
    report = analyze_series_trend(
        "test_agent",
        _observations([1.0, 1.5, 2.0, 2.5, 3.0]),
        _MAPPING,
        trend_threshold_pct=0.5,
        caveat="caveat",
    )

    assert report.bias == "bearish"
    assert report.confidence > 0.0
    assert "rising rationale" in report.supporting_evidence


def test_analyze_series_trend_detects_falling_trend() -> None:
    report = analyze_series_trend(
        "test_agent",
        _observations([5.0, 4.0, 3.0, 2.0, 1.0]),
        _MAPPING,
        trend_threshold_pct=0.5,
        caveat="caveat",
    )

    assert report.bias == "bullish"
    assert "falling rationale" in report.supporting_evidence


def test_analyze_series_trend_reports_neutral_for_flat_series() -> None:
    report = analyze_series_trend(
        "test_agent",
        _observations([2.0, 2.0, 2.0, 2.0]),
        _MAPPING,
        trend_threshold_pct=0.5,
        caveat="caveat",
    )

    assert report.bias == "neutral"
    assert report.confidence == 0.0


def test_analyze_series_trend_always_includes_caveat() -> None:
    report = analyze_series_trend(
        "test_agent",
        _observations([1.0, 2.0, 3.0]),
        _MAPPING,
        trend_threshold_pct=0.5,
        caveat="always shown",
    )

    assert "always shown" in report.unknowns
