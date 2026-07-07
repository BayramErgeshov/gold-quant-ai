"""Abstract base for Technical Department agents.

Per AGENT_SYSTEM.md: "Every agent has one responsibility. No agent makes
final trading decisions. Every agent produces an independent report...
Agents never hide uncertainty." Every concrete agent (Market Structure,
Trend, Liquidity, ...) analyzes one discipline and returns a structured
`AgentReport` — never a BUY/SELL recommendation, which is the Chief AI's
responsibility alone (a later roadmap phase).

`AgentReport` and `Bias` are defined in `src.core.agents.report` and
re-exported here for backward compatibility, since they are shared with
the Macro Department (`src.core.macro_analysis`) rather than being
Technical-Department-specific.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.agents.report import AgentReport, Bias
from src.models.candle import Candle

__all__ = ["AgentReport", "Bias", "TechnicalAgent"]


class TechnicalAgent(ABC):
    """Base class for a single independent technical-analysis discipline."""

    name: str

    @abstractmethod
    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Analyze a series of candles and produce a structured report.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            A structured `AgentReport`.
        """
