"""Unit tests for `src.engines.historical_engine.regime_detection`.

Uses synthetic price series with known characteristics (steady uptrend,
steady downtrend, tight sideways range, choppy high-volatility swings) to
validate the classifier's behavior — not real historical XAUUSD data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.historical_engine.regime_detection import (
    RegimeThresholds,
    classify_regime,
    compute_features,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _make_window(closes: list[float], *, spread_pct: float = 0.1) -> list[Candle]:
    window: list[Candle] = []
    for index, close in enumerate(closes):
        half_spread = close * spread_pct / 100
        window.append(
            Candle(
                symbol_id=_SYMBOL_ID,
                timeframe="H1",
                timestamp=_BASE_TIME + timedelta(hours=index),
                open=close,
                high=close + half_spread,
                low=close - half_spread,
                close=close,
                source="test_fixture",
            )
        )
    return window


def test_compute_features_raises_for_too_few_candles() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        compute_features(_make_window([100.0]))


def test_compute_features_handles_zero_average_price_without_dividing_by_zero() -> None:
    features = compute_features(_make_window([0.0, 0.0]))

    assert features.trend_slope_pct == 0.0
    assert features.range_width_pct == 0.0


def test_compute_features_two_candle_window_has_zero_volatility() -> None:
    # A single bar-over-bar return has no variance to measure (sample
    # stddev needs at least 2 return observations), so volatility is 0.0
    # rather than an ill-defined value.
    features = compute_features(_make_window([3000.0, 3010.0]))

    assert features.volatility_pct == 0.0


def test_classify_regime_detects_steady_uptrend() -> None:
    closes = [3000.0 + index * 5 for index in range(30)]  # ~0.17%/bar drift, low noise

    result = classify_regime(_make_window(closes))

    assert result.regime == "bull_trend"
    assert result.confidence > 0.0


def test_classify_regime_detects_steady_downtrend() -> None:
    closes = [3000.0 - index * 5 for index in range(30)]

    result = classify_regime(_make_window(closes))

    assert result.regime == "bear_trend"


def test_classify_regime_detects_tight_range() -> None:
    closes = [3000.0, 3001.0, 2999.0, 3000.5, 2999.5, 3000.2, 2999.8, 3000.1, 2999.9, 3000.0]

    result = classify_regime(_make_window(closes))

    assert result.regime == "range"


def test_classify_regime_detects_high_volatility() -> None:
    # A palindrome sequence has an exact zero least-squares linear slope,
    # isolating "large bar-to-bar swings" from "net directional trend" so
    # this fixture cannot be confused with a trend by construction.
    closes = [3200.0, 2800.0, 3200.0, 2800.0, 2800.0, 3200.0, 2800.0, 3200.0]

    result = classify_regime(_make_window(closes))

    assert result.regime == "high_volatility"


def test_classify_regime_respects_custom_thresholds() -> None:
    closes = [3000.0 + index * 0.5 for index in range(20)]
    strict_thresholds = RegimeThresholds(trend_slope_pct=10.0)  # unreachable by this series

    result = classify_regime(_make_window(closes), thresholds=strict_thresholds)

    assert result.regime != "bull_trend"


def test_features_are_attached_to_classification() -> None:
    closes = [3000.0 + index * 5 for index in range(30)]

    result = classify_regime(_make_window(closes))

    assert result.features.trend_slope_pct > 0


def test_classify_regime_falls_back_to_low_volatility() -> None:
    # A tiny, non-trending, non-zero-noise series: with the "range" and
    # "trend" thresholds pushed unreachably tight, only the volatility
    # branches remain — this series' real volatility is small, so it
    # should land on "low_volatility" rather than "range" or "transition".
    closes = [3000.0, 3000.5, 2999.7, 3000.2, 2999.9, 3000.1, 2999.8, 3000.0]
    thresholds = RegimeThresholds(
        trend_slope_pct=1000.0, range_width_pct=0.0001, high_volatility_pct=1000.0
    )

    result = classify_regime(_make_window(closes), thresholds=thresholds)

    assert result.regime == "low_volatility"


def test_classify_regime_falls_back_to_transition_when_nothing_matches() -> None:
    # Every threshold is pushed out of reach in both directions, so no
    # branch matches and the classifier must fall back to "transition".
    closes = [3000.0, 3010.0, 2995.0, 3005.0, 2998.0, 3002.0, 2996.0, 3004.0]
    thresholds = RegimeThresholds(
        trend_slope_pct=1000.0,
        range_width_pct=0.0001,
        high_volatility_pct=1000.0,
        low_volatility_pct=0.0001,
    )

    result = classify_regime(_make_window(closes), thresholds=thresholds)

    assert result.regime == "transition"
    assert result.confidence == 0.5
