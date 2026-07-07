"""Volatility Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per AGENT_SYSTEM.md: "Analyze ATR, Historical volatility, Realized
volatility, Session volatility, Expansion, Compression." Computes Average
True Range (ATR) and compares recent ATR against a longer-term baseline to
classify volatility as expanding, compressing, or stable. Volatility has
no inherent direction, so this agent always reports a "neutral" bias — its
value is the expansion/compression read and the raw ATR metrics other
departments (e.g. Risk) consume.
"""

from __future__ import annotations

from src.core.technical_analysis.agent import AgentReport, TechnicalAgent
from src.models.candle import Candle

_DEFAULT_PERIOD = 14
_DEFAULT_COMPARISON_PERIOD = 50
_EXPANSION_RATIO = 1.3
_COMPRESSION_RATIO = 0.7


def true_range(current: Candle, previous: Candle) -> float:
    """Compute a single candle's True Range against the prior candle's close.

    Args:
        current: The candle to compute True Range for.
        previous: The candle immediately preceding `current`.

    Returns:
        The True Range value.
    """
    return max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )


def average_true_range(candles: list[Candle], *, period: int) -> float | None:
    """Compute the Average True Range over the most recent `period` candles.

    Args:
        candles: Candles ordered by timestamp ascending.
        period: Number of True Range observations to average.

    Returns:
        The ATR value, or None if fewer than `period + 1` candles are available.
    """
    if period <= 0 or len(candles) < period + 1:
        return None
    recent = candles[-period:]
    previous_candles = candles[-period - 1 : -1]
    ranges = [
        true_range(current, previous)
        for current, previous in zip(recent, previous_candles, strict=True)
    ]
    return sum(ranges) / len(ranges)


class VolatilityAgent(TechnicalAgent):
    """Measures ATR and classifies volatility expansion/compression."""

    name = "volatility"

    def __init__(
        self, *, period: int = _DEFAULT_PERIOD, comparison_period: int = _DEFAULT_COMPARISON_PERIOD
    ) -> None:
        """Initialize the agent.

        Args:
            period: Number of bars for the "recent" ATR measurement.
            comparison_period: Number of bars for the baseline ATR measurement.
        """
        self._period = period
        self._comparison_period = comparison_period

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Compute ATR and classify volatility expansion/compression.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` with a "neutral" bias (volatility has no
            direction) and ATR-derived metrics.
        """
        recent_atr = average_true_range(candles, period=self._period)
        if recent_atr is None:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=[f"Need at least {self._period + 1} candles to compute ATR."],
            )

        comparison_window = min(self._comparison_period, len(candles) - 1)
        baseline_atr = average_true_range(candles, period=comparison_window)
        metrics: dict[str, float] = {"atr": recent_atr}
        supporting: list[str] = []
        opposing: list[str] = []

        if baseline_atr is not None and baseline_atr > 0:
            ratio = recent_atr / baseline_atr
            metrics["baseline_atr"] = baseline_atr
            metrics["atr_ratio"] = ratio
            if ratio >= _EXPANSION_RATIO:
                supporting.append(f"Recent ATR is {ratio:.2f}x baseline: volatility expansion")
            elif ratio <= _COMPRESSION_RATIO:
                supporting.append(f"Recent ATR is {ratio:.2f}x baseline: volatility compression")
            else:
                opposing.append("Volatility is stable relative to its recent history")

        return AgentReport(
            agent_name=self.name,
            bias="neutral",
            confidence=1.0 if baseline_atr is not None else 0.5,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics=metrics,
        )
