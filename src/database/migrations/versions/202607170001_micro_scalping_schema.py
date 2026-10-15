"""Add Micro Scalping Engine settings and learning column.

Per the user's request for a fifth, completely independent engine
focused on many small, fast profitable trades (~$1 target) rather than
large trends: adds its own enable toggle, confidence/holding-time
overrides, dynamic-profit-target/trailing-stop toggles, and lot-sizing
mode to `runtime_settings` (same independent-override convention as
Scalping/Swing/Shakky), plus its own learning-verdict column on `trades`
(mirrors `shakky_learning` -- Micro Scalping's own questions "was profit
taken too early/late" don't apply to the other engines).

Revision ID: 202607170001
Revises: 202607140001
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607170001"
down_revision: str | None = "202607140001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runtime_settings",
        sa.Column("micro_scalping_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "runtime_settings", sa.Column("micro_scalping_min_confidence", sa.Float(), nullable=True)
    )
    op.add_column(
        "runtime_settings",
        sa.Column("micro_scalping_max_holding_minutes", sa.Float(), nullable=True),
    )
    op.add_column(
        "runtime_settings",
        sa.Column(
            "micro_scalping_dynamic_profit_target_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "runtime_settings",
        sa.Column(
            "micro_scalping_trailing_stop_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "runtime_settings",
        sa.Column(
            "micro_scalping_lot_mode", sa.String(10), nullable=False, server_default="manual"
        ),
    )
    op.add_column(
        "runtime_settings", sa.Column("micro_scalping_fixed_lot_size", sa.Float(), nullable=True)
    )
    op.create_check_constraint(
        "ck_runtime_settings_micro_scalping_lot_mode_valid",
        "runtime_settings",
        "micro_scalping_lot_mode IN ('auto', 'manual')",
    )
    op.add_column("trades", sa.Column("micro_scalping_learning", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "micro_scalping_learning")
    op.drop_constraint("ck_runtime_settings_micro_scalping_lot_mode_valid", "runtime_settings")
    op.drop_column("runtime_settings", "micro_scalping_fixed_lot_size")
    op.drop_column("runtime_settings", "micro_scalping_lot_mode")
    op.drop_column("runtime_settings", "micro_scalping_trailing_stop_enabled")
    op.drop_column("runtime_settings", "micro_scalping_dynamic_profit_target_enabled")
    op.drop_column("runtime_settings", "micro_scalping_max_holding_minutes")
    op.drop_column("runtime_settings", "micro_scalping_min_confidence")
    op.drop_column("runtime_settings", "micro_scalping_enabled")
