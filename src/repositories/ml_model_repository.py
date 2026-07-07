"""Domain repository for `MLModel` entities (the Model Registry)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.ml_model import MLModel


class MLModelRepository(BaseRepository[MLModel]):
    """Repository for versioned, registered ML models."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MLModel)

    async def next_version(self, name: str) -> int:
        """Compute the next version number for a model name.

        Args:
            name: Model family name, e.g. "xauusd_direction_classifier".

        Returns:
            1 if no version of `name` has been registered yet, otherwise
            the highest existing version plus one.
        """
        latest = await self.get_latest(name)
        return latest.version + 1 if latest is not None else 1

    async def get_latest(self, name: str) -> MLModel | None:
        """Fetch the highest-versioned registered model for a name.

        Args:
            name: Model family name.

        Returns:
            The latest `MLModel`, or None if none has been registered yet.
        """
        statement = (
            select(MLModel).where(MLModel.name == name).order_by(MLModel.version.desc()).limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_production(self, name: str) -> MLModel | None:
        """Fetch the current production model for a name, if any.

        Args:
            name: Model family name.

        Returns:
            The `MLModel` with `status == "production"`, or None if no
            version has been promoted yet.
        """
        statement = select(MLModel).where(MLModel.name == name, MLModel.status == "production")
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_versions(self, name: str) -> list[MLModel]:
        """List every registered version of a model, most recent first.

        Args:
            name: Model family name.

        Returns:
            Matching `MLModel` rows ordered by `version` descending.
        """
        statement = select(MLModel).where(MLModel.name == name).order_by(MLModel.version.desc())
        result = await self.session.execute(statement)
        return list(result.scalars().all())
