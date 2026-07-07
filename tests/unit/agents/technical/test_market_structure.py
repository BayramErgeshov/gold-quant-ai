"""Unit tests for `MarketStructureAgent`.

Candles are built with explicit high/low values (not derived from a
closing-price series) so the intended fractal swing shape is unambiguous.
"""

from __future__ import annotations

import pytest

from src.agents.technical.market_structure import MarketStructureAgent
from tests.unit.agents.technical._helpers import make_candle

pytestmark = pytest.mark.unit


def _uptrend_candles(*, final_close: float = 100.0) -> list:
    # Padding, trough(80), padding, peak(110), padding, trough(90 > 80),
    # padding, peak(130 > 110), padding — a clear Higher-High/Higher-Low
    # sequence with plenty of buffer for lookaround=2 fractal detection.
    highs_lows = [
        (95, 90), (92, 87), (85, 80), (92, 87), (100, 95),
        (108, 103), (115, 110), (108, 103), (98, 93), (95, 90),
        (98, 93), (105, 100), (120, 115), (130, 125), (122, 117),
        (115, 110),
    ]
    candles = []
    for index, (high, low) in enumerate(highs_lows):
        candles.append(
            make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        )
    candles[-1] = make_candle(
        len(highs_lows) - 1,
        open_=candles[-1].open,
        high=candles[-1].high,
        low=candles[-1].low,
        close=final_close,
    )
    return candles


def test_analyze_reports_neutral_with_insufficient_swings() -> None:
    candles = [make_candle(index, open_=100, high=101, low=99, close=100) for index in range(5)]

    report = MarketStructureAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_detects_bullish_structure() -> None:
    candles = _uptrend_candles(final_close=122.0)

    report = MarketStructureAgent().analyze(candles)

    assert report.bias == "bullish"
    assert report.confidence > 0.0
    assert "Higher high confirmed" in report.supporting_evidence
    assert "Higher low confirmed" in report.supporting_evidence


def test_analyze_detects_change_of_character_in_uptrend() -> None:
    # Same bullish swing structure, but the final close breaks below the
    # last swing low (90), invalidating the uptrend.
    candles = _uptrend_candles(final_close=85.0)

    report = MarketStructureAgent().analyze(candles)

    assert report.bias == "neutral"
    assert any("change of character" in note for note in report.opposing_evidence)
    assert 0.0 < report.confidence < 0.75


def _downtrend_candles(*, final_close: float) -> list:
    # A mirror image of `_uptrend_candles` (price -> 210 - price), giving a
    # clear Lower-High/Lower-Low sequence.
    highs_lows = [
        (120, 115), (123, 118), (130, 125), (123, 118), (115, 110),
        (107, 102), (100, 95), (107, 102), (117, 112), (120, 115),
        (117, 112), (110, 105), (95, 90), (85, 80), (93, 88),
        (100, 95),
    ]
    candles = []
    for index, (high, low) in enumerate(highs_lows):
        candles.append(
            make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        )
    candles[-1] = make_candle(
        len(highs_lows) - 1,
        open_=candles[-1].open,
        high=candles[-1].high,
        low=candles[-1].low,
        close=final_close,
    )
    return candles


def test_analyze_detects_bearish_structure() -> None:
    candles = _downtrend_candles(final_close=88.0)

    report = MarketStructureAgent().analyze(candles)

    assert report.bias == "bearish"
    assert report.confidence > 0.0
    assert "Lower high confirmed" in report.supporting_evidence
    assert "Lower low confirmed" in report.supporting_evidence


def test_analyze_detects_change_of_character_in_downtrend() -> None:
    # Same bearish swing structure, but the final close breaks above the
    # last swing high (120), invalidating the downtrend.
    candles = _downtrend_candles(final_close=125.0)

    report = MarketStructureAgent().analyze(candles)

    assert report.bias == "neutral"
    assert any("change of character" in note for note in report.opposing_evidence)
    assert 0.0 < report.confidence < 0.75


def test_analyze_detects_mixed_structure() -> None:
    # Higher high but a lower low: highs and lows disagree on direction.
    highs_lows = [
        (95, 90), (92, 87), (85, 80), (92, 87), (100, 95),
        (108, 103), (115, 110), (108, 103), (98, 93), (95, 60),
        (98, 93), (105, 100), (120, 115), (130, 125), (122, 117),
        (115, 110),
    ]
    candles = [
        make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(highs_lows)
    ]

    report = MarketStructureAgent().analyze(candles)

    assert report.bias == "neutral"
    assert any("mixed" in note for note in report.opposing_evidence)


def test_analyze_reports_metrics_for_explainability() -> None:
    candles = _uptrend_candles(final_close=122.0)

    report = MarketStructureAgent().analyze(candles)

    assert "last_swing_high" in report.metrics
    assert "last_swing_low" in report.metrics
