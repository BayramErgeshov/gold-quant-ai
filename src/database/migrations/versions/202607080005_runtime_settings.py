"""Runtime settings for the minimalistic local web UI.

Per the "User Interface" production requirement: "Settings: Lot Size,
Auto Trading, Confidence Threshold, Strategy Selection, Risk Mode" must
be changeable from the interface and take effect without a restart. A
single row (id "default") holds the platform's current overrides.

Revision ID: 202607080005
Revises: 202607080004
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607080005"
down_revision: str | None = "202607080004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.String(length=20), primary_key=True),
        sa.Column("fixed_lot_size", sa.Float(), nullable=True),
        sa.Column("auto_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("confidence_threshold", sa.Float(), nullable=True),
        sa.Column("scalping_enabled", sa.Boolean(), nullable=False),
        sa.Column("risk_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_mode IN ('conservative', 'normal', 'aggressive')",
            name="ck_runtime_settings_risk_mode_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("runtime_settings")
