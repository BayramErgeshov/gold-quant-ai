"""Integration tests for the per-strategy Performance data assembly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.strategy_performance_service import get_strategy_performance
from src.models.trade import Trade
from src.repositories.trade_repository import TradeRepository

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _closed_trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "exit_price": 2010.0,
        "realized_pnl": 10.0,
        "magic_number": 1,
        "opened_at": _BASE_TIME,
        "closed_at": _BASE_TIME + timedelta(hours=2),
        "department_votes": {"technical": {"bias": "bullish"}},
    }
    defaults.update(overrides)
    return Trade(**defaults)


async def test_returns_all_five_strategies_with_empty_reports_when_no_trades(
    session: AsyncSession,
) -> None:
    view = await get_strategy_performance(session)

    assert [s.strategy for s in view.strategies] == [
        "Intraday",
        "Scalping",
        "Swing",
        "Shakky",
        "MicroScalping",
    ]
    assert all(s.report.trade_count == 0 for s in view.strategies)
    assert all(s.average_confidence_pct is None for s in view.strategies)
    assert all(s.best_market_regime is None for s in view.strategies)
    assert view.ranking == []


async def test_keeps_each_strategys_statistics_completely_separate(
    session: AsyncSession,
) -> None:
    repository = TradeRepository(session)
    # Intraday: one winner, high confidence/quality.
    await repository.add(
        _closed_trade(
            department_votes={"technical": {"bias": "bullish"}},
            realized_pnl=100.0,
            exit_price=2010.0,
            confidence_pct=90.0,
            quality_score=85.0,
            market_regime="bull_trend",
        )
    )
    # Scalping: one loser, low confidence/quality.
    await repository.add(
        _closed_trade(
            department_votes={"scalping_engine": {"bias": "bullish"}},
            direction="sell",
            realized_pnl=-40.0,
            exit_price=2010.0,
            confidence_pct=55.0,
            quality_score=40.0,
            market_regime="range",
        )
    )
    await session.commit()

    view = await get_strategy_performance(session)

    by_name = {s.strategy: s for s in view.strategies}
    assert by_name["Intraday"].report.trade_count == 1
    assert by_name["Intraday"].report.win_rate == 1.0
    assert by_name["Intraday"].average_confidence_pct == 90.0
    assert by_name["Intraday"].average_quality_score == 85.0
    assert by_name["Intraday"].best_market_regime == "bull_trend"

    assert by_name["Scalping"].report.trade_count == 1
    assert by_name["Scalping"].report.win_rate == 0.0
    assert by_name["Scalping"].average_confidence_pct == 55.0

    # Swing had no trades at all -- an honest empty report, not borrowed
    # data from the other two strategies.
    assert by_name["Swing"].report.trade_count == 0
    assert by_name["Swing"].average_confidence_pct is None


async def test_excludes_trades_with_no_recorded_department_votes_from_every_strategy(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(_closed_trade(department_votes=None))
    await session.commit()

    view = await get_strategy_performance(session)

    assert all(s.report.trade_count == 0 for s in view.strategies)


async def test_averages_mfe_and_mae_per_strategy_and_is_none_when_never_recorded(
    session: AsyncSession,
) -> None:
    repository = TradeRepository(session)
    await repository.add(
        _closed_trade(
            department_votes={"shakky_engine": {"bias": "bullish"}},
            max_favorable_excursion=12.0,
            max_adverse_excursion=3.0,
        )
    )
    await repository.add(
        _closed_trade(
            department_votes={"shakky_engine": {"bias": "bullish"}},
            max_favorable_excursion=8.0,
            max_adverse_excursion=5.0,
        )
    )
    await repository.add(_closed_trade(department_votes={"technical": {"bias": "bullish"}}))
    await session.commit()

    view = await get_strategy_performance(session)

    by_name = {s.strategy: s for s in view.strategies}
    assert by_name["Shakky"].average_mfe == 10.0
    assert by_name["Shakky"].average_mae == 4.0
    # Intraday trade never had MFE/MAE recorded -- an honest None, not 0.
    assert by_name["Intraday"].average_mfe is None
    assert by_name["Intraday"].average_mae is None


async def test_ranking_orders_strategies_by_profit_factor_and_excludes_empty_ones(
    session: AsyncSession,
) -> None:
    repository = TradeRepository(session)
    # Intraday: only winners -> infinite profit factor.
    await repository.add(
        _closed_trade(department_votes={"technical": {"bias": "bullish"}}, realized_pnl=50.0)
    )
    # Scalping: a losing trade mixed in -> finite, lower profit factor.
    await repository.add(
        _closed_trade(
            department_votes={"scalping_engine": {"bias": "bullish"}},
            realized_pnl=20.0,
            exit_price=2005.0,
        )
    )
    await repository.add(
        _closed_trade(
            department_votes={"scalping_engine": {"bias": "bullish"}},
            direction="sell",
            realized_pnl=-15.0,
            exit_price=2005.0,
        )
    )
    await session.commit()

    view = await get_strategy_performance(session)

    ranked_strategies = [r.strategy for r in view.ranking]
    assert ranked_strategies == ["Intraday", "Scalping"]
    assert view.ranking[0].rank == 1
    assert view.ranking[1].rank == 2
