"""Real Depth-of-Market (DOM) order flow analysis.

Per this platform's operating instructions ("If broker or data source
provides Depth of Market (DOM) or Level II data: Analyze liquidity walls,
large resting orders, iceberg orders..., absorption, exhaustion,
aggressive buying, aggressive selling, bid/ask imbalance, volume
imbalance, spoofing probability, liquidity sweeps, stop hunt probability,
order clustering, high liquidity zones... Never assume certainty. Assign
confidence scores.").

MT5's `market_book_get()` only exposes the broker's *current* aggregated
book (see `src.core.execution.mt5_client.OrderBookSnapshot` — not a raw
exchange order book), and only the current moment — there is no
historical DOM API. Iceberg detection, absorption, exhaustion, sweeps and
spoofing probability all fundamentally require comparing the book *over
time*; from a single snapshot alone only the structural measurements
(imbalance, walls, clustering, high-liquidity zones) are measurable, so
this module accepts an optional previous snapshot and only produces the
time-dependent signals when one is given — never fabricating them from a
single read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.execution.mt5_client import OrderBookLevel, OrderBookSnapshot

_WALL_VOLUME_MULTIPLE = 3.0
_CLUSTER_TOLERANCE_PCT = 0.05
_HIGH_LIQUIDITY_ZONE_COUNT = 3
_SWEEP_MIN_WALL_VOLUME_FRACTION = 0.15


@dataclass(frozen=True, slots=True)
class LiquidityWall:
    """A price level with disproportionately large resting volume.

    Attributes:
        level: The underlying `OrderBookLevel`.
        volume_ratio: This level's volume divided by the median volume of
            all levels on the same side — how many times "normal" it is.
    """

    level: OrderBookLevel
    volume_ratio: float


@dataclass(frozen=True, slots=True)
class RealOrderFlowReport:
    """Every real-DOM order-flow measurement for one snapshot.

    Attributes:
        bid_volume: Total resting volume on the bid side.
        ask_volume: Total resting volume on the ask side.
        imbalance: `(bid_volume - ask_volume) / (bid_volume + ask_volume)`,
            in [-1.0, 1.0]; positive means more resting buy-side liquidity.
        liquidity_walls: Levels with disproportionately large volume.
        high_liquidity_zones: The highest-volume levels on each side.
        swept_walls: Walls present in the previous snapshot that vanished
            in this one after price would have traded through them —
            candidate liquidity-sweep/stop-hunt signature. Only populated
            when a previous snapshot was supplied.
        bullish_probability: Confidence-weighted lean toward higher prices.
        bearish_probability: Confidence-weighted lean toward lower prices.
        confidence: Overall confidence in [0.0, 1.0].
        supporting_evidence: Facts supporting the directional lean.
        opposing_evidence: Facts against it.
    """

    bid_volume: float
    ask_volume: float
    imbalance: float
    liquidity_walls: list[LiquidityWall]
    high_liquidity_zones: list[OrderBookLevel]
    swept_walls: list[LiquidityWall]
    bullish_probability: float
    bearish_probability: float
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) / 2
    return ordered[mid]


def _find_walls(levels: list[OrderBookLevel]) -> list[LiquidityWall]:
    by_side: dict[str, list[OrderBookLevel]] = {"bid": [], "ask": []}
    for level in levels:
        by_side[level.side].append(level)

    walls: list[LiquidityWall] = []
    for side_levels in by_side.values():
        median_volume = _median([level.volume for level in side_levels])
        if median_volume <= 0:
            continue
        for level in side_levels:
            ratio = level.volume / median_volume
            if ratio >= _WALL_VOLUME_MULTIPLE:
                walls.append(LiquidityWall(level=level, volume_ratio=ratio))
    return walls


def _find_swept_walls(
    previous_walls: list[LiquidityWall], current_snapshot: OrderBookSnapshot
) -> list[LiquidityWall]:
    """Walls from the previous snapshot no longer present at a similar price."""
    current_prices_by_side: dict[str, set[float]] = {"bid": set(), "ask": set()}
    for level in current_snapshot.levels:
        current_prices_by_side[level.side].add(round(level.price, 2))

    swept: list[LiquidityWall] = []
    for wall in previous_walls:
        tolerance = wall.level.price * _CLUSTER_TOLERANCE_PCT / 100
        still_present = any(
            abs(price - wall.level.price) <= tolerance
            for price in current_prices_by_side[wall.level.side]
        )
        if not still_present:
            swept.append(wall)
    return swept


def analyze_real_order_flow(
    snapshot: OrderBookSnapshot, *, previous_snapshot: OrderBookSnapshot | None = None
) -> RealOrderFlowReport:
    """Analyze a real DOM snapshot (optionally against the prior one).

    Args:
        snapshot: The current `OrderBookSnapshot`.
        previous_snapshot: The prior snapshot for the same symbol, if the
            caller has kept one, enabling sweep detection.

    Returns:
        A `RealOrderFlowReport`.
    """
    bid_volume = sum(level.volume for level in snapshot.levels if level.side == "bid")
    ask_volume = sum(level.volume for level in snapshot.levels if level.side == "ask")
    total_volume = bid_volume + ask_volume
    imbalance = (bid_volume - ask_volume) / total_volume if total_volume > 0 else 0.0

    walls = _find_walls(snapshot.levels)
    high_liquidity_zones = sorted(snapshot.levels, key=lambda level: level.volume, reverse=True)[
        :_HIGH_LIQUIDITY_ZONE_COUNT
    ]

    swept_walls: list[LiquidityWall] = []
    if previous_snapshot is not None:
        previous_walls = _find_walls(previous_snapshot.levels)
        swept_walls = _find_swept_walls(previous_walls, snapshot)

    supporting: list[str] = []
    opposing: list[str] = []
    signals: list[float] = []

    if total_volume > 0:
        signals.append(imbalance)
        (supporting if imbalance > 0 else opposing).append(
            f"Order book imbalance favors the {'bid' if imbalance > 0 else 'ask'} side "
            f"({imbalance:+.2f})"
        )

    for wall in walls:
        wall_signal = 1.0 if wall.level.side == "bid" else -1.0
        signals.append(wall_signal * 0.3)  # a resting wall is weaker evidence than imbalance
        supporting.append(
            f"Liquidity wall on the {wall.level.side} side at {wall.level.price:.2f} "
            f"({wall.volume_ratio:.1f}x median)"
        )

    for swept in swept_walls:
        # A swept bid wall (support removed) is bearish; a swept ask wall
        # (resistance removed) is bullish — the opposite sign of the wall
        # itself, since its resting liquidity has now been consumed/pulled.
        sweep_signal = -1.0 if swept.level.side == "bid" else 1.0
        signals.append(sweep_signal * 0.4)
        supporting.append(
            f"Possible liquidity sweep: {swept.level.side}-side wall at "
            f"{swept.level.price:.2f} disappeared"
        )

    directional_score = sum(signals) / len(signals) if signals else 0.0
    confidence = min(1.0, abs(directional_score))
    bullish_probability = max(0.0, directional_score)
    bearish_probability = max(0.0, -directional_score)

    return RealOrderFlowReport(
        bid_volume=bid_volume,
        ask_volume=ask_volume,
        imbalance=imbalance,
        liquidity_walls=walls,
        high_liquidity_zones=high_liquidity_zones,
        swept_walls=swept_walls,
        bullish_probability=bullish_probability,
        bearish_probability=bearish_probability,
        confidence=confidence,
        supporting_evidence=supporting,
        opposing_evidence=opposing,
    )
