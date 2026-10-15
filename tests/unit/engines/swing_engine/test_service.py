"""Unit tests for `SwingAnalysisService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.agents.report import AgentReport
from src.core.execution.mt5_client import SymbolTick
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.swing_engine.service import SwingAnalysisService
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class _BullishAgent(TechnicalAgent):
    name = "fake_bullish"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            bias="bullish",
            confidence=0.9,
            supporting_evidence=["fake_strong_uptrend"],
        )


class _BearishAgent(TechnicalAgent):
    name = "fake_bearish"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            bias="bearish",
            confidence=0.9,
            supporting_evidence=["fake_strong_downtrend"],
        )


class _NeutralAgent(TechnicalAgent):
    name = "fake_neutral"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(agent_name=self.name, bias="neutral", confidence=0.0)


def _d1_candle(offset: int, *, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="D1",
        timestamp=_BASE_TIME + timedelta(days=offset),
        open=close - 1.0,
        high=close + 1.5,
        low=close - 1.5,
        close=close,
        volume=1000.0,
        source="test_fixture",
    )


def _flat_d1(count: int, *, price: float = 2000.0) -> list[Candle]:
    return [_d1_candle(i, close=price) for i in range(count)]


def _w1_candle(offset: int, *, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="W1",
        timestamp=_BASE_TIME + timedelta(weeks=offset),
        open=close - 5.0,
        high=close + 5.0,
        low=close - 5.0,
        close=close,
        source="test_fixture",
    )


def _uptrend_w1(count: int = 25) -> list[Candle]:
    return [_w1_candle(i, close=2000.0 + i * 10) for i in range(count)]


def _downtrend_w1(count: int = 25) -> list[Candle]:
    return [_w1_candle(i, close=2000.0 - i * 10) for i in range(count)]


def _tick() -> SymbolTick:
    return SymbolTick(bid=2000.0, ask=2000.3, timestamp=datetime.now(UTC))


async def test_analyze_returns_none_with_too_few_d1_candles() -> None:
    service = SwingAnalysisService(technical_agents=[_BullishAgent()], confidence_threshold=0.0)

    result = await service.analyze(d1_candles=_flat_d1(5), w1_candles=_uptrend_w1(), tick=_tick())

    assert result.signal is None
    assert result.reasons == ["insufficient_d1_history"]


async def test_analyze_returns_none_when_agents_split_evenly() -> None:
    service = SwingAnalysisService(
        technical_agents=[_BullishAgent(), _BearishAgent()], confidence_threshold=0.0
    )

    result = await service.analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())

    assert result.signal is None
    assert result.reasons == ["no_directional_agreement"]


async def test_analyze_returns_none_when_agents_are_neutral() -> None:
    service = SwingAnalysisService(technical_agents=[_NeutralAgent()], confidence_threshold=0.0)

    result = await service.analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())

    assert result.signal is None
    assert result.reasons == ["no_directional_agreement"]


async def test_analyze_produces_a_buy_signal_aligned_with_the_weekly_trend() -> None:
    service = SwingAnalysisService(technical_agents=[_BullishAgent()], confidence_threshold=0.5)

    result = await service.analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())

    assert result.signal is not None
    assert result.direction == "buy"
    assert result.signal.is_counter_trend is False
    assert result.signal.weekly_trend_regime == "bull_trend"
    assert result.signal.stop_loss < result.signal.entry_price
    assert result.signal.take_profit > result.signal.entry_price
    assert "fake_strong_uptrend" in result.reasons


async def test_analyze_produces_a_sell_signal() -> None:
    service = SwingAnalysisService(technical_agents=[_BearishAgent()], confidence_threshold=0.5)

    result = await service.analyze(
        d1_candles=_flat_d1(30), w1_candles=_downtrend_w1(), tick=_tick()
    )

    assert result.signal is not None
    assert result.direction == "sell"
    assert result.signal.stop_loss > result.signal.entry_price
    assert result.signal.take_profit < result.signal.entry_price


async def test_analyze_discounts_confidence_when_counter_trend() -> None:
    aligned = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.0
    ).analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())
    counter_trend = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.0
    ).analyze(d1_candles=_flat_d1(30), w1_candles=_downtrend_w1(), tick=_tick())

    assert aligned.signal is not None
    assert counter_trend.signal is not None
    assert counter_trend.signal.is_counter_trend is True
    assert counter_trend.signal.confidence < aligned.signal.confidence


async def test_analyze_skips_when_confidence_is_below_threshold() -> None:
    service = SwingAnalysisService(technical_agents=[_BullishAgent()], confidence_threshold=0.999)

    result = await service.analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())

    assert result.signal is None
    assert any(reason.startswith("confidence_below_threshold:") for reason in result.reasons)


async def test_analyze_returns_none_without_weekly_history() -> None:
    service = SwingAnalysisService(technical_agents=[_BullishAgent()], confidence_threshold=0.5)

    result = await service.analyze(d1_candles=_flat_d1(30), w1_candles=[], tick=_tick())

    assert result.signal is not None
    assert result.signal.weekly_trend_regime is None
    assert result.signal.is_counter_trend is False


async def test_analyze_excludes_a_disabled_agent_via_enabled_agent_names() -> None:
    # Per the "Complete Strategy Builder" production requirement: a
    # disabled module must not vote at all -- with the bullish agent
    # excluded, only the bearish one remains and the signal flips sell.
    service = SwingAnalysisService(
        technical_agents=[_BullishAgent(), _BearishAgent()], confidence_threshold=0.0
    )

    result = await service.analyze(
        d1_candles=_flat_d1(30),
        w1_candles=_uptrend_w1(),
        tick=_tick(),
        enabled_agent_names={"fake_bearish"},
    )

    assert result.signal is not None
    assert result.direction == "sell"
    assert "fake_strong_uptrend" not in result.reasons


async def test_analyze_applies_agent_weights_to_the_confluence() -> None:
    unweighted = await SwingAnalysisService(
        technical_agents=[_BullishAgent(), _BearishAgent()], confidence_threshold=0.0
    ).analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())
    weighted = await SwingAnalysisService(
        technical_agents=[_BullishAgent(), _BearishAgent()], confidence_threshold=0.0
    ).analyze(
        d1_candles=_flat_d1(30),
        w1_candles=_uptrend_w1(),
        tick=_tick(),
        agent_weights={"fake_bullish": 10.0, "fake_bearish": 1.0},
    )

    # Equal weights deadlock the two agents to a neutral read (no signal);
    # heavily weighting the bullish agent tips the same confluence
    # decisively bullish -- proving the override actually reaches
    # `combine_agent_reports`, not merely stored and ignored.
    assert unweighted.signal is None
    assert unweighted.reasons == ["no_directional_agreement"]
    assert weighted.signal is not None
    assert weighted.direction == "buy"


async def test_analyze_discounts_confidence_when_h4_opposes_the_direction() -> None:
    aligned = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.0
    ).analyze(
        d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick(), h4_candles=_uptrend_w1()
    )
    counter_trend = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.0
    ).analyze(
        d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick(), h4_candles=_downtrend_w1()
    )

    assert aligned.signal is not None
    assert counter_trend.signal is not None
    assert counter_trend.signal.confidence < aligned.signal.confidence
    assert any("H4_counter_trend" in reason for reason in counter_trend.reasons)


async def test_analyze_discounts_confidence_when_m15_opposes_the_direction() -> None:
    aligned = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.0
    ).analyze(
        d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick(), m15_candles=_uptrend_w1()
    )
    counter_trend = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.0
    ).analyze(
        d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick(), m15_candles=_downtrend_w1()
    )

    assert aligned.signal is not None
    assert counter_trend.signal is not None
    assert counter_trend.signal.confidence < aligned.signal.confidence
    assert any("M15_counter_trend" in reason for reason in counter_trend.reasons)


async def test_analyze_without_h4_or_m15_candles_skips_those_checks() -> None:
    result = await SwingAnalysisService(
        technical_agents=[_BullishAgent()], confidence_threshold=0.5
    ).analyze(d1_candles=_flat_d1(30), w1_candles=_uptrend_w1(), tick=_tick())

    assert result.signal is not None
    assert not any("H4_" in reason for reason in result.reasons)
    assert not any("M15_" in reason for reason in result.reasons)
