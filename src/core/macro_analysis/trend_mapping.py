"""Shared trend-based macro analysis helper.

Several Macro Department agents (Interest Rate, Inflation, Employment)
share the same shape: read the trend of a single economic series and map
it to a gold bias via a well-known directional relationship. This module
holds that shared logic once, per CODING_STANDARDS.md ("Never duplicate
functionality").
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.agents.report import AgentReport, Bias
from src.core.macro_analysis.agent import MacroObservation
from src.utils.statistics import linear_regression_slope_pct

_MIN_OBSERVATIONS = 3


@dataclass(frozen=True, slots=True)
class TrendGoldMapping:
    """How a rising/falling trend in a series maps to a gold bias.

    Attributes:
        rising_bias: Gold bias when the series is trending up.
        falling_bias: Gold bias when the series is trending down.
        rising_rationale: Human-readable explanation for `rising_bias`.
        falling_rationale: Human-readable explanation for `falling_bias`.
    """

    rising_bias: Bias
    falling_bias: Bias
    rising_rationale: str
    falling_rationale: str


def analyze_series_trend(
    agent_name: str,
    observations: list[MacroObservation],
    mapping: TrendGoldMapping,
    *,
    trend_threshold_pct: float,
    caveat: str,
) -> AgentReport:
    """Analyze a macro series' trend and map it to a gold bias.

    Args:
        agent_name: The calling agent's name, for the report.
        observations: Observations ordered by date ascending.
        mapping: How rising/falling trends map to a gold bias.
        trend_threshold_pct: Minimum absolute regression slope (%/period)
            to call the series trending rather than neutral.
        caveat: A disclaimer describing this heuristic's limitations,
            always included (AGENT_SYSTEM.md: "Agents never hide uncertainty").

    Returns:
        A structured `AgentReport`.
    """
    if len(observations) < _MIN_OBSERVATIONS:
        return AgentReport(
            agent_name=agent_name,
            bias="neutral",
            confidence=0.0,
            unknowns=[f"Not enough observations to assess trend (need >= {_MIN_OBSERVATIONS})."],
        )

    values = [observation.value for observation in observations]
    slope_pct = linear_regression_slope_pct(values)

    bias: Bias = "neutral"
    supporting: list[str] = []
    if slope_pct >= trend_threshold_pct:
        bias = mapping.rising_bias
        supporting.append(mapping.rising_rationale)
    elif slope_pct <= -trend_threshold_pct:
        bias = mapping.falling_bias
        supporting.append(mapping.falling_rationale)

    confidence = min(1.0, abs(slope_pct) / (trend_threshold_pct * 4)) if bias != "neutral" else 0.0

    return AgentReport(
        agent_name=agent_name,
        bias=bias,
        confidence=confidence,
        supporting_evidence=supporting,
        unknowns=[caveat],
        metrics={"slope_pct": slope_pct, "latest_value": values[-1]},
    )
