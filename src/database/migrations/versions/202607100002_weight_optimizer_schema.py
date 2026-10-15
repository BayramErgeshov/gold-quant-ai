"""AI Weight Optimizer schema: weight_recommendations, department_weight_overrides

Per the "AI Weight Optimizer" production requirement: recommendations are
generated every 100 completed trades and never auto-applied; an override
only ever gets written when the user explicitly approves one.

Revision ID: 202607100002
Revises: 202607100001
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607100002"
down_revision: str | None = "202607100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEIGHT_RECOMMENDATION_STATUSES = "('pending', 'approved', 'rejected')"


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
        "weight_recommendations",
        *_timestamp_columns(),
        sa.Column("department_name", sa.String(length=50), nullable=False),
        sa.Column("trade_batch_number", sa.Integer(), nullable=False),
        sa.Column("current_weight", sa.Float(), nullable=False),
        sa.Column("suggested_weight", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("supporting_stats", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"status IN {_WEIGHT_RECOMMENDATION_STATUSES}",
            name="ck_weight_recommendations_status_valid",
        ),
        sa.UniqueConstraint(
            "department_name",
            "trade_batch_number",
            name="uq_weight_recommendations_department_batch",
        ),
    )
    op.create_index(
        "ix_weight_recommendations_department_name", "weight_recommendations", ["department_name"]
    )
    op.create_index(
        "ix_weight_recommendations_trade_batch_number",
        "weight_recommendations",
        ["trade_batch_number"],
    )
    op.create_index("ix_weight_recommendations_status", "weight_recommendations", ["status"])

    op.create_table(
        "department_weight_overrides",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("department_name", sa.String(length=50), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source_recommendation_id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("department_name"),
    )


def downgrade() -> None:
    op.drop_table("department_weight_overrides")
    op.drop_index("ix_weight_recommendations_status", table_name="weight_recommendations")
    op.drop_index(
        "ix_weight_recommendations_trade_batch_number", table_name="weight_recommendations"
    )
    op.drop_index("ix_weight_recommendations_department_name", table_name="weight_recommendations")
    op.drop_table("weight_recommendations")
