"""ORM model for durable system log entries (DATABASE.md: `system_logs` table).

Distinct from the file-based structured logs written by
`src.common.logging` (PROJECT_STRUCTURE.md `logs/` tree): this table holds
the subset of events that must remain queryable and permanent per
DATABASE.md ("Nothing important may be lost... Every important action must
be logged", CODING_STANDARDS.md) — e.g. startup diagnostics outcomes,
workflow failures, security incidents.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_VALID_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class SystemLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single durable, queryable system event.

    Attributes:
        level: Severity level; one of DEBUG/INFO/WARNING/ERROR/CRITICAL.
        source: Originating module or component, e.g. "bootstrap".
        event: Short machine-readable event name, e.g. "startup_check".
        context: Structured event payload (already redacted upstream by
            `src.common.logging.redaction` before it ever reaches here).
    """

    __tablename__ = "system_logs"
    __table_args__ = (
        CheckConstraint(f"level IN {_VALID_LEVELS}", name="ck_system_logs_level_valid"),
    )

    level: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(200), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"SystemLog(level={self.level!r}, source={self.source!r}, event={self.event!r})"
