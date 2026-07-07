"""Domain repository for `Concept` and `ConceptRelationship` (knowledge graph)."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.concept import Concept, ConceptRelationship


class ConceptRepository(BaseRepository[Concept]):
    """Repository for knowledge graph concept nodes."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Concept)

    async def get_by_name(self, name: str) -> Concept | None:
        """Fetch a concept by its canonical name.

        Args:
            name: Canonical concept name, e.g. "Order Block".

        Returns:
            The matching `Concept`, or None if it does not exist.
        """
        statement = select(Concept).where(Concept.name == name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str, *, category: str | None = None) -> Concept:
        """Fetch a concept by name, creating it if it does not exist.

        Args:
            name: Canonical concept name.
            category: Topic category, used only when creating a new concept.

        Returns:
            The existing or newly created `Concept`.
        """
        existing = await self.get_by_name(name)
        if existing is not None:
            return existing
        return await self.add(Concept(name=name, category=category))


class ConceptRelationshipRepository(BaseRepository[ConceptRelationship]):
    """Repository for knowledge graph relationship edges."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ConceptRelationship)

    async def link(
        self,
        from_concept_id: uuid.UUID,
        to_concept_id: uuid.UUID,
        *,
        relationship_type: str,
        weight: float = 1.0,
    ) -> ConceptRelationship:
        """Create a relationship edge between two concepts, if not already present.

        Args:
            from_concept_id: Source concept id.
            to_concept_id: Target concept id.
            relationship_type: Relationship label, e.g. "related_to".
            weight: Relationship strength/confidence in [0.0, 1.0].

        Returns:
            The existing or newly created `ConceptRelationship`.
        """
        statement = select(ConceptRelationship).where(
            ConceptRelationship.from_concept_id == from_concept_id,
            ConceptRelationship.to_concept_id == to_concept_id,
            ConceptRelationship.relationship_type == relationship_type,
        )
        result = await self.session.execute(statement)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        return await self.add(
            ConceptRelationship(
                from_concept_id=from_concept_id,
                to_concept_id=to_concept_id,
                relationship_type=relationship_type,
                weight=weight,
            )
        )

    async def list_related(self, concept_id: uuid.UUID) -> list[ConceptRelationship]:
        """Fetch every relationship (incoming or outgoing) for a concept.

        Args:
            concept_id: The concept id to look up relationships for.

        Returns:
            Matching `ConceptRelationship` rows.
        """
        statement = select(ConceptRelationship).where(
            or_(
                ConceptRelationship.from_concept_id == concept_id,
                ConceptRelationship.to_concept_id == concept_id,
            )
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
