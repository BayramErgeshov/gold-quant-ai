"""Dollar Index (DXY) Agent (AGENT_SYSTEM.md: Macro Department).

Gold is priced in US dollars, so a strengthening dollar mechanically makes
gold more expensive in other currencies — the standard inverse
relationship. Reads the trend of a dollar index series (e.g. FRED
"DTWEXBGS": Trade Weighted US Dollar Index) and reports a bearish-for-gold
bias when the dollar is strengthening, bullish when weakening.
"""

from __future__ import annotations

from src.core.agents.report import AgentReport
from src.core.macro_analysis.agent import MacroAgent, MacroObservation
from src.core.macro_analysis.trend_mapping import TrendGoldMapping, analyze_series_trend

_DEFAULT_TREND_THRESHOLD_PCT = 0.3
_CAVEAT = (
    "Directional heuristic only; the gold/dollar relationship can decouple "
    "during periods of simultaneous safe-haven demand for both assets."
)
_MAPPING = TrendGoldMapping(
    rising_bias="bearish",
    falling_bias="bullish",
    rising_rationale="Dollar index strengthening: makes gold more expensive in other currencies",
    falling_rationale="Dollar index weakening: makes gold cheaper in other currencies",
)


class DollarIndexAgent(MacroAgent):
    """Reads dollar index trend and its (inverse) implication for gold."""

    name = "dxy"

    def __init__(self, *, trend_threshold_pct: float = _DEFAULT_TREND_THRESHOLD_PCT) -> None:
        """Initialize the agent.

        Args:
            trend_threshold_pct: Minimum absolute regression slope (%/period)
                to call the dollar index trending rather than neutral.
        """
        self._trend_threshold_pct = trend_threshold_pct

    def analyze(self, observations: list[MacroObservation]) -> AgentReport:
        """Analyze a dollar index series' trend.

        Args:
            observations: Dollar index observations ordered by date ascending.

        Returns:
            A structured `AgentReport`.
        """
        return analyze_series_trend(
            self.name,
            observations,
            _MAPPING,
            trend_threshold_pct=self._trend_threshold_pct,
            caveat=_CAVEAT,
        )
