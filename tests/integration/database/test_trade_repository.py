"""Integration tests for `TradeRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _trade(symbol_id: object, **overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": symbol_id,
        "direction": "buy",
        "volume": 1.0,
        "stop_loss": 1990.0,
        "magic_number": 12345,
    }
    defaults.update(overrides)
    return Trade(**defaults)  # type: ignore[arg-type]


async def test_get_by_broker_ticket_finds_existing_trade(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = TradeRepository(session)
    await repo.add(_trade(symbol.id, broker_ticket="TICKET-1"))

    found = await repo.get_by_broker_ticket("TICKET-1")

    assert found is not None
    assert found.broker_ticket == "TICKET-1"


async def test_get_by_broker_ticket_returns_none_when_missing(session: AsyncSession) -> None:
    repo = TradeRepository(session)

    assert await repo.get_by_broker_ticket("does-not-exist") is None


async def test_list_open_returns_only_open_trades(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = TradeRepository(session)
    await repo.add(_trade(symbol.id, status="open", opened_at=_BASE_TIME, broker_ticket="T1"))
    await repo.add(_trade(symbol.id, status="closed", broker_ticket="T2"))
    await repo.add(_trade(symbol.id, status="pending", broker_ticket="T3"))

    open_trades = await repo.list_open()

    assert len(open_trades) == 1
    assert open_trades[0].broker_ticket == "T1"


async def test_list_by_status_orders_most_recent_first(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    repo = TradeRepository(session)
    await repo.add(_trade(symbol.id, status="closed", broker_ticket="OLD", created_at=_BASE_TIME))
    await repo.add(
        _trade(
            symbol.id,
            status="closed",
            broker_ticket="NEW",
            created_at=_BASE_TIME + timedelta(hours=1),
        )
    )
    await repo.add(_trade(symbol.id, status="pending", broker_ticket="OTHER"))

    closed = await repo.list_by_status("closed")

    assert [trade.broker_ticket for trade in closed] == ["NEW", "OLD"]
