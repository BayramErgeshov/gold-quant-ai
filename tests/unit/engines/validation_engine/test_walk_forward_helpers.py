"""Unit tests for the Walk-Forward Validation Engine's pure-function helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.agents.confluence import CombinedVote
from src.engines.validation_engine.walk_forward import _department_agreement, _simulate_forward
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)


def _vote(bullish: float, bearish: float) -> CombinedVote:
    return CombinedVote(
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=max(0.0, 1.0 - bullish - bearish),
        confidence=0.8,
        quality_grade="A",
        strongest_supporting_factors=[],
        strongest_opposing_factors=[],
    )


def test_department_agreement_returns_empty_lists_when_direction_is_none() -> None:
    agreeing, disagreeing, missing = _department_agreement(
        {"technical": _vote(0.8, 0.1)}, direction=None
    )

    assert agreeing == []
    assert disagreeing == []
    assert missing != []


def test_department_agreement_splits_by_bias_relative_to_direction() -> None:
    department_votes = {
        "technical": _vote(0.8, 0.1),
        "historical": _vote(0.1, 0.8),
        "ml": _vote(0.5, 0.5),
    }

    agreeing, disagreeing, missing = _department_agreement(department_votes, direction="buy")

    assert agreeing == ["technical"]
    assert disagreeing == ["historical"]
    assert "ml" not in agreeing and "ml" not in disagreeing
    assert "macro" in missing
    assert "news" in missing


def test_department_agreement_flips_for_sell_direction() -> None:
    department_votes = {"technical": _vote(0.8, 0.1)}

    agreeing, disagreeing, _ = _department_agreement(department_votes, direction="sell")

    assert agreeing == []
    assert disagreeing == ["technical"]


def _candle(offset: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="M15",
        timestamp=_BASE_TIME + timedelta(minutes=15 * offset),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def test_simulate_forward_returns_none_when_entry_is_the_last_candle() -> None:
    candles = [_candle(i, high=2001.0, low=1999.0, close=2000.0) for i in range(5)]

    result = _simulate_forward(candles, 4, "buy", 2000.0, 1990.0, 2010.0, max_holding_bars=100)

    assert result is None


def test_simulate_forward_exits_on_stop_loss_for_a_buy() -> None:
    candles = [_candle(0, high=2001.0, low=1999.0, close=2000.0)] + [
        _candle(1, high=2000.5, low=1989.0, close=1990.0)
    ]

    result = _simulate_forward(candles, 0, "buy", 2000.0, 1990.0, 2010.0, max_holding_bars=100)

    assert result is not None
    assert result.exit_reason == "stop_loss"
    assert result.realized_return_pct == pytest.approx(-0.5)
    assert result.holding_bars == 1


def test_simulate_forward_exits_on_take_profit_for_a_buy() -> None:
    candles = [_candle(0, high=2001.0, low=1999.0, close=2000.0)] + [
        _candle(1, high=2011.0, low=1999.0, close=2005.0)
    ]

    result = _simulate_forward(candles, 0, "buy", 2000.0, 1990.0, 2010.0, max_holding_bars=100)

    assert result is not None
    assert result.exit_reason == "take_profit"
    assert result.realized_return_pct == pytest.approx(0.5)


def test_simulate_forward_assumes_stop_triggers_first_when_both_hit_the_same_bar() -> None:
    candles = [_candle(0, high=2001.0, low=1999.0, close=2000.0)] + [
        _candle(1, high=2011.0, low=1989.0, close=2000.0)
    ]

    result = _simulate_forward(candles, 0, "buy", 2000.0, 1990.0, 2010.0, max_holding_bars=100)

    assert result is not None
    assert result.exit_reason == "stop_loss"


def test_simulate_forward_exits_on_stop_loss_for_a_sell() -> None:
    candles = [_candle(0, high=2001.0, low=1999.0, close=2000.0)] + [
        _candle(1, high=2011.0, low=1999.0, close=2005.0)
    ]

    result = _simulate_forward(candles, 0, "sell", 2000.0, 2010.0, 1990.0, max_holding_bars=100)

    assert result is not None
    assert result.exit_reason == "stop_loss"
    assert result.realized_return_pct == pytest.approx(-0.5)


def test_simulate_forward_closes_at_max_holding_bars_when_neither_hit() -> None:
    candles = [_candle(0, high=2001.0, low=1999.0, close=2000.0)] + [
        _candle(i, high=2002.0, low=1998.0, close=2001.0) for i in range(1, 6)
    ]

    result = _simulate_forward(candles, 0, "buy", 2000.0, 1900.0, 2100.0, max_holding_bars=3)

    assert result is not None
    assert result.exit_reason == "max_holding_bars_reached"
    assert result.holding_bars == 3


def test_simulate_forward_closes_at_end_of_data_when_neither_hit_and_horizon_not_reached() -> None:
    candles = [_candle(0, high=2001.0, low=1999.0, close=2000.0)] + [
        _candle(i, high=2002.0, low=1998.0, close=2001.0) for i in range(1, 4)
    ]

    result = _simulate_forward(candles, 0, "buy", 2000.0, 1900.0, 2100.0, max_holding_bars=100)

    assert result is not None
    assert result.exit_reason == "end_of_data"
    assert result.holding_bars == 3


def test_simulate_forward_tracks_mfe_and_mae() -> None:
    candles = [
        _candle(0, high=2001.0, low=1999.0, close=2000.0),
        _candle(1, high=2020.0, low=1990.0, close=2005.0),
        _candle(2, high=2015.0, low=1985.0, close=2010.0),
    ]

    result = _simulate_forward(candles, 0, "buy", 2000.0, 1900.0, 2100.0, max_holding_bars=100)

    assert result is not None
    # Best favorable excursion across both bars: (2020-2000)/2000*100 = 1.0%.
    assert result.mfe_pct == pytest.approx(1.0)
    # Worst adverse excursion: (1985-2000)/2000*100 = -0.75%.
    assert result.mae_pct == pytest.approx(-0.75)
