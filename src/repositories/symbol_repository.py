"""Domain repository for `Symbol` entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.symbol import Symbol


class SymbolRepository(BaseRepository[Symbol]):
    """Repository for tradable symbols."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Symbol)

    async def get_by_name(self, name: str) -> Symbol | None:
        """Fetch a symbol by its broker-facing name.

        Args:
            name: Symbol name, e.g. "XAUUSD".

        Returns:
            The matching `Symbol`, or None if it does not exist.
        """
        statement = select(Symbol).where(Symbol.name == name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_primary(self) -> Symbol | None:
        """Fetch the platform's primary traded symbol.

        Returns:
            The `Symbol` flagged as primary, or None if none is configured.
        """
        statement = select(Symbol).where(Symbol.is_primary.is_(True))
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_enabled(self) -> list[Symbol]:
        """Fetch every symbol currently enabled for analysis/execution.

        Returns:
            A list of enabled `Symbol` rows.
        """
        statement = select(Symbol).where(Symbol.is_enabled.is_(True))
        result = await self.session.execute(statement)
        return list(result.scalars().all())
