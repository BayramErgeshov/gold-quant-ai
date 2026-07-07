"""Support/Resistance Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Clusters swing highs/lows (`src.core.technical_analysis.swings`) into
price levels touched multiple times, then reports the nearest support
(below current price) and resistance (above current price), with touch
count as a simple strength proxy. Level identification has no inherent
direction, so this agent always reports a "neutral" bias.
"""

from __future__ import annotations

from src.core.technical_analysis.agent import AgentReport, TechnicalAgent
from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle

_DEFAULT_SWING_LOOKAROUND = 2
_DEFAULT_CLUSTER_TOLERANCE_PCT = 0.3
_LEVEL_FOUND_CONFIDENCE = 0.6


def _cluster_levels(prices: list[float], *, tolerance_pct: float) -> list[tuple[float, int]]:
    """Cluster nearby prices into levels.

    Args:
        prices: Prices to cluster (e.g. swing high or swing low values).
        tolerance_pct: Maximum distance from a cluster's running average,
            as a percentage of that average, for a price to join it.

    Returns:
        `(average_price, touch_count)` pairs, one per cluster.
    """
    if not prices:
        return []
    sorted_prices = sorted(prices)
    clusters: list[list[float]] = [[sorted_prices[0]]]
    for price in sorted_prices[1:]:
        cluster_average = sum(clusters[-1]) / len(clusters[-1])
        distance_pct = (
            abs(price - cluster_average) / cluster_average * 100 if cluster_average != 0 else None
        )
        if distance_pct is not None and distance_pct <= tolerance_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return [(sum(cluster) / len(cluster), len(cluster)) for cluster in clusters]


class SupportResistanceAgent(TechnicalAgent):
    """Identifies clustered swing levels acting as support/resistance."""

    name = "support_resistance"

    def __init__(
        self,
        *,
        swing_lookaround: int = _DEFAULT_SWING_LOOKAROUND,
        cluster_tolerance_pct: float = _DEFAULT_CLUSTER_TOLERANCE_PCT,
    ) -> None:
        """Initialize the agent.

        Args:
            swing_lookaround: Candles on each side required to confirm a
                fractal swing point.
            cluster_tolerance_pct: Maximum %-distance for two swing prices
                to be considered the same level.
        """
        self._swing_lookaround = swing_lookaround
        self._cluster_tolerance_pct = cluster_tolerance_pct

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Identify the nearest support and resistance levels.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            A "neutral"-bias `AgentReport` describing the nearest
            support/resistance levels found, if any.
        """
        swings = find_swing_points(candles, lookaround=self._swing_lookaround)
        if not swings:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["No swing points detected to derive support/resistance levels."],
            )

        highs = [swing.candle.high for swing in swings if swing.kind == "high"]
        lows = [swing.candle.low for swing in swings if swing.kind == "low"]
        resistance_levels = _cluster_levels(highs, tolerance_pct=self._cluster_tolerance_pct)
        support_levels = _cluster_levels(lows, tolerance_pct=self._cluster_tolerance_pct)

        current_price = candles[-1].close
        nearest_resistance = min(
            (level for level in resistance_levels if level[0] > current_price),
            key=lambda level: level[0],
            default=None,
        )
        nearest_support = max(
            (level for level in support_levels if level[0] < current_price),
            key=lambda level: level[0],
            default=None,
        )

        supporting: list[str] = []
        unknowns: list[str] = []
        metrics: dict[str, float] = {}

        if nearest_support is not None:
            supporting.append(
                f"Nearest support at {nearest_support[0]:.2f} ({nearest_support[1]} touches)"
            )
            metrics["nearest_support"] = nearest_support[0]
            metrics["nearest_support_touches"] = float(nearest_support[1])
        else:
            unknowns.append("No support level found below current price in this window.")

        if nearest_resistance is not None:
            supporting.append(
                f"Nearest resistance at {nearest_resistance[0]:.2f} "
                f"({nearest_resistance[1]} touches)"
            )
            metrics["nearest_resistance"] = nearest_resistance[0]
            metrics["nearest_resistance_touches"] = float(nearest_resistance[1])
        else:
            unknowns.append("No resistance level found above current price in this window.")

        confidence = _LEVEL_FOUND_CONFIDENCE if (nearest_support or nearest_resistance) else 0.0

        return AgentReport(
            agent_name=self.name,
            bias="neutral",
            confidence=confidence,
            supporting_evidence=supporting,
            unknowns=unknowns,
            metrics=metrics,
        )
