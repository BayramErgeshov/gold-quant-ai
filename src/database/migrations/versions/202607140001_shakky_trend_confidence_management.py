"""Add Shakky Trend Confidence Engine / Dynamic TP / Hold Manager / Position Scaling columns.

Per the user's request to improve Shakky's move-management (recognizing
and holding large trends instead of exiting at a fixed target): adds
MFE/MAE tracking and entry-time Trend Confidence to `trades` (needed by
both the "Strategy Comparison" and "Learning" phases), a `scale_events`
log for Position Scaling, a Shakky-specific learning verdict column
separate from the general `post_mortem`, and two independent toggles on
`runtime_settings` so Dynamic TP/Scaling can be disabled without
disabling Shakky entirely.

Revision ID: 202607140001
Revises: 202607130005
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607140001"
down_revision: str | None = "202607130005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("max_favorable_excursion", sa.Float(), nullable=True))
    op.add_column("trades", sa.Column("max_adverse_excursion", sa.Float(), nullable=True))
    op.add_column("trades", sa.Column("entry_trend_confidence_score", sa.Float(), nullable=True))
    op.add_column("trades", sa.Column("scale_events", sa.JSON(), nullable=True))
    op.add_column("trades", sa.Column("shakky_learning", sa.JSON(), nullable=True))
    op.add_column(
        "runtime_settings",
        sa.Column(
            "shakky_dynamic_tp_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "runtime_settings",
        sa.Column("shakky_scaling_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "shakky_scaling_enabled")
    op.drop_column("runtime_settings", "shakky_dynamic_tp_enabled")
    op.drop_column("trades", "shakky_learning")
    op.drop_column("trades", "scale_events")
    op.drop_column("trades", "entry_trend_confidence_score")
    op.drop_column("trades", "max_adverse_excursion")
    op.drop_column("trades", "max_favorable_excursion")
