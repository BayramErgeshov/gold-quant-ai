"""Book Engine schema: concepts, books, book_chunks, book_claims, concept_relationships

Revision ID: 202607060002
Revises: 202607060001
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202607060002"
down_revision: str | None = "202607060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALIDATION_STATUSES = "('pending', 'accepted', 'rejected', 'unknown')"


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
        "concepts",
        *_timestamp_columns(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_concepts_name"),
    )
    op.create_index("ix_concepts_name", "concepts", ["name"])
    op.create_index("ix_concepts_category", "concepts", ["category"])

    op.create_table(
        "books",
        *_timestamp_columns(),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=300), nullable=False),
        sa.Column("edition", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("publisher", sa.String(length=300), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("source_path", sa.String(length=1000), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "validation_status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"validation_status IN {_VALIDATION_STATUSES}", name="ck_books_validation_status"
        ),
    )
    op.create_index("ix_books_category", "books", ["category"])
    op.create_index("ix_books_validation_status", "books", ["validation_status"])

    op.create_table(
        "book_chunks",
        *_timestamp_columns(),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("chapter", sa.String(length=300), nullable=True),
        sa.Column("section", sa.String(length=300), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=True),
        sa.Column("entities", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column(
            "historical_validation",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            f"historical_validation IN {_VALIDATION_STATUSES}",
            name="ck_book_chunks_historical_validation",
        ),
    )
    op.create_index("ix_book_chunks_book_id", "book_chunks", ["book_id"])
    op.create_index("ix_book_chunks_topic", "book_chunks", ["topic"])
    op.create_index(
        "ix_book_chunks_historical_validation", "book_chunks", ["historical_validation"]
    )

    op.create_table(
        "book_claims",
        *_timestamp_columns(),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=True),
        sa.Column(
            "validation_status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["book_chunks.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            f"validation_status IN {_VALIDATION_STATUSES}",
            name="ck_book_claims_validation_status",
        ),
    )
    op.create_index("ix_book_claims_book_id", "book_claims", ["book_id"])
    op.create_index("ix_book_claims_chunk_id", "book_claims", ["chunk_id"])
    op.create_index("ix_book_claims_topic", "book_claims", ["topic"])
    op.create_index("ix_book_claims_validation_status", "book_claims", ["validation_status"])

    op.create_table(
        "concept_relationships",
        *_timestamp_columns(),
        sa.Column("from_concept_id", sa.Uuid(), nullable=False),
        sa.Column("to_concept_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["from_concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "from_concept_id",
            "to_concept_id",
            "relationship_type",
            name="uq_concept_relationships_edge",
        ),
    )
    op.create_index(
        "ix_concept_relationships_from_concept_id", "concept_relationships", ["from_concept_id"]
    )
    op.create_index(
        "ix_concept_relationships_to_concept_id", "concept_relationships", ["to_concept_id"]
    )


def downgrade() -> None:
    op.drop_table("concept_relationships")
    op.drop_table("book_claims")
    op.drop_table("book_chunks")
    op.drop_table("books")
    op.drop_table("concepts")
