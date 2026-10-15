"""Integration tests for `ClaimValidationService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.report import AgentReport
from src.engines.book_engine.claim_validation import ClaimValidationService
from src.models.book_claim import BookClaim
from src.models.candle import Candle
from src.repositories.book_claim_repository import BookClaimRepository

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeAgent:
    """Always reports the same bias/confidence, regardless of the window."""

    name = "fake"

    def __init__(self, *, bias: str, confidence: float = 0.9) -> None:
        self._bias = bias
        self._confidence = confidence

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(agent_name=self.name, bias=self._bias, confidence=self._confidence)  # type: ignore[arg-type]


def _candle(offset: int, *, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="H1",
        timestamp=_BASE_TIME + timedelta(hours=offset),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        source="test_fixture",
    )


def _rising_candles(count: int) -> list[Candle]:
    return [_candle(i, close=2000.0 + i * 2.0) for i in range(count)]


async def _add_claim(session: AsyncSession, *, topic: str | None, statement: str) -> BookClaim:
    claim = BookClaim(book_id=uuid.uuid4(), chunk_id=uuid.uuid4(), statement=statement, topic=topic)
    session.add(claim)
    await session.flush()
    await session.refresh(claim)
    return claim


async def test_claim_with_untestable_topic_becomes_unknown(session: AsyncSession) -> None:
    await _add_claim(session, topic="psychology", statement="Discipline often beats greed.")
    service = ClaimValidationService(claim_repository=BookClaimRepository(session))

    results = await service.validate_pending_claims(_rising_candles(100))

    assert len(results) == 1
    assert results[0].status == "unknown"
    assert "no_testable_agent_for_topic" in results[0].reason


async def test_claim_with_insufficient_candle_history_becomes_unknown(
    session: AsyncSession,
) -> None:
    await _add_claim(
        session, topic="market_structure", statement="Break of structure often signals a move."
    )
    service = ClaimValidationService(claim_repository=BookClaimRepository(session))

    with patch.dict(
        "src.engines.book_engine.claim_validation._TOPIC_AGENTS",
        {"market_structure": lambda: _FakeAgent(bias="bullish")},
    ):
        results = await service.validate_pending_claims(_rising_candles(35))

    assert results[0].status == "unknown"
    assert "insufficient_samples" in results[0].reason

    stored = await BookClaimRepository(session).get_by_id(results[0].claim_id)
    assert stored is not None
    assert stored.validation_status == "unknown"
    assert stored.confidence == 0.0


async def test_neutral_and_low_confidence_signals_are_excluded_from_the_sample(
    session: AsyncSession,
) -> None:
    await _add_claim(
        session, topic="market_structure", statement="Break of structure often signals a move."
    )
    service = ClaimValidationService(claim_repository=BookClaimRepository(session))

    with patch.dict(
        "src.engines.book_engine.claim_validation._TOPIC_AGENTS",
        {"market_structure": lambda: _FakeAgent(bias="neutral")},
    ):
        results = await service.validate_pending_claims(_rising_candles(100))

    # Every window reports "neutral" -> zero signal occurrences collected,
    # not merely "too few" -- confirms the neutral/low-confidence filter
    # runs before the sample-size check, rather than counting non-signals.
    assert results[0].status == "unknown"
    assert results[0].sample_size == 0


async def test_claim_is_accepted_when_the_agent_signal_shows_a_positive_edge(
    session: AsyncSession,
) -> None:
    await _add_claim(
        session, topic="market_structure", statement="Break of structure often signals a move up."
    )
    service = ClaimValidationService(claim_repository=BookClaimRepository(session))

    with patch.dict(
        "src.engines.book_engine.claim_validation._TOPIC_AGENTS",
        {"market_structure": lambda: _FakeAgent(bias="bullish")},
    ):
        results = await service.validate_pending_claims(_rising_candles(100))

    assert results[0].status == "accepted"
    assert results[0].win_rate == pytest.approx(1.0)
    assert results[0].sample_size > 0

    stored = await BookClaimRepository(session).get_by_id(results[0].claim_id)
    assert stored is not None
    assert stored.validation_status == "accepted"
    assert stored.confidence == pytest.approx(1.0)


async def test_claim_is_rejected_when_the_agent_signal_shows_no_edge(
    session: AsyncSession,
) -> None:
    await _add_claim(
        session,
        topic="market_structure",
        statement="Break of structure often signals a move down.",
    )
    service = ClaimValidationService(claim_repository=BookClaimRepository(session))

    # A bearish-biased agent on a steadily *rising* market -> every
    # signal loses, a genuine "no historical edge" outcome.
    with patch.dict(
        "src.engines.book_engine.claim_validation._TOPIC_AGENTS",
        {"market_structure": lambda: _FakeAgent(bias="bearish")},
    ):
        results = await service.validate_pending_claims(_rising_candles(100))

    assert results[0].status == "rejected"
    assert results[0].win_rate == pytest.approx(0.0)

    stored = await BookClaimRepository(session).get_by_id(results[0].claim_id)
    assert stored is not None
    assert stored.validation_status == "rejected"
    assert stored.confidence == 0.0
