"""Domain repository for `Trade` entities (the trade journal)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.trade import Trade


class TradeRepository(BaseRepository[Trade]):
    """Repository for journaled orders/positions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Trade)

    async def get_by_broker_ticket(self, broker_ticket: str) -> Trade | None:
        """Fetch a trade by its broker-assigned ticket.

        Args:
            broker_ticket: The broker's order/position ticket.

        Returns:
            The matching `Trade`, or None if not found.
        """
        statement = select(Trade).where(Trade.broker_ticket == broker_ticket)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_open(self) -> list[Trade]:
        """Fetch every currently open position.

        Returns:
            `Trade` rows with `status == "open"`, ordered by `opened_at` ascending.
        """
        statement = select(Trade).where(Trade.status == "open").order_by(Trade.opened_at)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_by_status(self, status: str, *, limit: int = 100) -> list[Trade]:
        """Fetch trades in a given status, most recently created first.

        Args:
            status: One of `src.models.trade.TRADE_STATUSES`.
            limit: Maximum number of trades to return.

        Returns:
            Matching `Trade` rows ordered by `created_at` descending.
        """
        statement = (
            select(Trade)
            .where(Trade.status == status)
            .order_by(Trade.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_status(self, status: str) -> int:
        """Count every trade in a given status.

        Args:
            status: One of `src.models.trade.TRADE_STATUSES`.

        Returns:
            The total row count, unaffected by any pagination limit --
            used by the AI Weight Optimizer to detect when a new
            100-trade batch has completed.
        """
        statement = select(func.count()).select_from(Trade).where(Trade.status == status)
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def count_open_by_magic_number(self, magic_number: int) -> int:
        """Count currently open positions for one specific strategy.

        Per the "Parallel Strategy Execution" production requirement:
        each strategy (Intraday/Scalping/Swing) is limited to its own
        single open position, identified by its own distinct magic
        number (`src.core.execution.magic_number.compute_magic_number`)
        -- never a shared, cross-strategy count.

        Args:
            magic_number: The strategy's own magic number.

        Returns:
            The number of currently open positions with this magic number.
        """
        statement = (
            select(func.count())
            .select_from(Trade)
            .where(Trade.status == "open", Trade.magic_number == magic_number)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()
