"""Add shakky_enabled toggle to runtime_settings.

Per the "Classic M5 Strategy" (Shakky) production requirement: the user
must be able to enable/disable this fourth independent engine, same
convention as `scalping_enabled`/`swing_enabled`.

Revision ID: 202607130004
Revises: 202607130003
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607130004"
down_revision: str | None = "202607130003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column("shakky_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "shakky_enabled")
