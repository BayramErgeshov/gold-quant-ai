"""Integration tests for the automatic post-mortem service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.learning_engine.post_mortem import PostMortemService, generate_post_mortem
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository

_SYMBOL_ID = uuid.uuid4()


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _closed_trade(symbol_id: uuid.UUID, **overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": symbol_id,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "exit_price": 1990.0,
        "realized_pnl": -100.0,
        "magic_number": 42,
        "opened_at": datetime(2026, 1, 1, tzinfo=UTC),
        "closed_at": datetime(2026, 1, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_generate_post_mortem_flags_disagreement_and_missing_departments() -> None:
    trade = _closed_trade(
        _SYMBOL_ID,
        department_votes={
            "technical": {"bias": "bullish", "confidence": 0.8},
            "macro": {"bias": "bearish", "confidence": 0.7},
            "news": {"bias": "bearish", "confidence": 0.6},
        },
    )

    report = generate_post_mortem(trade)

    assert report.review.is_win is False
    assert set(report.disagreeing_departments) == {"macro", "news"}
    assert "order_flow" in report.missing_departments
    assert report.should_have_been_skipped is True
    assert report.would_repeat is False


def test_generate_post_mortem_includes_department_correctness_against_the_outcome() -> None:
    # `_closed_trade`'s default is a LOSING buy -- the bullish "technical"
    # vote agreed with the entry direction but is WRONG against the
    # actual (losing) outcome, while the bearish "macro"/"news" votes
    # opposed the entry but turn out RIGHT.
    trade = _closed_trade(
        _SYMBOL_ID,
        department_votes={
            "technical": {"bias": "bullish", "confidence": 0.8},
            "macro": {"bias": "bearish", "confidence": 0.7},
            "news": {"bias": "bearish", "confidence": 0.6},
        },
    )

    report = generate_post_mortem(trade)

    assert report.department_correctness == {"technical": False, "macro": True, "news": True}


def test_generate_post_mortem_no_skip_flag_with_single_disagreement() -> None:
    trade = _closed_trade(
        _SYMBOL_ID,
        department_votes={
            "technical": {"bias": "bullish", "confidence": 0.8},
            "macro": {"bias": "bearish", "confidence": 0.7},
        },
    )

    report = generate_post_mortem(trade)

    assert report.should_have_been_skipped is False
    assert report.would_repeat is True


async def test_run_for_closed_trade_returns_a_report_for_a_winning_trade_too(
    session: AsyncSession,
) -> None:
    # Per the "Post Trade Analysis" production requirement: every closed
    # trade -- win or loss -- gets a report, judged on entry process
    # quality rather than the realized P&L sign.
    symbol = await _make_symbol(session)
    trade = await TradeRepository(session).add(
        _closed_trade(symbol.id, realized_pnl=100.0, exit_price=2010.0)
    )
    service = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )

    report = await service.run_for_closed_trade(trade)

    assert report.trade_id == str(trade.id)
    assert report.review.is_win is True


async def test_a_winning_trade_never_creates_an_improvement_proposal(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trades_repo = TradeRepository(session)
    proposals_repo = ImprovementProposalRepository(session)
    service = PostMortemService(
        trade_repository=trades_repo,
        proposal_repository=proposals_repo,
        min_occurrences_for_proposal=1,
    )

    for _ in range(3):
        trade = await trades_repo.add(
            _closed_trade(symbol.id, realized_pnl=100.0, exit_price=2010.0, department_votes={})
        )
        await service.run_for_closed_trade(trade)

    assert await proposals_repo.list_pending() == []


async def test_run_for_closed_trade_returns_a_report_for_a_losing_trade(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = await TradeRepository(session).add(_closed_trade(symbol.id))
    service = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )

    report = await service.run_for_closed_trade(trade)

    assert report is not None
    assert report.trade_id == str(trade.id)


async def test_recurring_missing_department_factor_creates_a_pending_proposal(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trades_repo = TradeRepository(session)
    proposals_repo = ImprovementProposalRepository(session)
    service = PostMortemService(
        trade_repository=trades_repo,
        proposal_repository=proposals_repo,
        min_occurrences_for_proposal=3,
    )

    last_report = None
    for _ in range(3):
        trade = await trades_repo.add(_closed_trade(symbol.id, department_votes={}))
        last_report = await service.run_for_closed_trade(trade)

    assert last_report is not None
    pending = await proposals_repo.list_pending()
    assert len(pending) >= 1
    assert pending[0].status == "pending"


async def test_does_not_duplicate_an_already_proposed_hypothesis(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trades_repo = TradeRepository(session)
    proposals_repo = ImprovementProposalRepository(session)
    service = PostMortemService(
        trade_repository=trades_repo,
        proposal_repository=proposals_repo,
        min_occurrences_for_proposal=3,
    )

    for _ in range(3):
        trade = await trades_repo.add(_closed_trade(symbol.id, department_votes={}))
        await service.run_for_closed_trade(trade)

    # A 4th losing trade with the same recurring factor must not duplicate the proposal.
    trade = await trades_repo.add(_closed_trade(symbol.id, department_votes={}))
    await service.run_for_closed_trade(trade)

    pending = await proposals_repo.list_pending()
    titles = [proposal.title for proposal in pending]
    assert len(titles) == len(set(titles))
