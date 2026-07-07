"""Interest Rate Agent (AGENT_SYSTEM.md: Macro Department).

Rising policy rates increase the opportunity cost of holding non-yielding
gold — the standard, widely-cited inverse relationship. Reads the trend of
a policy rate series (e.g. FRED "DFF": Federal Funds Effective Rate; "DGS10"
for longer-dated rates) and reports a bearish-for-gold bias when rates are
trending up, bullish when trending down.
"""

from __future__ import annotations

from src.core.agents.report import AgentReport
from src.core.macro_analysis.agent import MacroAgent, MacroObservation
from src.core.macro_analysis.trend_mapping import TrendGoldMapping, analyze_series_trend

_DEFAULT_TREND_THRESHOLD_PCT = 0.5
_CAVEAT = (
    "Directional heuristic only; does not account for real yields, "
    "already-priced-in rate expectations, or simultaneous inflation dynamics."
)
_MAPPING = TrendGoldMapping(
    rising_bias="bearish",
    falling_bias="bullish",
    rising_rationale="Policy rate trending up: raises the opportunity cost of holding gold",
    falling_rationale="Policy rate trending down: lowers the opportunity cost of holding gold",
)


class InterestRateAgent(MacroAgent):
    """Reads policy rate trend and its (inverse) implication for gold."""

    name = "interest_rate"

    def __init__(self, *, trend_threshold_pct: float = _DEFAULT_TREND_THRESHOLD_PCT) -> None:
        """Initialize the agent.

        Args:
            trend_threshold_pct: Minimum absolute regression slope (%/period)
                to call the rate series trending rather than neutral.
        """
        self._trend_threshold_pct = trend_threshold_pct

    def analyze(self, observations: list[MacroObservation]) -> AgentReport:
        """Analyze a policy rate series' trend.

        Args:
            observations: Rate observations ordered by date ascending.

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
