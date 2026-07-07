"""Price Action Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per AGENT_SYSTEM.md: "Analyze Pin Bars, Inside Bars, Outside Bars,
Engulfing, Doji, Hammer, Shooting Star, Marubozu, Rejection candles,
Continuation candles." Detects the classic single- and two-candle price
action patterns on the most recent candles using measurable body/wick
ratios — never a subjective visual read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.technical_analysis.agent import AgentReport, Bias, TechnicalAgent
from src.models.candle import Candle

PatternBias = Literal["bullish", "bearish", "neutral"]

_DOJI_BODY_RATIO = 0.1
_MARUBOZU_BODY_RATIO = 0.9
_PIN_BAR_WICK_RATIO = 0.66
_PIN_BAR_OPPOSITE_WICK_RATIO = 0.15
_CONFIDENCE_PER_PATTERN = 0.3


@dataclass(frozen=True, slots=True)
class CandlePattern:
    """A single detected candlestick pattern."""

    name: str
    bias: PatternBias


def _candle_range(candle: Candle) -> float:
    return candle.high - candle.low


def _body(candle: Candle) -> float:
    return abs(candle.close - candle.open)


def _upper_wick(candle: Candle) -> float:
    return candle.high - max(candle.open, candle.close)


def _lower_wick(candle: Candle) -> float:
    return min(candle.open, candle.close) - candle.low


def detect_doji(candle: Candle) -> CandlePattern | None:
    """Detect a doji: a candle whose body is a tiny fraction of its range."""
    candle_range = _candle_range(candle)
    if candle_range > 0 and _body(candle) / candle_range <= _DOJI_BODY_RATIO:
        return CandlePattern(name="doji", bias="neutral")
    return None


def detect_marubozu(candle: Candle) -> CandlePattern | None:
    """Detect a marubozu: a candle whose body dominates its range (minimal wicks)."""
    candle_range = _candle_range(candle)
    if candle_range > 0 and _body(candle) / candle_range >= _MARUBOZU_BODY_RATIO:
        bias: PatternBias = "bullish" if candle.close > candle.open else "bearish"
        return CandlePattern(name="marubozu", bias=bias)
    return None


def detect_pin_bar(candle: Candle) -> CandlePattern | None:
    """Detect a pin bar (hammer/shooting star): a long wick with a small opposite wick and body."""
    candle_range = _candle_range(candle)
    if candle_range == 0:
        return None
    lower_ratio = _lower_wick(candle) / candle_range
    upper_ratio = _upper_wick(candle) / candle_range
    if lower_ratio >= _PIN_BAR_WICK_RATIO and upper_ratio <= _PIN_BAR_OPPOSITE_WICK_RATIO:
        return CandlePattern(name="hammer", bias="bullish")
    if upper_ratio >= _PIN_BAR_WICK_RATIO and lower_ratio <= _PIN_BAR_OPPOSITE_WICK_RATIO:
        return CandlePattern(name="shooting_star", bias="bearish")
    return None


def detect_engulfing(previous: Candle, current: Candle) -> CandlePattern | None:
    """Detect an engulfing candle: `current` body fully contains, and opposes, `previous`."""
    previous_bullish = previous.close > previous.open
    current_bullish = current.close > current.open
    if previous_bullish == current_bullish:
        return None
    engulfs = min(current.open, current.close) <= min(
        previous.open, previous.close
    ) and max(current.open, current.close) >= max(previous.open, previous.close)
    if not engulfs:
        return None
    return CandlePattern(
        name="bullish_engulfing" if current_bullish else "bearish_engulfing",
        bias="bullish" if current_bullish else "bearish",
    )


def detect_inside_bar(previous: Candle, current: Candle) -> CandlePattern | None:
    """Detect an inside bar: `current`'s range is fully contained within `previous`'s."""
    if current.high <= previous.high and current.low >= previous.low:
        return CandlePattern(name="inside_bar", bias="neutral")
    return None


def detect_outside_bar(previous: Candle, current: Candle) -> CandlePattern | None:
    """Detect an outside bar: `current`'s range fully contains `previous`'s (and is wider)."""
    contains = current.high >= previous.high and current.low <= previous.low
    strictly_wider = current.high > previous.high or current.low < previous.low
    if contains and strictly_wider:
        return CandlePattern(name="outside_bar", bias="neutral")
    return None


class PriceActionAgent(TechnicalAgent):
    """Detects classic candlestick price action patterns on recent candles."""

    name = "price_action"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Detect price action patterns on the most recent one or two candles.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` biased toward the direction of the detected
            pattern(s), or neutral if none were found or they conflict.
        """
        if len(candles) < 2:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["Need at least 2 candles to detect price action patterns."],
            )

        current, previous = candles[-1], candles[-2]
        patterns: list[CandlePattern] = []
        for single_candle_detector in (detect_doji, detect_marubozu, detect_pin_bar):
            pattern = single_candle_detector(current)
            if pattern is not None:
                patterns.append(pattern)
        for two_candle_detector in (detect_engulfing, detect_inside_bar, detect_outside_bar):
            pattern = two_candle_detector(previous, current)
            if pattern is not None:
                patterns.append(pattern)

        if not patterns:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["No recognizable price action pattern on the most recent candle(s)."],
            )

        bullish_patterns = [pattern for pattern in patterns if pattern.bias == "bullish"]
        bearish_patterns = [pattern for pattern in patterns if pattern.bias == "bearish"]

        bias: Bias
        if bullish_patterns and not bearish_patterns:
            bias = "bullish"
        elif bearish_patterns and not bullish_patterns:
            bias = "bearish"
        else:
            bias = "neutral"

        supporting = [
            _describe(pattern) for pattern in patterns if bias != "neutral" and pattern.bias == bias
        ]
        opposing = [
            _describe(pattern)
            for pattern in patterns
            if pattern.bias != "neutral" and pattern.bias != bias
        ]
        confirming_count = sum(1 for pattern in patterns if pattern.bias == bias)
        confidence = (
            min(1.0, _CONFIDENCE_PER_PATTERN * confirming_count) if bias != "neutral" else 0.0
        )

        return AgentReport(
            agent_name=self.name,
            bias=bias,
            confidence=confidence,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics={"pattern_count": float(len(patterns))},
        )


def _describe(pattern: CandlePattern) -> str:
    return f"{pattern.name.replace('_', ' ').title()} detected"
