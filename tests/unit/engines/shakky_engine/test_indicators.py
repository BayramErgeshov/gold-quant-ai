"""Unit tests for Shakky's own new indicator math."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.shakky_engine.indicators import (
    bollinger_bands,
    nearest_psychological_levels,
    nearest_resistance,
    nearest_support,
    support_resistance_levels,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    offset: int, *, close: float, high: float | None = None, low: float | None = None
) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=5 * offset),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def test_bollinger_bands_returns_none_with_too_few_closes() -> None:
    assert bollinger_bands([2000.0] * 10) is None


def test_bollinger_bands_flat_series_has_zero_width() -> None:
    bands = bollinger_bands([2000.0] * 20)

    assert bands is not None
    assert bands.middle_band == pytest.approx(2000.0)
    assert bands.upper_band == pytest.approx(2000.0)
    assert bands.lower_band == pytest.approx(2000.0)


def test_bollinger_bands_widens_with_dispersion() -> None:
    closes = [2000.0 + (10.0 if i % 2 == 0 else -10.0) for i in range(20)]

    bands = bollinger_bands(closes)

    assert bands is not None
    assert bands.upper_band > bands.middle_band > bands.lower_band


def test_nearest_psychological_levels_brackets_the_price() -> None:
    below, above = nearest_psychological_levels(2034.0, step=10.0)

    assert below == pytest.approx(2030.0)
    assert above == pytest.approx(2040.0)


def test_nearest_psychological_levels_exact_multiple() -> None:
    below, above = nearest_psychological_levels(2030.0, step=10.0)

    assert below == pytest.approx(2030.0)
    assert above == pytest.approx(2030.0)


def test_nearest_psychological_levels_rejects_non_positive_step() -> None:
    with pytest.raises(ValueError, match="step"):
        nearest_psychological_levels(2000.0, step=0.0)


def _swing_candles() -> list[Candle]:
    # A clean W-shape: swing low, swing high, swing low, swing high --
    # produces one clear support cluster and one clear resistance cluster.
    closes = [2000, 1990, 1980, 1990, 2000, 2010, 2020, 2010, 2000, 1990, 1980, 1990, 2000]
    return [_candle(i, close=float(c)) for i, c in enumerate(closes)]


def test_support_resistance_levels_finds_clusters() -> None:
    support, resistance = support_resistance_levels(_swing_candles(), lookaround=2)

    assert support
    assert resistance
    assert min(support) < min(resistance)


def test_support_resistance_levels_empty_for_too_short_a_series() -> None:
    support, resistance = support_resistance_levels(_swing_candles()[:3])

    assert support == []
    assert resistance == []


def test_nearest_support_picks_the_highest_level_at_or_below_price() -> None:
    assert nearest_support([1980.0, 1990.0, 2010.0], 2000.0) == pytest.approx(1990.0)


def test_nearest_support_none_when_all_levels_are_above() -> None:
    assert nearest_support([2010.0, 2020.0], 2000.0) is None


def test_nearest_resistance_picks_the_lowest_level_at_or_above_price() -> None:
    assert nearest_resistance([1980.0, 2010.0, 2020.0], 2000.0) == pytest.approx(2010.0)


def test_nearest_resistance_none_when_all_levels_are_below() -> None:
    assert nearest_resistance([1980.0, 1990.0], 2000.0) is None
