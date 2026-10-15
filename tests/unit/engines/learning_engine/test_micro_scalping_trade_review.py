"""Unit tests for Micro Scalping-specific post-trade learning."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.learning_engine.micro_scalping_trade_review import review_micro_scalping_trade
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _micro_scalping_trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 0.05,
        "entry_price": 2000.0,
        "stop_loss": 1998.0,
        "initial_stop_loss": 1998.0,
        "take_profit": None,
        "exit_price": 2001.0,
        "realized_pnl": 1.0,
        "magic_number": 99,
        "opened_at": _BASE_TIME,
        "closed_at": _BASE_TIME + timedelta(minutes=2),
        "department_votes": {"micro_scalping_engine": {"bias": "bullish"}},
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_insufficient_data_returns_an_honest_empty_verdict() -> None:
    trade = _micro_scalping_trade(exit_price=None)

    verdict = review_micro_scalping_trade(trade)

    assert verdict.reasons == ["insufficient_trade_data"]
    assert verdict.closed_too_early is False
    assert verdict.gave_back_profit is False
    assert verdict.held_too_long is False


def test_flags_closed_too_early_when_mfe_meaningfully_exceeds_realized_move() -> None:
    trade = _micro_scalping_trade(
        exit_price=2001.0,  # realized favorable move = 1.0
        max_favorable_excursion=1.5,  # 50% beyond the realized move
    )

    verdict = review_micro_scalping_trade(trade)

    assert verdict.closed_too_early is True
    assert any("exceeds_realized_favorable_move" in reason for reason in verdict.reasons)


def test_does_not_flag_closed_too_early_when_mfe_is_close_to_the_realized_move() -> None:
    trade = _micro_scalping_trade(exit_price=2001.0, max_favorable_excursion=1.05)

    verdict = review_micro_scalping_trade(trade)

    assert verdict.closed_too_early is False


def test_flags_gave_back_profit_when_a_meaningful_mfe_reverses_to_flat_or_negative() -> None:
    trade = _micro_scalping_trade(
        exit_price=2000.0,
        realized_pnl=0.0,
        max_favorable_excursion=1.5,  # 75% of the 2.0 risk distance
    )

    verdict = review_micro_scalping_trade(trade)

    assert verdict.gave_back_profit is True
    assert any("closed_flat_or_negative" in reason for reason in verdict.reasons)


def test_does_not_flag_gave_back_profit_on_a_genuine_win() -> None:
    trade = _micro_scalping_trade(exit_price=2001.0, realized_pnl=1.0, max_favorable_excursion=1.2)

    verdict = review_micro_scalping_trade(trade)

    assert verdict.gave_back_profit is False


def test_flags_held_too_long_when_holding_duration_reaches_the_max_holding_cap() -> None:
    trade = _micro_scalping_trade(
        opened_at=_BASE_TIME, closed_at=_BASE_TIME + timedelta(minutes=29)
    )

    verdict = review_micro_scalping_trade(trade, max_holding_minutes=30.0)

    assert verdict.held_too_long is True
    assert any("reached_max_holding_cap" in reason for reason in verdict.reasons)


def test_does_not_flag_held_too_long_for_a_typical_fast_scalp() -> None:
    trade = _micro_scalping_trade(opened_at=_BASE_TIME, closed_at=_BASE_TIME + timedelta(minutes=2))

    verdict = review_micro_scalping_trade(trade, max_holding_minutes=30.0)

    assert verdict.held_too_long is False
