"""Smart Money Agent (AGENT_SYSTEM.md: Technical Analysis Department).

Per AGENT_SYSTEM.md: "Detect Order Blocks, Breaker Blocks, Mitigation
Blocks, Displacement, Imbalance, Premium, Discount, Institutional
movement." An order block is the last opposite-direction candle before a
displacement move; an imbalance (Fair Value Gap) is a three-candle gap
with no wick overlap; premium/discount is read from where price sits
within its recent swing range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.core.technical_analysis.agent import AgentReport, Bias, TechnicalAgent
from src.models.candle import Candle

_MIN_CANDLES = 5
_DISPLACEMENT_LOOKBACK = 10
_DISPLACEMENT_RATIO = 2.0
_PREMIUM_THRESHOLD = 0.6
_DISCOUNT_THRESHOLD = 0.4
_DISPLACEMENT_CONFIDENCE = 0.65

GapDirection = Literal["bullish", "bearish"]


@dataclass(frozen=True, slots=True)
class FairValueGap:
    """A three-candle imbalance with no wick overlap between the outer candles."""

    index: int
    direction: GapDirection
    gap_low: float
    gap_high: float


def _average_body_size(candles: list[Candle]) -> float:
    bodies = [abs(candle.close - candle.open) for candle in candles]
    return sum(bodies) / len(bodies) if bodies else 0.0


def find_displacement_index(candles: list[Candle]) -> int | None:
    """Find the most recent candle whose body is a displacement move.

    A displacement candle's body is at least `_DISPLACEMENT_RATIO` times
    the average body size of up to the preceding 10 candles.

    Args:
        candles: Candles ordered by timestamp ascending.

    Returns:
        The index of the most recent displacement candle, or None if none
        is found.
    """
    if len(candles) < _MIN_CANDLES:
        return None
    for index in range(len(candles) - 1, 0, -1):
        preceding = candles[max(0, index - _DISPLACEMENT_LOOKBACK) : index]
        if not preceding:  # pragma: no cover - unreachable: index >= 1 always yields a slice
            continue
        average_body = _average_body_size(preceding)
        body = abs(candles[index].close - candles[index].open)
        if average_body > 0 and body >= average_body * _DISPLACEMENT_RATIO:
            return index
    return None


def find_fair_value_gaps(candles: list[Candle]) -> list[FairValueGap]:
    """Find three-candle Fair Value Gaps (no wick overlap) in a series.

    Args:
        candles: Candles ordered by timestamp ascending.

    Returns:
        `FairValueGap`s in chronological order.
    """
    gaps: list[FairValueGap] = []
    for index in range(1, len(candles) - 1):
        left, right = candles[index - 1], candles[index + 1]
        if left.high < right.low:
            gaps.append(
                FairValueGap(
                    index=index, direction="bullish", gap_low=left.high, gap_high=right.low
                )
            )
        elif left.low > right.high:
            gaps.append(
                FairValueGap(
                    index=index, direction="bearish", gap_low=right.high, gap_high=left.low
                )
            )
    return gaps


class SmartMoneyAgent(TechnicalAgent):
    """Detects order blocks, displacement, imbalances and premium/discount."""

    name = "smart_money"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        """Detect the most recent displacement move, its order block, and price positioning.

        Args:
            candles: Candles ordered by timestamp ascending.

        Returns:
            An `AgentReport` biased toward the direction of the most
            recent displacement move, or neutral if none was found.
        """
        if len(candles) < _MIN_CANDLES:
            return AgentReport(
                agent_name=self.name,
                bias="neutral",
                confidence=0.0,
                unknowns=["Not enough candles to detect smart money structure."],
            )

        supporting: list[str] = []
        opposing: list[str] = []
        metrics: dict[str, float] = {}
        bias: Bias = "neutral"

        displacement_index = find_displacement_index(candles)
        if displacement_index is not None:
            displacement_candle = candles[displacement_index]
            bias = "bullish" if displacement_candle.close > displacement_candle.open else "bearish"
            supporting.append(
                f"Displacement candle at index {displacement_index} confirms {bias} intent"
            )
            order_block_index = displacement_index - 1
            if order_block_index >= 0:
                order_block = candles[order_block_index]
                metrics["order_block_high"] = order_block.high
                metrics["order_block_low"] = order_block.low
                supporting.append(
                    f"Order block identified at {order_block.low:.2f}-{order_block.high:.2f}"
                )

        gaps = find_fair_value_gaps(candles)
        metrics["fair_value_gap_count"] = float(len(gaps))
        if gaps:
            supporting.append(f"Most recent fair value gap is {gaps[-1].direction}")

        swing_high = max(candle.high for candle in candles)
        swing_low = min(candle.low for candle in candles)
        swing_range = swing_high - swing_low
        if swing_range > 0:
            position = (candles[-1].close - swing_low) / swing_range
            metrics["range_position"] = position
            self._apply_premium_discount(position, bias, supporting, opposing)

        confidence = _DISPLACEMENT_CONFIDENCE if bias != "neutral" else 0.0

        return AgentReport(
            agent_name=self.name,
            bias=bias,
            confidence=confidence,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            metrics=metrics,
        )

    @staticmethod
    def _apply_premium_discount(
        position: float, bias: Bias, supporting: list[str], opposing: list[str]
    ) -> None:
        """Record whether price is in premium/discount territory relative to `bias`."""
        if position >= _PREMIUM_THRESHOLD:
            if bias == "bullish":
                opposing.append("Price is in premium territory: unfavorable for new buying")
            elif bias == "bearish":
                supporting.append("Price is in premium territory: favorable for selling")
        elif position <= _DISCOUNT_THRESHOLD:
            if bias == "bearish":
                opposing.append("Price is in discount territory: unfavorable for new selling")
            elif bias == "bullish":
                supporting.append("Price is in discount territory: favorable for buying")
