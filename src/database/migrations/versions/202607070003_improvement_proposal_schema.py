"""Improvement Proposal schema: improvement_proposals

Revision ID: 202607070003
Revises: 202607070002
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607070003"
down_revision: str | None = "202607070002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMPLEMENTATION_DIFFICULTIES = "('low', 'medium', 'high')"
_PROPOSAL_STATUSES = "('pending', 'approved', 'rejected')"


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
        "improvement_proposals",
        *_timestamp_columns(),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column(
            "historical_statistics", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("expected_benefit", sa.Text(), nullable=False),
        sa.Column("potential_risk", sa.Text(), nullable=False),
        sa.Column("implementation_difficulty", sa.String(length=10), nullable=False),
        sa.Column("validation_results", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="pending", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"implementation_difficulty IN {_IMPLEMENTATION_DIFFICULTIES}",
            name="ck_improvement_proposals_difficulty_valid",
        ),
        sa.CheckConstraint(
            f"status IN {_PROPOSAL_STATUSES}", name="ck_improvement_proposals_status_valid"
        ),
    )
    op.create_index("ix_improvement_proposals_status", "improvement_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("improvement_proposals")
