"""Dynamic trailing stop / break-even trigger (production "Position Management" requirement).

Per the spec: "Trailing Stop and Break-Even must never follow fixed rules
-- must be adjusted dynamically according to volatility, liquidity, order
flow, higher timeframe trend, market regime, support/resistance, news
risk." Every input here is a signal this platform already computes
elsewhere this cycle (`VolatilityAgent`/`SupportResistanceAgent`/`TrendAgent`
reports via `CombinedVote.agent_reports`, the Order Flow Engine's vote,
the classified market regime) -- never a fabricated number. News risk
defaults to "not imminent" when the News department is unconfigured
(this platform's existing reduced-confidence pattern), not a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

_BASE_BREAKEVEN_TRIGGER_R = 1.0
_MIN_BREAKEVEN_TRIGGER_R = 0.5
_MAX_BREAKEVEN_TRIGGER_R = 2.5

_HIGH_VOLATILITY_ATR_RATIO = 1.3
_LOW_VOLATILITY_ATR_RATIO = 0.7
_STRONG_ORDER_FLOW_CONFIDENCE = 0.6

_TRAIL_RISK_DISTANCE_FRACTION = 0.5
_TREND_FAVORING_REGIMES = frozenset({"bull_trend", "bear_trend"})
_CHOPPY_REGIMES = frozenset({"range", "accumulation", "distribution", "high_volatility"})

# A support/resistance level closer to price than this fraction of the
# computed trail distance is treated as market structure worth respecting,
# rather than noise too close to be meaningful.
_MIN_STRUCTURE_RELEVANCE_FRACTION = 0.1
# Small buffer (percent of the level's price) placed just beyond the
# support/resistance level itself, so the stop isn't sitting exactly on
# a level the market may briefly test.
_STRUCTURE_STOP_BUFFER_PCT = 0.1


@dataclass(frozen=True, slots=True)
class DynamicStopInputs:
    """Every real signal this cycle's dynamic stop computation draws on.

    Attributes:
        atr_ratio: Current ATR / baseline ATR, from
            `VolatilityAgent`'s report metrics (`"atr_ratio"`). None if
            that agent didn't run or had insufficient history.
        order_flow_bias: The Order Flow Engine's directional read, if any.
        order_flow_confidence: The Order Flow Engine's confidence, 0-1.
        htf_trend_bias: `TrendAgent`'s directional read, if any.
        market_regime: This cycle's classified regime, if known.
        nearest_support: Nearest support price below/at the current price,
            from `SupportResistanceAgent`'s metrics, if any.
        nearest_resistance: Nearest resistance price above/at the current
            price, from `SupportResistanceAgent`'s metrics, if any.
        news_risk_imminent: Whether high-impact news is imminent. False
            when the News department is unconfigured -- an honest
            "unknown treated as no elevated signal," not a guess.
    """

    atr_ratio: float | None = None
    order_flow_bias: str | None = None
    order_flow_confidence: float = 0.0
    htf_trend_bias: str | None = None
    market_regime: str | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    news_risk_imminent: bool = False


def _volatility_multiplier(atr_ratio: float | None) -> float:
    if atr_ratio is None:
        return 1.0
    if atr_ratio >= _HIGH_VOLATILITY_ATR_RATIO:
        return 1.3
    if atr_ratio <= _LOW_VOLATILITY_ATR_RATIO:
        return 0.7
    return 1.0


def compute_dynamic_breakeven_trigger_r_multiple(
    inputs: DynamicStopInputs, position_direction: Literal["buy", "sell"]
) -> float:
    """Compute how many R-multiples of favorable move must occur before break-even.

    Args:
        inputs: This cycle's real signals.
        position_direction: The position's own direction.

    Returns:
        The R-multiple trigger, clamped to
        `[_MIN_BREAKEVEN_TRIGGER_R, _MAX_BREAKEVEN_TRIGGER_R]`.
    """
    multiplier = _volatility_multiplier(inputs.atr_ratio)

    if inputs.news_risk_imminent:
        multiplier *= 0.6

    position_bias = "bullish" if position_direction == "buy" else "bearish"
    opposing_bias = "bearish" if position_direction == "buy" else "bullish"
    if (
        inputs.order_flow_bias == opposing_bias
        and inputs.order_flow_confidence >= _STRONG_ORDER_FLOW_CONFIDENCE
    ):
        multiplier *= 0.7
    elif inputs.htf_trend_bias == position_bias:
        multiplier *= 1.2

    if inputs.market_regime in _CHOPPY_REGIMES:
        multiplier *= 1.15
    elif inputs.market_regime in _TREND_FAVORING_REGIMES and inputs.htf_trend_bias == position_bias:
        multiplier *= 1.1

    trigger = _BASE_BREAKEVEN_TRIGGER_R * multiplier
    return max(_MIN_BREAKEVEN_TRIGGER_R, min(trigger, _MAX_BREAKEVEN_TRIGGER_R))


def compute_trailing_stop_price(
    inputs: DynamicStopInputs,
    *,
    position_direction: Literal["buy", "sell"],
    current_price: float,
    risk_distance: float,
) -> float:
    """Compute the trailing stop price once a position has reached break-even.

    Args:
        inputs: This cycle's real signals.
        position_direction: The position's own direction.
        current_price: The position's current market price.
        risk_distance: The position's original entry-to-stop distance.

    Returns:
        The candidate new stop price. The caller must still check this is
        more favorable than the current stop before applying it -- a
        trailing stop only ever tightens, never loosens.
    """
    multiplier = _volatility_multiplier(inputs.atr_ratio)
    if inputs.news_risk_imminent:
        multiplier *= 0.7
    distance = risk_distance * _TRAIL_RISK_DISTANCE_FRACTION * multiplier

    if position_direction == "buy":
        candidate = current_price - distance
        if inputs.nearest_support is not None and inputs.nearest_support < current_price:
            structure_gap = current_price - inputs.nearest_support
            if structure_gap >= distance * _MIN_STRUCTURE_RELEVANCE_FRACTION:
                candidate = max(
                    candidate, inputs.nearest_support * (1 - _STRUCTURE_STOP_BUFFER_PCT / 100)
                )
        return candidate

    candidate = current_price + distance
    if inputs.nearest_resistance is not None and inputs.nearest_resistance > current_price:
        structure_gap = inputs.nearest_resistance - current_price
        if structure_gap >= distance * _MIN_STRUCTURE_RELEVANCE_FRACTION:
            candidate = min(
                candidate, inputs.nearest_resistance * (1 + _STRUCTURE_STOP_BUFFER_PCT / 100)
            )
    return candidate
