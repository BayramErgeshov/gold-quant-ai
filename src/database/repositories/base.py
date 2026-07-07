"""Generic async repository base class.

Implements the Repository Pattern mandated by CODING_STANDARDS.md
("Never write raw SQL unless necessary. Use repositories.") and
ARCHITECTURE.md (Clean Architecture / Domain Separation). Domain
repositories (see `src/repositories/`) subclass `BaseRepository` and add
query methods specific to their entity.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.postgres.base import Base


class BaseRepository[ModelT: Base]:
    """Generic CRUD operations for a single SQLAlchemy model.

    Attributes:
        session: The `AsyncSession` this repository operates within.
        model: The SQLAlchemy model class this repository manages.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        """Initialize the repository.

        Args:
            session: An active `AsyncSession` (constructor-injected, per
                CODING_STANDARDS.md Dependency Injection).
            model: The SQLAlchemy model class this repository manages.
        """
        self.session = session
        self.model = model

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        """Fetch a single row by primary key.

        Args:
            entity_id: The UUID primary key to look up.

        Returns:
            The matching entity, or None if it does not exist.
        """
        return await self.session.get(self.model, entity_id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Fetch a page of rows ordered by primary key.

        Args:
            limit: Maximum number of rows to return.
            offset: Number of rows to skip.

        Returns:
            A list of matching entities.
        """
        statement = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        """Persist a new entity.

        Args:
            entity: The entity instance to add.

        Returns:
            The same entity, refreshed with database-generated fields
            (id, timestamps) after flush.
        """
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Delete an entity.

        Args:
            entity: The entity instance to remove.
        """
        await self.session.delete(entity)
        await self.session.flush()
