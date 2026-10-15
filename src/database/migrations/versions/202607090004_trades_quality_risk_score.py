"""Add quality_score and risk_score to trades.

Per the "Trade Quality Engine" production requirement: every executed
trade's Trade Quality Score and Risk Score at signal time
(`src.engines.chief_ai.trade_quality`) are journaled alongside its
existing `department_votes` snapshot, so later reporting (Telegram,
dashboard, post-trade analysis) never needs to recompute them.

Revision ID: 202607090004
Revises: 202607090003
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090004"
down_revision: str | None = "202607090003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column("trades", sa.Column("risk_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "risk_score")
    op.drop_column("trades", "quality_score")
