"""Add a swing_enabled flag to runtime_settings.

Per the "Multi Strategy" production requirement: the independent Swing
Engine (`src.engines.swing_engine.service`, Phase 26) can be disabled at
runtime, mirroring `scalping_enabled`'s own opt-out pattern.

Revision ID: 202607090003
Revises: 202607090002
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090003"
down_revision: str | None = "202607090002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column("swing_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "swing_enabled")
