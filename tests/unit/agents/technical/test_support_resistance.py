"""Unit tests for `SupportResistanceAgent`."""

from __future__ import annotations

import pytest

from src.agents.technical.support_resistance import SupportResistanceAgent, _cluster_levels
from tests.unit.agents.technical._helpers import make_candle

pytestmark = pytest.mark.unit


def _range_bound_candles() -> list:
    # Repeated touches of ~110 resistance and ~90 support, ending mid-range.
    highs_lows = [
        (95, 90), (109, 104), (95, 91), (89, 85), (95, 91),
        (110, 105), (95, 91), (91, 86), (96, 91), (109, 104),
        (100, 95),
    ]
    return [
        make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(highs_lows)
    ]


def test_analyze_reports_unknown_with_no_swings() -> None:
    candles = [make_candle(index, open_=100, high=101, low=99, close=100) for index in range(3)]

    report = SupportResistanceAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_finds_nearest_support_and_resistance() -> None:
    report = SupportResistanceAgent(cluster_tolerance_pct=2.0).analyze(_range_bound_candles())

    assert "nearest_support" in report.metrics
    assert "nearest_resistance" in report.metrics
    assert report.metrics["nearest_support"] < report.metrics["nearest_resistance"]
    assert report.confidence > 0.0


def test_analyze_reports_touch_counts() -> None:
    report = SupportResistanceAgent(cluster_tolerance_pct=2.0).analyze(_range_bound_candles())

    assert report.metrics["nearest_resistance_touches"] >= 1
    assert report.metrics["nearest_support_touches"] >= 1


def test_analyze_reports_unknown_when_no_support_below_price() -> None:
    candles = [*_range_bound_candles(), make_candle(11, open_=60, high=61, low=40, close=50)]

    report = SupportResistanceAgent(cluster_tolerance_pct=2.0).analyze(candles)

    assert "nearest_support" not in report.metrics
    assert any("No support level" in note for note in report.unknowns)


def test_analyze_reports_unknown_when_no_resistance_above_price() -> None:
    candles = [*_range_bound_candles(), make_candle(11, open_=150, high=151, low=149, close=150)]

    report = SupportResistanceAgent(cluster_tolerance_pct=2.0).analyze(candles)

    assert "nearest_resistance" not in report.metrics
    assert any("No resistance level" in note for note in report.unknowns)


def test_cluster_levels_returns_empty_for_no_prices() -> None:
    assert _cluster_levels([], tolerance_pct=1.0) == []


def test_cluster_levels_separates_distant_prices_into_multiple_clusters() -> None:
    clusters = _cluster_levels([100.0, 200.0], tolerance_pct=1.0)

    assert len(clusters) == 2
