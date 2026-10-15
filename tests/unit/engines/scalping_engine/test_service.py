"""Unit tests for `ScalpingAnalysisService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.agents.confluence import CombinedVote
from src.core.execution.mt5_client import (
    AccountInfo,
    MT5Client,
    OpenPosition,
    OrderBookSnapshot,
    OrderRequest,
    OrderResult,
    SymbolTick,
)
from src.engines.order_flow_engine.service import OrderFlowAnalysisService, OrderFlowResult
from src.engines.scalping_engine.service import ScalpingAnalysisService, _combine_signals
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeMT5Client(MT5Client):
    """No DOM -> Order Flow Engine falls back to its synthetic path."""

    async def connect(self) -> bool:
        return True

    async def is_connected(self) -> bool:
        return True

    async def get_account_info(self) -> AccountInfo:
        raise NotImplementedError

    async def place_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def modify_order(
        self,
        broker_ticket: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        raise NotImplementedError

    async def close_position(
        self, broker_ticket: str, *, volume: float | None = None
    ) -> OrderResult:
        raise NotImplementedError

    async def cancel_order(self, broker_ticket: str) -> OrderResult:
        raise NotImplementedError

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        raise NotImplementedError

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        raise NotImplementedError

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        return None

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        raise NotImplementedError


def _m1_candle(offset: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="M1",
        timestamp=_BASE_TIME + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def _flat_m1(count: int, *, price: float = 2000.0) -> list[Candle]:
    return [
        _m1_candle(i, open_=price, high=price + 0.2, low=price - 0.2, close=price)
        for i in range(count)
    ]


def _bullish_burst_m1() -> list[Candle]:
    baseline = _flat_m1(20, price=2000.0)
    burst = [
        _m1_candle(20, open_=2000.0, high=2003.0, low=1999.9, close=2002.5),
        _m1_candle(21, open_=2002.5, high=2005.5, low=2002.4, close=2005.0),
        _m1_candle(22, open_=2005.0, high=2008.5, low=2004.9, close=2008.0),
    ]
    return baseline + burst


def _htf_candle(offset: int, *, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="H1",
        timestamp=_BASE_TIME + timedelta(hours=offset),
        open=close - 1,
        high=close + 1,
        low=close - 1,
        close=close,
        source="test_fixture",
    )


def _uptrend_htf(count: int = 25) -> list[Candle]:
    return [_htf_candle(i, close=2000.0 + i * 5) for i in range(count)]


def _downtrend_htf(count: int = 25) -> list[Candle]:
    return [_htf_candle(i, close=2000.0 - i * 5) for i in range(count)]


def _service() -> ScalpingAnalysisService:
    mt5 = _FakeMT5Client()
    return ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
        confidence_threshold=0.5,
    )


async def test_analyze_returns_none_with_too_few_m1_candles() -> None:
    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_flat_m1(5),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2000.0, ask=2000.2, timestamp=datetime.now(UTC)),
    )

    assert result.signal is None
    assert result.reasons == ["insufficient_m1_history"]


async def test_analyze_returns_none_with_no_microstructure_signal() -> None:
    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_flat_m1(30),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2000.0, ask=2000.2, timestamp=datetime.now(UTC)),
    )

    assert result.signal is None
    assert result.reasons == ["no_microstructure_signal"]


async def test_analyze_produces_a_buy_signal_aligned_with_the_htf_trend() -> None:
    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
    )

    assert result.signal is not None
    assert result.direction == "buy"
    assert result.signal.is_counter_trend is False
    assert result.signal.htf_trend_regime == "bull_trend"
    assert result.signal.stop_loss < result.signal.entry_price
    assert result.signal.take_profit > result.signal.entry_price


async def test_analyze_discounts_confidence_when_counter_trend() -> None:
    # Strong bullish M1 burst but the higher timeframe is in a downtrend.
    aligned = await ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    ).analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
    )
    counter_trend = await ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    ).analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_downtrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
    )

    assert aligned.signal is not None
    assert counter_trend.signal is not None
    assert counter_trend.signal.is_counter_trend is True
    assert counter_trend.signal.confidence < aligned.signal.confidence


async def test_analyze_skips_when_confidence_is_below_threshold() -> None:
    high_bar_service = ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.999,
    )

    result = await high_bar_service.analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_downtrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
    )

    assert result.signal is None
    assert any(reason.startswith("confidence_below_threshold:") for reason in result.reasons)


async def test_analyze_uses_correlation_vote_when_provided() -> None:
    strongly_bullish_correlation = CombinedVote(
        bullish_probability=1.0,
        bearish_probability=0.0,
        neutral_probability=0.0,
        confidence=1.0,
        quality_grade="AAA",
        strongest_supporting_factors=["test"],
        strongest_opposing_factors=[],
    )

    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        correlation_vote=strongly_bullish_correlation,
    )

    assert result.signal is not None
    assert "correlation_confirmation" in result.reasons


async def test_analyze_returns_none_without_htf_history() -> None:
    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=[],
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
    )

    assert result.signal is not None
    assert result.signal.htf_trend_regime is None
    assert result.signal.is_counter_trend is False


def _failed_breakout_m1() -> list[Candle]:
    prior = [_m1_candle(i, open_=2000.0, high=2001.0, low=1999.0, close=2000.0) for i in range(20)]
    failed = _m1_candle(20, open_=2000.5, high=2002.0, low=2000.4, close=2000.8)
    return prior + [failed]


def _micro_pullback_m1() -> list[Candle]:
    baseline = _flat_m1(19, price=2000.0)
    impulse = _m1_candle(19, open_=2000.0, high=2010.5, low=1999.9, close=2010.0)
    pullback = _m1_candle(20, open_=2010.0, high=2010.1, low=2009.0, close=2009.2)
    return baseline + [impulse, pullback]


async def test_analyze_produces_a_signal_from_a_failed_breakout() -> None:
    # A low confidence_threshold here since order flow confirmation (not the
    # breakout failure itself) ends up deciding the final direction on this
    # otherwise-flat fixture -- this test only exercises the breakout-failure
    # detection branch, not a specific directional outcome.
    low_bar_service = ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    )

    result = await low_bar_service.analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_failed_breakout_m1(),
        htf_candles=_downtrend_htf(),
        tick=SymbolTick(bid=2000.6, ask=2000.8, timestamp=datetime.now(UTC)),
    )

    assert result.signal is not None
    assert any(reason.startswith("breakout_failure_at:") for reason in result.reasons)


async def test_analyze_produces_a_signal_from_a_micro_pullback() -> None:
    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_micro_pullback_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2009.0, ask=2009.2, timestamp=datetime.now(UTC)),
    )

    assert result.signal is not None
    assert result.direction == "buy"
    assert "micro_pullback_continuation" in result.reasons


def test_combine_signals_returns_neutral_buy_when_total_weight_is_zero() -> None:
    zero_confidence_order_flow = OrderFlowResult(
        source="synthetic",
        bullish_probability=0.0,
        bearish_probability=0.0,
        confidence=0.0,
    )

    direction, confidence = _combine_signals([], zero_confidence_order_flow, None)

    assert direction == "buy"
    assert confidence == 0.0


async def test_analyze_discounts_confidence_when_m15_opposes_the_direction() -> None:
    aligned = await ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    ).analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        m15_candles=_uptrend_htf(),
    )
    counter_trend = await ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    ).analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        m15_candles=_downtrend_htf(),
    )

    assert aligned.signal is not None
    assert counter_trend.signal is not None
    assert counter_trend.signal.confidence < aligned.signal.confidence
    assert any("M15_counter_trend" in reason for reason in counter_trend.reasons)


async def test_analyze_discounts_confidence_when_m5_opposes_the_direction() -> None:
    aligned = await ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    ).analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        m5_candles=_uptrend_htf(),
    )
    counter_trend = await ScalpingAnalysisService(
        order_flow_service=OrderFlowAnalysisService(mt5_client=_FakeMT5Client()),
        confidence_threshold=0.0,
    ).analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        m5_candles=_downtrend_htf(),
    )

    assert aligned.signal is not None
    assert counter_trend.signal is not None
    assert counter_trend.signal.confidence < aligned.signal.confidence
    assert any("M5_counter_trend" in reason for reason in counter_trend.reasons)


async def test_analyze_without_m15_or_m5_candles_skips_those_checks() -> None:
    result = await _service().analyze(
        mt5_symbol="XAUUSD",
        m1_candles=_bullish_burst_m1(),
        htf_candles=_uptrend_htf(),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
    )

    assert result.signal is not None
    assert not any("M15_" in reason for reason in result.reasons)
    assert not any("M5_" in reason for reason in result.reasons)
