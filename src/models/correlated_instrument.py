"""ORM model for cross-market reference instruments (Market Correlation Engine).

Deliberately separate from `src.models.symbol.Symbol`: those rows mean
"tradable by this platform" (CONFIGURATION.md: "exactly one symbol is
primary"), while correlated instruments (DXY, EURUSD, equity indices,
Treasury proxies, etc.) exist purely as observational context for
XAUUSD's confidence scoring and must never be reachable by any order
placement code path.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CORRELATED_INSTRUMENT_CATEGORIES: tuple[str, ...] = (
    "dollar_index",
    "fx",
    "precious_metal",
    "energy",
    "crypto",
    "equity_index",
    "etf",
    "rates",
    "volatility",
)


class CorrelatedInstrument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A non-tradable reference instrument tracked for correlation analysis.

    Attributes:
        name: Platform-facing identifier, e.g. "DXY".
        display_name: Human-readable name, e.g. "US Dollar Index".
        mt5_symbol: Broker symbol name to fetch candles for, if available
            via MT5 (e.g. "USDX"). Null when this instrument has no MT5
            symbol and depends on an external provider that is not yet
            configured (e.g. COT reports, Treasury yields) — its category
            and purpose are still recorded so it is ready to activate the
            moment a data source is added, per this platform's "reduced
            mode" pattern (macro/news engines).
        category: One of `CORRELATED_INSTRUMENT_CATEGORIES`.
        is_enabled: Whether ingestion/correlation analysis currently runs
            for this instrument (false when no data source is available yet).
    """

    __tablename__ = "correlated_instruments"

    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    mt5_symbol: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"CorrelatedInstrument(name={self.name!r}, category={self.category!r})"
