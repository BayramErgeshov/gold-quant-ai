"""Add a paused flag to runtime_settings.

Per the "Live Control" production requirement: "PAUSE" keeps the live
loop process running (still monitoring already-open positions and
sending the "Before Market Close" report) but skips new market scans and
signal execution -- a softer control than STOP, which the web UI
implements as actually terminating the process
(`src.interfaces.web.process_control`).

Revision ID: 202607090002
Revises: 202607090001
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090002"
down_revision: str | None = "202607090001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "paused")
