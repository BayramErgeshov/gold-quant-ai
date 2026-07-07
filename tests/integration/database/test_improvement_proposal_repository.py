"""Integration tests for `ImprovementProposalRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.improvement_proposal import ImprovementProposal
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _proposal(**overrides: object) -> ImprovementProposal:
    defaults: dict[str, object] = {
        "title": "Widen stops in high volatility regimes",
        "problem": "Stops are hit prematurely during high volatility.",
        "evidence": "12 losing trades identified stop_too_close.",
        "expected_benefit": "Fewer premature stop-outs.",
        "potential_risk": "Larger losses per trade if wrong.",
        "implementation_difficulty": "medium",
        "recommendation": "Backtest wider stops in high-volatility regimes.",
    }
    defaults.update(overrides)
    return ImprovementProposal(**defaults)  # type: ignore[arg-type]


async def test_list_pending_returns_only_pending_proposals(session: AsyncSession) -> None:
    repo = ImprovementProposalRepository(session)
    await repo.add(_proposal(title="Pending one", status="pending", created_at=_BASE_TIME))
    await repo.add(_proposal(title="Approved one", status="approved"))
    await repo.add(_proposal(title="Rejected one", status="rejected"))

    pending = await repo.list_pending()

    assert [proposal.title for proposal in pending] == ["Pending one"]


async def test_list_pending_orders_oldest_first(session: AsyncSession) -> None:
    repo = ImprovementProposalRepository(session)
    await repo.add(
        _proposal(title="Newer", created_at=_BASE_TIME + timedelta(hours=1))
    )
    await repo.add(_proposal(title="Older", created_at=_BASE_TIME))

    pending = await repo.list_pending()

    assert [proposal.title for proposal in pending] == ["Older", "Newer"]


async def test_list_pending_respects_limit(session: AsyncSession) -> None:
    repo = ImprovementProposalRepository(session)
    for index in range(3):
        await repo.add(
            _proposal(title=f"Proposal {index}", created_at=_BASE_TIME + timedelta(hours=index))
        )

    pending = await repo.list_pending(limit=2)

    assert len(pending) == 2
