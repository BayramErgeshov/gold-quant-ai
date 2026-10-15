"""Unit tests for Shakky's five entry-logic families."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.shakky_engine.confirmations import (
    Confirmation,
    adx_strength_confirmation,
    bollinger_confirmation,
    breakout_confirmation,
    collect_confirmations,
    doji_confirmation,
    dxy_confirmation,
    ema_trend_confirmation,
    engulfing_confirmation,
    hammer_hanging_man_confirmation,
    intermarket_structure_confirmation,
    macd_confirmation,
    mean_reversion_atr_confirmation,
    momentum_impulse_confirmation,
    pin_bar_level_confirmation,
    resolve_entry_signal,
    rsi_confirmation,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    offset: int, *, close: float, high: float | None = None, low: float | None = None
) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=5 * offset),
        open=close,
        high=high if high is not None else close + 0.3,
        low=low if low is not None else close - 0.3,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _uptrend(count: int = 80, *, start: float = 1900.0, slope: float = 1.5) -> list[Candle]:
    return [_candle(i, close=start + i * slope) for i in range(count)]


def _downtrend(count: int = 80, *, start: float = 2100.0, slope: float = 1.5) -> list[Candle]:
    return [_candle(i, close=start - i * slope) for i in range(count)]


def _flat(count: int = 80, *, price: float = 2000.0, amplitude: float = 2.0) -> list[Candle]:
    return [_candle(i, close=price + amplitude * math.sin(i * 0.6)) for i in range(count)]


def _accelerating_uptrend(count: int = 80, *, start: float = 1900.0) -> list[Candle]:
    # A perfectly linear ramp makes the MACD line settle to a flat
    # constant equal to its own signal line (histogram exactly 0) -- an
    # accelerating move is needed for the two to meaningfully diverge.
    return [_candle(i, close=start + i * i * 0.05) for i in range(count)]


def _accelerating_downtrend(count: int = 80, *, start: float = 2100.0) -> list[Candle]:
    return [_candle(i, close=start - i * i * 0.05) for i in range(count)]


def test_ema_trend_confirmation_buy_on_a_clean_uptrend() -> None:
    confirmation = ema_trend_confirmation(_uptrend())

    assert confirmation is not None
    assert confirmation.direction == "buy"
    assert confirmation.family == "trend_following"


def test_ema_trend_confirmation_sell_on_a_clean_downtrend() -> None:
    confirmation = ema_trend_confirmation(_downtrend())

    assert confirmation is not None
    assert confirmation.direction == "sell"


def test_ema_trend_confirmation_none_without_enough_history() -> None:
    assert ema_trend_confirmation(_uptrend(count=10)) is None


def test_macd_confirmation_buy_on_an_accelerating_uptrend() -> None:
    confirmation = macd_confirmation(_accelerating_uptrend())

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_macd_confirmation_sell_on_an_accelerating_downtrend() -> None:
    confirmation = macd_confirmation(_accelerating_downtrend())

    assert confirmation is not None
    assert confirmation.direction == "sell"


def test_rsi_confirmation_buy_when_oversold() -> None:
    candles = _downtrend(count=40, start=2100.0, slope=3.0)

    confirmation = rsi_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_rsi_confirmation_sell_when_overbought() -> None:
    candles = _uptrend(count=40, start=1900.0, slope=3.0)

    confirmation = rsi_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "sell"


def test_rsi_confirmation_none_in_neutral_territory() -> None:
    assert rsi_confirmation(_flat()) is None


def test_bollinger_confirmation_buy_below_lower_band() -> None:
    candles = _flat(count=30, amplitude=1.0)
    spike_down = _candle(30, close=1950.0)
    candles = candles + [spike_down]

    confirmation = bollinger_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_bollinger_confirmation_none_inside_the_bands() -> None:
    assert bollinger_confirmation(_flat(count=30, amplitude=1.0)) is None


def test_mean_reversion_atr_confirmation_sell_when_extended_above() -> None:
    candles = _flat(count=60, amplitude=1.0) + [_candle(60, close=2100.0)]

    confirmation = mean_reversion_atr_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "sell"


def test_momentum_impulse_confirmation_buy_on_a_strong_recent_move() -> None:
    candles = _flat(count=60, amplitude=0.5) + [
        _candle(60 + i, close=2000.0 + i * 5.0) for i in range(6)
    ]

    confirmation = momentum_impulse_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_momentum_impulse_confirmation_none_without_a_strong_move() -> None:
    assert momentum_impulse_confirmation(_flat()) is None


def test_breakout_confirmation_buy_above_recent_resistance() -> None:
    candles = _uptrend(count=60, start=1900.0, slope=0.5) + [_candle(60, close=2100.0, high=2100.5)]

    confirmation = breakout_confirmation(
        candles, support_levels=[1900.0], resistance_levels=[2000.0]
    )

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_breakout_confirmation_none_when_price_stays_inside_structure() -> None:
    confirmation = breakout_confirmation(
        _flat(), support_levels=[1900.0], resistance_levels=[2100.0]
    )

    assert confirmation is None


def test_adx_strength_confirmation_confirms_a_strong_trend() -> None:
    confirmation = adx_strength_confirmation(_uptrend(count=60, slope=3.0), "buy")

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_adx_strength_confirmation_none_for_a_flat_market() -> None:
    assert adx_strength_confirmation(_flat(), "buy") is None


def test_dxy_confirmation_buy_when_dxy_falls() -> None:
    confirmation = dxy_confirmation(_downtrend(count=20))

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_dxy_confirmation_sell_when_dxy_rises() -> None:
    confirmation = dxy_confirmation(_uptrend(count=20))

    assert confirmation is not None
    assert confirmation.direction == "sell"


def test_intermarket_structure_confirmation_requires_both_dxy_and_a_nearby_level() -> None:
    m5_candles = _flat(count=20, price=2000.0, amplitude=0.1)
    falling_dxy = _downtrend(count=20)

    confirmation = intermarket_structure_confirmation(
        m5_candles, falling_dxy, support_levels=[1999.9], resistance_levels=[2100.0]
    )

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_intermarket_structure_confirmation_none_without_a_nearby_level() -> None:
    m5_candles = _flat(count=20, price=2000.0, amplitude=0.1)
    falling_dxy = _downtrend(count=20)

    confirmation = intermarket_structure_confirmation(
        m5_candles, falling_dxy, support_levels=[1500.0], resistance_levels=[2500.0]
    )

    assert confirmation is None


def test_pin_bar_level_confirmation_requires_proximity_to_a_level() -> None:
    candles = _flat(count=20, price=2000.0, amplitude=0.1)
    candles[-1] = _candle(19, close=2000.2, high=2000.3, low=1995.0)

    confirmation = pin_bar_level_confirmation(
        candles, support_levels=[2000.0], resistance_levels=[2100.0]
    )

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_engulfing_confirmation_detects_a_bullish_engulfing() -> None:
    candles = _flat(count=18, price=2000.0, amplitude=0.1)
    previous = Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=90),
        open=2001.0,
        high=2001.5,
        low=1999.0,
        close=1999.5,
        volume=100.0,
        source="test_fixture",
    )
    current = Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=95),
        open=1999.0,
        high=2002.0,
        low=1998.5,
        close=2001.8,
        volume=100.0,
        source="test_fixture",
    )
    candles = candles + [previous, current]

    confirmation = engulfing_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_doji_confirmation_takes_direction_from_short_term_ema_lean() -> None:
    candles = _uptrend(count=30, start=1900.0, slope=1.0)
    doji = _candle(
        30,
        close=candles[-1].close + 0.01,
        high=candles[-1].close + 1.0,
        low=candles[-1].close - 1.0,
    )
    candles = candles + [doji]

    confirmation = doji_confirmation(candles)

    assert confirmation is not None
    assert confirmation.direction == "buy"


def test_hammer_hanging_man_confirmation_wraps_the_pattern_detector() -> None:
    down = [_candle(i, close=2010.0 - i) for i in range(10)]
    pin_bar = _candle(10, close=2000.8, high=2001.0, low=1995.0)
    candles = down + [pin_bar]

    confirmation = hammer_hanging_man_confirmation(candles)

    assert confirmation is not None
    assert confirmation.name == "hammer"
    assert confirmation.direction == "buy"


def test_collect_confirmations_pools_every_family() -> None:
    confirmations = collect_confirmations(
        m5_candles=_uptrend(count=80, slope=2.0), dxy_candles=None
    )

    families = {c.family for c in confirmations}
    assert "trend_following" in families


def test_collect_confirmations_skips_intermarket_without_dxy_data() -> None:
    confirmations = collect_confirmations(
        m5_candles=_uptrend(count=80, slope=2.0), dxy_candles=None
    )

    assert all(c.family != "intermarket" for c in confirmations)


def test_resolve_entry_signal_requires_at_least_three_agreeing() -> None:
    two_buys = [
        Confirmation(family="trend_following", name="ema_trend", direction="buy", detail=""),
        Confirmation(family="trend_following", name="macd", direction="buy", detail=""),
    ]

    assert resolve_entry_signal(two_buys) is None


def test_resolve_entry_signal_returns_the_majority_direction() -> None:
    mixed = [
        Confirmation(family="trend_following", name="ema_trend", direction="buy", detail=""),
        Confirmation(family="trend_following", name="macd", direction="buy", detail=""),
        Confirmation(family="mean_reversion", name="rsi", direction="buy", detail=""),
        Confirmation(family="mean_reversion", name="bollinger_band", direction="sell", detail=""),
    ]

    resolved = resolve_entry_signal(mixed)

    assert resolved is not None
    direction, agreeing = resolved
    assert direction == "buy"
    assert len(agreeing) == 3
