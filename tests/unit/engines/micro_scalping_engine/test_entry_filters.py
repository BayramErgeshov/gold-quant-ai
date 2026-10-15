"""Unit tests for Micro Scalping's own entry gates."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.execution.mt5_client import SymbolTick
from src.engines.micro_scalping_engine.entry_filters import (
    check_liquidity,
    check_momentum,
    check_recent_high_impact_news,
    check_spread,
)
from src.models.candle import Candle
from src.models.news_article import NewsArticle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
# 13:00 UTC -- inside the London/New York overlap window.
_LIQUID_TIME = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
# 02:00 UTC -- Asia session only.
_ILLIQUID_TIME = datetime(2026, 1, 5, 2, 0, tzinfo=UTC)


def _tick(*, bid: float, ask: float, timestamp: datetime = _LIQUID_TIME) -> SymbolTick:
    return SymbolTick(bid=bid, ask=ask, timestamp=timestamp)


def _candle(offset: int, *, close: float) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M1",
        timestamp=_LIQUID_TIME + timedelta(minutes=offset),
        open=close,
        high=close + 0.05,
        low=close - 0.05,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _article(*, minutes_ago: float, importance: float = 0.9) -> NewsArticle:
    return NewsArticle(
        title="Fed surprise rate decision",
        source="test",
        url=f"https://example.test/{uuid.uuid4()}",
        content_hash=str(uuid.uuid4()),
        published_at=_LIQUID_TIME - timedelta(minutes=minutes_ago),
        importance_score=importance,
    )


def test_check_spread_passes_a_tight_spread() -> None:
    result = check_spread(_tick(bid=2000.0, ask=2000.03), max_spread_points=5.0)

    assert result.passed is True


def test_check_spread_rejects_a_wide_spread() -> None:
    result = check_spread(_tick(bid=2000.0, ask=2000.10), max_spread_points=5.0)

    assert result.passed is False
    assert any("spread_too_wide" in reason for reason in result.reasons)


def test_check_liquidity_passes_during_the_london_new_york_overlap() -> None:
    result = check_liquidity(_tick(bid=2000.0, ask=2000.03, timestamp=_LIQUID_TIME))

    assert result.passed is True


def test_check_liquidity_rejects_the_asia_session() -> None:
    result = check_liquidity(_tick(bid=2000.0, ask=2000.03, timestamp=_ILLIQUID_TIME))

    assert result.passed is False
    assert any("insufficient_liquidity_session" in reason for reason in result.reasons)


def test_check_momentum_passes_on_a_strong_recent_burst() -> None:
    candles = [_candle(i, close=2000.0) for i in range(20)]
    candles += [_candle(20 + i, close=2000.0 + i * 2.0) for i in range(3)]

    result = check_momentum(candles)

    assert result.passed is True
    assert any("momentum_burst_bullish" in reason for reason in result.reasons)


def test_check_momentum_rejects_a_flat_market() -> None:
    candles = [_candle(i, close=2000.0) for i in range(20)]

    result = check_momentum(candles)

    assert result.passed is False
    assert result.reasons == ["no_momentum_burst"]


def test_check_recent_high_impact_news_passes_without_any_data() -> None:
    result = check_recent_high_impact_news([], now=_LIQUID_TIME)

    assert result.passed is True


def test_check_recent_high_impact_news_blocks_on_a_just_published_article() -> None:
    result = check_recent_high_impact_news(
        [_article(minutes_ago=5.0)], now=_LIQUID_TIME, blackout_minutes=15.0
    )

    assert result.passed is False
    assert any("recent_high_impact_news" in reason for reason in result.reasons)


def test_check_recent_high_impact_news_passes_once_outside_the_blackout_window() -> None:
    result = check_recent_high_impact_news(
        [_article(minutes_ago=30.0)], now=_LIQUID_TIME, blackout_minutes=15.0
    )

    assert result.passed is True
