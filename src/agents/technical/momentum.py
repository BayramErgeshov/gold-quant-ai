"""Momentum Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per the "Momentum Engine" production requirement: "Analyze RSI, MACD,
Histogram, Divergence, ROC, Stochastic, Acceleration." Combines several
independent momentum readings into one bias/confidence report — no
single indicator (e.g. "RSI > 50") decides the bias alone; the bias is
the average direction across every available reading, and a detected
price/RSI divergence is reported as a distinct, separately-weighted
warning signal (a classic early-reversal read), never silently folded in.
"""

from __future__ import annotations

from typing import Literal

from src.core.technical_analysis.agent import AgentReport, Bias, TechnicalAgent
from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle
from src.utils.indicators import (
    macd,
    rate_of_change,
    relative_strength_index,
    relative_strength_index_series,
    stochastic_oscillator,
)

_RSI_PERIOD = 14
_ROC_PERIOD = 12
_STOCH_K_PERIOD = 14
_STOCH_D_PERIOD = 3
_MACD_FAST_PERIOD = 12
_MACD_SLOW_PERIOD = 26
_MACD_SIGNAL_PERIOD = 9
_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD = 30.0
_NEUTRAL_BAND = 0.15
_SWING_LOOKAROUND = 2
_DIVERGENCE_WEIGHT = 1.5
# Full-strength (+-1.0) normalization scales for magnitude-based signals --
# a MACD histogram of 0.1% of price, or a 5% ROC, count as maximal
# conviction; smaller readings scale down proportionally rather than
# being treated as equally strong as a large one.
_MACD_FULL_STRENGTH_PCT_OF_PRICE = 0.001
_ROC_FULL_STRENGTH_PCT = 5.0

DivergenceBias = Literal["bullish", "bearish"]


def _rsi_at_index(rsi_series: list[float], *, period: int, candle_index: int) -> float | None:
    """Map a candle index back to its RSI value in a series built via `_period` offset."""
    series_index = candle_index - period
    if series_index < 0 or series_index >= len(rsi_series):
        return None
    return rsi_series[series_index]


def detect_rsi_divergence(
    candles: list[Candle],
    *,
    rsi_period: int = _RSI_PERIOD,
    swing_lookaround: int = _SWING_LOOKAROUND,
) -> DivergenceBias | None:
    """Detect a classic price/RSI divergence between the last two swing points.

    Args:
        candles: Candles ordered by timestamp ascending.
        rsi_period: RSI period used to build the comparison series.
        swing_lookaround: Fractal swing-point window (`find_swing_points`).

    Returns:
        "bearish" if price made a higher high while RSI made a lower high
        (momentum weakening into a rising price -- a reversal warning);
        "bullish" if price made a lower low while RSI made a higher low;
        None if there is not enough data or no divergence is present.
    """
    closes = [candle.close for candle in candles]
    rsi_series = relative_strength_index_series(closes, period=rsi_period)
    if rsi_series is None:
        return None

    swings = find_swing_points(candles, lookaround=swing_lookaround)
    highs = [swing for swing in swings if swing.kind == "high"]
    lows = [swing for swing in swings if swing.kind == "low"]

    if len(highs) >= 2:
        previous_high, latest_high = highs[-2], highs[-1]
        previous_rsi = _rsi_at_index(
            rsi_series, period=rsi_period, candle_index=previous_high.index
        )
        latest_rsi = _rsi_at_index(rsi_series, period=rsi_period, candle_index=latest_high.index)
        if (
            previous_rsi is not None
            and latest_rsi is not None
            and latest_high.candle.high > previous_high.candle.high
            and latest_rsi < previous_rsi
        ):
            return "bearish"

    if len(lows) >= 2:
        previous_low, latest_low = lows[-2], lows[-1]
        previous_rsi = _rsi_at_index(rsi_series, period=rsi_period, candle_index=previous_low.index)
        latest_rsi = _rsi_at_index(rsi_series, period=rsi_period, candle_index=latest_low.index)
        if (
            previous_rsi is not None
            and latest_rsi is not None
            and latest_low.candle.low < previous_low.candle.low
            and latest_rsi > previous_rsi
        ):
            return "bullish"

    return None


class MomentumAgent(TechnicalAgent):
    """Combines RSI, MACD, ROC, Stochastic and RSI divergence into one momentum read."""

    name = "momentum"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Analyze momentum across several independent indicators.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` whose bias is the average direction across
            every available reading (never a single fixed threshold).
        """
        closes = [candle.close for candle in candles]
        rsi = relative_strength_index(closes, period=_RSI_PERIOD)
        if rsi is None:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=[f"Need at least {_RSI_PERIOD + 1} candles to compute RSI."],
            )

        metrics: dict[str, float] = {"rsi": rsi}
        supporting: list[str] = []
        opposing: list[str] = []
        signals: list[float] = [(rsi - 50.0) / 50.0]

        if rsi >= _RSI_OVERBOUGHT:
            opposing.append(f"RSI {rsi:.1f} is overbought")
        elif rsi <= _RSI_OVERSOLD:
            opposing.append(f"RSI {rsi:.1f} is oversold")

        macd_result = macd(
            closes,
            fast_period=_MACD_FAST_PERIOD,
            slow_period=_MACD_SLOW_PERIOD,
            signal_period=_MACD_SIGNAL_PERIOD,
        )
        current_price = closes[-1]
        if macd_result is not None and current_price != 0:
            metrics["macd_histogram"] = macd_result.histogram
            full_strength = _MACD_FULL_STRENGTH_PCT_OF_PRICE * current_price
            macd_signal = max(-1.0, min(1.0, macd_result.histogram / full_strength))
            if abs(macd_signal) > 0.05:
                signals.append(macd_signal)
                direction = "positive" if macd_result.histogram > 0 else "negative"
                supporting.append(f"MACD histogram is {direction} ({macd_result.histogram:.4f})")

        roc = rate_of_change(closes, period=_ROC_PERIOD)
        if roc is not None:
            metrics["roc_pct"] = roc
            roc_signal = max(-1.0, min(1.0, roc / _ROC_FULL_STRENGTH_PCT))
            if abs(roc_signal) > 0.05:
                signals.append(roc_signal)

        stochastic = stochastic_oscillator(
            candles, k_period=_STOCH_K_PERIOD, d_period=_STOCH_D_PERIOD
        )
        if stochastic is not None:
            percent_k, percent_d = stochastic
            metrics["stochastic_k"] = percent_k
            metrics["stochastic_d"] = percent_d
            signals.append((percent_k - 50.0) / 50.0)

        divergence = detect_rsi_divergence(candles, rsi_period=_RSI_PERIOD)
        if divergence is not None:
            metrics[
                "rsi_divergence_bearish" if divergence == "bearish" else "rsi_divergence_bullish"
            ] = 1.0
            signals.extend([1.0 if divergence == "bullish" else -1.0] * int(_DIVERGENCE_WEIGHT * 2))
            opposing.append(f"Price/RSI {divergence} divergence detected: possible reversal")

        combined = sum(signals) / len(signals)
        bias: Bias
        if combined > _NEUTRAL_BAND:
            bias = "bullish"
        elif combined < -_NEUTRAL_BAND:
            bias = "bearish"
        else:
            bias = "neutral"

        if bias != "neutral":
            supporting.insert(
                0, f"Combined momentum score {combined:+.2f} across {len(signals)} readings"
            )

        return AgentReport(
            agent_name=self.name,
            bias=bias,
            confidence=min(1.0, abs(combined)),
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics=metrics,
        )
