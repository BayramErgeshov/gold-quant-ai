"""Inflation Agent (AGENT_SYSTEM.md: Macro Department).

Rising inflation is the standard "inflation hedge" narrative for gold —
gold is widely used to preserve purchasing power as fiat currency value
erodes. Reads the trend of an inflation series (e.g. FRED "CPIAUCSL": CPI,
"PCEPI": PCE Price Index) and reports a bullish-for-gold bias when
inflation is accelerating, bearish when decelerating.
"""

from __future__ import annotations

from src.core.agents.report import AgentReport
from src.core.macro_analysis.agent import MacroAgent, MacroObservation
from src.core.macro_analysis.trend_mapping import TrendGoldMapping, analyze_series_trend

_DEFAULT_TREND_THRESHOLD_PCT = 0.3
_CAVEAT = (
    "Directional heuristic only (the 'inflation hedge' narrative); does not "
    "account for the central bank's expected policy response, which can "
    "dominate gold's reaction (e.g. inflation prompting rate hikes)."
)
_MAPPING = TrendGoldMapping(
    rising_bias="bullish",
    falling_bias="bearish",
    rising_rationale="Inflation accelerating: supports gold's inflation-hedge demand",
    falling_rationale="Inflation decelerating: reduces gold's inflation-hedge demand",
)


class InflationAgent(MacroAgent):
    """Reads inflation trend and its implication for gold."""

    name = "inflation"

    def __init__(self, *, trend_threshold_pct: float = _DEFAULT_TREND_THRESHOLD_PCT) -> None:
        """Initialize the agent.

        Args:
            trend_threshold_pct: Minimum absolute regression slope (%/period)
                to call the inflation series trending rather than neutral.
        """
        self._trend_threshold_pct = trend_threshold_pct

    def analyze(self, observations: list[MacroObservation]) -> AgentReport:
        """Analyze an inflation series' trend.

        Args:
            observations: Inflation observations ordered by date ascending.

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
