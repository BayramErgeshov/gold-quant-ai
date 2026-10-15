"""Add Micro Scalping's own configurable max-spread-points override.

Production incident: the engine's own spread gate defaulted to an
untested 5.0 points, while this account's real XAUUSD spread sits at a
stable ~36 points -- every single cycle since launch was silently
rejected at the spread gate, so the engine never once qualified a trade.
The hardcoded default is raised to 60.0 (comfortably above the observed
baseline) and this column lets the value be corrected from Settings if
the account's real spread shifts again, without another code change.

Revision ID: 202607180001
Revises: 202607170001
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607180001"
down_revision: str | None = "202607170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column("micro_scalping_max_spread_points", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "micro_scalping_max_spread_points")
