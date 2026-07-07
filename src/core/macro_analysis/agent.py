"""Abstract base for Macro Department agents.

Per AGENT_SYSTEM.md (Macro Department): agents analyze one macroeconomic
series (interest rates, inflation, employment, ...) and return a
structured `AgentReport` — never a trading signal. Unlike Technical
agents (which analyze OHLCV candles), Macro agents analyze a time series
of scalar economic observations (e.g. FRED series data).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from src.core.agents.report import AgentReport


@dataclass(frozen=True, slots=True)
class MacroObservation:
    """A single economic data point.

    Attributes:
        observed_on: The date this value was reported/observed for.
        value: The reported value (e.g. CPI index level, unemployment rate %).
    """

    observed_on: date
    value: float


class MacroAgent(ABC):
    """Base class for a single independent macroeconomic-analysis discipline."""

    name: str

    @abstractmethod
    def analyze(self, observations: list[MacroObservation]) -> AgentReport:
        """Analyze a macroeconomic time series and produce a structured report.

        Args:
            observations: Observations ordered by `observed_on` ascending.

        Returns:
            A structured `AgentReport`.
        """
