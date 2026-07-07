"""Declarative base and shared mixins for PostgreSQL ORM models.

Per DATABASE.md: "Every record must include Timestamp, Source, Confidence,
Validation Status, Integrity Check, Version." `TimestampMixin` and
`UUIDPrimaryKeyMixin` provide the universal subset of that requirement
shared by every table; domain-specific fields (confidence, validation
status, ...) are added per model as their owning engine is implemented.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for every GOLD QUANT AI ORM model."""


class UUIDPrimaryKeyMixin:
    """Adds a UUIDv4 primary key column named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


class TimestampMixin:
    """Adds `created_at` / `updated_at` columns, both stored in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
