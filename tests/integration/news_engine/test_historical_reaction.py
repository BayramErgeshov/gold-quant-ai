"""Integration tests for news category historical reaction measurement."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.news_engine.historical_reaction import measure_historical_reaction
from src.models.candle import Candle
from src.models.news_article import NewsArticle
from src.repositories.candle_repository import CandleRepository

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _article(published_at: datetime) -> NewsArticle:
    return NewsArticle(
        title="Fed holds rates steady",
        source="reuters.com",
        published_at=published_at,
        category="central_bank",
        content_hash=f"hash-{published_at.isoformat()}",
    )


def _candles_from(start: datetime, closes: list[float]) -> list[Candle]:
    return [
        Candle(
            symbol_id=_SYMBOL_ID,
            timeframe="M15",
            timestamp=start + timedelta(minutes=15 * i),
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            source="test_fixture",
        )
        for i, close in enumerate(closes)
    ]


async def test_returns_none_with_too_few_measurable_articles(session: AsyncSession) -> None:
    repository = CandleRepository(session)
    await repository.insert_new(_candles_from(_BASE_TIME, [2000.0, 2001.0, 2002.0]))
    articles = [_article(_BASE_TIME)]

    result = await measure_historical_reaction(
        category="central_bank",
        articles=articles,
        candle_repository=repository,
        symbol_id=_SYMBOL_ID,
        timeframe="M15",
        forward_bars=2,
    )

    assert result is None


async def test_measures_average_best_and_worst_case_reaction(session: AsyncSession) -> None:
    repository = CandleRepository(session)
    articles = []
    for i in range(6):
        published_at = _BASE_TIME + timedelta(days=i)
        # Each article's own price series rises by a different amount --
        # a real, distinct forward return per article, not a fabricated
        # uniform reaction.
        await repository.insert_new(
            _candles_from(published_at, [2000.0, 2000.0 + i, 2000.0 + 2 * i])
        )
        articles.append(_article(published_at))

    result = await measure_historical_reaction(
        category="central_bank",
        articles=articles,
        candle_repository=repository,
        symbol_id=_SYMBOL_ID,
        timeframe="M15",
        forward_bars=2,
    )

    assert result is not None
    assert result.category == "central_bank"
    assert result.sample_size == 6
    assert result.best_case_return_pct > result.average_return_pct
    assert result.worst_case_return_pct <= result.average_return_pct


async def test_skips_articles_without_enough_subsequent_candles(session: AsyncSession) -> None:
    repository = CandleRepository(session)
    # Enough measurable articles, plus one too close to "now" to have
    # `forward_bars` candles after it yet.
    for i in range(5):
        published_at = _BASE_TIME + timedelta(days=i)
        await repository.insert_new(_candles_from(published_at, [2000.0, 2001.0, 2002.0]))
    measurable_articles = [_article(_BASE_TIME + timedelta(days=i)) for i in range(5)]
    unmeasurable_article = _article(_BASE_TIME + timedelta(days=100))

    result = await measure_historical_reaction(
        category="central_bank",
        articles=[*measurable_articles, unmeasurable_article],
        candle_repository=repository,
        symbol_id=_SYMBOL_ID,
        timeframe="M15",
        forward_bars=2,
    )

    assert result is not None
    assert result.sample_size == 5
