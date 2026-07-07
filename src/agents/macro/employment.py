"""Employment Agent (AGENT_SYSTEM.md: Macro Department).

Rising unemployment signals economic weakness, typically supporting safe-haven
gold demand and rate-cut expectations; falling unemployment (a strong labor
market) typically supports risk assets and rate-hike expectations over gold.
Expects an unemployment-rate-style series (e.g. FRED "UNRATE") — a series
where a HIGHER value means a WEAKER labor market.
"""

from __future__ import annotations

from src.core.agents.report import AgentReport
from src.core.macro_analysis.agent import MacroAgent, MacroObservation
from src.core.macro_analysis.trend_mapping import TrendGoldMapping, analyze_series_trend

_DEFAULT_TREND_THRESHOLD_PCT = 0.5
_CAVEAT = (
    "Directional heuristic only, calibrated for an unemployment-rate-style "
    "series (higher = weaker labor market); a payrolls-count series would "
    "need the opposite rising/falling mapping."
)
_MAPPING = TrendGoldMapping(
    rising_bias="bullish",
    falling_bias="bearish",
    rising_rationale=(
        "Unemployment rising: signals labor market weakness, supports safe-haven gold demand"
    ),
    falling_rationale=(
        "Unemployment falling: signals labor market strength, favors risk assets over gold"
    ),
)


class EmploymentAgent(MacroAgent):
    """Reads unemployment-rate trend and its implication for gold."""

    name = "employment"

    def __init__(self, *, trend_threshold_pct: float = _DEFAULT_TREND_THRESHOLD_PCT) -> None:
        """Initialize the agent.

        Args:
            trend_threshold_pct: Minimum absolute regression slope (%/period)
                to call the unemployment series trending rather than neutral.
        """
        self._trend_threshold_pct = trend_threshold_pct

    def analyze(self, observations: list[MacroObservation]) -> AgentReport:
        """Analyze an unemployment rate series' trend.

        Args:
            observations: Unemployment rate observations ordered by date ascending.

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
