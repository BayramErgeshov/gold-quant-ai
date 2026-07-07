"""ORM model for classified market regime periods (DATABASE.md: `market_regimes`).

Per HISTORICAL_RESEARCH_ENGINE.md: "Every historical candle belongs to
Bull Trend, Bear Trend, Range, Accumulation, Distribution, Expansion,
Compression..." A regime row spans a contiguous period of one classified
state for a given symbol/timeframe.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

REGIME_TYPES: tuple[str, ...] = (
    "bull_trend",
    "bear_trend",
    "range",
    "accumulation",
    "distribution",
    "high_volatility",
    "low_volatility",
    "transition",
)


class MarketRegime(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A contiguous, classified market regime period.

    Attributes:
        symbol_id: Owning `Symbol`.
        timeframe: One of `src.models.candle.TIMEFRAMES`.
        start_timestamp: First candle timestamp in this regime period.
        end_timestamp: Last candle timestamp in this regime period.
        regime: One of `REGIME_TYPES`.
        confidence: Classification confidence in [0.0, 1.0].
    """

    __tablename__ = "market_regimes"
    __table_args__ = (
        CheckConstraint(f"regime IN {REGIME_TYPES}", name="ck_market_regimes_regime_valid"),
    )

    symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    regime: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    def __repr__(self) -> str:
        return f"MarketRegime(regime={self.regime!r}, start={self.start_timestamp!r})"
