"""ORM model for tradable symbols (DATABASE.md: `symbols` table).

Foundational reference data shared by every department — not owned by any
single research engine, so it is modeled here rather than deferred to a
later phase.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Symbol(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A tradable instrument known to the platform.

    Attributes:
        name: Broker-facing symbol name, e.g. "XAUUSD".
        display_name: Human-readable name, e.g. "Gold vs US Dollar".
        is_primary: Whether this is the platform's primary traded symbol
            (CONFIGURATION.md: exactly one symbol is primary at a time).
        is_enabled: Whether analysis/execution is currently enabled for it.
    """

    __tablename__ = "symbols"

    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"Symbol(name={self.name!r}, is_primary={self.is_primary})"
