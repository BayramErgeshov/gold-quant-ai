"""Integration tests for Market Replay Mode's step decision engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.technical_analysis.agent import AgentReport, TechnicalAgent
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.replay_engine.decision import compute_replay_decision
from src.models.candle import Candle
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.symbol_repository import SymbolRepository

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)


class _BullishAgent(TechnicalAgent):
    name = "fake_bullish"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            bias="bullish",
            confidence=0.95,
            supporting_evidence=["fake_strong_uptrend"],
        )


class _WindowRecordingAgent(TechnicalAgent):
    """Records how many candles it was actually given, to assert no leakage."""

    name = "fake_window_recorder"

    def __init__(self) -> None:
        self.seen_timestamps: list[datetime] = []

    def analyze(self, candles: list[Candle]) -> AgentReport:
        self.seen_timestamps = [candle.timestamp for candle in candles]
        return AgentReport(agent_name=self.name, bias="neutral", confidence=0.0)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _rising_candles(symbol_id: object, count: int) -> list[Candle]:
    candles = []
    price = 2000.0
    for i in range(count):
        candles.append(
            Candle(
                symbol_id=symbol_id,
                timeframe="M15",
                timestamp=_BASE_TIME + timedelta(minutes=15 * i),
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.5,
                volume=100.0,
                spread=2.0,
                source="test_fixture",
            )
        )
        price += 0.5
    return candles


async def test_compute_replay_decision_never_sees_candles_at_or_after_the_decided_bar(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    all_candles = _rising_candles(symbol.id, 60)
    await CandleRepository(session).insert_new(all_candles)

    window = all_candles[:40]
    next_candle = all_candles[40]
    recorder = _WindowRecordingAgent()

    await compute_replay_decision(
        symbol_id=symbol.id,
        timeframe="M15",
        window=window,
        next_candle=next_candle,
        technical_agents=[recorder],
        similarity_service=HistoricalSimilarityService(
            candle_repository=CandleRepository(session),
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
    )

    assert recorder.seen_timestamps == [candle.timestamp for candle in window]
    assert next_candle.timestamp not in recorder.seen_timestamps


async def test_compute_replay_decision_flags_macro_news_correlation_order_flow_ml_absent(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    all_candles = _rising_candles(symbol.id, 60)
    await CandleRepository(session).insert_new(all_candles)

    step = await compute_replay_decision(
        symbol_id=symbol.id,
        timeframe="M15",
        window=all_candles[:40],
        next_candle=all_candles[40],
        technical_agents=[_BullishAgent()],
        similarity_service=HistoricalSimilarityService(
            candle_repository=CandleRepository(session),
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
    )

    assert "reduced_confidence:macro_unavailable" in step.decision.reduced_confidence_factors
    assert "reduced_confidence:news_unavailable" in step.decision.reduced_confidence_factors
    assert "reduced_confidence:correlation_unavailable" in step.decision.reduced_confidence_factors
    assert "reduced_confidence:order_flow_unavailable" in step.decision.reduced_confidence_factors
    assert "reduced_confidence:ml_unavailable" in step.decision.reduced_confidence_factors


async def test_compute_replay_decision_does_not_persist_similarity_matches(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    all_candles = _rising_candles(symbol.id, 80)
    await CandleRepository(session).insert_new(all_candles)

    await compute_replay_decision(
        symbol_id=symbol.id,
        timeframe="M15",
        window=all_candles[:60],
        next_candle=all_candles[60],
        technical_agents=[_BullishAgent()],
        similarity_service=HistoricalSimilarityService(
            candle_repository=CandleRepository(session),
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
    )

    persisted = await HistoricalSimilarityRepository(session).list_all(limit=1000)
    assert persisted == []


async def test_compute_replay_decision_sets_trade_parameters_only_when_actionable(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    all_candles = _rising_candles(symbol.id, 60)
    await CandleRepository(session).insert_new(all_candles)

    step = await compute_replay_decision(
        symbol_id=symbol.id,
        timeframe="M15",
        window=all_candles[:40],
        next_candle=all_candles[40],
        technical_agents=[_BullishAgent()],
        similarity_service=HistoricalSimilarityService(
            candle_repository=CandleRepository(session),
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
        confidence_threshold=0.0,
    )

    if step.decision.state in ("BUY", "SELL"):
        assert step.entry_price == all_candles[40].open
        assert step.stop_loss is not None
        assert step.take_profit is not None
    else:
        assert step.entry_price is None
        assert step.stop_loss is None
        assert step.take_profit is None
