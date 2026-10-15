"""Initial schema: symbols, system_logs

Revision ID: 202607060001
Revises:
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607060001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Required for gen_random_uuid() server-side defaults (also provisioned
    # by infrastructure/postgres/init/001_extensions.sql for container
    # startup; repeated here so `alembic upgrade head` is self-sufficient
    # against any PostgreSQL instance, e.g. bare CI service containers).
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "symbols",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_symbols_name", "symbols", ["name"])

    op.create_table(
        "system_logs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("event", sa.String(length=200), nullable=False),
        sa.Column("context", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')",
            name="ck_system_logs_level_valid",
        ),
    )
    op.create_index("ix_system_logs_level", "system_logs", ["level"])
    op.create_index("ix_system_logs_source", "system_logs", ["source"])


def downgrade() -> None:
    op.drop_index("ix_system_logs_source", table_name="system_logs")
    op.drop_index("ix_system_logs_level", table_name="system_logs")
    op.drop_table("system_logs")

    op.drop_index("ix_symbols_name", table_name="symbols")
    op.drop_table("symbols")
