"""Integration tests for the AI Weight Optimizer's persistence trigger."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.learning_engine.weight_optimizer import maybe_generate_recommendations
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository
from src.repositories.weight_recommendation_repository import WeightRecommendationRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _closed_trade(symbol_id: uuid.UUID, *, index: int, **overrides: object) -> Trade:
    # "correlation" votes bullish on every trade below, but only every
    # other trade actually wins -- ~50% accuracy, a large enough gap from
    # the neutral 1.0 baseline (no prior evidence) to cross the
    # optimizer's materiality threshold.
    defaults: dict[str, object] = {
        "symbol_id": symbol_id,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "exit_price": 2010.0,
        "realized_pnl": 10.0 if index % 2 == 0 else -10.0,
        "magic_number": 1,
        "department_votes": {"correlation": {"bias": "bullish", "confidence": 0.6}},
        "opened_at": _BASE_TIME + timedelta(minutes=index),
        "closed_at": _BASE_TIME + timedelta(minutes=index, seconds=30),
    }
    defaults.update(overrides)
    return Trade(**defaults)


async def test_does_nothing_below_one_completed_batch(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    trades_repo = TradeRepository(session)
    for i in range(50):
        await trades_repo.add(_closed_trade(symbol.id, index=i))

    result = await maybe_generate_recommendations(session)

    assert result == []
    assert await WeightRecommendationRepository(session).list_pending() == []


async def test_persists_recommendations_once_a_batch_completes(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    trades_repo = TradeRepository(session)
    for i in range(100):
        await trades_repo.add(_closed_trade(symbol.id, index=i))

    result = await maybe_generate_recommendations(session)

    assert len(result) > 0
    correlation = next(r for r in result if r.department_name == "correlation")
    assert correlation.trade_batch_number == 1
    assert correlation.status == "pending"
    assert correlation.suggested_weight < correlation.current_weight

    pending = await WeightRecommendationRepository(session).list_pending()
    assert len(pending) == len(result)


async def test_is_idempotent_when_called_again_for_the_same_batch(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trades_repo = TradeRepository(session)
    for i in range(100):
        await trades_repo.add(_closed_trade(symbol.id, index=i))

    first = await maybe_generate_recommendations(session)
    second = await maybe_generate_recommendations(session)

    assert len(first) > 0
    assert second == []
    pending = await WeightRecommendationRepository(session).list_pending()
    assert len(pending) == len(first)
