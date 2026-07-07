"""Trade Journal schema: trades

Revision ID: 202607070002
Revises: 202607070001
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607070002"
down_revision: str | None = "202607070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRADE_DIRECTIONS = "('buy', 'sell')"
_TRADE_STATUSES = "('pending', 'open', 'closed', 'rejected', 'cancelled')"


def _timestamp_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "trades",
        *_timestamp_columns(),
        sa.Column("symbol_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("magic_number", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=200), nullable=True),
        sa.Column("strategy_version", sa.String(length=50), nullable=True),
        sa.Column("journal_reference", sa.String(length=200), nullable=True),
        sa.Column("broker_ticket", sa.String(length=50), nullable=True),
        sa.Column("account", sa.String(length=50), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spread", sa.Float(), nullable=True),
        sa.Column("slippage", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("swap", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"direction IN {_TRADE_DIRECTIONS}", name="ck_trades_direction_valid"),
        sa.CheckConstraint(f"status IN {_TRADE_STATUSES}", name="ck_trades_status_valid"),
    )
    op.create_index("ix_trades_symbol_id", "trades", ["symbol_id"])
    op.create_index("ix_trades_status", "trades", ["status"])
    op.create_index("ix_trades_magic_number", "trades", ["magic_number"])
    op.create_index("ix_trades_broker_ticket", "trades", ["broker_ticket"])


def downgrade() -> None:
    op.drop_table("trades")
