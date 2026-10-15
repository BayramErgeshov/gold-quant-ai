"""Unit tests for the Hold Manager."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.shakky_engine.hold_manager import assess_hold
from src.engines.shakky_engine.trend_confidence import TrendConfidenceAssessment
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(offset: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=5 * offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _plain_uptrend(count: int = 10, *, start: float = 1900.0) -> list[Candle]:
    return [
        _candle(
            i, open_=start + i, high=start + i + 0.5, low=start + i - 0.5, close=start + i + 0.3
        )
        for i in range(count)
    ]


def _assessment(*, level: str, continuation_likely: bool) -> TrendConfidenceAssessment:
    return TrendConfidenceAssessment(
        level=level,  # type: ignore[arg-type]
        score=80.0 if level != "minor" else 10.0,
        continuation_likely=continuation_likely,
        reasons=["fixture"],
    )


def test_holds_a_strong_uptrend_with_no_opposing_signal() -> None:
    candles = _plain_uptrend()

    result = assess_hold(
        position_direction="buy",
        trend_confidence=_assessment(level="strong", continuation_likely=True),
        m5_candles=candles,
    )

    assert result.should_hold is True
    assert result.continuation_expected is True
    assert result.reversal_expected is False


def test_exhausted_trend_confidence_triggers_reversal_expected() -> None:
    candles = _plain_uptrend()

    result = assess_hold(
        position_direction="buy",
        trend_confidence=_assessment(level="minor", continuation_likely=False),
        m5_candles=candles,
    )

    assert result.should_hold is False
    assert result.reversal_expected is True
    assert "trend_confidence_dropped_to_minor" in result.reasons


def test_opposing_bearish_engulfing_triggers_reversal_for_a_buy_position() -> None:
    candles = _plain_uptrend(count=8)
    # Append a clean bearish engulfing candle against the held buy.
    previous = _candle(8, open_=1950.0, high=1951.0, low=1949.5, close=1950.8)
    engulfing = _candle(9, open_=1951.2, high=1951.5, low=1945.0, close=1945.5)
    candles = [*candles, previous, engulfing]

    result = assess_hold(
        position_direction="buy",
        trend_confidence=_assessment(level="strong", continuation_likely=True),
        m5_candles=candles,
    )

    assert result.reversal_expected is True
    assert result.should_hold is False
    assert any("opposing" in reason for reason in result.reasons)


def test_too_few_candles_for_reversal_check_still_returns_a_result() -> None:
    result = assess_hold(
        position_direction="sell",
        trend_confidence=_assessment(level="strong", continuation_likely=True),
        m5_candles=[_candle(0, open_=1900.0, high=1901.0, low=1899.0, close=1900.5)],
    )

    assert result.should_hold is True
