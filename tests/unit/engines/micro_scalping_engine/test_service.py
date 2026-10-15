"""Unit tests for `MicroScalpingAnalysisService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.execution.mt5_client import SymbolTick
from src.engines.micro_scalping_engine.service import MicroScalpingAnalysisService
from src.engines.shakky_engine.service import ShakkyAnalysisService
from src.models.candle import Candle
from src.models.news_article import NewsArticle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
# 13:00 UTC on a Monday -- inside the London/New York overlap, always liquid.
_BASE_TIME = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)


def _tick(price: float, *, spread: float = 0.03) -> SymbolTick:
    return SymbolTick(bid=price - spread / 2, ask=price + spread / 2, timestamp=_BASE_TIME)


def _candle(offset: int, *, close: float, minutes_per_bar: int) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M1",
        timestamp=_BASE_TIME + timedelta(minutes=minutes_per_bar * offset),
        open=close,
        high=close + 0.3,
        low=close - 0.3,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _strong_uptrend(
    count: int = 80, *, start: float = 1900.0, minutes_per_bar: int = 5
) -> list[Candle]:
    return [
        _candle(i, close=start + i * i * 0.05, minutes_per_bar=minutes_per_bar)
        for i in range(count)
    ]


def _flat(count: int = 80, *, price: float = 2000.0, minutes_per_bar: int = 5) -> list[Candle]:
    return [_candle(i, close=price, minutes_per_bar=minutes_per_bar) for i in range(count)]


def _service() -> MicroScalpingAnalysisService:
    return MicroScalpingAnalysisService(shakky_service=ShakkyAnalysisService())


async def test_passes_through_no_signal_when_shakky_itself_finds_none() -> None:
    flat_m5 = _flat()
    flat_m1 = _flat(minutes_per_bar=1)
    service = _service()

    outcome = await service.analyze(
        m1_candles=flat_m1,
        m5_candles=flat_m5,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=_tick(2000.0),
        recent_high_importance_news=[],
        min_confidence=0.0,
    )

    assert outcome.signal is None


async def test_blocks_on_wide_spread_even_with_a_qualifying_shakky_signal() -> None:
    m5_candles = _strong_uptrend()
    m1_candles = _strong_uptrend(minutes_per_bar=1)
    service = _service()

    outcome = await service.analyze(
        m1_candles=m1_candles,
        m5_candles=m5_candles,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=_tick(m5_candles[-1].close, spread=1.0),
        recent_high_importance_news=[],
        min_confidence=0.0,
        max_spread_points=0.01,
    )

    assert outcome.signal is None
    assert any("spread_too_wide" in reason for reason in outcome.reasons)


async def test_blocks_on_illiquid_session_even_with_a_qualifying_shakky_signal() -> None:
    m5_candles = _strong_uptrend()
    m1_candles = _strong_uptrend(minutes_per_bar=1)
    service = _service()
    asia_tick = SymbolTick(
        bid=m5_candles[-1].close - 0.01,
        ask=m5_candles[-1].close + 0.01,
        timestamp=_BASE_TIME.replace(hour=2),
    )

    outcome = await service.analyze(
        m1_candles=m1_candles,
        m5_candles=m5_candles,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=asia_tick,
        recent_high_importance_news=[],
        min_confidence=0.0,
    )

    assert outcome.signal is None
    assert any("insufficient_liquidity_session" in reason for reason in outcome.reasons)


async def test_blocks_when_m1_shows_no_momentum_burst() -> None:
    m5_candles = _strong_uptrend()
    flat_m1 = _flat(minutes_per_bar=1)
    service = _service()

    outcome = await service.analyze(
        m1_candles=flat_m1,
        m5_candles=m5_candles,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=_tick(m5_candles[-1].close),
        recent_high_importance_news=[],
        min_confidence=0.0,
    )

    assert outcome.signal is None
    assert any("no_momentum_burst" in reason for reason in outcome.reasons)


async def test_blocks_when_confidence_is_below_the_configured_minimum() -> None:
    # Trend Confidence is capped at 100.0 -- a threshold just above that
    # ceiling deterministically blocks regardless of how strong the
    # synthetic market data is, without needing a "moderate" scenario.
    m5_candles = _strong_uptrend()
    m1_candles = _strong_uptrend(minutes_per_bar=1)
    service = _service()

    outcome = await service.analyze(
        m1_candles=m1_candles,
        m5_candles=m5_candles,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=_tick(m5_candles[-1].close),
        recent_high_importance_news=[],
        min_confidence=100.1,
    )

    assert outcome.signal is None
    assert outcome.trend_confidence_score is not None
    assert any("confidence_below_threshold" in reason for reason in outcome.reasons)


async def test_produces_a_signal_inheriting_shakkys_entry_and_stop_loss() -> None:
    m5_candles = _strong_uptrend()
    m1_candles = _strong_uptrend(minutes_per_bar=1)
    service = _service()

    outcome = await service.analyze(
        m1_candles=m1_candles,
        m5_candles=m5_candles,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=_tick(m5_candles[-1].close),
        recent_high_importance_news=[],
        min_confidence=0.0,
    )

    assert outcome.signal is not None
    assert outcome.signal.direction == "buy"
    assert outcome.signal.stop_loss < outcome.signal.entry_price
    assert outcome.trend_confidence_score is not None


async def test_blocks_on_a_just_published_high_impact_article() -> None:
    m5_candles = _strong_uptrend()
    m1_candles = _strong_uptrend(minutes_per_bar=1)
    service = _service()
    article = NewsArticle(
        title="Surprise Fed decision",
        source="test",
        url="https://example.test/1",
        content_hash=str(uuid.uuid4()),
        published_at=_BASE_TIME - timedelta(minutes=5),
        importance_score=0.9,
    )

    outcome = await service.analyze(
        m1_candles=m1_candles,
        m5_candles=m5_candles,
        m15_candles=None,
        h1_candles=None,
        dxy_candles=None,
        tick=_tick(m5_candles[-1].close),
        recent_high_importance_news=[article],
        min_confidence=0.0,
    )

    assert outcome.signal is None
    assert any("recent_high_impact_news" in reason for reason in outcome.reasons)
