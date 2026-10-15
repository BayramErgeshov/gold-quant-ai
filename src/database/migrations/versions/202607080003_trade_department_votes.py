"""Trade department votes snapshot: department_votes

Revision ID: 202607080003
Revises: 202607080002
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607080003"
down_revision: str | None = "202607080002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("department_votes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "department_votes")
