"""Bond Yield Agent (AGENT_SYSTEM.md: Macro Department).

Rising bond yields increase the opportunity cost of holding non-yielding
gold relative to interest-bearing government debt — the standard inverse
relationship, particularly pronounced for real (inflation-adjusted)
yields. Reads the trend of a yield series (e.g. FRED "DGS10": 10-Year
Treasury Yield) and reports a bearish-for-gold bias when yields are
rising, bullish when falling.
"""

from __future__ import annotations

from src.core.agents.report import AgentReport
from src.core.macro_analysis.agent import MacroAgent, MacroObservation
from src.core.macro_analysis.trend_mapping import TrendGoldMapping, analyze_series_trend

_DEFAULT_TREND_THRESHOLD_PCT = 0.5
_CAVEAT = (
    "Directional heuristic only; nominal yields conflate real yield and "
    "inflation-expectation components, which can have offsetting effects on gold."
)
_MAPPING = TrendGoldMapping(
    rising_bias="bearish",
    falling_bias="bullish",
    rising_rationale="Bond yields rising: raises the opportunity cost of holding gold",
    falling_rationale="Bond yields falling: lowers the opportunity cost of holding gold",
)


class BondYieldAgent(MacroAgent):
    """Reads bond yield trend and its (inverse) implication for gold."""

    name = "bond_yield"

    def __init__(self, *, trend_threshold_pct: float = _DEFAULT_TREND_THRESHOLD_PCT) -> None:
        """Initialize the agent.

        Args:
            trend_threshold_pct: Minimum absolute regression slope (%/period)
                to call the yield series trending rather than neutral.
        """
        self._trend_threshold_pct = trend_threshold_pct

    def analyze(self, observations: list[MacroObservation]) -> AgentReport:
        """Analyze a bond yield series' trend.

        Args:
            observations: Yield observations ordered by date ascending.

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
