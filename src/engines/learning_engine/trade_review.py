"""Post-trade review for the Self Learning Engine.

Per SELF_LEARNING_ENGINE.md "Every Closed Trade": derives the measurable
outcome fields (holding time, realized return, R-multiple) from a closed
`Trade` row. Maximum Favorable/Adverse Excursion require tick-level price
history during the trade's lifetime, which is not yet collected by any
engine in this platform, so they are omitted here rather than
approximated — a genuine gap to close once tick storage exists (MT5_ENGINE.md
"Market Data": "Download Ticks... Store permanently").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from src.engines.statistics_engine.risk_metrics import r_multiple
from src.models.trade import Trade


@dataclass(frozen=True, slots=True)
class TradeReview:
    """Measurable outcome summary for one closed trade.

    Attributes:
        trade_id: The reviewed `Trade`'s id.
        is_win: True if `realized_pnl` was positive.
        realized_return_pct: Realized return, in percent of entry price.
        risk_pct: Planned risk (entry-to-stop distance), in percent of entry price.
        r_multiple: `realized_return_pct / risk_pct` (0.0 if risk_pct is 0).
        holding_time: Time between `opened_at` and `closed_at`, if both are known.
    """

    trade_id: str
    is_win: bool
    realized_return_pct: float
    risk_pct: float
    r_multiple: float
    holding_time: timedelta | None


def review_closed_trade(trade: Trade) -> TradeReview:
    """Build a `TradeReview` from a closed trade's recorded fields.

    Args:
        trade: A `Trade` with `status == "closed"`.

    Returns:
        The derived `TradeReview`.

    Raises:
        ValueError: If `trade.entry_price` or `trade.exit_price` is missing
            — a closed trade must have both recorded, never assumed.
    """
    if trade.entry_price is None or trade.exit_price is None:
        raise ValueError("A closed trade must have both entry_price and exit_price recorded")

    direction_sign = 1.0 if trade.direction == "buy" else -1.0
    realized_return_pct = (
        (trade.exit_price - trade.entry_price) / trade.entry_price * 100 * direction_sign
    )
    risk_pct = abs(trade.entry_price - trade.stop_loss) / trade.entry_price * 100

    holding_time = None
    if trade.opened_at is not None and trade.closed_at is not None:
        holding_time = trade.closed_at - trade.opened_at

    return TradeReview(
        trade_id=str(trade.id),
        is_win=(trade.realized_pnl or 0.0) > 0,
        realized_return_pct=realized_return_pct,
        risk_pct=risk_pct,
        r_multiple=r_multiple(realized_return_pct, risk_pct),
        holding_time=holding_time,
    )
