"""Order Flow Engine orchestrator: real DOM when available, else synthetic.

Per this platform's operating instructions: "If broker or data source
provides Depth of Market (DOM)... analyze [it]. If real DOM is
unavailable: Automatically switch to synthetic order flow analysis...
Never assume certainty. Assign confidence scores." This service is the
single entrypoint the live loop calls each cycle; it never forces a
trade, only produces a directional lean and confidence for Chief AI to
weigh alongside every other department (wired in
`src.engines.chief_ai.decision` as an optional "order_flow" report).

Must be constructed once and reused across scan cycles (not rebuilt per
cycle like `MarketScanner`) — it keeps the last DOM snapshot per symbol in
memory so `real_order_flow.analyze_real_order_flow` can detect swept
liquidity walls between cycles. This state is intentionally ephemeral
(never persisted): DOM snapshots are momentary microstructure, not a
journal artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.core.execution.mt5_client import MT5Client, OrderBookSnapshot
from src.engines.order_flow_engine.real_order_flow import (
    RealOrderFlowReport,
    analyze_real_order_flow,
)
from src.engines.order_flow_engine.synthetic_order_flow import (
    SyntheticOrderFlowReport,
    analyze_synthetic_order_flow,
)
from src.models.candle import Candle

OrderFlowSource = Literal["real_dom", "synthetic"]


@dataclass(frozen=True, slots=True)
class OrderFlowResult:
    """The unified outcome of one Order Flow Engine analysis cycle.

    Attributes:
        source: Whether this cycle used a real DOM read or the synthetic fallback.
        bullish_probability: Confidence-weighted lean toward higher prices.
        bearish_probability: Confidence-weighted lean toward lower prices.
        confidence: Overall confidence in [0.0, 1.0].
        supporting_evidence: Facts supporting the directional lean.
        opposing_evidence: Facts against it.
        real_report: The full real-DOM report, if `source == "real_dom"`.
        synthetic_report: The full synthetic report, if `source == "synthetic"`.
    """

    source: OrderFlowSource
    bullish_probability: float
    bearish_probability: float
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)
    real_report: RealOrderFlowReport | None = None
    synthetic_report: SyntheticOrderFlowReport | None = None


class OrderFlowAnalysisService:
    """Analyzes order flow for a symbol, preferring real DOM over synthetic."""

    def __init__(self, *, mt5_client: MT5Client) -> None:
        """Initialize the service (constructor injection).

        Args:
            mt5_client: Gateway to (optionally) fetch a live DOM snapshot from.
        """
        self._mt5 = mt5_client
        self._previous_snapshots: dict[str, OrderBookSnapshot] = {}

    async def analyze(self, mt5_symbol: str, recent_candles: list[Candle]) -> OrderFlowResult:
        """Analyze order flow for one symbol this cycle.

        Args:
            mt5_symbol: Broker symbol name to fetch a DOM snapshot for.
            recent_candles: Recent candles for the synthetic fallback, if
                DOM is unavailable. Ordered by timestamp ascending.

        Returns:
            An `OrderFlowResult` from whichever source was available.
        """
        snapshot = await self._mt5.get_order_book(mt5_symbol)
        if snapshot is not None:
            previous = self._previous_snapshots.get(mt5_symbol)
            report = analyze_real_order_flow(snapshot, previous_snapshot=previous)
            self._previous_snapshots[mt5_symbol] = snapshot
            return OrderFlowResult(
                source="real_dom",
                bullish_probability=report.bullish_probability,
                bearish_probability=report.bearish_probability,
                confidence=report.confidence,
                supporting_evidence=report.supporting_evidence,
                opposing_evidence=report.opposing_evidence,
                real_report=report,
            )

        synthetic_report = analyze_synthetic_order_flow(recent_candles)
        return OrderFlowResult(
            source="synthetic",
            bullish_probability=synthetic_report.bullish_probability,
            bearish_probability=synthetic_report.bearish_probability,
            confidence=synthetic_report.confidence,
            supporting_evidence=synthetic_report.supporting_evidence,
            opposing_evidence=synthetic_report.opposing_evidence,
            synthetic_report=synthetic_report,
        )
