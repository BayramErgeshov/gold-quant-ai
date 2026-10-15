"""Unit tests for synthetic order flow analysis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.order_flow_engine.synthetic_order_flow import (
    analyze_synthetic_order_flow,
    compute_delta_approximation,
    compute_volume_profile,
    compute_vwap,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    offset: int, *, open_: float, high: float, low: float, close: float, volume: float = 100.0
) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=offset * 5),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source="test_fixture",
    )


def test_compute_volume_profile_is_empty_for_no_candles() -> None:
    profile = compute_volume_profile([])

    assert profile.bins == []
    assert profile.point_of_control is None


def test_compute_volume_profile_finds_point_of_control() -> None:
    # Most volume concentrated near 105 -> POC bin should cover that price.
    candles = [
        _candle(0, open_=100, high=101, low=99, close=100, volume=10),
        _candle(1, open_=105, high=106, low=104, close=105, volume=1000),
        _candle(2, open_=110, high=111, low=109, close=110, volume=10),
    ]

    profile = compute_volume_profile(candles, bin_count=10)

    assert profile.point_of_control is not None
    assert 104 <= profile.point_of_control.midpoint <= 106
    assert profile.value_area != []
    assert profile.high_volume_nodes != []


def test_compute_volume_profile_is_empty_when_price_range_is_zero() -> None:
    candles = [_candle(0, open_=100, high=100, low=100, close=100) for _ in range(5)]

    profile = compute_volume_profile(candles)

    assert profile.bins == []
    assert profile.point_of_control is None


def test_compute_volume_profile_is_empty_when_candles_have_no_volume() -> None:
    candles = [
        _candle(0, open_=100, high=101, low=99, close=100, volume=0.0),
        _candle(1, open_=101, high=102, low=100, close=101, volume=0.0),
    ]

    profile = compute_volume_profile(candles)

    assert profile.bins != []  # bins exist (real price range)
    assert profile.point_of_control is None
    assert profile.value_area == []


def test_compute_volume_profile_expands_toward_the_low_side_when_poc_is_near_the_high_end() -> None:
    # A lot of volume concentrated at the top of the range, but not enough
    # on its own to reach 70% of the total -> value-area expansion must
    # walk toward the low side (the only side available, since the POC is
    # at the highest bin) to reach the threshold.
    candles = [
        _candle(i, open_=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=100.0)
        for i in range(15)
    ] + [_candle(15, open_=115, high=116, low=114, close=115, volume=1000.0)]

    profile = compute_volume_profile(candles, bin_count=10)

    assert profile.point_of_control is not None
    assert len(profile.value_area) > 1


def test_compute_vwap_returns_none_without_volume() -> None:
    candles = [_candle(0, open_=100, high=101, low=99, close=100, volume=0.0)]

    assert compute_vwap(candles) is None


def test_compute_vwap_weights_by_volume() -> None:
    candles = [
        _candle(0, open_=100, high=100, low=100, close=100, volume=1.0),
        _candle(1, open_=200, high=200, low=200, close=200, volume=99.0),
    ]

    vwap = compute_vwap(candles)

    assert vwap is not None
    assert vwap == pytest.approx(199.0, abs=0.1)


def test_compute_delta_approximation_signs_match_candle_direction() -> None:
    candles = [
        _candle(0, open_=100, high=102, low=99, close=101, volume=50.0),  # up
        _candle(1, open_=101, high=102, low=98, close=99, volume=30.0),  # down
        _candle(2, open_=99, high=100, low=98, close=99, volume=20.0),  # flat
    ]

    delta = compute_delta_approximation(candles)

    assert delta.per_candle_delta == [50.0, -30.0, 0.0]
    assert delta.net_delta == pytest.approx(20.0)


def test_analyze_synthetic_order_flow_neutral_with_too_few_candles() -> None:
    result = analyze_synthetic_order_flow([_candle(0, open_=100, high=101, low=99, close=100)])

    assert result.confidence == 0.0
    assert result.bullish_probability == 0.0
    assert result.bearish_probability == 0.0


def test_analyze_synthetic_order_flow_leans_bullish_on_uptrend() -> None:
    candles = [
        _candle(i, open_=100 + i, high=101 + i, low=99 + i, close=101 + i, volume=100.0)
        for i in range(20)
    ]

    result = analyze_synthetic_order_flow(candles)

    assert result.bullish_probability > result.bearish_probability
    assert result.confidence > 0.0
    assert result.vwap is not None


def test_analyze_synthetic_order_flow_caps_confidence_below_one() -> None:
    candles = [
        _candle(i, open_=100 + i, high=101 + i, low=99 + i, close=101 + i, volume=100.0)
        for i in range(20)
    ]

    result = analyze_synthetic_order_flow(candles)

    assert result.confidence <= 0.6


def test_analyze_synthetic_order_flow_detects_a_fair_value_gap() -> None:
    candles = [
        _candle(0, open_=100, high=101, low=99, close=100, volume=50.0),
        _candle(1, open_=100, high=101, low=99, close=100, volume=50.0),
        _candle(2, open_=100, high=101, low=99, close=100, volume=50.0),
        _candle(3, open_=100, high=101, low=99, close=100, volume=50.0),
        # Displacement candle creating a bullish imbalance (gap between
        # candle 3's high=101 and candle 5's low=110).
        _candle(4, open_=101, high=112, low=101, close=111, volume=500.0),
        _candle(5, open_=111, high=113, low=110, close=112, volume=50.0),
        _candle(6, open_=112, high=114, low=111, close=113, volume=50.0),
        _candle(7, open_=113, high=115, low=112, close=114, volume=50.0),
        _candle(8, open_=114, high=116, low=113, close=115, volume=50.0),
        _candle(9, open_=115, high=117, low=114, close=116, volume=50.0),
    ]

    result = analyze_synthetic_order_flow(candles)

    assert result.fair_value_gaps != []
    assert any("fair value gap" in note for note in result.supporting_evidence)
