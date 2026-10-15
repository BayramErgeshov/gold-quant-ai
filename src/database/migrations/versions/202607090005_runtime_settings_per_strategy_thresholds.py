"""Add intraday_enabled and per-strategy confidence thresholds to runtime_settings.

Per the "User Configuration" production requirement: the user must be
able to choose any combination of Scalping/Intraday/Swing (including
excluding Intraday, e.g. "Scalping only") and set each engine's own
confidence threshold independently.

Revision ID: 202607090005
Revises: 202607090004
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090005"
down_revision: str | None = "202607090004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column("intraday_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "runtime_settings", sa.Column("scalping_confidence_threshold", sa.Float(), nullable=True)
    )
    op.add_column(
        "runtime_settings", sa.Column("swing_confidence_threshold", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "swing_confidence_threshold")
    op.drop_column("runtime_settings", "scalping_confidence_threshold")
    op.drop_column("runtime_settings", "intraday_enabled")
