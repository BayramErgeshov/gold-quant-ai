"""Integration tests for the web UI's dashboard data assembly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.dashboard_service import get_dashboard_status
from src.models.improvement_proposal import ImprovementProposal
from src.models.system_log import SystemLog
from src.models.trade import Trade
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.system_log_repository import SystemLogRepository
from src.repositories.trade_repository import TradeRepository

_SYMBOL_ID = uuid.uuid4()


def _proposal(**overrides: object) -> ImprovementProposal:
    defaults: dict[str, object] = {
        "title": "Widen stops",
        "problem": "Premature stop-outs.",
        "evidence": "12 trades.",
        "expected_benefit": "Fewer stop-outs.",
        "potential_risk": "Larger losses if wrong.",
        "implementation_difficulty": "medium",
        "recommendation": "Backtest wider stops.",
        "status": "pending",
    }
    defaults.update(overrides)
    return ImprovementProposal(**defaults)


async def test_defaults_when_no_scan_has_run_yet(session: AsyncSession) -> None:
    status = await get_dashboard_status(session)

    assert status.market == "XAUUSD"
    assert status.state is None
    assert status.confidence_pct is None
    assert status.open_positions == []
    assert status.today_pnl == 0.0
    assert status.last_updated is None
    assert status.trade_quality_score is None
    assert status.risk_score is None
    assert status.mt5_status == "unknown"
    # Reflects this environment's real .env, not a fixed assumption --
    # telegram_configured/news_configured are read-only checks of
    # whatever secret is actually set, never fabricated.
    assert isinstance(status.telegram_configured, bool)
    assert isinstance(status.news_configured, bool)


async def test_reflects_the_latest_scan_snapshot(session: AsyncSession) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="market_scan_snapshot",
        event="scan_completed",
        context={
            "market": "XAUUSD",
            "state": "BUY",
            "confidence_pct": 82.5,
            "market_regime": "bull_trend",
            "strategy_name": "xauusd_m15_live",
            "explanation": "Momentum confirmed by order flow.",
        },
    )

    status = await get_dashboard_status(session)

    assert status.state == "BUY"
    assert status.confidence_pct == 82.5
    assert status.market_regime == "bull_trend"
    assert status.active_strategy == "xauusd_m15_live"
    assert status.ai_explanation == "Momentum confirmed by order flow."
    assert status.last_updated is not None


async def test_reflects_trade_quality_and_mt5_status_from_the_snapshot(
    session: AsyncSession,
) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="market_scan_snapshot",
        event="scan_completed",
        context={
            "market": "XAUUSD",
            "trade_quality_score": 82.0,
            "risk_score": 90.0,
            "mt5_connected": True,
        },
    )

    status = await get_dashboard_status(session)

    assert status.trade_quality_score == 82.0
    assert status.risk_score == 90.0
    assert status.mt5_status == "connected"


async def test_reflects_no_trade_reasons_and_next_scan_minutes_from_the_snapshot(
    session: AsyncSession,
) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="market_scan_snapshot",
        event="scan_completed",
        context={
            "market": "XAUUSD",
            "state": "WAIT",
            "no_trade_reasons": ["Уверенность ниже порога", "Технический анализ ↓"],
            "next_scan_minutes": 2.0,
        },
    )

    status = await get_dashboard_status(session)

    assert status.no_trade_reasons == ["Уверенность ниже порога", "Технический анализ ↓"]
    assert status.next_scan_minutes == 2.0


async def test_no_trade_reasons_defaults_to_empty_without_a_snapshot(
    session: AsyncSession,
) -> None:
    status = await get_dashboard_status(session)

    assert status.no_trade_reasons == []
    assert status.next_scan_minutes is None


async def test_reports_mt5_disconnected_when_the_last_cycle_lost_the_connection(
    session: AsyncSession,
) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="market_scan_snapshot",
        event="scan_completed",
        context={"market": "XAUUSD", "mt5_connected": False},
    )

    status = await get_dashboard_status(session)

    assert status.mt5_status == "disconnected"


async def test_only_the_most_recent_snapshot_is_used(session: AsyncSession) -> None:
    repo = SystemLogRepository(session)
    await repo.add(
        SystemLog(
            level="INFO",
            source="market_scan_snapshot",
            event="scan_completed",
            context={"state": "WAIT", "confidence_pct": 40.0},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await repo.add(
        SystemLog(
            level="INFO",
            source="market_scan_snapshot",
            event="scan_completed",
            context={"state": "SELL", "confidence_pct": 91.0},
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )

    status = await get_dashboard_status(session)

    assert status.state == "SELL"
    assert status.confidence_pct == 91.0


async def test_lists_open_positions(session: AsyncSession) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9700",
        )
    )

    status = await get_dashboard_status(session)

    assert len(status.open_positions) == 1
    assert status.open_positions[0].direction == "buy"
    assert status.open_positions[0].entry_price == 2000.0


async def test_open_position_includes_strategy_explanation_fields(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9701",
            quality_score=72.0,
            confidence_pct=88.0,
            risk_score=35.0,
            department_votes={
                "technical": {"bias": "bullish", "confidence": 0.8},
                "macro": {"bias": "bearish", "confidence": 0.5},
            },
            reasons=["bullish_probability_exceeds_bearish"],
            scenario_plan={"primary_scenario": "Price continues higher."},
        )
    )

    status = await get_dashboard_status(session)

    position = status.open_positions[0]
    assert position.strategy == "Intraday"
    assert position.quality_score == 72.0
    assert position.confidence_pct == 88.0
    assert position.risk_score == 35.0
    assert position.expected_scenario == "Price continues higher."
    assert position.reasons == ["bullish_probability_exceeds_bearish"]
    assert position.positive_confirmations == ["✅ Технический анализ"]
    assert position.negative_confirmations == ["❌ Макро"]


async def test_open_position_includes_the_similarity_summary_when_present(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9702",
            similarity_summary={
                "found_count": 42,
                "profitable_count": 28,
                "failed_count": 14,
                "win_rate_pct": 66.7,
                "average_rr": 2.1,
                "average_holding_time_minutes": 150.0,
                "average_drawdown_pct": 0.8,
            },
        )
    )

    status = await get_dashboard_status(session)

    position = status.open_positions[0]
    assert position.similarity_summary is not None
    assert "Найдено: 42" in position.similarity_summary
    assert "прибыльных: 28" in position.similarity_summary
    assert "провал: 14" in position.similarity_summary
    assert "RR 2.1" in position.similarity_summary


async def test_open_position_omits_the_similarity_summary_when_absent(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9703",
        )
    )

    status = await get_dashboard_status(session)

    assert status.open_positions[0].similarity_summary is None


async def test_closed_trade_includes_would_repeat_from_post_mortem(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            exit_price=1990.0,
            realized_pnl=-10.0,
            magic_number=42,
            closed_at=datetime.now(UTC),
            post_mortem={"would_repeat": False, "department_correctness": {}},
        )
    )

    status = await get_dashboard_status(session)

    assert status.closed_trades[0].would_repeat is False


async def test_open_position_shows_the_strategys_own_measured_expected_holding_time(
    session: AsyncSession,
) -> None:
    trade_repository = TradeRepository(session)
    # A closed Intraday trade with a known holding time establishes the
    # "expected" statistical average for any currently-open Intraday trade.
    await trade_repository.add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            exit_price=2010.0,
            realized_pnl=10.0,
            magic_number=41,
            opened_at=datetime(2026, 1, 1, tzinfo=UTC),
            closed_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    )
    await trade_repository.add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9702",
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    )

    status = await get_dashboard_status(session)

    assert len(status.open_positions) == 1
    assert status.open_positions[0].expected_holding_time_minutes == 60.0


async def test_sums_todays_realized_pnl(session: AsyncSession) -> None:
    trade_repository = TradeRepository(session)
    now = datetime.now(UTC)
    await trade_repository.add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            exit_price=2010.0,
            realized_pnl=10.0,
            magic_number=42,
            closed_at=now,
        )
    )
    await trade_repository.add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="sell",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=2010.0,
            exit_price=1995.0,
            realized_pnl=5.0,
            magic_number=42,
            closed_at=now,
        )
    )

    status = await get_dashboard_status(session)

    assert status.today_pnl == 15.0


async def test_excludes_pnl_from_trades_closed_on_other_days(session: AsyncSession) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            exit_price=2010.0,
            realized_pnl=100.0,
            magic_number=42,
            closed_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    status = await get_dashboard_status(session)

    assert status.today_pnl == 0.0


async def test_system_health_is_unknown_without_a_snapshot(session: AsyncSession) -> None:
    status = await get_dashboard_status(session)

    assert status.system_health == "unknown"


async def test_system_health_is_healthy_for_a_fresh_snapshot(session: AsyncSession) -> None:
    await SystemLogRepository(session).record(
        level="INFO", source="market_scan_snapshot", event="scan_completed", context={}
    )

    status = await get_dashboard_status(session)

    assert status.system_health == "healthy"


async def test_system_health_is_stalled_for_an_old_snapshot(session: AsyncSession) -> None:
    await SystemLogRepository(session).add(
        SystemLog(
            level="INFO",
            source="market_scan_snapshot",
            event="scan_completed",
            context={},
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )

    status = await get_dashboard_status(session)

    assert status.system_health == "stalled"


async def test_reflects_department_votes_and_current_trend(session: AsyncSession) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="market_scan_snapshot",
        event="scan_completed",
        context={
            "department_votes": {
                "technical": {"bias": "bullish", "confidence": 0.8},
                "correlation": {"bias": "bearish", "confidence": 0.6},
            },
            "current_trend": "bullish",
        },
    )

    status = await get_dashboard_status(session)

    assert status.current_trend == "bullish"
    assert status.active_departments == ["correlation", "technical"]
    assert status.correlation_summary == "bearish (60% confidence)"
    assert status.news_summary == "не настроено"


async def test_counts_pending_signals(session: AsyncSession) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="pending",
            volume=1.0,
            stop_loss=1990.0,
            magic_number=42,
        )
    )

    status = await get_dashboard_status(session)

    assert status.pending_signals == 1


async def test_computes_win_rate_profit_factor_and_drawdown(session: AsyncSession) -> None:
    trade_repository = TradeRepository(session)
    now = datetime.now(UTC)
    # Chronologically: win first (new equity high), then a loss (drawdown).
    await trade_repository.add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            exit_price=2020.0,
            realized_pnl=20.0,
            magic_number=42,
            closed_at=now - timedelta(hours=2),
        )
    )
    await trade_repository.add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="closed",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            exit_price=1995.0,
            realized_pnl=-5.0,
            magic_number=42,
            closed_at=now - timedelta(hours=1),
        )
    )

    status = await get_dashboard_status(session)

    assert status.win_rate_pct == 50.0
    assert status.profit_factor is not None and status.profit_factor > 0
    assert status.current_drawdown_usd == 5.0
    assert len(status.closed_trades) == 2


async def test_win_rate_and_profit_factor_are_none_without_closed_trades(
    session: AsyncSession,
) -> None:
    status = await get_dashboard_status(session)

    assert status.win_rate_pct is None
    assert status.profit_factor is None
    assert status.current_drawdown_usd == 0.0


async def test_learning_progress_counts_proposals_by_status(session: AsyncSession) -> None:
    repository = ImprovementProposalRepository(session)
    await repository.add(_proposal(title="A", status="pending"))
    await repository.add(_proposal(title="B", status="approved"))
    await repository.add(_proposal(title="C", status="rejected"))
    await repository.add(_proposal(title="D", status="rejected"))

    status = await get_dashboard_status(session)

    assert status.learning_progress.pending == 1
    assert status.learning_progress.approved == 1
    assert status.learning_progress.rejected == 2


async def test_books_summary_processed_count_reflects_the_book_repository(
    session: AsyncSession,
) -> None:
    status = await get_dashboard_status(session)

    assert status.books_summary.processed == 0


async def test_strategy_status_is_searching_without_any_snapshot(session: AsyncSession) -> None:
    status = await get_dashboard_status(session)

    assert status.strategies["intraday"].status == "searching"
    assert status.strategies["scalping"].status == "searching"
    assert status.strategies["swing"].status == "searching"


async def test_strategy_status_is_waiting_when_disabled(session: AsyncSession) -> None:
    runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
    runtime_settings.scalping_enabled = False
    await RuntimeSettingsRepository(session).add(runtime_settings)

    status = await get_dashboard_status(session)

    assert status.strategies["scalping"].status == "waiting"
    assert status.strategies["scalping"].enabled is False
    assert status.strategies["intraday"].status == "searching"


async def test_strategy_status_is_waiting_for_every_strategy_when_paused(
    session: AsyncSession,
) -> None:
    runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
    runtime_settings.paused = True
    await RuntimeSettingsRepository(session).add(runtime_settings)

    status = await get_dashboard_status(session)

    assert status.strategies["intraday"].status == "waiting"
    assert status.strategies["scalping"].status == "waiting"
    assert status.strategies["swing"].status == "waiting"


async def test_strategy_status_is_no_trade_from_its_own_snapshot(session: AsyncSession) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="scalping_scan_snapshot",
        event="scan_completed",
        context={
            "state": "no_trade",
            "trade_quality_score": 45.0,
            "confidence_pct": 30.0,
            "reasons": ["Недостаточно данных M1"],
        },
    )

    status = await get_dashboard_status(session)

    scalping = status.strategies["scalping"]
    assert scalping.status == "no_trade"
    assert scalping.quality_score == 45.0
    assert scalping.confidence_pct == 30.0
    assert scalping.reasons == ["Недостаточно данных M1"]
    # Intraday and Swing are independent -- an unrelated Scalping snapshot
    # never leaks into either of their own statuses.
    assert status.strategies["intraday"].status == "searching"
    assert status.strategies["swing"].status == "searching"


async def test_strategy_status_is_trade_found_from_its_own_snapshot(session: AsyncSession) -> None:
    await SystemLogRepository(session).record(
        level="INFO",
        source="swing_scan_snapshot",
        event="scan_completed",
        context={"state": "trade_found", "trade_quality_score": 88.0, "confidence_pct": 82.0},
    )

    status = await get_dashboard_status(session)

    assert status.strategies["swing"].status == "trade_found"
    assert status.strategies["swing"].quality_score == 88.0


async def test_strategy_status_is_trade_open_when_it_owns_an_open_position(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=99,
            broker_ticket="8800",
            department_votes={"scalping_engine": {"bias": "bullish", "confidence": 0.8}},
        )
    )

    status = await get_dashboard_status(session)

    assert status.strategies["scalping"].status == "trade_open"
    assert status.strategies["intraday"].status != "trade_open"
    assert status.strategies["swing"].status != "trade_open"


async def test_strategy_status_attributes_an_intraday_trade_by_its_technical_vote(
    session: AsyncSession,
) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=1,
            broker_ticket="8801",
            department_votes={
                "technical": {"bias": "bullish", "confidence": 0.8},
                "historical": {"bias": "bullish", "confidence": 0.6},
            },
        )
    )

    status = await get_dashboard_status(session)

    assert status.strategies["intraday"].status == "trade_open"
