"""Unit tests for ML label generation."""

from __future__ import annotations

import pytest

from src.core.ml.labels import LabelThresholds, compute_label

pytestmark = pytest.mark.unit


def test_small_positive_return_is_neutral() -> None:
    assert compute_label(0.05) == "neutral"


def test_small_negative_return_is_neutral() -> None:
    assert compute_label(-0.05) == "neutral"


def test_moderate_positive_return_is_bullish() -> None:
    assert compute_label(0.5) == "bullish"


def test_moderate_negative_return_is_bearish() -> None:
    assert compute_label(-0.5) == "bearish"


def test_large_positive_return_is_strong_bullish() -> None:
    assert compute_label(1.5) == "strong_bullish"


def test_large_negative_return_is_strong_bearish() -> None:
    assert compute_label(-1.5) == "strong_bearish"


def test_boundary_at_neutral_band_is_neutral() -> None:
    assert compute_label(0.1) == "neutral"


def test_boundary_at_strong_move_is_strong_bullish() -> None:
    assert compute_label(1.0) == "strong_bullish"


def test_custom_thresholds_are_respected() -> None:
    thresholds = LabelThresholds(neutral_band_pct=1.0, strong_move_pct=5.0)

    assert compute_label(0.5, thresholds) == "neutral"
    assert compute_label(2.0, thresholds) == "bullish"
    assert compute_label(6.0, thresholds) == "strong_bullish"
