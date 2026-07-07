"""Market Structure Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per AGENT_SYSTEM.md: "Detect trend. Detect BOS. Detect CHoCH. Detect
Higher High. Detect Lower Low. Detect transitions. Identify market
phase." Structure is derived from fractal swing points
(`src.core.technical_analysis.swings`): the trend is read from the most
recent pair of swing highs/lows, and a "change of character" is flagged
when price closes beyond the swing point that would invalidate that trend.
"""

from __future__ import annotations

from src.core.technical_analysis.agent import AgentReport, Bias, TechnicalAgent
from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle

_MIN_SWINGS_PER_SIDE = 2
_CONFIRMED_CONFIDENCE = 0.75
_CHANGE_OF_CHARACTER_CONFIDENCE = 0.35


class MarketStructureAgent(TechnicalAgent):
    """Classifies current market structure from swing high/low sequences."""

    name = "market_structure"

    def __init__(self, *, swing_lookaround: int = 2) -> None:
        """Initialize the agent.

        Args:
            swing_lookaround: Candles on each side required to confirm a
                fractal swing point (see `find_swing_points`).
        """
        self._swing_lookaround = swing_lookaround

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Classify market structure from the most recent swing points.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` with bias "bullish"/"bearish" when structure
            is clear, or "neutral" when structure is mixed, insufficient,
            or a change of character was just detected.
        """
        swings = find_swing_points(candles, lookaround=self._swing_lookaround)
        highs = [swing for swing in swings if swing.kind == "high"]
        lows = [swing for swing in swings if swing.kind == "low"]

        if len(highs) < _MIN_SWINGS_PER_SIDE or len(lows) < _MIN_SWINGS_PER_SIDE:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["Not enough swing points detected to assess market structure."],
            )

        higher_high = highs[-1].candle.high > highs[-2].candle.high
        higher_low = lows[-1].candle.low > lows[-2].candle.low
        supporting: list[str] = []
        opposing: list[str] = []

        bias: Bias
        if higher_high and higher_low:
            bias = "bullish"
            supporting = ["Higher high confirmed", "Higher low confirmed"]
        elif not higher_high and not higher_low:
            bias = "bearish"
            supporting = ["Lower high confirmed", "Lower low confirmed"]
        else:
            bias = "neutral"
            opposing = ["Structure is mixed: highs and lows disagree on direction"]

        last_swing_high = highs[-1].candle.high
        last_swing_low = lows[-1].candle.low
        latest_close = candles[-1].close
        change_of_character = False

        if bias == "bullish" and latest_close < last_swing_low:
            change_of_character = True
            opposing.append("Price closed below the last swing low: change of character")
        elif bias == "bearish" and latest_close > last_swing_high:
            change_of_character = True
            opposing.append("Price closed above the last swing high: change of character")

        confidence = 0.0
        if bias != "neutral":
            confidence = (
                _CHANGE_OF_CHARACTER_CONFIDENCE if change_of_character else _CONFIRMED_CONFIDENCE
            )

        return AgentReport(
            agent_name=self.name,
            bias="neutral" if change_of_character else bias,
            confidence=confidence,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics={
                "last_swing_high": last_swing_high,
                "last_swing_low": last_swing_low,
                "swing_high_count": float(len(highs)),
                "swing_low_count": float(len(lows)),
            },
        )
