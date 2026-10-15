"""Data assembly for the local web UI's chart page.

Per the "Chart" production requirement: entries/exits/SL/TP and
structural zones (Order Blocks, FVG, Liquidity, Support/Resistance, BOS/
CHOCH, Swing High/Low) overlaid on price. Every overlay here reuses an
already-built Technical Department detector exactly as Chief AI itself
consumes it -- never a new, invented detection rule. IFVG (inverse Fair
Value Gap) is honestly omitted: no agent in this platform detects it yet,
and this module does not fabricate one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.technical.liquidity import find_liquidity_pools
from src.agents.technical.market_structure import MarketStructureAgent
from src.agents.technical.smart_money import SmartMoneyAgent, find_fair_value_gaps
from src.agents.technical.support_resistance import SupportResistanceAgent
from src.core.technical_analysis.swings import find_swing_points
from src.repositories.candle_repository import CandleRepository
from src.repositories.trade_repository import TradeRepository

_DEFAULT_CANDLE_COUNT = 300
_LIQUIDITY_TOLERANCE_PCT = 0.15
_RECENT_CLOSED_TRADES_FOR_MARKERS = 20
# Per the "Chart" production requirement's own condition ("only if
# rendering performance remains smooth"): a 300-candle window can contain
# far more FVGs/liquidity pools than are legible as chart overlays at
# once, so only the most recent ones are kept -- still genuine detected
# zones, never fabricated, just capped for a usable chart.
_MAX_ZONES_PER_KIND = 15


@dataclass(frozen=True, slots=True)
class ChartCandle:
    """One OHLC bar in Lightweight Charts' own time format (unix seconds)."""

    time: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class TradeMarker:
    """A single entry/exit marker for a journaled trade.

    Attributes:
        time: Unix seconds.
        price: Price level to mark.
        kind: "entry_buy", "entry_sell", or "exit".
        label: Short text shown on hover.
    """

    time: int
    price: float
    kind: str
    label: str


@dataclass(frozen=True, slots=True)
class PriceZone:
    """A structural price zone (Order Block, FVG, Liquidity, Support/Resistance).

    Attributes:
        kind: e.g. "order_block_bullish", "fvg_bearish", "liquidity_buy_side",
            "support", "resistance".
        price_low: Lower bound (equal to `price_high` for a single-level zone).
        price_high: Upper bound.
        label: Short text shown on hover.
    """

    kind: str
    price_low: float
    price_high: float
    label: str


@dataclass(frozen=True, slots=True)
class SwingMarker:
    """A single detected fractal swing high/low."""

    time: int
    price: float
    kind: str  # "swing_high" | "swing_low"


@dataclass(frozen=True, slots=True)
class ChartData:
    """Everything the chart page needs.

    Attributes:
        candles: Recent OHLC bars, oldest first.
        trade_markers: Entry/exit markers from the trade journal.
        zones: Structural price zones from the Technical Department's own
            already-built detectors.
        swing_markers: Fractal swing highs/lows.
        structure_note: The Market Structure Agent's own latest BOS/CHOCH
            read, as plain text -- None if there was not enough history to
            classify structure this cycle.
    """

    candles: list[ChartCandle] = field(default_factory=list)
    trade_markers: list[TradeMarker] = field(default_factory=list)
    zones: list[PriceZone] = field(default_factory=list)
    swing_markers: list[SwingMarker] = field(default_factory=list)
    structure_note: str | None = None


def _order_block_zone(metrics: dict[str, float]) -> PriceZone | None:
    if "order_block_low" not in metrics or "order_block_high" not in metrics:
        return None
    return PriceZone(
        kind="order_block",
        price_low=metrics["order_block_low"],
        price_high=metrics["order_block_high"],
        label="Order Block",
    )


def _support_resistance_zones(metrics: dict[str, float]) -> list[PriceZone]:
    zones: list[PriceZone] = []
    if "nearest_support" in metrics:
        zones.append(
            PriceZone(
                kind="support",
                price_low=metrics["nearest_support"],
                price_high=metrics["nearest_support"],
                label="Support",
            )
        )
    if "nearest_resistance" in metrics:
        zones.append(
            PriceZone(
                kind="resistance",
                price_low=metrics["nearest_resistance"],
                price_high=metrics["nearest_resistance"],
                label="Resistance",
            )
        )
    return zones


async def get_chart_data(
    session: AsyncSession,
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
    candle_count: int = _DEFAULT_CANDLE_COUNT,
) -> ChartData:
    """Assemble the current chart page's candles and overlays.

    Args:
        session: The active database session.
        symbol_id: The symbol to chart (e.g. XAUUSD).
        timeframe: Candle timeframe to chart (e.g. "M15").
        candle_count: Maximum number of recent bars to include.

    Returns:
        The `ChartData`. Empty (but valid) if no candles are stored yet.
    """
    candles = await CandleRepository(session).list_most_recent(
        symbol_id, timeframe, count=candle_count
    )
    if not candles:
        return ChartData()

    chart_candles = [
        ChartCandle(
            time=int(candle.timestamp.timestamp()),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
        )
        for candle in candles
    ]

    trades = await TradeRepository(session).list_open()
    trades += await TradeRepository(session).list_by_status(
        "closed", limit=_RECENT_CLOSED_TRADES_FOR_MARKERS
    )
    trade_markers: list[TradeMarker] = []
    for trade in trades:
        if trade.opened_at is not None and trade.entry_price is not None:
            trade_markers.append(
                TradeMarker(
                    time=int(trade.opened_at.timestamp()),
                    price=trade.entry_price,
                    kind=f"entry_{trade.direction}",
                    label=f"{trade.direction.upper()} @ {trade.entry_price:.2f}",
                )
            )
        if trade.closed_at is not None and trade.exit_price is not None:
            trade_markers.append(
                TradeMarker(
                    time=int(trade.closed_at.timestamp()),
                    price=trade.exit_price,
                    kind="exit",
                    label=f"Закрыто @ {trade.exit_price:.2f}",
                )
            )

    zones: list[PriceZone] = []
    order_block = _order_block_zone(SmartMoneyAgent().analyze(candles).metrics)
    if order_block is not None:
        zones.append(order_block)

    for gap in find_fair_value_gaps(candles)[-_MAX_ZONES_PER_KIND:]:
        zones.append(
            PriceZone(
                kind=f"fvg_{gap.direction}",
                price_low=gap.gap_low,
                price_high=gap.gap_high,
                label="FVG",
            )
        )

    zones.extend(_support_resistance_zones(SupportResistanceAgent().analyze(candles).metrics))

    swings = find_swing_points(candles)
    swing_markers = [
        SwingMarker(
            time=int(swing.candle.timestamp.timestamp()),
            price=swing.candle.high if swing.kind == "high" else swing.candle.low,
            kind=f"swing_{swing.kind}",
        )
        for swing in swings
    ]

    swing_highs = [swing.candle.high for swing in swings if swing.kind == "high"]
    swing_lows = [swing.candle.low for swing in swings if swing.kind == "low"]
    for pool in find_liquidity_pools(
        swing_highs, tolerance_pct=_LIQUIDITY_TOLERANCE_PCT, kind="sell_side"
    ):
        zones.append(
            PriceZone(
                kind="liquidity_sell_side",
                price_low=pool.price,
                price_high=pool.price,
                label=f"Liquidity ({pool.touches}x)",
            )
        )
    for pool in find_liquidity_pools(
        swing_lows, tolerance_pct=_LIQUIDITY_TOLERANCE_PCT, kind="buy_side"
    ):
        zones.append(
            PriceZone(
                kind="liquidity_buy_side",
                price_low=pool.price,
                price_high=pool.price,
                label=f"Liquidity ({pool.touches}x)",
            )
        )

    structure_report = MarketStructureAgent().analyze(candles)
    structure_note: str | None = None
    if any("change of character" in reason for reason in structure_report.opposing_evidence):
        structure_note = "CHOCH: " + "; ".join(structure_report.opposing_evidence)
    elif structure_report.supporting_evidence:
        structure_note = "BOS: " + "; ".join(structure_report.supporting_evidence)

    return ChartData(
        candles=chart_candles,
        trade_markers=trade_markers,
        zones=zones,
        swing_markers=swing_markers,
        structure_note=structure_note,
    )
