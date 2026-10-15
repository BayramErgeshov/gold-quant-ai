"""Add similarity_summary column to trades.

Per the "Trade Similarity Engine" production requirement: "Display this
information before every trade" -- persisted at signal time so it is
still visible after the cycle that computed it, matching the existing
`reasons`/`scenario_plan` convention (202607130003).

Revision ID: 202607130005
Revises: 202607130004
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607130005"
down_revision: str | None = "202607130004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("similarity_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "similarity_summary")
