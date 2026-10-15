"""Add reasons and scenario_plan columns to trades.

Per the "Strategy Explanation" production requirement: every trade must
display Reasons and Expected Scenario, persisted at signal time rather
than only used transiently for the Telegram entry message.

Revision ID: 202607130003
Revises: 202607130002
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607130003"
down_revision: str | None = "202607130002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("reasons", sa.JSON(), nullable=True))
    op.add_column("trades", sa.Column("scenario_plan", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "scenario_plan")
    op.drop_column("trades", "reasons")
