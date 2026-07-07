"""ORM model for OHLCV market data (DATABASE.md: `candles`).

Per DATA_QUALITY_STANDARD.md: "Every candle must contain Timestamp, Open,
High, Low, Close, Volume, Spread, Session, Timeframe, Broker, Validation
Status." `source` records which provider supplied the candle
(DATA_COLLECTION_ENGINE.md: "Every dataset receives... a source").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TIMEFRAMES: tuple[str, ...] = ("MN", "W1", "D1", "H4", "H1", "M30", "M15", "M5", "M1")


class Candle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single OHLCV bar for one symbol/timeframe/timestamp.

    Attributes:
        symbol_id: Owning `Symbol`.
        timeframe: One of `TIMEFRAMES`.
        timestamp: Bar open time, always stored in UTC
            (DATA_COLLECTION_ENGINE.md: "Convert all timestamps to UTC").
        open, high, low, close: Price levels.
        volume: Tick/traded volume, if reported by the source.
        spread: Bid/ask spread at bar open, if reported by the source.
        source: Name of the data provider this candle came from.
    """

    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint(
            "symbol_id", "timeframe", "timestamp", name="uq_candles_symbol_timeframe_timestamp"
        ),
        CheckConstraint(f"timeframe IN {TIMEFRAMES}", name="ck_candles_timeframe_valid"),
        CheckConstraint("high >= low", name="ck_candles_high_gte_low"),
    )

    symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float)
    spread: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"Candle(timeframe={self.timeframe!r}, timestamp={self.timestamp!r})"
