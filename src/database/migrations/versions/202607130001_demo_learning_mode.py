"""Add demo_learning_mode_enabled toggle to runtime_settings.

Per the "Demo Learning Mode" production requirement: a dedicated,
explicitly opt-in mode that relaxes the optional portfolio-wide position
cap and applies a bounded confidence-threshold discount, to maximize
statistically useful trading experience -- default False preserves every
existing behavior unchanged.

Revision ID: 202607130001
Revises: 202607120002
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607130001"
down_revision: str | None = "202607120002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column(
            "demo_learning_mode_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "demo_learning_mode_enabled")
