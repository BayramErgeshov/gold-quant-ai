"""Historical Research Engine schema: candles, market_regimes, historical_similarities

Revision ID: 202607060003
Revises: 202607060002
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607060003"
down_revision: str | None = "202607060002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMEFRAMES = "('MN', 'W1', 'D1', 'H4', 'H1', 'M30', 'M15', 'M5', 'M1')"
_REGIME_TYPES = (
    "('bull_trend', 'bear_trend', 'range', 'accumulation', 'distribution', "
    "'high_volatility', 'low_volatility', 'transition')"
)


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
        "candles",
        *_timestamp_columns(),
        sa.Column("symbol_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("spread", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "symbol_id", "timeframe", "timestamp", name="uq_candles_symbol_timeframe_timestamp"
        ),
        sa.CheckConstraint(f"timeframe IN {_TIMEFRAMES}", name="ck_candles_timeframe_valid"),
        sa.CheckConstraint("high >= low", name="ck_candles_high_gte_low"),
    )
    op.create_index("ix_candles_symbol_id", "candles", ["symbol_id"])
    op.create_index("ix_candles_timeframe", "candles", ["timeframe"])

    op.create_table(
        "market_regimes",
        *_timestamp_columns(),
        sa.Column("symbol_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("start_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"regime IN {_REGIME_TYPES}", name="ck_market_regimes_regime_valid"),
    )
    op.create_index("ix_market_regimes_symbol_id", "market_regimes", ["symbol_id"])
    op.create_index("ix_market_regimes_timeframe", "market_regimes", ["timeframe"])
    op.create_index("ix_market_regimes_regime", "market_regimes", ["regime"])

    op.create_table(
        "historical_similarities",
        *_timestamp_columns(),
        sa.Column("symbol_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe", sa.String(length=3), nullable=False),
        sa.Column("query_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matched_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("outcome_return_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_historical_similarities_symbol_id", "historical_similarities", ["symbol_id"]
    )
    op.create_index(
        "ix_historical_similarities_query_timestamp",
        "historical_similarities",
        ["query_timestamp"],
    )


def downgrade() -> None:
    op.drop_table("historical_similarities")
    op.drop_table("market_regimes")
    op.drop_table("candles")
