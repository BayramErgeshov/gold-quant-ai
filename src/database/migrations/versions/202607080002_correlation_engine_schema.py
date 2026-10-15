"""Market Correlation Engine schema: correlated_instruments, correlated_prices

Revision ID: 202607080002
Revises: 202607080001
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607080002"
down_revision: str | None = "202607080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMEFRAMES = "('MN', 'W1', 'D1', 'H4', 'H1', 'M30', 'M15', 'M5', 'M1')"


def _timestamp_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "correlated_instruments",
        *_timestamp_columns(),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("mt5_symbol", sa.String(length=20), nullable=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_correlated_instruments_name"),
    )
    op.create_index("ix_correlated_instruments_name", "correlated_instruments", ["name"])

    op.create_table(
        "correlated_prices",
        *_timestamp_columns(),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["correlated_instruments.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            f"timeframe IN {_TIMEFRAMES}", name="ck_correlated_prices_timeframe_valid"
        ),
        sa.CheckConstraint("high >= low", name="ck_correlated_prices_high_gte_low"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "timestamp",
            name="uq_correlated_prices_instrument_timeframe_timestamp",
        ),
    )
    op.create_index("ix_correlated_prices_instrument_id", "correlated_prices", ["instrument_id"])
    op.create_index("ix_correlated_prices_timeframe", "correlated_prices", ["timeframe"])


def downgrade() -> None:
    op.drop_table("correlated_prices")
    op.drop_table("correlated_instruments")
