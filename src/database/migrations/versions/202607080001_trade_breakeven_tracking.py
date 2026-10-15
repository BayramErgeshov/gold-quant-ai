"""Trade break-even tracking: initial_stop_loss, breakeven_moved

Revision ID: 202607080001
Revises: 202607070003
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607080001"
down_revision: str | None = "202607070003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("initial_stop_loss", sa.Float(), nullable=True))
    op.add_column(
        "trades",
        sa.Column("breakeven_moved", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("trades", "breakeven_moved")
    op.drop_column("trades", "initial_stop_loss")
