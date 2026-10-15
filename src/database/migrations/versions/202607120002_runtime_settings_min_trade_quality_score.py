"""Add min_trade_quality_score override to runtime_settings.

Per the "Trade Quality Engine" production requirement: the 0-100 Trade
Quality Score becomes a real execution gate; the user can override the
`config/risk.yaml` default from the interface, live, without a restart.

Revision ID: 202607120002
Revises: 202607120001
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607120002"
down_revision: str | None = "202607120001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings", sa.Column("min_trade_quality_score", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "min_trade_quality_score")
