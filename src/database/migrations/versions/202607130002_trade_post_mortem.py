"""Add post_mortem verdict column to trades.

Per the "Post Trade Learning" production requirement: persist each closed
trade's "would Chief AI open this again" verdict, department
correctness, and contributing factors, instead of discarding the report
after sending its Telegram notification.

Revision ID: 202607130002
Revises: 202607130001
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607130002"
down_revision: str | None = "202607130001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("post_mortem", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "post_mortem")
