"""Unit tests for the AI Weight Optimizer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.learning_engine.weight_optimizer import (
    TRADES_PER_BATCH,
    generate_weight_recommendations,
)
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _closed_trade(
    *,
    index: int,
    direction: str,
    realized_pnl: float,
    department_votes: dict[str, dict[str, object]] | None,
) -> Trade:
    return Trade(
        symbol_id=_SYMBOL_ID,
        direction=direction,
        status="closed",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        magic_number=1,
        realized_pnl=realized_pnl,
        department_votes=department_votes,
        opened_at=_BASE_TIME + timedelta(minutes=index),
        closed_at=_BASE_TIME + timedelta(minutes=index, seconds=30),
    )


def test_returns_no_recommendations_when_no_batch_has_completed() -> None:
    trades = [
        _closed_trade(index=i, direction="buy", realized_pnl=10.0, department_votes=None)
        for i in range(50)
    ]

    result = generate_weight_recommendations(trades, trade_batch_number=1)

    assert result == []


def test_recommends_higher_weight_when_batch_accuracy_improves_on_the_baseline() -> None:
    # Batch 1 (the first 100 trades): "technical" agrees with every buy,
    # and every buy wins -- perfect accuracy, well above the neutral 1.0
    # baseline's... actually the baseline defaults to neutral (1.0), so
    # construct batch 2 instead: a mixed-accuracy first 100 trades
    # establishes a below-neutral baseline, then a high-accuracy second
    # batch should trigger an upward recommendation.
    votes = {"technical": {"bias": "bullish", "confidence": 0.8}}
    first_batch = [
        _closed_trade(
            index=i,
            direction="buy",
            realized_pnl=10.0 if i % 2 == 0 else -10.0,
            department_votes=votes,
        )
        for i in range(TRADES_PER_BATCH)
    ]
    second_batch = [
        _closed_trade(
            index=TRADES_PER_BATCH + i, direction="buy", realized_pnl=10.0, department_votes=votes
        )
        for i in range(TRADES_PER_BATCH)
    ]

    result = generate_weight_recommendations(first_batch + second_batch, trade_batch_number=2)

    technical = next(r for r in result if r.department_name == "technical")
    assert technical.suggested_weight > technical.current_weight
    assert "Higher" in technical.reason
    assert technical.supporting_stats["batch_accuracy"] == pytest.approx(1.0)
    assert technical.supporting_stats["batch_total_calls"] == TRADES_PER_BATCH


def test_omits_departments_whose_weight_barely_moved() -> None:
    # "technical" never votes at all across either batch -- both windows
    # measure it at the same neutral default, so no recommendation.
    trades = [
        _closed_trade(index=i, direction="buy", realized_pnl=10.0, department_votes=None)
        for i in range(2 * TRADES_PER_BATCH)
    ]

    result = generate_weight_recommendations(trades, trade_batch_number=2)

    assert not any(r.department_name == "technical" for r in result)


def test_trade_batch_number_is_recorded_on_every_recommendation() -> None:
    votes = {"correlation": {"bias": "bearish", "confidence": 0.6}}
    trades = [
        _closed_trade(index=i, direction="buy", realized_pnl=-10.0, department_votes=votes)
        for i in range(TRADES_PER_BATCH)
    ]

    result = generate_weight_recommendations(trades, trade_batch_number=1)

    assert all(r.trade_batch_number == 1 for r in result)
