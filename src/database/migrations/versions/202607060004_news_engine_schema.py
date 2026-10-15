"""News Engine schema: news_articles

Revision ID: 202607060004
Revises: 202607060003
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607060004"
down_revision: str | None = "202607060003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXPECTED_VOLATILITY_LEVELS = "('low', 'medium', 'high')"


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
        "news_articles",
        *_timestamp_columns(),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("entities", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("importance_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "expected_volatility", sa.String(length=10), server_default="low", nullable=False
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_news_articles_content_hash"),
        sa.CheckConstraint(
            f"expected_volatility IN {_EXPECTED_VOLATILITY_LEVELS}",
            name="ck_news_articles_expected_volatility",
        ),
    )
    op.create_index("ix_news_articles_source", "news_articles", ["source"])
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"])
    op.create_index("ix_news_articles_category", "news_articles", ["category"])


def downgrade() -> None:
    op.drop_table("news_articles")
