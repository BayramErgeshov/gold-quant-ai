"""Domain repository for `StrategyProfile`/`StrategyProfileModule` (Strategy Builder)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.repositories.base import BaseRepository
from src.models.strategy_profile import StrategyProfile, StrategyProfileModule


class StrategyProfileRepository(BaseRepository[StrategyProfile]):
    """Repository for saved Strategy Builder profiles."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StrategyProfile)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[StrategyProfile]:
        """Fetch every saved profile with its modules eager-loaded.

        Overrides `BaseRepository.list_all` to eager-load `modules` --
        lazy relationship access is not awaitable under the async ORM
        session this platform uses.
        """
        statement = (
            select(StrategyProfile)
            .options(selectinload(StrategyProfile.modules))
            .order_by(StrategyProfile.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> StrategyProfile | None:
        """Fetch one profile by its unique name, with modules eager-loaded.

        Args:
            name: The profile's unique name.

        Returns:
            The matching `StrategyProfile`, or None if no profile has this name.
        """
        statement = (
            select(StrategyProfile)
            .options(selectinload(StrategyProfile.modules))
            .where(StrategyProfile.name == name)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def replace_modules(
        self, profile: StrategyProfile, modules: list[StrategyProfileModule]
    ) -> StrategyProfile:
        """Replace a profile's entire module set with a new one.

        Args:
            profile: The owning, already-persisted profile (its existing
                modules are cleared first).
            modules: The new modules to attach -- `profile_id` is set here,
                callers do not need to set it themselves.

        Returns:
            The updated `StrategyProfile`, refreshed with its new modules.
        """
        # Issued as a direct statement rather than `profile.modules.clear()`
        # -- the latter requires the relationship to already be loaded,
        # which is not guaranteed for every caller under this platform's
        # async ORM session.
        await self.session.execute(
            delete(StrategyProfileModule).where(StrategyProfileModule.profile_id == profile.id)
        )
        for module in modules:
            module.profile_id = profile.id
            self.session.add(module)
        await self.session.flush()
        await self.session.refresh(profile, attribute_names=["modules"])
        return profile

    async def delete_by_name(self, name: str) -> bool:
        """Delete a profile (and its modules, via cascade) by name.

        Args:
            name: The profile's unique name.

        Returns:
            True if a profile was found and deleted, False otherwise.
        """
        profile = await self.get_by_name(name)
        if profile is None:
            return False
        await self.session.delete(profile)
        await self.session.flush()
        return True
