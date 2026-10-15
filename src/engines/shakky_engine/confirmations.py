"""Shakky's five entry-logic families: Trend Following, Candlestick, Mean
Reversion, Momentum, Intermarket.

Per the "Classic M5 Strategy" specification, each family is broken down
into atomic, independently-checkable confirmations (e.g. "EMA trend",
"MACD", "RSI" are three separate confirmations, not one combined Trend
Following verdict) -- matching the spec's own "Entry Requirements"
examples, which mix confirmations from different families into one
qualifying combination (e.g. "EMA trend + MACD + RSI", "Candlestick +
Support + DXY", "Momentum + Breakout + ADX"). `resolve_entry_signal`
pools every atomic confirmation this cycle produced and requires at
least three agreeing on the same direction before a trade is even
considered -- never a fabricated entry from one or two weak signals.

DXY is checked exactly once (in the Intermarket family), even though the
spec's own "Momentum" section separately restates the same "DXY falling
-> BUY / DXY rising -> SELL" rule -- both are the identical underlying
comparison, so it is computed once rather than duplicated under two names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.agents.technical.volatility import average_true_range
from src.engines.shakky_engine.candlestick_patterns import (
    classify_hammer_or_hanging_man,
    detect_doji_signal,
    detect_engulfing_signal,
    detect_pin_bar_signal,
)
from src.engines.shakky_engine.indicators import (
    bollinger_bands,
    nearest_resistance,
    nearest_support,
    support_resistance_levels,
)
from src.models.candle import Candle
from src.utils.indicators import (
    average_directional_index,
    exponential_moving_average,
    macd,
    rate_of_change,
    relative_strength_index,
)

Direction = Literal["buy", "sell"]

_EMA_FAST_PERIOD = 9
_EMA_MID_PERIOD = 21
_EMA_SLOW_PERIOD = 50
_RSI_PERIOD = 14
_ADX_PERIOD = 14
_ATR_PERIOD = 14
_ADX_TREND_STRENGTH_THRESHOLD = 25.0
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_MEAN_REVERSION_ATR_MULTIPLE = 2.0
_LEVEL_PROXIMITY_PCT = 0.15
_BREAKOUT_LOOKBACK = 20
_MOMENTUM_IMPULSE_ROC_PERIOD = 5
_MOMENTUM_IMPULSE_ATR_MULTIPLE = 1.5
_MIN_CONFIRMATIONS_TO_ENTER = 3


@dataclass(frozen=True, slots=True)
class Confirmation:
    """One atomic, independently-checkable piece of entry evidence.

    Attributes:
        family: Which of the five entry-logic families produced this
            (for display/journaling only -- entry counting pools all
            families together).
        name: A short tag, e.g. "ema_trend", "pin_bar", "rsi".
        direction: "buy" or "sell".
        detail: Human-readable (English) explanation of the specific
            reading that produced this confirmation.
    """

    family: str
    name: str
    direction: Direction
    detail: str


def _closes(candles: list[Candle]) -> list[float]:
    return [candle.close for candle in candles]


def ema_trend_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Trend Following: EMA9 > EMA21 > EMA50 (buy) or EMA9 < EMA21 < EMA50 (sell)."""
    closes = _closes(m5_candles)
    fast = exponential_moving_average(closes, period=_EMA_FAST_PERIOD)
    mid = exponential_moving_average(closes, period=_EMA_MID_PERIOD)
    slow = exponential_moving_average(closes, period=_EMA_SLOW_PERIOD)
    if fast is None or mid is None or slow is None:
        return None
    ema9, ema21, ema50 = fast[-1], mid[-1], slow[-1]
    if ema9 > ema21 > ema50:
        return Confirmation(
            family="trend_following",
            name="ema_trend",
            direction="buy",
            detail=f"EMA9 {ema9:.2f} > EMA21 {ema21:.2f} > EMA50 {ema50:.2f}",
        )
    if ema9 < ema21 < ema50:
        return Confirmation(
            family="trend_following",
            name="ema_trend",
            direction="sell",
            detail=f"EMA9 {ema9:.2f} < EMA21 {ema21:.2f} < EMA50 {ema50:.2f}",
        )
    return None


def macd_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Trend Following: MACD(12,26,9) line above/below its signal line."""
    result = macd(_closes(m5_candles))
    if result is None or result.histogram == 0:
        return None
    direction: Direction = "buy" if result.histogram > 0 else "sell"
    return Confirmation(
        family="trend_following",
        name="macd",
        direction=direction,
        detail=f"MACD histogram {result.histogram:+.4f}",
    )


def pin_bar_level_confirmation(
    m5_candles: list[Candle], *, support_levels: list[float], resistance_levels: list[float]
) -> Confirmation | None:
    """Candlestick: a pin bar whose wick points away from a nearby support/resistance level."""
    signal = detect_pin_bar_signal(m5_candles[-1])
    if signal is None or signal.direction is None:
        return None
    price = m5_candles[-1].close
    if signal.direction == "buy":
        level = nearest_support(support_levels, price)
    else:
        level = nearest_resistance(resistance_levels, price)
    if level is None or price == 0:
        return None
    if abs(price - level) / price * 100 > _LEVEL_PROXIMITY_PCT:
        return None
    return Confirmation(
        family="candlestick",
        name="pin_bar",
        direction=signal.direction,
        detail=f"Pin bar near level {level:.2f} (price {price:.2f})",
    )


def engulfing_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Candlestick: a bullish/bearish engulfing candle."""
    if len(m5_candles) < 2:
        return None
    signal = detect_engulfing_signal(m5_candles[-2], m5_candles[-1])
    if signal is None or signal.direction is None:
        return None
    return Confirmation(
        family="candlestick", name="engulfing", direction=signal.direction, detail=signal.name
    )


def doji_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Candlestick: a doji, given a direction by the short-term EMA9-vs-EMA21 lean.

    Per the "Doji + confirmation" entry rule: a doji alone has no
    direction, so it only becomes a confirmation once paired with the
    short-term trend context (EMA9 vs EMA21) that "confirms" a side --
    never a fabricated direction from an inherently neutral candle.
    """
    signal = detect_doji_signal(m5_candles[-1])
    if signal is None:
        return None
    closes = _closes(m5_candles)
    fast = exponential_moving_average(closes, period=_EMA_FAST_PERIOD)
    mid = exponential_moving_average(closes, period=_EMA_MID_PERIOD)
    if fast is None or mid is None or fast[-1] == mid[-1]:
        return None
    direction: Direction = "buy" if fast[-1] > mid[-1] else "sell"
    return Confirmation(
        family="candlestick",
        name="doji",
        direction=direction,
        detail=f"Doji with EMA9 {'above' if direction == 'buy' else 'below'} EMA21",
    )


def hammer_hanging_man_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Candlestick: a hammer (after a downswing) or hanging man (after an upswing)."""
    signal = classify_hammer_or_hanging_man(m5_candles)
    if signal is None or signal.direction is None:
        return None
    return Confirmation(
        family="candlestick", name=signal.name, direction=signal.direction, detail=signal.name
    )


def mean_reversion_atr_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Mean Reversion: price more than 2 ATR away from EMA50."""
    closes = _closes(m5_candles)
    slow_ema = exponential_moving_average(closes, period=_EMA_SLOW_PERIOD)
    atr = average_true_range(m5_candles, period=_ATR_PERIOD)
    if slow_ema is None or atr is None or atr <= 0:
        return None
    price = closes[-1]
    distance = price - slow_ema[-1]
    if distance > _MEAN_REVERSION_ATR_MULTIPLE * atr:
        return Confirmation(
            family="mean_reversion",
            name="atr_extension",
            direction="sell",
            detail=f"Price {distance / atr:.2f} ATR above EMA50 (reversion down expected)",
        )
    if distance < -_MEAN_REVERSION_ATR_MULTIPLE * atr:
        return Confirmation(
            family="mean_reversion",
            name="atr_extension",
            direction="buy",
            detail=f"Price {abs(distance) / atr:.2f} ATR below EMA50 (reversion up expected)",
        )
    return None


def rsi_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Mean Reversion: RSI(14) oversold (buy) or overbought (sell)."""
    rsi = relative_strength_index(_closes(m5_candles), period=_RSI_PERIOD)
    if rsi is None:
        return None
    if rsi < _RSI_OVERSOLD:
        return Confirmation(
            family="mean_reversion", name="rsi", direction="buy", detail=f"RSI {rsi:.1f} oversold"
        )
    if rsi > _RSI_OVERBOUGHT:
        return Confirmation(
            family="mean_reversion",
            name="rsi",
            direction="sell",
            detail=f"RSI {rsi:.1f} overbought",
        )
    return None


def bollinger_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Mean Reversion: price at/beyond the lower (buy) or upper (sell) Bollinger Band."""
    bands = bollinger_bands(_closes(m5_candles))
    if bands is None or bands.upper_band == bands.lower_band:
        return None  # zero-width bands (no volatility) -- "at both bands" is not a real signal
    price = m5_candles[-1].close
    if price <= bands.lower_band:
        return Confirmation(
            family="mean_reversion",
            name="bollinger_band",
            direction="buy",
            detail=f"Price {price:.2f} at/below lower band {bands.lower_band:.2f}",
        )
    if price >= bands.upper_band:
        return Confirmation(
            family="mean_reversion",
            name="bollinger_band",
            direction="sell",
            detail=f"Price {price:.2f} at/above upper band {bands.upper_band:.2f}",
        )
    return None


def momentum_impulse_confirmation(m5_candles: list[Candle]) -> Confirmation | None:
    """Momentum: a strong recent impulse (rate of change beyond an ATR-scaled threshold)."""
    closes = _closes(m5_candles)
    roc = rate_of_change(closes, period=_MOMENTUM_IMPULSE_ROC_PERIOD)
    atr = average_true_range(m5_candles, period=_ATR_PERIOD)
    price = closes[-1]
    if roc is None or atr is None or atr <= 0 or price <= 0:
        return None
    move = price - closes[-_MOMENTUM_IMPULSE_ROC_PERIOD - 1]
    if abs(move) < _MOMENTUM_IMPULSE_ATR_MULTIPLE * atr:
        return None
    return Confirmation(
        family="momentum",
        name="momentum",
        direction="buy" if move > 0 else "sell",
        detail=f"{_MOMENTUM_IMPULSE_ROC_PERIOD}-bar move {roc:+.2f}% ({abs(move) / atr:.2f} ATR)",
    )


def breakout_confirmation(
    m5_candles: list[Candle], *, support_levels: list[float], resistance_levels: list[float]
) -> Confirmation | None:
    """Momentum: a candle that closes beyond recent support/resistance structure."""
    price = m5_candles[-1].close
    # The level about to be broken is found from the PRIOR close -- once
    # price has already broken past it, that level sits on the wrong side
    # of the current price to be found as "nearest" to it anymore.
    previous_price = m5_candles[-2].close
    resistance = nearest_resistance(resistance_levels, previous_price)
    support = nearest_support(support_levels, previous_price)
    lookback_high = max(candle.high for candle in m5_candles[-_BREAKOUT_LOOKBACK - 1 : -1])
    lookback_low = min(candle.low for candle in m5_candles[-_BREAKOUT_LOOKBACK - 1 : -1])
    if resistance is not None and price > max(resistance, lookback_high):
        return Confirmation(
            family="momentum",
            name="breakout",
            direction="buy",
            detail=f"Close {price:.2f} broke above resistance {resistance:.2f}",
        )
    if support is not None and price < min(support, lookback_low):
        return Confirmation(
            family="momentum",
            name="breakout",
            direction="sell",
            detail=f"Close {price:.2f} broke below support {support:.2f}",
        )
    return None


def adx_strength_confirmation(
    m5_candles: list[Candle], direction: Direction
) -> Confirmation | None:
    """Momentum: ADX confirms enough trend strength for `direction` (itself non-directional)."""
    adx = average_directional_index(m5_candles, period=_ADX_PERIOD)
    if adx is None or adx < _ADX_TREND_STRENGTH_THRESHOLD:
        return None
    return Confirmation(
        family="momentum",
        name="adx",
        direction=direction,
        detail=f"ADX {adx:.1f} confirms trend strength",
    )


def dxy_confirmation(dxy_candles: list[Candle]) -> Confirmation | None:
    """Intermarket: DXY falling implies gold buy pressure, DXY rising implies sell pressure."""
    roc = rate_of_change(_closes(dxy_candles), period=_MOMENTUM_IMPULSE_ROC_PERIOD)
    if roc is None or roc == 0:
        return None
    return Confirmation(
        family="intermarket",
        name="dxy",
        direction="buy" if roc < 0 else "sell",
        detail=f"DXY {_MOMENTUM_IMPULSE_ROC_PERIOD}-bar change {roc:+.2f}%",
    )


def intermarket_structure_confirmation(
    m5_candles: list[Candle],
    dxy_candles: list[Candle],
    *,
    support_levels: list[float],
    resistance_levels: list[float],
) -> Confirmation | None:
    """Intermarket: gold sitting at support/resistance while DXY agrees."""
    dxy = dxy_confirmation(dxy_candles)
    if dxy is None:
        return None
    price = m5_candles[-1].close
    if price == 0:
        return None
    if dxy.direction == "buy":
        level = nearest_support(support_levels, price)
    else:
        level = nearest_resistance(resistance_levels, price)
    if level is None or abs(price - level) / price * 100 > _LEVEL_PROXIMITY_PCT:
        return None
    return Confirmation(
        family="intermarket",
        name="intermarket_structure",
        direction=dxy.direction,
        detail=f"Gold at {level:.2f} with DXY {dxy.detail}",
    )


def collect_confirmations(
    *, m5_candles: list[Candle], dxy_candles: list[Candle] | None
) -> list[Confirmation]:
    """Run every entry-logic family and pool every atomic confirmation found.

    Args:
        m5_candles: Primary M5 candles, ordered by timestamp ascending.
        dxy_candles: Recent DXY candles for the Intermarket family, if
            the DXY correlated instrument is configured. None skips the
            Intermarket family entirely -- never a fabricated DXY reading.

    Returns:
        Every confirmation found this cycle, across all five families,
        in no particular order.
    """
    support_levels, resistance_levels = support_resistance_levels(m5_candles)
    confirmations: list[Confirmation] = []

    for check in (ema_trend_confirmation, macd_confirmation):
        confirmation = check(m5_candles)
        if confirmation is not None:
            confirmations.append(confirmation)

    pin_bar = pin_bar_level_confirmation(
        m5_candles, support_levels=support_levels, resistance_levels=resistance_levels
    )
    if pin_bar is not None:
        confirmations.append(pin_bar)
    for check in (engulfing_confirmation, doji_confirmation, hammer_hanging_man_confirmation):
        confirmation = check(m5_candles)
        if confirmation is not None:
            confirmations.append(confirmation)

    for check in (mean_reversion_atr_confirmation, rsi_confirmation, bollinger_confirmation):
        confirmation = check(m5_candles)
        if confirmation is not None:
            confirmations.append(confirmation)

    momentum = momentum_impulse_confirmation(m5_candles)
    if momentum is not None:
        confirmations.append(momentum)
    breakout = breakout_confirmation(
        m5_candles, support_levels=support_levels, resistance_levels=resistance_levels
    )
    if breakout is not None:
        confirmations.append(breakout)
    momentum_source = momentum or breakout
    if momentum_source is not None:
        adx = adx_strength_confirmation(m5_candles, momentum_source.direction)
        if adx is not None:
            confirmations.append(adx)

    if dxy_candles is not None:
        intermarket = intermarket_structure_confirmation(
            m5_candles,
            dxy_candles,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )
        if intermarket is not None:
            confirmations.append(intermarket)

    return confirmations


def resolve_entry_signal(
    confirmations: list[Confirmation],
) -> tuple[Direction, list[Confirmation]] | None:
    """Require at least three confirmations agreeing on one direction to enter.

    Args:
        confirmations: Every confirmation `collect_confirmations` found.

    Returns:
        `(direction, agreeing_confirmations)` for whichever side has at
        least `_MIN_CONFIRMATIONS_TO_ENTER` confirmations and more than
        the other side, or None if neither side qualifies -- never a
        forced trade from a weak or tied read.
    """
    buys = [c for c in confirmations if c.direction == "buy"]
    sells = [c for c in confirmations if c.direction == "sell"]
    if len(buys) >= _MIN_CONFIRMATIONS_TO_ENTER and len(buys) > len(sells):
        return "buy", buys
    if len(sells) >= _MIN_CONFIRMATIONS_TO_ENTER and len(sells) > len(buys):
        return "sell", sells
    return None
