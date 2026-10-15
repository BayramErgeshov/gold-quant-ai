"""Add max_positions and books_folder overrides to runtime_settings.

Per the "Settings" production requirement: "Max Positions" and "Books
Folder" must be changeable from the interface, per the same
`RuntimeSettings` mechanism (`202607080005_runtime_settings.py`) that
`LiveTradingLoop`/`BooksFolderWatcher` re-read every cycle -- both
columns are nullable overrides: None means "use the script's own
configured default," matching every other override on this table.

Revision ID: 202607090001
Revises: 202607080005
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090001"
down_revision: str | None = "202607080005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runtime_settings", sa.Column("max_positions", sa.Integer(), nullable=True))
    op.add_column(
        "runtime_settings", sa.Column("books_folder", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "books_folder")
    op.drop_column("runtime_settings", "max_positions")
