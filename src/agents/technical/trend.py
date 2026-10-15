"""Trend Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per AGENT_SYSTEM.md: "Measure Trend strength. Trend age. Trend
acceleration. Trend exhaustion." Direction and strength come from a
least-squares regression slope (`src.utils.statistics`); age counts
consecutive same-direction closes; acceleration compares the second half
of the window's slope against the first half.

Per the "Trend Engine" production requirement: EMA20/50/100/200 and ADX
supplement (never replace) the slope-based bias -- a full bullish/bearish
EMA "stack" and a strong ADX reading raise confidence in whichever
direction the regression slope already found, and a contradicting EMA
stack is reported as opposing evidence; neither ever flips the bias
itself, since a caller with too little history for EMA200 (200+ candles)
or ADX (29+ candles) must still get the same slope-only read this agent
has always produced.
"""

from __future__ import annotations

from src.core.technical_analysis.agent import AgentReport, Bias, TechnicalAgent
from src.models.candle import Candle
from src.utils.indicators import average_directional_index, exponential_moving_average
from src.utils.statistics import linear_regression_slope_pct

_MIN_CANDLES = 4
_DEFAULT_TREND_THRESHOLD_PCT = 0.05
_MIN_HALF_WINDOW = 2
_EMA_PERIODS: tuple[int, ...] = (20, 50, 100, 200)
_ADX_PERIOD = 14
_ADX_STRONG_TREND_THRESHOLD = 25.0
_EMA_ALIGNMENT_CONFIDENCE_BOOST = 0.15
_ADX_CONFIDENCE_BOOST = 0.15


class TrendAgent(TechnicalAgent):
    """Measures trend direction, strength, age and acceleration."""

    name = "trend"

    def __init__(self, *, trend_threshold_pct: float = _DEFAULT_TREND_THRESHOLD_PCT) -> None:
        """Initialize the agent.

        Args:
            trend_threshold_pct: Minimum absolute regression slope (%/bar)
                required to call the window trending rather than neutral.
        """
        self._trend_threshold_pct = trend_threshold_pct

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Measure trend direction, strength, age and acceleration.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` with bias "bullish"/"bearish" when a trend is
            detected, "neutral" otherwise.
        """
        if len(candles) < _MIN_CANDLES:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["Not enough candles to measure trend."],
            )

        closes = [candle.close for candle in candles]
        slope_pct = linear_regression_slope_pct(closes)

        bias: Bias
        if slope_pct >= self._trend_threshold_pct:
            bias = "bullish"
        elif slope_pct <= -self._trend_threshold_pct:
            bias = "bearish"
        else:
            bias = "neutral"

        age = self._trend_age(closes, bias)
        first_half_slope, second_half_slope = self._split_window_slopes(closes)
        accelerating = abs(second_half_slope) > abs(first_half_slope)

        supporting: list[str] = []
        opposing: list[str] = []
        confidence = 0.0

        if bias != "neutral":
            supporting.append(f"Regression slope {slope_pct:.3f}%/bar confirms {bias} trend")
            if accelerating:
                supporting.append("Trend is accelerating: second half steeper than first half")
            else:
                opposing.append("Trend is decelerating: possible exhaustion")
            confidence = min(1.0, abs(slope_pct) / (self._trend_threshold_pct * 4))

        metrics: dict[str, float] = {
            "slope_pct": slope_pct,
            "trend_age_bars": float(age),
            "first_half_slope_pct": first_half_slope,
            "second_half_slope_pct": second_half_slope,
        }

        ema_values: dict[int, float] = {}
        for period in _EMA_PERIODS:
            series = exponential_moving_average(closes, period=period)
            if series is not None:
                ema_values[period] = series[-1]
                metrics[f"ema_{period}"] = series[-1]

        if bias != "neutral" and len(ema_values) == len(_EMA_PERIODS):
            stacked_bullish = ema_values[20] > ema_values[50] > ema_values[100] > ema_values[200]
            stacked_bearish = ema_values[20] < ema_values[50] < ema_values[100] < ema_values[200]
            if (bias == "bullish" and stacked_bullish) or (bias == "bearish" and stacked_bearish):
                supporting.append("EMA20/50/100/200 are fully stacked, confirming the trend")
                confidence = min(1.0, confidence + _EMA_ALIGNMENT_CONFIDENCE_BOOST)
            elif (bias == "bullish" and stacked_bearish) or (bias == "bearish" and stacked_bullish):
                opposing.append("EMA20/50/100/200 are stacked against the detected trend")

        adx = average_directional_index(candles, period=_ADX_PERIOD)
        if adx is not None:
            metrics["adx"] = adx
            if bias != "neutral":
                if adx >= _ADX_STRONG_TREND_THRESHOLD:
                    supporting.append(f"ADX {adx:.1f} confirms a strong trend")
                    confidence = min(1.0, confidence + _ADX_CONFIDENCE_BOOST)
                else:
                    opposing.append(f"ADX {adx:.1f} suggests a weak or absent trend")

        return AgentReport(
            agent_name=self.name,
            bias=bias,
            confidence=confidence,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics=metrics,
        )

    @staticmethod
    def _trend_age(closes: list[float], bias: Bias) -> int:
        """Count consecutive most-recent bars moving in the trend direction."""
        if bias == "neutral":
            return 0
        age = 0
        for index in range(len(closes) - 1, 0, -1):
            continues_bullish = bias == "bullish" and closes[index] >= closes[index - 1]
            continues_bearish = bias == "bearish" and closes[index] <= closes[index - 1]
            if continues_bullish or continues_bearish:
                age += 1
            else:
                break
        return age

    @staticmethod
    def _split_window_slopes(closes: list[float]) -> tuple[float, float]:
        """Compute regression slopes for the first and second halves of the window."""
        midpoint = len(closes) // 2
        first_half = closes[:midpoint]
        second_half = closes[midpoint:]
        first_slope = (
            linear_regression_slope_pct(first_half) if len(first_half) >= _MIN_HALF_WINDOW else 0.0
        )
        second_slope = (
            linear_regression_slope_pct(second_half)
            if len(second_half) >= _MIN_HALF_WINDOW
            else 0.0
        )
        return first_slope, second_slope
