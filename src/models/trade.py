"""ORM model for the trade journal (DATABASE.md: `trades`; MT5_ENGINE.md
"ORDER PARAMETERS" / "EXECUTION LOG").

Per MT5_ENGINE.md: "Every order is traceable... Every execution must be
reproducible." One row tracks a single order/position from submission
through close, regardless of which execution gateway (MT5 demo, paper,
future live) placed it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TRADE_DIRECTIONS: tuple[str, ...] = ("buy", "sell")
TRADE_STATUSES: tuple[str, ...] = ("pending", "open", "closed", "rejected", "cancelled")


class Trade(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single order/position tracked from submission through close.

    Attributes:
        symbol_id: Owning `Symbol`.
        direction: One of `TRADE_DIRECTIONS`.
        status: One of `TRADE_STATUSES`.
        volume: Order/position size, in the broker's lot/unit convention.
        entry_price: Requested (or filled) entry price.
        stop_loss: Protective stop price (MT5_ENGINE.md: every order requires one).
        take_profit: Target price, if set.
        magic_number: Strategy identifier attached to every order
            (MT5_ENGINE.md "Magic Number").
        comment: Broker-visible order comment.
        strategy_version: Version tag of the strategy that generated this trade.
        journal_reference: Free-form reference to the originating Chief AI
            decision/journal entry (DECISION_ENGINE.md "Journal ID").
        broker_ticket: Broker-assigned order/position ticket, once filled.
        account: Broker account identifier the trade was placed on.
        exit_price: Realized exit price, once closed.
        opened_at: When the position was actually opened (broker-reported).
        closed_at: When the position was actually closed (broker-reported).
        spread: Spread at execution time.
        slippage: Realized slippage (entry_price - requested price).
        commission: Broker commission charged.
        swap: Broker swap/rollover charged.
        realized_pnl: Realized profit/loss once closed.
        error_message: Broker/gateway error, if the order was rejected.
    """

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(f"direction IN {TRADE_DIRECTIONS}", name="ck_trades_direction_valid"),
        CheckConstraint(f"status IN {TRADE_STATUSES}", name="ck_trades_status_valid"),
    )

    symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False, index=True)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float | None] = mapped_column(Float)
    magic_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(String(200))
    strategy_version: Mapped[str | None] = mapped_column(String(50))
    journal_reference: Mapped[str | None] = mapped_column(String(200))
    broker_ticket: Mapped[str | None] = mapped_column(String(50), index=True)
    account: Mapped[str | None] = mapped_column(String(50))
    exit_price: Mapped[float | None] = mapped_column(Float)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spread: Mapped[float | None] = mapped_column(Float)
    slippage: Mapped[float | None] = mapped_column(Float)
    commission: Mapped[float | None] = mapped_column(Float)
    swap: Mapped[float | None] = mapped_column(Float)
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(String(500))

    def __repr__(self) -> str:
        return f"Trade(direction={self.direction!r}, status={self.status!r})"
