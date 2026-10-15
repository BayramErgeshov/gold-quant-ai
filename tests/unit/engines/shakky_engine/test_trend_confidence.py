"""Unit tests for the Trend Confidence Engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.shakky_engine.trend_confidence import assess_trend_confidence
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    offset: int,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
    timeframe: str = "M5",
    minutes_per_bar: int = 5,
) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe=timeframe,
        timestamp=_BASE_TIME + timedelta(minutes=minutes_per_bar * offset),
        open=close,
        high=high if high is not None else close + 0.3,
        low=low if low is not None else close - 0.3,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _trending_candles(
    count: int,
    *,
    start: float,
    step: float,
    timeframe: str = "M5",
    minutes_per_bar: int = 5,
) -> list[Candle]:
    """A steadily trending series -- steep enough to stack EMA9/21/50 and expand ATR."""
    candles = []
    for i in range(count):
        close = start + step * i * i * 0.02
        candles.append(
            _candle(
                i,
                close=close,
                high=close + abs(step) * 0.6,
                low=close - abs(step) * 0.6,
                timeframe=timeframe,
                minutes_per_bar=minutes_per_bar,
            )
        )
    return candles


def _flat_candles(count: int, *, price: float = 2000.0, timeframe: str = "M5") -> list[Candle]:
    return [
        _candle(i, close=price, high=price + 0.5, low=price - 0.5, timeframe=timeframe)
        for i in range(count)
    ]


def test_strong_uptrend_on_every_timeframe_scores_high_and_expects_continuation() -> None:
    m5 = _trending_candles(120, start=1900.0, step=1.0)

    assessment = assess_trend_confidence(
        direction="buy",
        entry_price=m5[-1].close,
        d1_candles=_trending_candles(
            80, start=1850.0, step=1.0, timeframe="D1", minutes_per_bar=1440
        ),
        h4_candles=_trending_candles(
            80, start=1870.0, step=1.0, timeframe="H4", minutes_per_bar=240
        ),
        h1_candles=_trending_candles(
            80, start=1880.0, step=1.0, timeframe="H1", minutes_per_bar=60
        ),
        m15_candles=_trending_candles(
            80, start=1890.0, step=1.0, timeframe="M15", minutes_per_bar=15
        ),
        m5_candles=m5,
        dxy_candles=None,
    )

    assert assessment.score > 50.0
    assert assessment.level in ("strong", "exceptional")
    assert assessment.reasons


def test_flat_market_scores_low_and_does_not_expect_continuation() -> None:
    m5 = _flat_candles(120)

    assessment = assess_trend_confidence(
        direction="buy",
        entry_price=m5[-1].close,
        d1_candles=None,
        h4_candles=None,
        h1_candles=None,
        m15_candles=None,
        m5_candles=m5,
        dxy_candles=None,
    )

    assert assessment.level == "minor"
    assert assessment.continuation_likely is False


def test_missing_higher_timeframes_does_not_crash_and_still_scores() -> None:
    m5 = _trending_candles(120, start=1900.0, step=1.0)

    assessment = assess_trend_confidence(
        direction="buy",
        entry_price=m5[-1].close,
        d1_candles=None,
        h4_candles=None,
        h1_candles=None,
        m15_candles=None,
        m5_candles=m5,
        dxy_candles=None,
    )

    assert 0.0 <= assessment.score <= 100.0
    assert "trend_agreement:1/1_timeframes_agree" in assessment.reasons


def test_news_imminent_discounts_the_score() -> None:
    m5 = _trending_candles(120, start=1900.0, step=1.0)

    calm = assess_trend_confidence(
        direction="buy",
        entry_price=m5[-1].close,
        d1_candles=None,
        h4_candles=None,
        h1_candles=None,
        m15_candles=None,
        m5_candles=m5,
        dxy_candles=None,
        news_risk_imminent=False,
    )
    imminent = assess_trend_confidence(
        direction="buy",
        entry_price=m5[-1].close,
        d1_candles=None,
        h4_candles=None,
        h1_candles=None,
        m15_candles=None,
        m5_candles=m5,
        dxy_candles=None,
        news_risk_imminent=True,
    )

    assert imminent.score < calm.score
    assert "news_risk_imminent:score_discounted" in imminent.reasons


def test_too_few_candles_returns_minor_without_raising() -> None:
    m5 = _flat_candles(5)

    assessment = assess_trend_confidence(
        direction="sell",
        entry_price=m5[-1].close,
        d1_candles=None,
        h4_candles=None,
        h1_candles=None,
        m15_candles=None,
        m5_candles=m5,
        dxy_candles=None,
    )

    assert assessment.level == "minor"
    assert assessment.score == 0.0
