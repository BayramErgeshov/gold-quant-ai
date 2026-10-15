"""Unit tests for Micro Scalping's dynamic profit management."""

from __future__ import annotations

import pytest

from src.engines.micro_scalping_engine.exit_management import (
    Direction,
    MicroScalpingExitDecision,
    evaluate_exit,
)

pytestmark = pytest.mark.unit


def _evaluate(
    *,
    direction: Direction = "buy",
    floating_profit_usd: float = 0.0,
    min_profit_target_usd: float = 1.0,
    momentum_still_strong: bool = False,
    current_price: float = 2000.0,
    current_stop_loss: float = 1995.0,
    atr: float = 1.0,
    holding_minutes: float = 1.0,
    max_holding_minutes: float = 30.0,
    trailing_stop_enabled: bool = True,
) -> MicroScalpingExitDecision:
    return evaluate_exit(
        direction=direction,
        floating_profit_usd=floating_profit_usd,
        min_profit_target_usd=min_profit_target_usd,
        momentum_still_strong=momentum_still_strong,
        current_price=current_price,
        current_stop_loss=current_stop_loss,
        atr=atr,
        holding_minutes=holding_minutes,
        max_holding_minutes=max_holding_minutes,
        trailing_stop_enabled=trailing_stop_enabled,
    )


def test_holds_while_profit_is_below_target() -> None:
    decision = _evaluate(floating_profit_usd=0.5)

    assert decision.action == "hold"
    assert any("profit_below_target" in reason for reason in decision.reasons)


def test_closes_full_once_target_reached_without_strong_momentum() -> None:
    decision = _evaluate(floating_profit_usd=1.5, momentum_still_strong=False)

    assert decision.action == "close_full"


def test_trails_the_stop_when_target_reached_and_momentum_still_strong() -> None:
    decision = _evaluate(
        floating_profit_usd=1.5,
        momentum_still_strong=True,
        current_price=2010.0,
        current_stop_loss=1995.0,
    )

    assert decision.action == "trail"
    assert decision.new_stop_loss is not None
    assert decision.new_stop_loss > 1995.0


def test_holds_when_trailing_stop_would_not_improve_on_the_current_one() -> None:
    # current_price=2010 with a 0.5 ATR trail distance -> candidate stop
    # 2009.5, which is already worse than the existing 2009.8 stop.
    decision = _evaluate(
        floating_profit_usd=1.5,
        momentum_still_strong=True,
        current_price=2010.0,
        current_stop_loss=2009.8,
        atr=1.0,
    )

    assert decision.action == "hold"


def test_closes_full_when_trailing_disabled_even_with_strong_momentum() -> None:
    decision = _evaluate(
        floating_profit_usd=1.5, momentum_still_strong=True, trailing_stop_enabled=False
    )

    assert decision.action == "close_full"
    assert decision.reasons == ["profit_target_reached_trailing_disabled"]


def test_closes_full_unconditionally_once_max_holding_time_reached() -> None:
    # Even with profit still below target -- "never hold trades for hours."
    decision = _evaluate(floating_profit_usd=0.0, holding_minutes=45.0, max_holding_minutes=30.0)

    assert decision.action == "close_full"
    assert any("max_holding_time_reached" in reason for reason in decision.reasons)


def test_sell_direction_trails_the_stop_downward() -> None:
    decision = _evaluate(
        direction="sell",
        floating_profit_usd=1.5,
        momentum_still_strong=True,
        current_price=1990.0,
        current_stop_loss=2005.0,
    )

    assert decision.action == "trail"
    assert decision.new_stop_loss is not None
    assert decision.new_stop_loss < 2005.0
