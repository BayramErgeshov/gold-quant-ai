"""Integration tests for `MarketRegimeRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.market_regime import MarketRegime
from src.models.symbol import Symbol
from src.repositories.market_regime_repository import MarketRegimeRepository
from src.repositories.symbol_repository import SymbolRepository

_START = datetime(2026, 1, 1, tzinfo=UTC)


async def test_current_regime_finds_covering_period(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    repo = MarketRegimeRepository(session)
    await repo.add(
        MarketRegime(
            symbol_id=symbol.id,
            timeframe="D1",
            start_timestamp=_START,
            end_timestamp=_START + timedelta(days=10),
            regime="bull_trend",
        )
    )

    found = await repo.current_regime(symbol.id, "D1", _START + timedelta(days=5))

    assert found is not None
    assert found.regime == "bull_trend"


async def test_current_regime_returns_none_outside_any_period(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    repo = MarketRegimeRepository(session)
    await repo.add(
        MarketRegime(
            symbol_id=symbol.id,
            timeframe="D1",
            start_timestamp=_START,
            end_timestamp=_START + timedelta(days=10),
            regime="bull_trend",
        )
    )

    found = await repo.current_regime(symbol.id, "D1", _START + timedelta(days=100))

    assert found is None


async def test_list_by_symbol_orders_by_start(session: AsyncSession) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    repo = MarketRegimeRepository(session)
    await repo.add(
        MarketRegime(
            symbol_id=symbol.id,
            timeframe="D1",
            start_timestamp=_START + timedelta(days=20),
            end_timestamp=_START + timedelta(days=30),
            regime="range",
        )
    )
    await repo.add(
        MarketRegime(
            symbol_id=symbol.id,
            timeframe="D1",
            start_timestamp=_START,
            end_timestamp=_START + timedelta(days=10),
            regime="bull_trend",
        )
    )

    regimes = await repo.list_by_symbol(symbol.id, "D1")

    assert [regime.regime for regime in regimes] == ["bull_trend", "range"]
