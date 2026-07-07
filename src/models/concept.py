"""ORM models for the knowledge graph (BOOK_RAG.md: "Knowledge Graph").

A lightweight graph stored in PostgreSQL rather than a dedicated graph
database (Neo4j is listed as an optional Priority 4 MCP integration in
MCP_SERVERS.md, not required for this to function): `Concept` nodes and
`ConceptRelationship` edges are enough to support "related concepts" /
"conflicting concepts" retrieval without adding another datastore.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Concept(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single named concept extracted from books/research (a graph node).

    Attributes:
        name: Canonical concept name, e.g. "Order Block".
        category: Topic category the concept belongs to, e.g. "smart_money".
    """

    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("name", name="uq_concepts_name"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), index=True)

    def __repr__(self) -> str:
        return f"Concept(name={self.name!r}, category={self.category!r})"


class ConceptRelationship(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A directed, weighted edge between two concepts (a graph edge).

    Attributes:
        from_concept_id: Source concept.
        to_concept_id: Target concept.
        relationship_type: Relationship label, e.g. "precedes", "requires".
        weight: Relationship strength/confidence in [0.0, 1.0].
    """

    __tablename__ = "concept_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_concept_id",
            "to_concept_id",
            "relationship_type",
            name="uq_concept_relationships_edge",
        ),
    )

    from_concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    def __repr__(self) -> str:
        return (
            f"ConceptRelationship({self.from_concept_id} "
            f"-{self.relationship_type}-> {self.to_concept_id})"
        )
