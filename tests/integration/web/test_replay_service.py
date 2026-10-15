"""Integration tests for Market Replay Mode's session service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.replay_service import (
    ReplayInsufficientHistoryError,
    ReplaySessionNotFoundError,
    find_high_impact_news_windows,
    find_regime_windows,
    get_replay_session,
    start_replay_session,
    step_replay_session,
)
from src.models.candle import Candle
from src.models.market_regime import MarketRegime
from src.models.news_article import NewsArticle
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.market_regime_repository import MarketRegimeRepository
from src.repositories.news_article_repository import NewsArticleRepository
from src.repositories.symbol_repository import SymbolRepository

_BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


async def _seed_candles(session: AsyncSession, symbol_id: object, count: int) -> None:
    candles = []
    price = 2000.0
    for i in range(count):
        candles.append(
            Candle(
                symbol_id=symbol_id,
                timeframe="M15",
                timestamp=_BASE_TIME + timedelta(minutes=15 * i),
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.5,
                volume=100.0,
                spread=2.0,
                source="test_fixture",
            )
        )
        price += 0.5
    await CandleRepository(session).insert_new(candles)


async def test_start_replay_session_raises_with_too_little_history(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 10)

    with pytest.raises(ReplayInsufficientHistoryError):
        await start_replay_session(
            session,
            symbol_name="XAUUSD",
            timeframe="M15",
            start=_BASE_TIME,
            end=_BASE_TIME + timedelta(days=1),
            window_size=20,
        )


async def test_start_replay_session_computes_the_first_step(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 60)

    view = await start_replay_session(
        session,
        symbol_name="XAUUSD",
        timeframe="M15",
        start=_BASE_TIME,
        end=_BASE_TIME + timedelta(days=2),
        window_size=20,
    )

    assert view.total_candles == 60
    assert view.current_index == 20
    assert view.step is not None
    assert view.can_step_backward is False
    assert view.can_step_forward is True


async def test_step_forward_and_backward_move_the_cursor(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 60)
    started = await start_replay_session(
        session,
        symbol_name="XAUUSD",
        timeframe="M15",
        start=_BASE_TIME,
        end=_BASE_TIME + timedelta(days=2),
        window_size=20,
    )

    forward = await step_replay_session(session, started.session_id, direction="forward")
    assert forward.current_index == 21

    backward = await step_replay_session(session, started.session_id, direction="backward")
    assert backward.current_index == 20


async def test_step_forward_stays_put_at_the_end_of_the_range(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 22)
    started = await start_replay_session(
        session,
        symbol_name="XAUUSD",
        timeframe="M15",
        start=_BASE_TIME,
        end=_BASE_TIME + timedelta(days=2),
        window_size=20,
    )
    assert started.current_index == 20

    stepped = await step_replay_session(session, started.session_id, direction="forward")
    assert stepped.current_index == 21
    assert stepped.can_step_forward is False

    stayed = await step_replay_session(session, started.session_id, direction="forward")
    assert stayed.current_index == 21


async def test_step_raises_for_an_unknown_session(session: AsyncSession) -> None:
    with pytest.raises(ReplaySessionNotFoundError):
        await step_replay_session(session, "does-not-exist", direction="forward")


def test_get_replay_session_raises_for_an_unknown_session() -> None:
    with pytest.raises(ReplaySessionNotFoundError):
        get_replay_session("does-not-exist")


async def test_get_replay_session_returns_the_same_state_without_stepping(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 60)
    started = await start_replay_session(
        session,
        symbol_name="XAUUSD",
        timeframe="M15",
        start=_BASE_TIME,
        end=_BASE_TIME + timedelta(days=2),
        window_size=20,
    )

    fetched = get_replay_session(started.session_id)

    assert fetched.current_index == started.current_index
    assert fetched.step is not None
    assert started.step is not None
    assert fetched.step.market_regime == started.step.market_regime


async def test_find_high_impact_news_windows_filters_below_threshold(
    session: AsyncSession,
) -> None:
    await NewsArticleRepository(session).add(
        NewsArticle(
            title="FOMC holds rates",
            source="reuters.com",
            published_at=_BASE_TIME,
            content_hash="h1",
            importance_score=0.9,
        )
    )
    await NewsArticleRepository(session).add(
        NewsArticle(
            title="Minor update",
            source="reuters.com",
            published_at=_BASE_TIME,
            content_hash="h2",
            importance_score=0.2,
        )
    )

    windows = await find_high_impact_news_windows(session, min_importance=0.7)

    assert [window.label for window in windows] == ["FOMC holds rates"]
    # The test database backend returns naive datetimes even for
    # timezone-aware columns; compare wall-clock value only.
    assert windows[0].start.replace(tzinfo=UTC) == _BASE_TIME - timedelta(hours=6)
    assert windows[0].end.replace(tzinfo=UTC) == _BASE_TIME + timedelta(hours=6)


async def test_find_regime_windows_filters_by_regime_type(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await MarketRegimeRepository(session).add(
        MarketRegime(
            symbol_id=symbol.id,
            timeframe="M15",
            start_timestamp=_BASE_TIME,
            end_timestamp=_BASE_TIME + timedelta(days=1),
            regime="bull_trend",
            confidence=0.8,
        )
    )
    await MarketRegimeRepository(session).add(
        MarketRegime(
            symbol_id=symbol.id,
            timeframe="M15",
            start_timestamp=_BASE_TIME + timedelta(days=2),
            end_timestamp=_BASE_TIME + timedelta(days=3),
            regime="range",
            confidence=0.7,
        )
    )

    windows = await find_regime_windows(
        session, symbol_name="XAUUSD", timeframe="M15", regime_type="bull_trend"
    )

    assert len(windows) == 1
    assert "bull_trend" in windows[0].label


async def test_find_regime_windows_returns_empty_for_unknown_regime_type(
    session: AsyncSession,
) -> None:
    await _make_symbol(session)

    windows = await find_regime_windows(
        session, symbol_name="XAUUSD", timeframe="M15", regime_type="not_a_real_regime"
    )

    assert windows == []
