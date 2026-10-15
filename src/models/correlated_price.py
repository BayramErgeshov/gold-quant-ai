"""ORM model for correlated-instrument OHLCV data (Market Correlation Engine).

Mirrors `src.models.candle.Candle`'s shape exactly (same DATA_QUALITY_
STANDARD.md fields) but in its own table, keyed to `CorrelatedInstrument`
rather than the tradable `Symbol` — see that model's docstring for why
these are kept structurally separate from the trading-critical tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.candle import TIMEFRAMES


class CorrelatedPrice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single OHLCV bar for one correlated instrument/timeframe/timestamp."""

    __tablename__ = "correlated_prices"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "timestamp",
            name="uq_correlated_prices_instrument_timeframe_timestamp",
        ),
        CheckConstraint(f"timeframe IN {TIMEFRAMES}", name="ck_correlated_prices_timeframe_valid"),
        CheckConstraint("high >= low", name="ck_correlated_prices_high_gte_low"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("correlated_instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"CorrelatedPrice(timeframe={self.timeframe!r}, timestamp={self.timestamp!r})"
