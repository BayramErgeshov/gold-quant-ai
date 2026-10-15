"""Unit tests for `src.engines.chief_ai.multi_timeframe`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.chief_ai.multi_timeframe import (
    combine_timeframe_confirmations,
    confirm_timeframe,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _window(closes: list[float]) -> list[Candle]:
    window: list[Candle] = []
    for index, close in enumerate(closes):
        window.append(
            Candle(
                symbol_id=_SYMBOL_ID,
                timeframe="H4",
                timestamp=_BASE_TIME + timedelta(hours=4 * index),
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                source="test_fixture",
            )
        )
    return window


def _uptrend(count: int = 30) -> list[Candle]:
    return _window([2000.0 + i * 5.0 for i in range(count)])


def _downtrend(count: int = 30) -> list[Candle]:
    return _window([2000.0 - i * 5.0 for i in range(count)])


def _sideways(count: int = 30) -> list[Candle]:
    return _window([2000.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(count)])


def test_confirm_timeframe_returns_none_agreement_with_too_few_candles() -> None:
    result = confirm_timeframe("H4", _uptrend(5), "buy")

    assert result.regime is None
    assert result.agrees is None


def test_confirm_timeframe_agrees_when_uptrend_matches_buy() -> None:
    result = confirm_timeframe("H4", _uptrend(), "buy")

    assert result.regime == "bull_trend"
    assert result.agrees is True


def test_confirm_timeframe_disagrees_when_uptrend_opposes_sell() -> None:
    result = confirm_timeframe("H4", _uptrend(), "sell")

    assert result.regime == "bull_trend"
    assert result.agrees is False


def test_confirm_timeframe_agrees_when_downtrend_matches_sell() -> None:
    result = confirm_timeframe("H4", _downtrend(), "sell")

    assert result.regime == "bear_trend"
    assert result.agrees is True


def test_confirm_timeframe_has_no_opinion_when_not_trending() -> None:
    result = confirm_timeframe("H4", _sideways(), "buy")

    assert result.agrees is None


def test_combine_confirmations_stays_at_full_confidence_with_no_disagreement() -> None:
    confirmations = [
        confirm_timeframe("H4", _uptrend(), "buy"),
        confirm_timeframe("M15", _sideways(), "buy"),
    ]

    result = combine_timeframe_confirmations(confirmations)

    assert result.confidence_multiplier == pytest.approx(1.0)
    assert any("H4_confirms" in reason for reason in result.reasons)


def test_combine_confirmations_discounts_once_per_disagreeing_timeframe() -> None:
    confirmations = [
        confirm_timeframe("H4", _downtrend(), "buy"),
        confirm_timeframe("H1", _downtrend(), "buy"),
    ]

    result = combine_timeframe_confirmations(confirmations, discount_per_disagreement=0.5)

    assert result.confidence_multiplier == pytest.approx(0.25)
    assert sum("_counter_trend" in reason for reason in result.reasons) == 2


def test_combine_confirmations_with_no_timeframes_is_a_no_op() -> None:
    result = combine_timeframe_confirmations([])

    assert result.confidence_multiplier == 1.0
    assert result.reasons == []
