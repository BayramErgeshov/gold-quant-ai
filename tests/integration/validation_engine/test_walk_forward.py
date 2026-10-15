"""Integration tests for the Walk-Forward Validation Engine."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.technical_analysis.agent import AgentReport, TechnicalAgent
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.validation_engine.walk_forward import run_chief_ai_walk_forward
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
    """Records every window it was ever given, to assert no future leakage."""

    name = "fake_window_recorder"

    def __init__(self) -> None:
        self.seen_windows: list[list[datetime]] = []

    def analyze(self, candles: list[Candle]) -> AgentReport:
        self.seen_windows.append([candle.timestamp for candle in candles])
        return AgentReport(agent_name=self.name, bias="neutral", confidence=0.0)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _rising_candles(
    symbol_id: object, count: int, *, slope: float = 0.5, amplitude: float = 1.5
) -> list[Candle]:
    candles = []
    for i in range(count):
        close = 2000.0 + i * slope + amplitude * math.sin(i * 0.7)
        candles.append(
            Candle(
                symbol_id=symbol_id,
                timeframe="M15",
                timestamp=_BASE_TIME + timedelta(minutes=15 * i),
                open=close - 0.1,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=100.0,
                spread=2.0,
                source="test_fixture",
            )
        )
    return candles


def _similarity_service(session: AsyncSession) -> HistoricalSimilarityService:
    return HistoricalSimilarityService(
        candle_repository=CandleRepository(session),
        similarity_repository=HistoricalSimilarityRepository(session),
    )


async def test_run_chief_ai_walk_forward_produces_one_opportunity_per_step(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    candles = _rising_candles(symbol.id, 70)
    await CandleRepository(session).insert_new(candles)

    opportunities = await run_chief_ai_walk_forward(
        symbol_id=symbol.id,
        timeframe="M15",
        candles=candles,
        technical_agents=[_BullishAgent()],
        similarity_service=_similarity_service(session),
        window_size=40,
        confidence_threshold=0.0,
    )

    assert len(opportunities) == 70 - 40
    assert opportunities[0].timestamp == candles[40].timestamp
    assert opportunities[-1].timestamp == candles[-1].timestamp


async def test_run_chief_ai_walk_forward_never_leaks_a_future_candle(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    candles = _rising_candles(symbol.id, 45)
    await CandleRepository(session).insert_new(candles)
    recorder = _WindowRecordingAgent()

    await run_chief_ai_walk_forward(
        symbol_id=symbol.id,
        timeframe="M15",
        candles=candles,
        technical_agents=[recorder],
        similarity_service=_similarity_service(session),
        window_size=40,
        confidence_threshold=0.0,
    )

    all_timestamps = [candle.timestamp for candle in candles]
    for step_index, seen_window in enumerate(recorder.seen_windows):
        decided_timestamp = all_timestamps[40 + step_index]
        assert decided_timestamp not in seen_window
        assert all(timestamp < decided_timestamp for timestamp in seen_window)


async def test_run_chief_ai_walk_forward_records_a_forward_simulation_when_actionable(
    session: AsyncSession,
) -> None:
    # A long, clean uptrend so the Historical Research Engine accumulates
    # enough same-shaped analogues (all with a positive forward return)
    # for its own department vote to clear the Risk Engine's "high
    # quality" executable tier alongside a strongly bullish technical read.
    symbol = await _make_symbol(session)
    candles = _rising_candles(symbol.id, 260, slope=1.0)
    await CandleRepository(session).insert_new(candles)

    opportunities = await run_chief_ai_walk_forward(
        symbol_id=symbol.id,
        timeframe="M15",
        candles=candles,
        technical_agents=[_BullishAgent()],
        similarity_service=_similarity_service(session),
        window_size=150,
        confidence_threshold=0.0,
    )

    actionable = [o for o in opportunities if o.would_have_traded]
    assert actionable, "expected at least one actionable opportunity with confidence_threshold=0"
    traded = [o for o in actionable if o.realized_return_pct is not None]
    assert traded, "expected at least one actionable opportunity to have a forward simulation"
    sample = traded[0]
    assert sample.direction == "buy"
    assert "technical" in sample.agreeing_departments
    assert sample.holding_bars is not None and sample.holding_bars > 0
    assert sample.exit_reason is not None
    assert sample.mfe_pct is not None
    assert sample.mae_pct is not None
    assert sample.mae_pct <= 0.0 <= sample.mfe_pct


async def test_run_chief_ai_walk_forward_respects_the_step_parameter(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    candles = _rising_candles(symbol.id, 70)
    await CandleRepository(session).insert_new(candles)

    opportunities = await run_chief_ai_walk_forward(
        symbol_id=symbol.id,
        timeframe="M15",
        candles=candles,
        technical_agents=[_BullishAgent()],
        similarity_service=_similarity_service(session),
        window_size=40,
        step=5,
        confidence_threshold=0.0,
    )

    assert len(opportunities) == len(range(40, 70, 5))


async def test_run_chief_ai_walk_forward_reports_missing_departments(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    candles = _rising_candles(symbol.id, 45)
    await CandleRepository(session).insert_new(candles)

    opportunities = await run_chief_ai_walk_forward(
        symbol_id=symbol.id,
        timeframe="M15",
        candles=candles,
        technical_agents=[_BullishAgent()],
        similarity_service=_similarity_service(session),
        window_size=40,
        confidence_threshold=0.0,
    )

    assert opportunities
    assert "macro" in opportunities[0].missing_departments
    assert "news" in opportunities[0].missing_departments
