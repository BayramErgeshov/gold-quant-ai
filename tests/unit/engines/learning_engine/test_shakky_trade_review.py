"""Unit tests for Shakky-specific post-trade learning."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.engines.learning_engine.shakky_trade_review import review_shakky_trade
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _shakky_trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "initial_stop_loss": 1990.0,
        "take_profit": 2010.0,
        "exit_price": 2010.0,
        "realized_pnl": 10.0,
        "magic_number": 99,
        "opened_at": _BASE_TIME,
        "department_votes": {"shakky_engine": {"bias": "bullish"}},
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_insufficient_data_returns_an_honest_empty_verdict() -> None:
    trade = _shakky_trade(exit_price=None)

    verdict = review_shakky_trade(trade)

    assert verdict == review_shakky_trade(trade)
    assert verdict.reasons == ["insufficient_trade_data"]
    assert verdict.tp_too_small is False
    assert verdict.tp_too_large is False


def test_flags_tp_too_small_when_mfe_meaningfully_exceeds_target_distance() -> None:
    trade = _shakky_trade(
        take_profit=2010.0,  # 10 distance
        exit_price=2010.0,
        max_favorable_excursion=15.0,  # 50% beyond target distance
    )

    verdict = review_shakky_trade(trade)

    assert verdict.tp_too_small is True
    assert any("exceeds_target_distance" in reason for reason in verdict.reasons)


def test_does_not_flag_tp_too_small_when_mfe_is_close_to_target() -> None:
    trade = _shakky_trade(
        take_profit=2010.0,
        exit_price=2010.0,
        max_favorable_excursion=10.5,
    )

    verdict = review_shakky_trade(trade)

    assert verdict.tp_too_small is False


def test_flags_tp_too_large_when_trade_reversed_after_moving_favorably() -> None:
    trade = _shakky_trade(
        take_profit=2020.0,  # far target, never reached
        exit_price=1990.0,  # stopped out
        realized_pnl=-10.0,
        max_favorable_excursion=6.0,  # 60% of the 10-point risk distance
    )

    verdict = review_shakky_trade(trade)

    assert verdict.tp_too_large is True
    assert any("reversed_before_target" in reason for reason in verdict.reasons)


def test_does_not_flag_tp_too_large_for_a_clean_win_at_target() -> None:
    trade = _shakky_trade(
        take_profit=2010.0,
        exit_price=2010.0,
        realized_pnl=10.0,
        max_favorable_excursion=10.0,
    )

    verdict = review_shakky_trade(trade)

    assert verdict.tp_too_large is False


def test_flags_should_have_scaled_on_strong_r_multiple_with_no_scale_events() -> None:
    trade = _shakky_trade(
        take_profit=2050.0,
        exit_price=2035.0,  # 3.5R on a 10-point risk distance
        realized_pnl=350.0,
        entry_trend_confidence_score=72.0,
        scale_events=None,
    )

    verdict = review_shakky_trade(trade)

    assert verdict.should_have_scaled is True


def test_does_not_flag_should_have_scaled_when_already_scaled() -> None:
    trade = _shakky_trade(
        take_profit=2050.0,
        exit_price=2035.0,
        realized_pnl=350.0,
        entry_trend_confidence_score=72.0,
        scale_events=[{"price": 2020.0, "volume": 0.5, "at": _BASE_TIME.isoformat()}],
    )

    verdict = review_shakky_trade(trade)

    assert verdict.should_have_scaled is False


def test_better_strategy_picked_when_another_strategy_outperforms() -> None:
    trade = _shakky_trade(
        take_profit=2005.0,
        exit_price=2001.0,  # 0.1R -- a weak result
        realized_pnl=1.0,
    )

    verdict = review_shakky_trade(
        trade, other_strategy_average_r_multiple={"Swing": 1.8, "Scalping": 0.4}
    )

    assert verdict.better_strategy == "Swing"


def test_better_strategy_is_none_without_comparison_data() -> None:
    trade = _shakky_trade(exit_price=1995.0, realized_pnl=-50.0)

    verdict = review_shakky_trade(trade, other_strategy_average_r_multiple=None)

    assert verdict.better_strategy is None


def test_better_strategy_excludes_shakky_itself_from_candidates() -> None:
    # "Shakky": 5.0 would trivially "win" if the own-strategy exclusion
    # were broken -- asserting the actual pick is "Swing" (which alone
    # outperforms this trade's own 0.1R) proves the exclusion works,
    # not merely that some non-Shakky value happened to be returned.
    trade = _shakky_trade(exit_price=2001.0, realized_pnl=1.0)

    verdict = review_shakky_trade(
        trade, other_strategy_average_r_multiple={"Shakky": 5.0, "Swing": 0.5}
    )

    assert verdict.better_strategy == "Swing"
