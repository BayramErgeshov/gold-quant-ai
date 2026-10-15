"""Liquidity Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per AGENT_SYSTEM.md: "Detect Equal Highs, Equal Lows, Liquidity Pools,
Stop Hunts, Liquidity Sweeps... Generate liquidity score." Equal
highs/lows are clustered swing points (resting liquidity pools); a sweep
is the most recent candle wicking through such a pool and closing back on
the other side — the classic stop-hunt signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.technical_analysis.agent import AgentReport, Bias, TechnicalAgent
from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle

_DEFAULT_SWING_LOOKAROUND = 2
_DEFAULT_POOL_TOLERANCE_PCT = 0.15
_MIN_POOL_TOUCHES = 2
_SWEEP_CONFIDENCE = 0.7

PoolKind = Literal["buy_side", "sell_side"]


@dataclass(frozen=True, slots=True)
class LiquidityPool:
    """A resting liquidity pool formed by two or more nearly-equal swing points."""

    price: float
    touches: int
    kind: PoolKind


def find_liquidity_pools(
    prices: list[float], *, tolerance_pct: float, kind: PoolKind
) -> list[LiquidityPool]:
    """Cluster nearby swing prices into liquidity pools with >=2 touches.

    Public (not `TechnicalAgent`-specific) so other departments — e.g.
    `src.engines.order_flow_engine`'s synthetic liquidity-pool estimation —
    can reuse the exact same clustering rule rather than duplicating it.
    """
    if not prices:
        return []
    sorted_prices = sorted(prices)
    clusters: list[list[float]] = [[sorted_prices[0]]]
    for price in sorted_prices[1:]:
        cluster_average = sum(clusters[-1]) / len(clusters[-1])
        distance_pct = (
            abs(price - cluster_average) / cluster_average * 100 if cluster_average else None
        )
        if distance_pct is not None and distance_pct <= tolerance_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return [
        LiquidityPool(price=sum(cluster) / len(cluster), touches=len(cluster), kind=kind)
        for cluster in clusters
        if len(cluster) >= _MIN_POOL_TOUCHES
    ]


class LiquidityAgent(TechnicalAgent):
    """Detects resting liquidity pools (equal highs/lows) and sweeps."""

    name = "liquidity"

    def __init__(
        self,
        *,
        swing_lookaround: int = _DEFAULT_SWING_LOOKAROUND,
        pool_tolerance_pct: float = _DEFAULT_POOL_TOLERANCE_PCT,
    ) -> None:
        """Initialize the agent.

        Args:
            swing_lookaround: Candles on each side required to confirm a
                fractal swing point.
            pool_tolerance_pct: Maximum %-distance for two swing prices to
                be considered the same liquidity pool.
        """
        self._swing_lookaround = swing_lookaround
        self._pool_tolerance_pct = pool_tolerance_pct

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Detect liquidity pools and whether the latest candle swept one.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` biased toward the direction implied by a
            detected sweep (bearish after a buy-side sweep, bullish after
            a sell-side sweep), or neutral otherwise.
        """
        swings = find_swing_points(candles, lookaround=self._swing_lookaround)
        if not swings:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["No swing points detected to derive liquidity pools."],
            )

        highs = [swing.candle.high for swing in swings if swing.kind == "high"]
        lows = [swing.candle.low for swing in swings if swing.kind == "low"]
        buy_side_pools = find_liquidity_pools(
            highs, tolerance_pct=self._pool_tolerance_pct, kind="buy_side"
        )
        sell_side_pools = find_liquidity_pools(
            lows, tolerance_pct=self._pool_tolerance_pct, kind="sell_side"
        )

        latest = candles[-1]
        swept_buy_side = [
            pool
            for pool in buy_side_pools
            if latest.high > pool.price and latest.close < pool.price
        ]
        swept_sell_side = [
            pool
            for pool in sell_side_pools
            if latest.low < pool.price and latest.close > pool.price
        ]

        supporting: list[str] = []
        opposing: list[str] = []
        bias: Bias = "neutral"

        if swept_buy_side:
            bias = "bearish"
            supporting.append(
                f"Buy-side liquidity swept at {swept_buy_side[0].price:.2f} and rejected"
            )
        if swept_sell_side:
            bias = "neutral" if swept_buy_side else "bullish"
            supporting.append(
                f"Sell-side liquidity swept at {swept_sell_side[0].price:.2f} and rejected"
            )
        if swept_buy_side and swept_sell_side:
            opposing.append("Both buy-side and sell-side liquidity swept: conflicting signal")

        confidence = _SWEEP_CONFIDENCE if bias != "neutral" else 0.0

        return AgentReport(
            agent_name=self.name,
            bias=bias,
            confidence=confidence,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics={
                "buy_side_pool_count": float(len(buy_side_pools)),
                "sell_side_pool_count": float(len(sell_side_pools)),
                "swept_buy_side_count": float(len(swept_buy_side)),
                "swept_sell_side_count": float(len(swept_sell_side)),
            },
        )
