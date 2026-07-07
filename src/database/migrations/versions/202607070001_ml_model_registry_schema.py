"""ML Model Registry schema: ml_models

Revision ID: 202607070001
Revises: 202607060004
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607070001"
down_revision: str | None = "202607060004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODEL_TYPES = "('classification', 'regression')"
_MODEL_STATUSES = "('training', 'candidate', 'production', 'retired')"


def _timestamp_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "ml_models",
        *_timestamp_columns(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("model_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="training", nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_names", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("hyperparameters", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("metrics", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("n_samples", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_ml_models_name_version"),
        sa.CheckConstraint(
            f"model_type IN {_MODEL_TYPES}", name="ck_ml_models_model_type_valid"
        ),
        sa.CheckConstraint(f"status IN {_MODEL_STATUSES}", name="ck_ml_models_status_valid"),
    )
    op.create_index("ix_ml_models_name", "ml_models", ["name"])
    op.create_index("ix_ml_models_status", "ml_models", ["status"])


def downgrade() -> None:
    op.drop_table("ml_models")
