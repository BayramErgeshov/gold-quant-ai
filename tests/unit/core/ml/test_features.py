"""Unit tests for ML feature engineering."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.ml.features import FEATURE_NAMES, build_feature_vector
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _make_window(closes: list[float], *, volumes: list[float] | None = None) -> list[Candle]:
    window: list[Candle] = []
    for index, close in enumerate(closes):
        window.append(
            Candle(
                symbol_id=_SYMBOL_ID,
                timeframe="H1",
                timestamp=_BASE_TIME + timedelta(hours=index),
                open=close,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=volumes[index] if volumes else None,
                source="test_fixture",
            )
        )
    return window


def test_returns_all_zero_features_for_window_below_minimum() -> None:
    features = build_feature_vector(_make_window([100.0]))

    assert features == dict.fromkeys(FEATURE_NAMES, 0.0)


def test_computes_positive_momentum_for_rising_prices() -> None:
    closes = [100.0 + index for index in range(10)]
    features = build_feature_vector(_make_window(closes))

    assert features["momentum_pct"] > 0
    assert features["trend_slope_pct"] > 0


def test_computes_negative_momentum_for_falling_prices() -> None:
    closes = [110.0 - index for index in range(10)]
    features = build_feature_vector(_make_window(closes))

    assert features["momentum_pct"] < 0
    assert features["trend_slope_pct"] < 0


def test_computes_volume_trend_when_volume_present() -> None:
    closes = [100.0] * 5
    volumes = [1000.0, 1000.0, 1000.0, 1000.0, 1500.0]
    features = build_feature_vector(_make_window(closes, volumes=volumes))

    assert features["volume_trend_pct"] == pytest.approx(50.0)


def test_volume_trend_is_zero_when_volume_missing() -> None:
    closes = [100.0] * 5
    features = build_feature_vector(_make_window(closes))

    assert features["volume_trend_pct"] == 0.0


def test_feature_vector_keys_match_feature_names() -> None:
    features = build_feature_vector(_make_window([100.0, 101.0, 102.0]))

    assert set(features) == set(FEATURE_NAMES)
