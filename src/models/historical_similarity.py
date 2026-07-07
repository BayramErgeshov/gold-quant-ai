"""ORM model for cached historical analogue search results.

Per DATABASE.md (`historical_similarity` table) and
HISTORICAL_RESEARCH_ENGINE.md: "For every current market situation...
Find Top 100 Most Similar Situations... Calculate Similarity Score."
Results are cached so repeated queries for the same reference point don't
re-scan the full historical database.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HistoricalSimilarity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single historical analogue match for a reference point in time.

    Attributes:
        symbol_id: Owning `Symbol`.
        timeframe: One of `src.models.candle.TIMEFRAMES`.
        query_timestamp: The reference ("current") candle timestamp being
            analyzed.
        matched_timestamp: The historical candle timestamp judged similar.
        similarity_score: Similarity in [0.0, 1.0] (1.0 = identical feature
            vector).
        outcome_return_pct: Percentage price return N bars after
            `matched_timestamp`, used to build the probability distribution
            of likely outcomes. Null until computed.
    """

    __tablename__ = "historical_similarities"

    symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    query_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    matched_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    outcome_return_pct: Mapped[float | None] = mapped_column(Float)

    def __repr__(self) -> str:
        return (
            f"HistoricalSimilarity(query={self.query_timestamp!r}, "
            f"matched={self.matched_timestamp!r}, score={self.similarity_score:.3f})"
        )
