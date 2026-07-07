"""Unit tests for post-trade review."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.learning_engine.trade_review import review_closed_trade
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()


def _trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "exit_price": 2020.0,
        "magic_number": 42,
        "realized_pnl": 20.0,
    }
    defaults.update(overrides)
    return Trade(**defaults)  # type: ignore[arg-type]


def test_raises_when_entry_price_missing() -> None:
    trade = _trade(entry_price=None)

    with pytest.raises(ValueError, match="entry_price"):
        review_closed_trade(trade)


def test_raises_when_exit_price_missing() -> None:
    trade = _trade(exit_price=None)

    with pytest.raises(ValueError, match="exit_price"):
        review_closed_trade(trade)


def test_computes_positive_return_for_winning_buy() -> None:
    review = review_closed_trade(_trade())

    assert review.is_win is True
    assert review.realized_return_pct == pytest.approx(1.0)
    assert review.risk_pct == pytest.approx(0.5)
    assert review.r_multiple == pytest.approx(2.0)


def test_computes_negative_return_for_losing_sell() -> None:
    trade = _trade(
        direction="sell",
        entry_price=2000.0,
        stop_loss=2010.0,
        exit_price=2020.0,
        realized_pnl=-20.0,
    )

    review = review_closed_trade(trade)

    assert review.is_win is False
    assert review.realized_return_pct < 0


def test_holding_time_is_none_without_timestamps() -> None:
    review = review_closed_trade(_trade())

    assert review.holding_time is None


def test_holding_time_is_computed_when_timestamps_present() -> None:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC)
    closed_at = opened_at + timedelta(hours=4)
    trade = _trade(opened_at=opened_at, closed_at=closed_at)

    review = review_closed_trade(trade)

    assert review.holding_time == timedelta(hours=4)


def test_is_win_is_false_when_realized_pnl_missing() -> None:
    trade = _trade(realized_pnl=None)

    review = review_closed_trade(trade)

    assert review.is_win is False
