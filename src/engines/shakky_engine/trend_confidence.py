"""Trend Confidence Engine for Shakky (Classic M5 Strategy Engine).

Per the user's own analysis of a successful trading system: its edge was
not the indicators, but correctly recognizing large market moves and
managing them well. This module answers "how big is the current move,
and is it likely to continue?" for Shakky's own M5 signal, so
`exit_management`/`hold_manager`/`position_scaling` can let a strong
trend run instead of exiting at a fixed target.

Deliberately fully deterministic/rule-based, like the rest of
`src.engines.shakky_engine` -- Shakky's own specification (see
`service.py`'s module docstring) forbids using Chief AI decision logic,
the Trade Quality Engine, or any other existing AI scoring. Every input
here is either a plain indicator this engine (or `src.utils.indicators`/
`src.agents.technical.volatility`) already computes, or an honest
"unknown, excluded from the score" when data is missing -- never a
fabricated reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.agents.technical.volatility import average_true_range
from src.core.technical_analysis.swings import find_swing_points
from src.engines.shakky_engine.indicators import nearest_resistance, nearest_support
from src.models.candle import Candle
from src.utils.indicators import (
    average_directional_index,
    exponential_moving_average,
    rate_of_change,
)

Direction = Literal["buy", "sell"]
TrendConfidenceLevel = Literal["minor", "normal", "strong", "exceptional"]

_EMA_FAST_PERIOD = 9
_EMA_MID_PERIOD = 21
_EMA_SLOW_PERIOD = 50
_MIN_CANDLES_FOR_TREND_STACK = 60

_ADX_PERIOD = 14
_ADX_DEVELOPING = 20.0
_ADX_EXCEPTIONAL = 45.0

_ATR_PERIOD = 14
_ATR_BASELINE_LOOKBACK = 40
_ATR_RATIO_LOW = 0.8
_ATR_RATIO_HIGH = 1.8

_STRUCTURE_SWING_LOOKAROUND = 2
_STRUCTURE_MAX_SWINGS_CHECKED = 4

_LIQUIDITY_ROOM_ATR_LOW = 0.5
_LIQUIDITY_ROOM_ATR_HIGH = 3.0

_DXY_ROC_PERIOD = 5
_DXY_ALIGNMENT_SCALE = 20.0

_NEWS_IMMINENT_SCORE_DISCOUNT = 0.85

# `score` (0-100) bucket boundaries -- classification only, the
# continuous `score` is always available for anything needing finer
# granularity than the four labels.
_LEVEL_NORMAL_THRESHOLD = 35.0
_LEVEL_STRONG_THRESHOLD = 60.0
_LEVEL_EXCEPTIONAL_THRESHOLD = 80.0

# (component weight, name) -- must sum to 100; a component missing its
# input data is excluded and the remaining weights are renormalized,
# rather than silently scored as 0 (which would understate confidence
# just because e.g. DXY candles weren't supplied this cycle).
_WEIGHT_TREND_AGREEMENT = 30.0
_WEIGHT_ADX = 20.0
_WEIGHT_ATR_EXPANSION = 15.0
_WEIGHT_STRUCTURE = 15.0
_WEIGHT_LIQUIDITY_ROOM = 10.0
_WEIGHT_DXY = 10.0


@dataclass(frozen=True, slots=True)
class TrendConfidenceAssessment:
    """How large the current M5 move is, and whether it is likely to continue.

    Attributes:
        level: Coarse classification of move size.
        score: The underlying continuous 0-100 score `level` was
            bucketed from.
        continuation_likely: Whether the move looks likely to continue
            rather than exhaust -- `level` is "strong"/"exceptional" and
            ADX is not already declining out of a trending regime.
        reasons: Every component's own contribution, human-readable.
    """

    level: TrendConfidenceLevel
    score: float
    continuation_likely: bool
    reasons: list[str] = field(default_factory=list)


def _closes(candles: list[Candle]) -> list[float]:
    return [candle.close for candle in candles]


def _trend_stack_direction(candles: list[Candle]) -> Direction | None:
    """The EMA9/21/50 stack direction for one timeframe, or None if not stacked/insufficient.

    Mirrors `service.py`'s own private helper of the same purpose --
    kept as a small, self-contained duplication of the concept (not a
    shared import) per that module's own documented reasoning: this
    engine's pieces stay independently readable rather than growing a
    cross-module private dependency for a five-line calculation.
    """
    if len(candles) < _MIN_CANDLES_FOR_TREND_STACK:
        return None
    closes = _closes(candles)
    fast = exponential_moving_average(closes, period=_EMA_FAST_PERIOD)
    mid = exponential_moving_average(closes, period=_EMA_MID_PERIOD)
    slow = exponential_moving_average(closes, period=_EMA_SLOW_PERIOD)
    if fast is None or mid is None or slow is None:
        return None
    ema9, ema21, ema50 = fast[-1], mid[-1], slow[-1]
    if ema9 > ema21 > ema50:
        return "buy"
    if ema9 < ema21 < ema50:
        return "sell"
    return None


def _trend_agreement_score(
    direction: Direction, timeframe_candles: dict[str, list[Candle] | None]
) -> tuple[float | None, str]:
    agree = 0
    opinionated = 0
    for candles in timeframe_candles.values():
        if candles is None:
            continue
        stack_direction = _trend_stack_direction(candles)
        if stack_direction is None:
            continue
        opinionated += 1
        if stack_direction == direction:
            agree += 1
    if opinionated == 0:
        return None, "trend_agreement:no_timeframe_data"
    score = agree / opinionated * 100
    return score, f"trend_agreement:{agree}/{opinionated}_timeframes_agree"


def _adx_score(m5_candles: list[Candle]) -> tuple[float | None, str]:
    adx = average_directional_index(m5_candles, period=_ADX_PERIOD)
    if adx is None:
        return None, "adx:insufficient_history"
    # Linear interpolation between the "developing trend" and
    # "exceptional trend" thresholds already used elsewhere in this
    # engine (`confirmations._ADX_TREND_STRENGTH_THRESHOLD = 25.0` sits
    # inside this band) -- not a new, unrelated scale.
    score = (adx - _ADX_DEVELOPING) / (_ADX_EXCEPTIONAL - _ADX_DEVELOPING) * 100
    return max(0.0, min(score, 100.0)), f"adx:{adx:.1f}"


def _atr_expansion_score(m5_candles: list[Candle]) -> tuple[float | None, str]:
    current_atr = average_true_range(m5_candles, period=_ATR_PERIOD)
    if current_atr is None or len(m5_candles) < _ATR_PERIOD + _ATR_BASELINE_LOOKBACK:
        return None, "atr_expansion:insufficient_history"
    baseline_window = m5_candles[-(_ATR_PERIOD + _ATR_BASELINE_LOOKBACK) : -_ATR_BASELINE_LOOKBACK]
    baseline_atrs = [
        average_true_range(baseline_window[: i + 1], period=_ATR_PERIOD)
        for i in range(_ATR_PERIOD - 1, len(baseline_window))
    ]
    valid_baseline = [value for value in baseline_atrs if value is not None and value > 0]
    if not valid_baseline:
        return None, "atr_expansion:no_baseline"
    baseline_atr = sum(valid_baseline) / len(valid_baseline)
    ratio = current_atr / baseline_atr
    score = (ratio - _ATR_RATIO_LOW) / (_ATR_RATIO_HIGH - _ATR_RATIO_LOW) * 100
    return max(0.0, min(score, 100.0)), f"atr_expansion:ratio={ratio:.2f}"


def _structure_score(direction: Direction, m5_candles: list[Candle]) -> tuple[float | None, str]:
    swings = find_swing_points(m5_candles, lookaround=_STRUCTURE_SWING_LOOKAROUND)
    highs = [swing.candle.high for swing in swings if swing.kind == "high"][
        -_STRUCTURE_MAX_SWINGS_CHECKED:
    ]
    lows = [swing.candle.low for swing in swings if swing.kind == "low"][
        -_STRUCTURE_MAX_SWINGS_CHECKED:
    ]
    high_pairs = list(zip(highs, highs[1:], strict=False))
    low_pairs = list(zip(lows, lows[1:], strict=False))
    if not high_pairs and not low_pairs:
        return None, "structure:insufficient_swings"

    if direction == "buy":
        consistent = sum(1 for a, b in high_pairs if b > a) + sum(1 for a, b in low_pairs if b > a)
    else:
        consistent = sum(1 for a, b in high_pairs if b < a) + sum(1 for a, b in low_pairs if b < a)
    total_pairs = len(high_pairs) + len(low_pairs)
    score = consistent / total_pairs * 100
    return score, f"structure:{consistent}/{total_pairs}_swings_consistent"


def _liquidity_room_score(
    direction: Direction, entry_price: float, atr: float | None, m5_candles: list[Candle]
) -> tuple[float | None, str]:
    if atr is None or atr <= 0:
        return None, "liquidity_room:undefined_atr"
    swings = find_swing_points(m5_candles, lookaround=_STRUCTURE_SWING_LOOKAROUND)
    lows = sorted(swing.candle.low for swing in swings if swing.kind == "low")
    highs = sorted(swing.candle.high for swing in swings if swing.kind == "high")
    opposing_level = (
        nearest_resistance(highs, entry_price)
        if direction == "buy"
        else nearest_support(lows, entry_price)
    )
    if opposing_level is None:
        return None, "liquidity_room:no_opposing_level"
    distance_atr = abs(opposing_level - entry_price) / atr
    score = (
        (distance_atr - _LIQUIDITY_ROOM_ATR_LOW)
        / (_LIQUIDITY_ROOM_ATR_HIGH - _LIQUIDITY_ROOM_ATR_LOW)
        * 100
    )
    return max(0.0, min(score, 100.0)), f"liquidity_room:{distance_atr:.1f}x_atr_to_next_level"


def _dxy_score(direction: Direction, dxy_candles: list[Candle] | None) -> tuple[float | None, str]:
    if dxy_candles is None:
        return None, "dxy:not_configured"
    roc = rate_of_change(_closes(dxy_candles), period=_DXY_ROC_PERIOD)
    if roc is None:
        return None, "dxy:insufficient_history"
    # Gold and DXY are the well-established inverse relationship this
    # engine already applies in `confirmations.dxy_confirmation`: DXY
    # falling supports a gold buy, DXY rising supports a gold sell.
    gold_supportive_move = -roc if direction == "buy" else roc
    score = 50.0 + gold_supportive_move * _DXY_ALIGNMENT_SCALE
    return max(
        0.0, min(score, 100.0)
    ), f"dxy:roc={roc:.2f}%_{'supportive' if gold_supportive_move > 0 else 'opposing'}"


def bucket_trend_confidence_level(score: float) -> TrendConfidenceLevel:
    """Classify a 0-100 Trend Confidence score into its coarse level.

    Exposed publicly (not just used internally by `assess_trend_confidence`)
    so callers that only persisted `Trade.entry_trend_confidence_score`
    can recover the same `minor`/`normal`/`strong`/`exceptional` bucketing
    later, e.g. `exit_management.evaluate_exit`'s `entry_trend_confidence_level`.
    """
    if score >= _LEVEL_EXCEPTIONAL_THRESHOLD:
        return "exceptional"
    if score >= _LEVEL_STRONG_THRESHOLD:
        return "strong"
    if score >= _LEVEL_NORMAL_THRESHOLD:
        return "normal"
    return "minor"


def assess_trend_confidence(
    *,
    direction: Direction,
    entry_price: float,
    d1_candles: list[Candle] | None,
    h4_candles: list[Candle] | None,
    h1_candles: list[Candle] | None,
    m15_candles: list[Candle] | None,
    m5_candles: list[Candle],
    dxy_candles: list[Candle] | None,
    news_risk_imminent: bool = False,
) -> TrendConfidenceAssessment:
    """Classify how large the current M5 move is, and whether it's likely to continue.

    Args:
        direction: The direction being assessed (Shakky's own signal/position direction).
        entry_price: Current price, used for the liquidity-room component.
        d1_candles: D1 candles, if available.
        h4_candles: H4 candles, if available.
        h1_candles: H1 candles, if available.
        m15_candles: M15 candles, if available.
        m5_candles: Primary M5 candles, ordered by timestamp ascending.
        dxy_candles: Recent DXY candles, if configured.
        news_risk_imminent: Whether high-impact news is imminent. False
            when unconfigured -- an honest "unknown treated as no
            elevated signal," matching `src.engines.risk_engine.dynamic_stop`.

    Returns:
        A `TrendConfidenceAssessment`. Components with insufficient data
        are excluded and the remaining weights renormalized, so a
        missing input never silently drags the score toward "minor."
    """
    atr = average_true_range(m5_candles, period=_ATR_PERIOD)

    trend_score, trend_reason = _trend_agreement_score(
        direction,
        {
            "d1": d1_candles,
            "h4": h4_candles,
            "h1": h1_candles,
            "m15": m15_candles,
            "m5": m5_candles,
        },
    )
    adx_score, adx_reason = _adx_score(m5_candles)
    atr_score, atr_reason = _atr_expansion_score(m5_candles)
    structure_score, structure_reason = _structure_score(direction, m5_candles)
    liquidity_score, liquidity_reason = _liquidity_room_score(
        direction, entry_price, atr, m5_candles
    )
    dxy_score, dxy_reason = _dxy_score(direction, dxy_candles)

    components = [
        (_WEIGHT_TREND_AGREEMENT, trend_score, trend_reason),
        (_WEIGHT_ADX, adx_score, adx_reason),
        (_WEIGHT_ATR_EXPANSION, atr_score, atr_reason),
        (_WEIGHT_STRUCTURE, structure_score, structure_reason),
        (_WEIGHT_LIQUIDITY_ROOM, liquidity_score, liquidity_reason),
        (_WEIGHT_DXY, dxy_score, dxy_reason),
    ]
    reasons = [reason for _, _, reason in components]

    available = [(weight, score) for weight, score, _ in components if score is not None]
    if not available:
        return TrendConfidenceAssessment(
            level="minor",
            score=0.0,
            continuation_likely=False,
            reasons=[*reasons, "no_components_available"],
        )
    total_weight = sum(weight for weight, _ in available)
    raw_score = sum(weight * score for weight, score in available) / total_weight

    if news_risk_imminent:
        raw_score *= _NEWS_IMMINENT_SCORE_DISCOUNT
        reasons.append("news_risk_imminent:score_discounted")

    score = max(0.0, min(raw_score, 100.0))
    level = bucket_trend_confidence_level(score)

    adx = average_directional_index(m5_candles, period=_ADX_PERIOD)
    continuation_likely = level in ("strong", "exceptional") and (
        adx is None or adx >= _ADX_DEVELOPING
    )

    return TrendConfidenceAssessment(
        level=level, score=score, continuation_likely=continuation_likely, reasons=reasons
    )
