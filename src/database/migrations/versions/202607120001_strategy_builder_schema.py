"""Strategy Builder schema: strategy_profiles, strategy_profile_modules,
runtime_settings per-strategy profile assignment.

Per the "Complete Strategy Builder" production requirement: enable/
disable and weight every analysis module independently, and save/load
named profiles (e.g. "Conservative", "News Trading"). Assigning a
profile to a strategy is stored on `runtime_settings` alongside this
platform's other live-editable, per-strategy overrides.

Revision ID: 202607120001
Revises: 202607100002
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607120001"
down_revision: str | None = "202607100002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "strategy_profiles",
        *_timestamp_columns(),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_strategy_profiles_name"),
    )
    op.create_index("ix_strategy_profiles_name", "strategy_profiles", ["name"])

    op.create_table(
        "strategy_profile_modules",
        *_timestamp_columns(),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("module_name", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["strategy_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("profile_id", "module_name", name="uq_strategy_profile_modules_module"),
    )
    op.create_index(
        "ix_strategy_profile_modules_profile_id", "strategy_profile_modules", ["profile_id"]
    )

    op.add_column(
        "runtime_settings", sa.Column("intraday_profile_name", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "runtime_settings", sa.Column("scalping_profile_name", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "runtime_settings", sa.Column("swing_profile_name", sa.String(length=100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("runtime_settings", "swing_profile_name")
    op.drop_column("runtime_settings", "scalping_profile_name")
    op.drop_column("runtime_settings", "intraday_profile_name")
    op.drop_index("ix_strategy_profile_modules_profile_id", table_name="strategy_profile_modules")
    op.drop_table("strategy_profile_modules")
    op.drop_index("ix_strategy_profiles_name", table_name="strategy_profiles")
    op.drop_table("strategy_profiles")
