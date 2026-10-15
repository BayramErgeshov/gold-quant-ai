"""Integration tests for the Market Update Workflow (`MarketScanner`)."""

from __future__ import annotations

import dataclasses
import math
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.execution.mt5_client import (
    AccountInfo,
    MT5Client,
    OpenPosition,
    OrderBookSnapshot,
    OrderRequest,
    OrderResult,
    SymbolTick,
)
from src.core.ml.model import ClassificationModel, RegressionModel
from src.core.technical_analysis.agent import AgentReport, TechnicalAgent
from src.engines.correlation_engine.analysis import CorrelationAnalysisService
from src.engines.historical_engine.mt5_ingestion import MT5HistoricalIngestionService
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.ml_engine.dataset import Sample
from src.engines.order_flow_engine.service import OrderFlowAnalysisService
from src.engines.risk_engine.exposure import ExposureLimits
from src.models.candle import Candle
from src.models.correlated_instrument import CorrelatedInstrument
from src.models.correlated_price import CorrelatedPrice
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.symbol_repository import SymbolRepository
from src.workflows.market_update.pipeline import (
    MarketScanConfig,
    MarketScanner,
)

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)
_FEATURE_NAMES = (
    "momentum_pct",
    "trend_slope_pct",
    "volatility_pct",
    "range_width_pct",
    "volume_trend_pct",
)


class _BullishAgent(TechnicalAgent):
    """A deterministic stand-in agent, strongly and confidently bullish."""

    name = "fake_bullish"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            bias="bullish",
            confidence=0.99,
            supporting_evidence=["fake_strong_uptrend"],
        )


class _BearishAgent(TechnicalAgent):
    """A deterministic stand-in agent, strongly and confidently bearish."""

    name = "fake_bearish"

    def analyze(self, candles: list[Candle]) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            bias="bearish",
            confidence=0.99,
            supporting_evidence=["fake_strong_downtrend"],
        )


class _WindowRecordingAgent(TechnicalAgent):
    """Records how many candles it was actually given, for window-size assertions."""

    name = "fake_window_recorder"

    def __init__(self) -> None:
        self.received_candle_count: int | None = None

    def analyze(self, candles: list[Candle]) -> AgentReport:
        self.received_candle_count = len(candles)
        return AgentReport(agent_name=self.name, bias="neutral", confidence=0.0)


class _FakeMT5Client(MT5Client):
    def __init__(
        self,
        *,
        raw_candles: list[dict[str, object]],
        tick: SymbolTick,
        account: AccountInfo,
        positions: list[OpenPosition] | None = None,
        raw_candles_by_timeframe: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self._raw_candles = raw_candles
        self._tick = tick
        self._account = account
        self._positions = positions or []
        # Per-timeframe overrides for the "Complete Multi-Timeframe
        # Analysis" tests -- falls back to `raw_candles` for any timeframe
        # not explicitly given, matching every other test's assumption
        # that one candle series serves every timeframe requested.
        self._raw_candles_by_timeframe = raw_candles_by_timeframe or {}

    async def connect(self) -> bool:
        return True

    async def is_connected(self) -> bool:
        return True

    async def get_account_info(self) -> AccountInfo:
        return self._account

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
        candles = self._raw_candles_by_timeframe.get(timeframe, self._raw_candles)
        return candles[-count:]

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        return self._tick

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        return None

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        return self._positions


def _uptrend_raw_candles(
    count: int, *, slope: float = 0.5, amplitude: float = 2.0
) -> list[dict[str, object]]:
    base_epoch = int(_BASE_TIME.timestamp())
    candles: list[dict[str, object]] = []
    for index in range(count):
        close = 2000.0 + index * slope + amplitude * math.sin(index * 0.7)
        candles.append(
            {
                "time": base_epoch + index * 900,
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "tick_volume": 100.0 + index,
                "spread": 20,
            }
        )
    return candles


def _downtrend_raw_candles(
    count: int, *, slope: float = 0.5, amplitude: float = 2.0
) -> list[dict[str, object]]:
    base_epoch = int(_BASE_TIME.timestamp())
    candles: list[dict[str, object]] = []
    for index in range(count):
        close = 2000.0 - index * slope + amplitude * math.sin(index * 0.7)
        candles.append(
            {
                "time": base_epoch + index * 900,
                "open": close + 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "tick_volume": 100.0 + index,
                "spread": 20,
            }
        )
    return candles


def _bullish_classification_model() -> ClassificationModel:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    samples = [
        Sample(
            features={
                "momentum_pct": 3.0,
                "trend_slope_pct": 0.3,
                "volatility_pct": 0.2,
                "range_width_pct": 0.5,
                "volume_trend_pct": 1.0,
            },
            forward_return_pct=2.0,
            label="strong_bullish",
        )
        for _ in range(5)
    ] + [
        Sample(
            features={
                "momentum_pct": -3.0,
                "trend_slope_pct": -0.3,
                "volatility_pct": 0.2,
                "range_width_pct": 0.5,
                "volume_trend_pct": -1.0,
            },
            forward_return_pct=-2.0,
            label="strong_bearish",
        )
    ]
    model.fit(samples)
    return model


def _bullish_regression_model() -> RegressionModel:
    model = RegressionModel(feature_names=_FEATURE_NAMES)
    samples = [
        Sample(
            features={
                "momentum_pct": 3.0,
                "trend_slope_pct": 0.3,
                "volatility_pct": 0.2,
                "range_width_pct": 0.5,
                "volume_trend_pct": 1.0,
            },
            forward_return_pct=2.0,
            label="strong_bullish",
        ),
        Sample(
            features={
                "momentum_pct": -3.0,
                "trend_slope_pct": -0.3,
                "volatility_pct": 0.2,
                "range_width_pct": 0.5,
                "volume_trend_pct": -1.0,
            },
            forward_return_pct=-2.0,
            label="strong_bearish",
        ),
    ]
    model.fit(samples)
    return model


def _exposure_limits() -> ExposureLimits:
    return ExposureLimits(
        max_total_exposure_pct=5.0,
        max_instrument_exposure_pct=5.0,
        max_correlated_exposure_pct=7.5,
        max_session_exposure_pct=10.0,
        max_daily_exposure_pct=10.0,
    )


def _scan_config(symbol_id: uuid.UUID, *, window_size: int = 20) -> MarketScanConfig:
    return MarketScanConfig(
        symbol_id=symbol_id,
        mt5_symbol="XAUUSD",
        timeframe="M15",
        window_size=window_size,
        risk_per_trade_pct=0.5,
        atr_multiplier_for_stop=1.5,
        max_spread_points=350.0,
        confidence_threshold=1.0,  # low bar: this test asserts wiring, not model accuracy
        exposure_limits=_exposure_limits(),
        account_type="demo",
        expected_account="12345",
        live_trading_approved=False,
        strategy_name="xauusd_m15_live",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )


async def _make_symbol(session: AsyncSession, *, name: str = "XAUUSD") -> Symbol:
    return await SymbolRepository(session).add(Symbol(name=name, display_name="Gold"))


async def _seed_candles(
    session: AsyncSession, symbol_id: object, count: int, **kwargs: float
) -> None:
    """Insert deep candle history directly, as if an initial backfill already ran.

    `MarketScanner` only asks MT5 to top up the last `window_size + 50`
    candles each cycle (real production already has deep history from
    `scripts/mt5_historical_backfill.py`); tests must seed that depth
    directly rather than relying on the small per-cycle top-up count.
    """
    raw = _uptrend_raw_candles(count, **kwargs)
    candles = [
        Candle(
            symbol_id=symbol_id,
            timeframe="M15",
            timestamp=datetime.fromtimestamp(row["time"], tz=UTC),  # type: ignore[arg-type]
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["tick_volume"],
            spread=row["spread"],
            source="test_fixture",
        )
        for row in raw
    ]
    await CandleRepository(session).insert_new(candles)


def _make_scanner(
    session: AsyncSession,
    symbol: Symbol,
    mt5: _FakeMT5Client,
    *,
    window_size: int = 20,
    config: MarketScanConfig | None = None,
    technical_agents: list[TechnicalAgent] | None = None,
    technical_agent_weights: dict[str, float] | None = None,
) -> MarketScanner:
    candle_repository = CandleRepository(session)
    return MarketScanner(
        config=config or _scan_config(symbol.id, window_size=window_size),
        mt5_client=mt5,
        candle_repository=candle_repository,
        historical_ingestion=MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=mt5
        ),
        similarity_service=HistoricalSimilarityService(
            candle_repository=candle_repository,
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
        technical_agents=technical_agents if technical_agents is not None else [_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        technical_agent_weights=technical_agent_weights,
    )


async def test_scan_waits_on_insufficient_candle_history(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2000.0, ask=2000.5, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    scanner = _make_scanner(session, symbol, mt5, window_size=20)

    result = await scanner.scan()

    assert result.decision.state == "WAIT"
    assert "insufficient_candle_history" in result.blocked_reasons


async def test_scan_produces_reduced_confidence_decision_with_enough_history(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    # A steep, low-noise uptrend with 400 bars gives every department a
    # clean, near-unanimous bullish read (technical agent, historical
    # analogues, and the ML model all trained/queried on the same
    # pattern) so this scan reliably clears both Chief AI's and the Risk
    # Engine's confidence thresholds — proving the full BUY code path
    # (entry/stop/target/position-size/execution-validation) actually runs.
    # Deep history is seeded directly (as a real deployment's initial
    # backfill would have already done); MT5 only needs to supply the
    # small per-cycle top-up `MarketScanner` actually requests.
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    scanner = _make_scanner(session, symbol, mt5, window_size=20)

    result = await scanner.scan()

    # Macro/News are unconfigured in this platform's current reduced mode,
    # so every non-WAIT-hard-missing decision must be flagged accordingly.
    assert result.decision.is_reduced_confidence
    assert result.market_regime is not None
    assert result.decision.state == "BUY", (
        f"expected a clean uptrend to produce BUY, got {result.decision.state} "
        f"(confidence={result.decision.confidence_pct:.1f}, reasons={result.decision.reasons})"
    )
    assert result.entry_price is not None
    assert result.stop_loss is not None
    assert result.stop_loss < result.entry_price
    assert result.take_profit is not None
    assert result.take_profit > result.entry_price
    assert result.position_size is not None
    assert result.position_size.position_size_units > 0
    assert result.execution_request is not None
    assert result.execution_request.risk_approved is True
    # Per the "Trade Similarity Engine" production requirement: shown
    # before every trade, evaluated against the chosen (BUY) direction.
    assert result.similarity_summary is not None
    assert result.similarity_summary.found_count > 0
    assert result.similarity_summary.average_holding_time_minutes > 0


async def test_scan_uses_the_configured_fixed_lot_size_instead_of_risk_based_sizing(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    fixed_lot_config = dataclasses.replace(_scan_config(symbol.id), fixed_lot_size=2.5)
    scanner = _make_scanner(session, symbol, mt5, config=fixed_lot_config)

    result = await scanner.scan()

    assert result.decision.state == "BUY"
    assert result.position_size is not None
    # Always exactly the configured fixed size, regardless of confidence,
    # risk_per_trade_pct, or the stop distance for this cycle.
    assert result.position_size.position_size_units == pytest.approx(2.5)


async def test_scan_honors_technical_agent_weights_from_a_strategy_profile(
    session: AsyncSession,
) -> None:
    # Per the "Complete Strategy Builder" production requirement: a
    # profile's per-module weight must actually change the technical
    # vote, not just display as configured. One strongly bullish and one
    # strongly bearish agent, otherwise deadlocked, is tipped decisively
    # by weighting the bullish one far higher.
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    agents: list[TechnicalAgent] = [_BullishAgent(), _BearishAgent()]
    equal_weight_scanner = _make_scanner(session, symbol, mt5, technical_agents=agents)
    weighted_scanner = _make_scanner(
        session,
        symbol,
        mt5,
        technical_agents=agents,
        technical_agent_weights={"fake_bullish": 10.0, "fake_bearish": 1.0},
    )

    equal_result = await equal_weight_scanner.scan()
    weighted_result = await weighted_scanner.scan()

    # With equal weights, the deadlocked bullish/bearish agents cancel out
    # to a neutral technical read; heavily weighting the bullish one tips
    # the SAME confluence algorithm decisively bullish -- proving the
    # weight override actually reaches `TechnicalConfluence`, not merely
    # stored and ignored.
    equal_technical_vote = equal_result.department_votes["technical"]
    weighted_technical_vote = weighted_result.department_votes["technical"]
    assert equal_technical_vote.bullish_probability == pytest.approx(
        equal_technical_vote.bearish_probability
    )
    assert weighted_technical_vote.bullish_probability > weighted_technical_vote.bearish_probability


async def test_scan_gives_technical_agents_their_own_independently_sized_window(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    config = dataclasses.replace(_scan_config(symbol.id, window_size=20), technical_window_size=250)
    candle_repository = CandleRepository(session)
    window_recorder = _WindowRecordingAgent()
    scanner = MarketScanner(
        config=config,
        mt5_client=mt5,
        candle_repository=candle_repository,
        historical_ingestion=MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=mt5
        ),
        similarity_service=HistoricalSimilarityService(
            candle_repository=candle_repository,
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
        technical_agents=[window_recorder],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
    )

    await scanner.scan()

    # The technical agent gets its own, larger window; the ML model's
    # feature-vector length (`window_size=20`) is unaffected.
    assert window_recorder.received_candle_count == 250


async def test_scan_blocks_on_zero_equity_account(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=0.0,
            equity=0.0,
            margin=0.0,
            free_margin=0.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    scanner = _make_scanner(session, symbol, mt5, window_size=20)

    result = await scanner.scan()

    assert result.decision.state == "BUY"
    assert "zero_position_size" in result.blocked_reasons
    assert result.position_size is None


async def test_scan_waits_when_evidence_is_too_thin_for_an_actionable_decision(
    session: AsyncSession,
) -> None:
    # Exactly `window_size` candles: enough to pass the history-length
    # check, but not enough for the Historical Research Engine to find
    # even one analogue (needs at least two full windows) — the weak,
    # single-department confidence that results should fall short of the
    # Risk Engine's executable threshold and produce WAIT.
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(20),
        tick=SymbolTick(bid=2000.0, ask=2000.5, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    scanner = _make_scanner(session, symbol, mt5, window_size=20)

    result = await scanner.scan()

    assert result.decision.state == "WAIT"
    assert result.blocked_reasons == ["decision_not_actionable:WAIT"]
    assert result.entry_price is None


async def test_scan_blocks_on_undefined_stop_distance_when_tick_price_is_zero(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=0.0, ask=0.0, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    scanner = _make_scanner(session, symbol, mt5, window_size=20)

    result = await scanner.scan()

    assert result.decision.state == "BUY"
    assert result.blocked_reasons == ["undefined_stop_distance"]
    assert result.position_size is None


async def test_scan_includes_correlation_and_order_flow_votes_when_services_provided(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    instrument = await CorrelatedInstrumentRepository(session).add(
        CorrelatedInstrument(
            name="EURUSD", display_name="Euro vs US Dollar", mt5_symbol="EURUSD", category="fx"
        )
    )
    correlated_prices = [
        CorrelatedPrice(
            instrument_id=instrument.id,
            timeframe="M15",
            timestamp=datetime.fromtimestamp(row["time"], tz=UTC),  # type: ignore[arg-type]
            open=row["close"],
            high=row["close"] + 0.01,  # type: ignore[operator]
            low=row["close"] - 0.01,  # type: ignore[operator]
            close=row["close"],
            source="test_fixture",
        )
        for row in _uptrend_raw_candles(400, slope=1.0, amplitude=0.3)
    ]
    await CorrelatedPriceRepository(session).insert_new(correlated_prices)

    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    candle_repository = CandleRepository(session)
    scanner = MarketScanner(
        config=_scan_config(symbol.id, window_size=20),
        mt5_client=mt5,
        candle_repository=candle_repository,
        historical_ingestion=MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=mt5
        ),
        similarity_service=HistoricalSimilarityService(
            candle_repository=candle_repository,
            similarity_repository=HistoricalSimilarityRepository(session),
        ),
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        correlation_service=CorrelationAnalysisService(
            candle_repository=candle_repository,
            correlated_price_repository=CorrelatedPriceRepository(session),
            instrument_repository=CorrelatedInstrumentRepository(session),
        ),
        order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
    )

    result = await scanner.scan()

    # Both departments ran (even though order flow fell back to synthetic,
    # since the fake MT5 client has no DOM) -> neither should appear in
    # this decision's reduced-confidence factors, unlike macro/news.
    assert not any(
        "correlation" in factor or "order_flow" in factor
        for factor in result.decision.reduced_confidence_factors
    )
    assert any("macro" in factor for factor in result.decision.reduced_confidence_factors)
    assert any("news" in factor for factor in result.decision.reduced_confidence_factors)


async def test_scan_confirms_h4_h1_m5_when_they_agree_with_the_technical_lean(
    session: AsyncSession,
) -> None:
    # Per the "Complete Multi-Timeframe Analysis" production requirement's
    # Intraday role ("Primary: H4 + H1, Confirmation: M15, Entry: M5"):
    # every additional timeframe must be independently checked, not just
    # the M15 primary window -- an all-uptrend H4/H1/M5 read should
    # confirm (not discount) the bullish M15 lean.
    symbol = await _make_symbol(session)
    await _seed_candles(session, symbol.id, 400, slope=1.0, amplitude=0.3)
    # The H4/H1/M5 confirmation windows only see the most recent
    # `_INTRADAY_MTF_CANDLE_COUNT` (60) candles, unlike the 400-candle M15
    # window -- a shallow slope that trends decisively over 400 bars is
    # too flat to classify as trending over just 60, so these need their
    # own steeper series to deterministically read as `bull_trend`.
    mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        raw_candles_by_timeframe={
            "H4": _uptrend_raw_candles(110, slope=10.0, amplitude=0.3),
            "H1": _uptrend_raw_candles(110, slope=10.0, amplitude=0.3),
            "M5": _uptrend_raw_candles(110, slope=10.0, amplitude=0.3),
        },
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    scanner = _make_scanner(session, symbol, mt5, window_size=20)

    result = await scanner.scan()

    assert result.decision.state == "BUY"
    assert any("H4_confirms" in reason for reason in result.multi_timeframe_reasons)
    assert any("H1_confirms" in reason for reason in result.multi_timeframe_reasons)
    assert any("M5_confirms" in reason for reason in result.multi_timeframe_reasons)
    assert not any("counter_trend" in reason for reason in result.multi_timeframe_reasons)


async def test_scan_discounts_confidence_when_higher_timeframes_oppose_the_technical_lean(
    session: AsyncSession,
) -> None:
    # Separate symbols for the two scans -- `list_most_recent` selects by
    # timestamp across the whole symbol's stored history, so sharing one
    # symbol would let the aligned scan's freshly-inserted H4/H1/M5 rows
    # shadow the opposing scan's, regardless of which client inserted them.
    aligned_symbol = await _make_symbol(session, name="XAUUSD_ALIGNED")
    opposing_symbol = await _make_symbol(session, name="XAUUSD_OPPOSING")
    await _seed_candles(session, aligned_symbol.id, 400, slope=1.0, amplitude=0.3)
    await _seed_candles(session, opposing_symbol.id, 400, slope=1.0, amplitude=0.3)
    aligned_mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    opposing_mt5 = _FakeMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        raw_candles_by_timeframe={
            "H4": _downtrend_raw_candles(110, slope=10.0, amplitude=0.3),
            "H1": _downtrend_raw_candles(110, slope=10.0, amplitude=0.3),
            "M5": _downtrend_raw_candles(110, slope=10.0, amplitude=0.3),
        },
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        account=AccountInfo(
            login=1,
            broker="Demo",
            server="Demo-Server",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            is_demo=True,
            trading_allowed=True,
        ),
    )
    aligned_scanner = _make_scanner(session, aligned_symbol, aligned_mt5, window_size=20)
    opposing_scanner = _make_scanner(session, opposing_symbol, opposing_mt5, window_size=20)

    aligned_result = await aligned_scanner.scan()
    opposing_result = await opposing_scanner.scan()

    # `ChiefAIDecision.confidence_pct` is recomputed by `evaluate()` from
    # raw department votes and is unaffected by the multi-timeframe
    # discount (which only narrows the Risk Engine's own approval gate,
    # per `TradeApprovalRequest.confidence_pct=pre_confidence_pct`) -- the
    # discount's real, observable effect is whether the trade clears that
    # gate at all.
    assert sum("counter_trend" in reason for reason in opposing_result.multi_timeframe_reasons) == 3
    assert aligned_result.decision.state == "BUY"
    assert opposing_result.decision.state == "WAIT"
