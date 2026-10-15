"""Integration tests for `LiveTradingLoop` (Phase 20 "Live Loop")."""

from __future__ import annotations

import calendar
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.execution.magic_number import compute_magic_number
from src.core.execution.mt5_client import (
    AccountInfo,
    OpenPosition,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderRequest,
    OrderResult,
    SymbolTick,
)
from src.core.notifications.telegram_client import TelegramNotifier
from src.engines.micro_scalping_engine.service import MicroScalpingAnalysisService
from src.engines.order_flow_engine.service import OrderFlowAnalysisService
from src.engines.risk_engine.exposure import ExposureLimits
from src.engines.risk_engine.session_schedule import SessionSchedule, parse_session_schedule
from src.engines.scalping_engine.service import ScalpingAnalysisService
from src.engines.shakky_engine.service import ShakkyAnalysisService
from src.engines.swing_engine.service import SwingAnalysisService
from src.models.correlated_instrument import CorrelatedInstrument
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.system_log_repository import SystemLogRepository
from src.repositories.trade_repository import TradeRepository
from src.services.scheduler.live_loop import LiveTradingLoop
from src.workflows.market_update.pipeline import MarketScanConfig
from tests.integration.workflows.test_market_update_pipeline import (
    _bullish_classification_model,
    _bullish_regression_model,
    _BullishAgent,
    _FakeMT5Client,
    _seed_candles,
    _uptrend_raw_candles,
)

pytestmark = pytest.mark.asyncio


def _committing_session_factory(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Build a `session_factory` that commits on clean exit, like production.

    Mirrors `src.database.postgres.session.get_session`'s contract, which
    `LiveTradingLoop` relies on in production; the raw `async_sessionmaker`
    alone does not commit.
    """
    raw_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    @asynccontextmanager
    async def commit_on_exit() -> AsyncIterator[AsyncSession]:
        async with raw_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return commit_on_exit


class _ExecutingMT5Client(_FakeMT5Client):
    """The shared scan-test fake doesn't implement `place_order`; this one does.

    Also returns a strongly bid-skewed DOM snapshot, so the Order Flow
    Engine (always wired into `LiveTradingLoop`, per Phase 21) reads as
    confidently bullish here rather than falling back to the more
    conservatively-capped synthetic path — keeping this test's "clean
    uptrend -> BUY" scenario reliable now that a fourth department vote
    is always part of the confidence average.
    """

    async def place_order(self, request: OrderRequest) -> OrderResult:
        return OrderResult(success=True, broker_ticket="9100", filled_price=request.price)

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        # Overwhelming bid-side volume and no wall (uniform volume per
        # side) so the only signal is a near-maximal imbalance, rather
        # than diluting it with a lower-weighted wall signal.
        return OrderBookSnapshot(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            levels=[
                OrderBookLevel(price=2050.0, volume=1000.0, side="bid"),
                OrderBookLevel(price=2049.9, volume=1000.0, side="bid"),
                OrderBookLevel(price=2050.3, volume=1.0, side="ask"),
                OrderBookLevel(price=2050.4, volume=1.0, side="ask"),
            ],
        )


class _FakeTelegramNotifier(TelegramNotifier):
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str) -> bool:
        self.sent_messages.append((chat_id, text))
        return True


def _m1_burst_raw_candles(count: int = 60) -> list[dict[str, object]]:
    """Flat M1 baseline followed by a sharp 3-bar bullish burst."""
    base_epoch = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
    candles: list[dict[str, object]] = []
    for index in range(count - 3):
        candles.append(
            {
                "time": base_epoch + index * 60,
                "open": 2000.0,
                "high": 2000.2,
                "low": 1999.8,
                "close": 2000.0,
                "tick_volume": 100.0,
                "spread": 20,
            }
        )
    burst_bars = [
        (2000.0, 2003.0, 1999.9, 2002.5),
        (2002.5, 2005.5, 2002.4, 2005.0),
        (2005.0, 2008.5, 2004.9, 2008.0),
    ]
    for offset, (open_, high, low, close) in enumerate(burst_bars):
        index = count - 3 + offset
        candles.append(
            {
                "time": base_epoch + index * 60,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 150.0,
                "spread": 20,
            }
        )
    return candles


def _h1_uptrend_raw_candles(count: int = 30) -> list[dict[str, object]]:
    base_epoch = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
    return [
        {
            "time": base_epoch + index * 3600,
            "open": 2000.0 + index * 5.0,
            "high": 2000.0 + index * 5.0 + 1.0,
            "low": 2000.0 + index * 5.0 - 1.0,
            "close": 2000.0 + index * 5.0,
            "tick_volume": 100.0,
            "spread": 20,
        }
        for index in range(count)
    ]


class _ScalpingMT5Client(_ExecutingMT5Client):
    """Serves distinct fixtures per timeframe so the primary scan (M15,
    starved of history) stays WAIT while the Scalping Engine (M1/H1) sees
    a strong, deterministic bullish burst -- isolating the scalp-only
    trade-style-routing path from the already-covered primary path.
    """

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        if timeframe == "M1":
            return _m1_burst_raw_candles()[-count:]
        if timeframe == "H1":
            return _h1_uptrend_raw_candles()[-count:]
        return await super().get_candles(symbol, timeframe, count)


class _SwingMT5Client(_ExecutingMT5Client):
    """Serves a strong D1/W1 uptrend for the Swing Engine, M15 starved.

    Isolates the swing-only execution path from the already-covered
    primary (Intraday) path, mirroring `_ScalpingMT5Client`'s own
    per-timeframe fixture split.
    """

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        if timeframe in ("D1", "W1"):
            return _uptrend_raw_candles(max(count, 60), slope=1.0, amplitude=0.3)[-count:]
        return await super().get_candles(symbol, timeframe, count)


def _shakky_m5_uptrend_raw_candles(
    count: int = 120, *, start: float = 1900.0
) -> list[dict[str, object]]:
    """An accelerating M5 uptrend, matching `ShakkyAnalysisService`'s own
    unit-test fixture (`tests/unit/engines/shakky_engine/test_service.py`
    `_strong_uptrend`) -- a linear ramp settles MACD's histogram to
    exactly 0 (filtered out as "no signal"), so this uses the same
    quadratic acceleration to reliably clear Shakky's 3-confirmation
    minimum (EMA trend stack, MACD, ADX all agree on a clean, accelerating
    trend).
    """
    base_epoch = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
    candles: list[dict[str, object]] = []
    for index in range(count):
        close = start + index * index * 0.05
        candles.append(
            {
                "time": base_epoch + index * 300,
                "open": close,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "tick_volume": 100.0,
                "spread": 20,
            }
        )
    return candles


class _ShakkyMT5Client(_ExecutingMT5Client):
    """Serves a strong M5 uptrend for the Shakky Engine, other timeframes starved.

    Isolates the Shakky-only execution path from the already-covered
    primary/Scalping/Swing paths, mirroring `_ScalpingMT5Client`'s/
    `_SwingMT5Client`'s own per-timeframe fixture split.
    """

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        if timeframe == "M5":
            return _shakky_m5_uptrend_raw_candles()[-count:]
        return await super().get_candles(symbol, timeframe, count)


class _AllEnginesMT5Client(_ExecutingMT5Client):
    """Serves a qualifying setup for all three engines in the same cycle.

    M15 has enough history for the primary engine, M1/H1 carry a bullish
    scalp setup, and D1/W1 carry a bullish swing setup.
    """

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        if timeframe == "M1":
            return _m1_burst_raw_candles()[-count:]
        if timeframe == "H1":
            return _h1_uptrend_raw_candles()[-count:]
        if timeframe in ("D1", "W1"):
            return _uptrend_raw_candles(max(count, 60), slope=1.0, amplitude=0.3)[-count:]
        return await super().get_candles(symbol, timeframe, count)


def _exposure_limits() -> ExposureLimits:
    return ExposureLimits(
        max_total_exposure_pct=5.0,
        max_instrument_exposure_pct=5.0,
        max_correlated_exposure_pct=7.5,
        max_session_exposure_pct=10.0,
        max_daily_exposure_pct=10.0,
    )


def _session_schedule_always_within_window(*, weekend_approaching: bool) -> SessionSchedule:
    """Build a schedule guaranteed to be "within the pre-close window" right now.

    Avoids real-clock flakiness: the close time is always a minute from
    now with a 24-hour warning window, so "now" is always inside it
    regardless of when the test actually runs.
    """
    now = datetime.now(UTC)
    close = now + timedelta(minutes=1)
    weekday_name = calendar.day_name[now.weekday() if weekend_approaching else now.weekday() - 1]
    return parse_session_schedule(
        daily_close_utc=f"{close.hour:02d}:{close.minute:02d}",
        weekly_close_weekday=weekday_name.lower(),
        pre_close_warning_minutes=1440,
    )


def _scan_config(symbol: Symbol) -> MarketScanConfig:
    return MarketScanConfig(
        symbol_id=symbol.id,
        mt5_symbol="XAUUSD",
        timeframe="M15",
        window_size=20,
        risk_per_trade_pct=0.5,
        atr_multiplier_for_stop=1.5,
        max_spread_points=350.0,
        confidence_threshold=1.0,
        exposure_limits=_exposure_limits(),
        account_type="demo",
        expected_account=None,
        live_trading_approved=False,
        strategy_name="xauusd_m15_live",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )


async def test_run_once_executes_a_signal_when_the_scan_is_actionable(engine: AsyncEngine) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await setup_session.commit()

    mt5 = _ExecutingMT5Client(
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 1
    assert open_trades[0].direction == "buy"
    assert len(telegram.sent_messages) == 1
    assert open_trades[0].department_votes is not None
    assert "technical" in open_trades[0].department_votes
    assert "order_flow" in open_trades[0].department_votes
    assert open_trades[0].department_votes["order_flow"]["bias"] == "bullish"
    assert open_trades[0].quality_score is not None
    assert 0.0 <= open_trades[0].quality_score <= 100.0
    assert open_trades[0].risk_score is not None
    assert 0.0 <= open_trades[0].risk_score <= 100.0


async def test_run_once_suppresses_a_signal_when_max_positions_is_reached(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                magic_number=1,
                broker_ticket="8000",
            )
        )
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        runtime_settings.max_positions = 1
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    mt5 = _ExecutingMT5Client(
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 1
    assert open_trades[0].broker_ticket == "8000"
    assert telegram.sent_messages == []


async def test_run_once_ignores_max_positions_when_demo_learning_mode_is_enabled(
    engine: AsyncEngine,
) -> None:
    # Per the "Demo Learning Mode" production requirement: "allow parallel
    # trades... maximum statistically useful trading experience" -- the
    # same setup as `test_run_once_suppresses_a_signal_when_max_positions_
    # is_reached` (one pre-existing open position at the portfolio cap)
    # must instead open a second position once this mode is enabled.
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                magic_number=1,
                broker_ticket="8000",
            )
        )
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        runtime_settings.max_positions = 1
        runtime_settings.demo_learning_mode_enabled = True
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    mt5 = _ExecutingMT5Client(
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 2
    assert {trade.broker_ticket for trade in open_trades} != {"8000"}


async def test_run_once_skips_the_scan_but_keeps_monitoring_when_paused(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                magic_number=1,
                broker_ticket="8100",
            )
        )
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        runtime_settings.paused = True
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    mt5 = _ExecutingMT5Client(
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
        positions=[
            OpenPosition(
                ticket="8100",
                symbol="XAUUSD",
                direction="buy",
                volume=1.0,
                entry_price=2000.0,
                current_price=2050.0,
                stop_loss=1990.0,
                take_profit=None,
                profit=50.0,
                magic_number=1,
                opened_at=datetime.now(UTC),
            )
        ],
    )
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    # No new signal executed while paused (still just the pre-seeded position).
    assert len(open_trades) == 1
    assert open_trades[0].broker_ticket == "8100"


async def test_run_once_never_raises_when_a_cycle_fails(engine: AsyncEngine) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    class _BrokenMT5Client(_FakeMT5Client):
        async def get_symbol_tick(self, symbol: str) -> SymbolTick:
            raise RuntimeError("terminal disconnected")

    mt5 = _BrokenMT5Client(
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
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=_FakeTelegramNotifier(),
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()  # must not raise despite the broken MT5 client


async def test_run_once_does_not_execute_when_the_scan_is_not_actionable(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # Too little history for even one full analysis window: the scan
    # itself returns WAIT before any trade parameters are computed.
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert open_trades == []
    # No trade executed, but the "No Trade Explanation" digest still fires
    # for the WAIT decision.
    assert len(telegram.sent_messages) == 1
    assert "Нет сделки" in telegram.sent_messages[0][1]


async def test_run_once_executes_a_scalp_trade_when_only_the_scalping_engine_signals(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # Too little M15 history for the primary engine (stays WAIT), but a
    # deterministic bullish M1 burst plus a bullish H1 trend for the
    # independent Scalping Engine to act on instead.
    mt5 = _ScalpingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 1
    assert open_trades[0].direction == "buy"
    expected_scalp_magic_number = compute_magic_number(
        f"{_scan_config(symbol).strategy_name}_scalp", _scan_config(symbol).strategy_version
    )
    assert open_trades[0].magic_number == expected_scalp_magic_number
    assert open_trades[0].department_votes is not None
    assert open_trades[0].department_votes["scalping_engine"]["bias"] == "bullish"
    assert open_trades[0].quality_score is not None
    # One signal message for the executed scalp trade, plus the "No Trade
    # Explanation" digest for the primary engine's own WAIT decision.
    assert len(telegram.sent_messages) == 2
    assert any("Нет сделки" in message for _, message in telegram.sent_messages)

    # Per the "Why No Trade" production requirement: Scalping's own cycle
    # outcome is persisted independently of the primary engine's own
    # snapshot, whether or not it went on to execute.
    async with raw_session_factory() as check_session:
        scalping_snapshots = await SystemLogRepository(check_session).list_by_source(
            "scalping_scan_snapshot", limit=5
        )
    assert len(scalping_snapshots) == 1
    assert scalping_snapshots[0].context["state"] == "trade_found"
    assert scalping_snapshots[0].context["confidence_pct"] > 0
    assert scalping_snapshots[0].context["trade_quality_score"] is not None
    assert scalping_snapshots[0].context["reasons"] == []


async def test_run_once_executes_a_swing_trade_when_only_the_swing_engine_signals(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # Too little M15 history for the primary engine (stays WAIT), but a
    # deterministic bullish D1/W1 uptrend for the independent Swing
    # Engine to act on instead.
    mt5 = _SwingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        swing_service=SwingAnalysisService(
            technical_agents=[_BullishAgent()],
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 1
    assert open_trades[0].direction == "buy"
    expected_swing_magic_number = compute_magic_number(
        f"{_scan_config(symbol).strategy_name}_swing", _scan_config(symbol).strategy_version
    )
    assert open_trades[0].magic_number == expected_swing_magic_number
    assert open_trades[0].department_votes is not None
    assert open_trades[0].department_votes["swing_engine"]["bias"] == "bullish"
    assert open_trades[0].quality_score is not None
    # One signal message for the executed swing trade, plus the "No Trade
    # Explanation" digest for the primary engine's own WAIT decision.
    assert len(telegram.sent_messages) == 2
    assert any("Нет сделки" in message for _, message in telegram.sent_messages)


async def test_run_once_swing_snapshot_honestly_shows_no_trade_when_quality_blocks_it(
    engine: AsyncEngine,
) -> None:
    """Regression test for a production incident: the snapshot used to
    report "trade_found" purely from a confidence-qualifying signal,
    before the separate `quality_score < min_trade_quality_score` check
    could veto execution right after -- the dashboard then showed "сделка
    найдена" ("trade found") for a signal that was never actually going
    to open, with the real reason only ever reaching a log line. The
    snapshot must show the same verdict the engine actually acts on.
    """
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        # Deliberately above any quality score this fixture's signal can
        # reach, so execution is blocked purely on quality -- confidence
        # itself still qualifies (same fixture as the happy-path test).
        runtime_settings.min_trade_quality_score = 99.0
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    mt5 = _SwingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        swing_service=SwingAnalysisService(
            technical_agents=[_BullishAgent()],
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 0

    async with raw_session_factory() as check_session:
        swing_snapshots = await SystemLogRepository(check_session).list_by_source(
            "swing_scan_snapshot", limit=5
        )
    assert len(swing_snapshots) == 1
    assert swing_snapshots[0].context["state"] == "no_trade"
    assert any(
        "trade_quality_score_below_threshold" in reason
        for reason in swing_snapshots[0].context["reasons"]
    )


async def test_run_once_executes_a_shakky_trade_when_only_the_shakky_engine_signals(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # Too little M15 history for the primary engine (stays WAIT), but a
    # deterministic accelerating M5 uptrend for the independent Shakky
    # ("Classic M5 Strategy") Engine to act on instead.
    mt5 = _ShakkyMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        shakky_service=ShakkyAnalysisService(),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 1
    assert open_trades[0].direction == "buy"
    expected_shakky_magic_number = compute_magic_number(
        f"{_scan_config(symbol).strategy_name}_shakky", _scan_config(symbol).strategy_version
    )
    assert open_trades[0].magic_number == expected_shakky_magic_number
    assert open_trades[0].volume == pytest.approx(0.01)
    assert open_trades[0].department_votes is not None
    assert open_trades[0].department_votes["shakky_engine"]["bias"] == "bullish"
    # Per Shakky's own spec ("must NOT use... the Trade Quality Engine"):
    # never scored by `compute_trade_quality`, so these stay honestly
    # None rather than a fabricated placeholder.
    assert open_trades[0].quality_score is None
    assert open_trades[0].risk_score is None
    assert open_trades[0].confidence_pct is None
    # One signal message for the executed Shakky trade, plus the "No
    # Trade Explanation" digest for the primary engine's own WAIT decision.
    assert len(telegram.sent_messages) == 2
    assert any("Shakky" in message for _, message in telegram.sent_messages)

    # Per the "Why No Trade" production requirement: Shakky's own cycle
    # outcome is persisted independently of the primary engine's own
    # snapshot, whether or not it went on to execute.
    async with raw_session_factory() as check_session:
        shakky_snapshots = await SystemLogRepository(check_session).list_by_source(
            "shakky_scan_snapshot", limit=5
        )
    assert len(shakky_snapshots) == 1
    assert shakky_snapshots[0].context["state"] == "trade_found"
    assert shakky_snapshots[0].context["confirmation_count"] >= 3


async def test_run_once_still_records_shakky_snapshot_when_auto_trading_disabled(
    engine: AsyncEngine,
) -> None:
    """Regression test for a production incident: `auto_trading_enabled`
    used to gate every independent engine's own analysis step, not just
    its execution -- the moment it was turned off, Shakky's own "why no
    trade"/"trade found" snapshot silently stopped updating entirely and
    stayed frozen on whatever it last reported (observed stuck for two
    months in production). Analysis and snapshot recording must always
    run; only the final order placement may be suppressed.
    """
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        runtime_settings.auto_trading_enabled = False
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    mt5 = _ShakkyMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        shakky_service=ShakkyAnalysisService(),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 0

    async with raw_session_factory() as check_session:
        shakky_snapshots = await SystemLogRepository(check_session).list_by_source(
            "shakky_scan_snapshot", limit=5
        )
    assert len(shakky_snapshots) == 1
    assert shakky_snapshots[0].context["state"] == "trade_found"
    assert shakky_snapshots[0].context["confirmation_count"] >= 3


async def test_run_once_shakky_does_not_reopen_when_it_already_has_an_open_position(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        expected_shakky_magic_number = compute_magic_number(
            f"{_scan_config(symbol).strategy_name}_shakky", _scan_config(symbol).strategy_version
        )
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=0.01,
                entry_price=1900.0,
                stop_loss=1890.0,
                magic_number=expected_shakky_magic_number,
                broker_ticket="8500",
            )
        )
        await setup_session.commit()

    # Startup reconciliation closes any journaled "open" trade MT5 does not
    # also report as an open position, so the pre-seeded Shakky trade
    # must be mirrored here too.
    existing_shakky_position = OpenPosition(
        ticket="8500",
        symbol="XAUUSD",
        direction="buy",
        volume=0.01,
        entry_price=1900.0,
        stop_loss=1890.0,
        take_profit=None,
        current_price=1900.0,
        profit=0.0,
        magic_number=expected_shakky_magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _ShakkyMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        positions=[existing_shakky_position],
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        shakky_service=ShakkyAnalysisService(),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    shakky_trades = [t for t in open_trades if t.magic_number == expected_shakky_magic_number]
    assert len(shakky_trades) == 1
    assert shakky_trades[0].broker_ticket == "8500"


async def test_run_once_executes_all_three_engines_simultaneously_when_each_qualifies(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await setup_session.commit()

    # Per the "Multi Strategy" production requirement: every engine that
    # independently qualifies this cycle executes -- never limited to
    # picking only one. `_AllEnginesMT5Client` serves a qualifying M15
    # primary window, M1/H1 bullish scalp setup, and D1/W1 bullish swing
    # setup, all in the same cycle.
    mt5 = _AllEnginesMT5Client(
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=0.5,
        ),
        swing_service=SwingAnalysisService(
            technical_agents=[_BullishAgent()],
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 3
    magic_numbers = {trade.magic_number for trade in open_trades}
    assert len(magic_numbers) == 3  # each engine journaled under its own distinct magic number
    assert len(telegram.sent_messages) == 3


async def test_run_once_swing_still_opens_when_scalping_already_has_an_open_position(
    engine: AsyncEngine,
) -> None:
    """Per "Parallel Strategy Execution": one strategy's own open position
    must never block a different strategy's independent opportunity --
    only Scalping (which already has one) is prevented from reopening;
    Intraday and Swing, which have no open position of their own, still execute.
    """
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        scalping_magic_number = compute_magic_number(
            f"{_scan_config(symbol).strategy_name}_scalp", _scan_config(symbol).strategy_version
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                magic_number=scalping_magic_number,
                broker_ticket="7000",
            )
        )
        await setup_session.commit()

    # Startup reconciliation closes any journaled "open" trade MT5 does not
    # also report as an open position, so the pre-seeded Scalping trade
    # must be mirrored here too.
    existing_scalping_position = OpenPosition(
        ticket="7000",
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=None,
        current_price=2050.0,
        profit=50.0,
        magic_number=scalping_magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _AllEnginesMT5Client(
        raw_candles=_uptrend_raw_candles(400, slope=1.0, amplitude=0.3),
        tick=SymbolTick(bid=2050.0, ask=2050.3, timestamp=datetime.now(UTC)),
        positions=[existing_scalping_position],
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=0.5,
        ),
        swing_service=SwingAnalysisService(
            technical_agents=[_BullishAgent()],
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    # The pre-seeded Scalping trade, plus one new Intraday and one new
    # Swing trade -- Scalping does not reopen a second position of its own.
    assert len(open_trades) == 3
    scalping_trades = [t for t in open_trades if t.magic_number == scalping_magic_number]
    assert len(scalping_trades) == 1
    assert scalping_trades[0].broker_ticket == "7000"


async def test_run_once_exposure_limit_blocks_a_new_trade_even_with_no_position_open(
    engine: AsyncEngine,
) -> None:
    """Per "Parallel Strategy Execution": "Chief AI must evaluate total
    portfolio exposure before approving additional positions" -- this
    must hold for Scalping too, not only the primary engine. An existing
    MT5 position that already consumes far more than the configured
    exposure ceiling blocks a new Scalping trade even though Scalping has
    no open position of its own.
    """
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        await setup_session.commit()

    # 50 units at a $100 stop distance risks $5,000 of a $10,000 account:
    # 50% exposure, far past the 5% ceiling in `_exposure_limits()` --
    # any further trade must be rejected regardless of its own size.
    existing_position = OpenPosition(
        ticket="6000",
        symbol="XAUUSD",
        direction="buy",
        volume=50.0,
        entry_price=2000.0,
        stop_loss=1900.0,
        take_profit=None,
        current_price=2050.0,
        profit=2500.0,
        magic_number=999,
        opened_at=datetime.now(UTC),
    )
    mt5 = _ScalpingMT5Client(
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
        positions=[existing_position],
    )
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert open_trades == []


async def test_run_once_trades_nothing_when_both_engines_are_quiet(engine: AsyncEngine) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # Too little history for every timeframe (primary M15 and Scalping
    # Engine's own M1/H1 alike): both engines stay quiet this cycle.
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert open_trades == []
    # No trade executed, but the "No Trade Explanation" digest still fires
    # for the primary engine's own WAIT decision.
    assert len(telegram.sent_messages) == 1
    assert "Нет сделки" in telegram.sent_messages[0][1]

    # Per the "Why No Trade" production requirement: even a quiet cycle
    # with no signal at all records Scalping's own reason, not silence.
    async with raw_session_factory() as check_session:
        scalping_snapshots = await SystemLogRepository(check_session).list_by_source(
            "scalping_scan_snapshot", limit=5
        )
    assert len(scalping_snapshots) == 1
    assert scalping_snapshots[0].context["state"] == "no_trade"
    assert scalping_snapshots[0].context["confidence_pct"] == 0
    assert scalping_snapshots[0].context["reasons"] != []


async def test_run_once_refreshes_enabled_correlated_instruments(engine: AsyncEngine) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        instrument = await CorrelatedInstrumentRepository(setup_session).add(
            CorrelatedInstrument(
                name="EURUSD",
                display_name="Euro vs US Dollar",
                mt5_symbol="EURUSD",
                category="fx",
                is_enabled=True,
            )
        )
        await setup_session.commit()

    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=_FakeTelegramNotifier(),
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        prices = await CorrelatedPriceRepository(check_session).list_most_recent(
            instrument.id, "M15", count=10
        )
    assert len(prices) > 0


class _BreakevenThenBrokenMT5Client(_FakeMT5Client):
    """Confirms position monitoring and the market scan commit independently.

    Per an institutional audit finding: running both phases in one shared
    session meant a market-scan-phase failure would roll back an
    *already-succeeded* breakeven-move write too (the same failure class
    already found and fixed once this session for a Telegram notification
    error). `modify_order` here succeeds; `get_symbol_tick` (used early in
    the market scan) always raises.
    """

    async def modify_order(
        self,
        broker_ticket: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        return OrderResult(success=True, broker_ticket=broker_ticket, filled_price=stop_loss)

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        raise RuntimeError("terminal disconnected")


async def test_run_once_keeps_a_breakeven_move_even_when_the_market_scan_fails(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        magic_number = compute_magic_number(config.strategy_name, config.strategy_version)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                take_profit=2020.0,
                magic_number=magic_number,
                broker_ticket="9100",
            )
        )
        await setup_session.commit()

    # 1R risk distance is 10.0; +10.0 in favor meets the 1.0 R trigger.
    breakeven_position = OpenPosition(
        ticket="9100",
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2010.0,
        profit=100.0,
        magic_number=magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _BreakevenThenBrokenMT5Client(
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
        positions=[breakeven_position],
    )
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=_FakeTelegramNotifier(),
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()  # must not raise despite the market-scan phase failing

    async with raw_session_factory() as check_session:
        stored = await TradeRepository(check_session).get_by_broker_ticket("9100")
    assert stored is not None
    assert stored.breakeven_moved is True
    assert stored.stop_loss == pytest.approx(2000.0)


async def test_startup_reconciliation_never_raises_when_clean_or_mismatched(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # No journal row at all for this broker-open position -> a genuine
    # mismatch; the check must still complete without raising.
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
        positions=[
            OpenPosition(
                ticket="9200",
                symbol="XAUUSD",
                direction="buy",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
                current_price=2005.0,
                profit=5.0,
                magic_number=1,
                opened_at=datetime.now(UTC),
            )
        ],
    )
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=_FakeTelegramNotifier(),
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop._check_startup_reconciliation()  # noqa: SLF001 - only testable entry point


async def test_startup_reconciliation_completes_when_positions_match_the_journal(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                magic_number=compute_magic_number(config.strategy_name, config.strategy_version),
                broker_ticket="9300",
            )
        )
        await setup_session.commit()

    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
        positions=[
            OpenPosition(
                ticket="9300",
                symbol="XAUUSD",
                direction="buy",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
                current_price=2005.0,
                profit=5.0,
                magic_number=1,
                opened_at=datetime.now(UTC),
            )
        ],
    )
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=_FakeTelegramNotifier(),
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop._check_startup_reconciliation()  # noqa: SLF001 - only testable entry point


async def test_pre_close_report_sent_for_open_positions_within_the_window(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        magic_number = compute_magic_number(config.strategy_name, config.strategy_version)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                take_profit=2020.0,
                magic_number=magic_number,
                broker_ticket="9400",
            )
        )
        await setup_session.commit()

    position = OpenPosition(
        ticket="9400",
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2005.0,
        profit=5.0,
        magic_number=magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
        positions=[position],
    )
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        session_schedule=_session_schedule_always_within_window(weekend_approaching=False),
    )

    await loop.run_once()

    pre_close_messages = [
        msg for _, msg in telegram.sent_messages if "Перед закрытием рынка" in msg
    ]
    assert len(pre_close_messages) == 1
    assert "риск гэпа" not in pre_close_messages[0].lower()


async def test_pre_close_report_includes_weekend_risk_on_the_weekly_close_day(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        magic_number = compute_magic_number(config.strategy_name, config.strategy_version)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                take_profit=2020.0,
                magic_number=magic_number,
                broker_ticket="9401",
            )
        )
        await setup_session.commit()

    position = OpenPosition(
        ticket="9401",
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2005.0,
        profit=5.0,
        magic_number=magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
        positions=[position],
    )
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        session_schedule=_session_schedule_always_within_window(weekend_approaching=True),
    )

    await loop.run_once()

    pre_close_messages = [
        msg for _, msg in telegram.sent_messages if "Перед закрытием рынка" in msg
    ]
    assert len(pre_close_messages) == 1
    assert "риск гэпа" in pre_close_messages[0].lower()


async def test_pre_close_report_does_not_send_twice_the_same_day(engine: AsyncEngine) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        magic_number = compute_magic_number(config.strategy_name, config.strategy_version)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                take_profit=2020.0,
                magic_number=magic_number,
                broker_ticket="9402",
            )
        )
        await setup_session.commit()

    position = OpenPosition(
        ticket="9402",
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2005.0,
        profit=5.0,
        magic_number=magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
        positions=[position],
    )
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        session_schedule=_session_schedule_always_within_window(weekend_approaching=False),
    )

    await loop.run_once()
    await loop.run_once()

    pre_close_messages = [
        msg for _, msg in telegram.sent_messages if "Перед закрытием рынка" in msg
    ]
    assert len(pre_close_messages) == 1


async def test_pre_close_report_disabled_when_no_schedule_configured(engine: AsyncEngine) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        magic_number = compute_magic_number(config.strategy_name, config.strategy_version)
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=1.0,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                take_profit=2020.0,
                magic_number=magic_number,
                broker_ticket="9403",
            )
        )
        await setup_session.commit()

    position = OpenPosition(
        ticket="9403",
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2005.0,
        profit=5.0,
        magic_number=magic_number,
        opened_at=datetime.now(UTC),
    )
    mt5 = _ExecutingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
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
        positions=[position],
    )
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )

    await loop.run_once()

    assert all("Перед закрытием рынка" not in msg for _, msg in telegram.sent_messages)


async def test_run_once_skips_intraday_when_disabled_but_other_engines_still_run(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await _seed_candles(setup_session, symbol.id, 400, slope=1.0, amplitude=0.3)
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        runtime_settings.intraday_enabled = False
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    # Per the "User Configuration" production requirement: any engine
    # combination is selectable, including excluding Intraday entirely
    # (e.g. "Scalping only" / "Scalping + Swing").
    class _AllEnginesMT5Client(_ExecutingMT5Client):
        async def get_candles(
            self, symbol: str, timeframe: str, count: int
        ) -> list[dict[str, object]]:
            if timeframe == "M1":
                return _m1_burst_raw_candles()[-count:]
            if timeframe == "H1":
                return _h1_uptrend_raw_candles()[-count:]
            if timeframe in ("D1", "W1"):
                return _uptrend_raw_candles(max(count, 60), slope=1.0, amplitude=0.3)[-count:]
            return await super().get_candles(symbol, timeframe, count)

    mt5 = _AllEnginesMT5Client(
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=0.5,
        ),
        swing_service=SwingAnalysisService(
            technical_agents=[_BullishAgent()],
            confidence_threshold=0.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    # Only Scalping + Swing executed -- the primary (Intraday) engine's own
    # qualifying signal this cycle was skipped, not blocked by exposure.
    assert len(open_trades) == 2
    strategy_suffixes = {"scalping_engine", "swing_engine"} & {
        name for trade in open_trades for name in (trade.department_votes or {})
    }
    assert strategy_suffixes == {"scalping_engine", "swing_engine"}


async def test_run_once_applies_the_scalping_confidence_threshold_override(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        settings_repository = RuntimeSettingsRepository(setup_session)
        runtime_settings = await settings_repository.get_or_create_default()
        # Per the "User Configuration" production requirement: each
        # engine's confidence threshold is independently adjustable, down
        # to 0% -- confirms the override actually reaches the engine
        # (the constructor's own high default would otherwise WAIT).
        runtime_settings.scalping_confidence_threshold = 0.0
        await settings_repository.add(runtime_settings)
        await setup_session.commit()

    mt5 = _ScalpingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        scalping_service=ScalpingAnalysisService(
            # A constructor default above the maximum possible confidence
            # (1.0) can never clear on its own -- any executed trade below
            # must have come from the live per-cycle override, not this
            # constructed default.
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5),
            confidence_threshold=1.5,
        ),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    assert len(open_trades) == 1
    assert open_trades[0].department_votes is not None
    assert "scalping_engine" in open_trades[0].department_votes


class _MicroScalpingMT5Client(_ExecutingMT5Client):
    """Serves a qualifying M1 momentum burst + M5 uptrend for Micro Scalping.

    Reuses Scalping's own `_m1_burst_raw_candles` (a proven momentum-burst
    fixture, `check_momentum`'s own gate) and Shakky's own
    `_shakky_m5_uptrend_raw_candles` (Micro Scalping's inherited entry
    logic, primary M5 timeframe) -- every other timeframe (notably the
    primary M15 engine's own) stays starved via `super().get_candles`'s
    tiny default `raw_candles`, isolating this path exactly like
    `_ShakkyMT5Client` already does for Shakky.
    """

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        if timeframe == "M1":
            return _m1_burst_raw_candles()[-count:]
        if timeframe == "M5":
            return _shakky_m5_uptrend_raw_candles()[-count:]
        return await super().get_candles(symbol, timeframe, count)


async def test_run_once_executes_a_micro_scalping_trade_when_only_it_signals(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        await setup_session.commit()

    # 13:00 UTC on a Monday -- inside the London/New York overlap, so
    # Micro Scalping's own liquidity-session gate passes; a 0.02-wide
    # spread stays well under its own 5-point default cap.
    mt5 = _MicroScalpingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(
            bid=2007.99, ask=2008.01, timestamp=datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
        ),
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
    telegram = _FakeTelegramNotifier()
    shakky_service = ShakkyAnalysisService()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        shakky_service=shakky_service,
        micro_scalping_service=MicroScalpingAnalysisService(shakky_service=shakky_service),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    micro_scalping_trades = [
        trade
        for trade in open_trades
        if trade.department_votes and "micro_scalping_engine" in trade.department_votes
    ]
    assert len(micro_scalping_trades) == 1
    trade = micro_scalping_trades[0]
    assert trade.direction == "buy"
    expected_magic_number = compute_magic_number(
        f"{_scan_config(symbol).strategy_name}_micro_scalp", _scan_config(symbol).strategy_version
    )
    assert trade.magic_number == expected_magic_number
    # Default lot mode is "manual" with no override -- the engine's own
    # small constructed default fixed lot.
    assert trade.volume == pytest.approx(0.05)
    # Per this engine's own spec: exit is managed entirely by
    # `_manage_micro_scalping_positions` every cycle, never a fixed
    # broker-side take profit.
    assert trade.take_profit is None
    assert trade.department_votes is not None
    assert trade.department_votes["micro_scalping_engine"]["bias"] == "bullish"
    assert trade.entry_trend_confidence_score is not None
    assert any("Микро-скальп" in message for _, message in telegram.sent_messages)

    async with raw_session_factory() as check_session:
        snapshots = await SystemLogRepository(check_session).list_by_source(
            "micro_scalping_scan_snapshot", limit=5
        )
    assert len(snapshots) == 1
    assert snapshots[0].context["state"] == "trade_found"


async def test_run_once_micro_scalping_does_not_reopen_when_it_already_has_an_open_position(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        expected_magic_number = compute_magic_number(
            f"{_scan_config(symbol).strategy_name}_micro_scalp",
            _scan_config(symbol).strategy_version,
        )
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=0.05,
                entry_price=2000.0,
                stop_loss=1990.0,
                magic_number=expected_magic_number,
                broker_ticket="9200",
            )
        )
        await setup_session.commit()

    mt5 = _MicroScalpingMT5Client(
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(
            bid=2007.99, ask=2008.01, timestamp=datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
        ),
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
        positions=[
            OpenPosition(
                ticket="9200",
                symbol="XAUUSD",
                direction="buy",
                volume=0.05,
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=None,
                current_price=2000.0,
                profit=0.0,
                magic_number=expected_magic_number,
                opened_at=datetime.now(UTC),
            )
        ],
    )
    telegram = _FakeTelegramNotifier()
    shakky_service = ShakkyAnalysisService()
    loop = LiveTradingLoop(
        scan_config=_scan_config(symbol),
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        shakky_service=shakky_service,
        micro_scalping_service=MicroScalpingAnalysisService(shakky_service=shakky_service),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        open_trades = await TradeRepository(check_session).list_by_status("open", limit=10)
    micro_scalping_trades = [
        trade
        for trade in open_trades
        if trade.department_votes and "micro_scalping_engine" in trade.department_votes
    ]
    assert len(micro_scalping_trades) == 0


class _RaisesForPrimaryMagicNumberMT5Client(_ExecutingMT5Client):
    """Simulates a transient MT5 read failure for one specific magic number.

    Reproduces a production incident: a manually-closed position stayed
    journaled as "open" forever because one engine's own position-
    monitoring read failing aborted reconciliation for every engine
    processed after it that cycle (`_run_position_monitoring` previously
    had no per-engine isolation). `magic_number` here is whichever one
    should fail, so the test can assert every *other* engine's own
    reconciliation still runs regardless of its position in the list.
    """

    def __init__(self, *args: object, failing_magic_number: int, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._failing_magic_number = failing_magic_number

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        if magic_number == self._failing_magic_number:
            raise ConnectionError("simulated transient MT5 IPC failure")
        return await super().get_open_positions(symbol=symbol, magic_number=magic_number)


async def test_run_once_reconciles_a_manually_closed_position_despite_an_earlier_engines_failure(
    engine: AsyncEngine,
) -> None:
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        config = _scan_config(symbol)
        primary_magic_number = compute_magic_number(config.strategy_name, config.strategy_version)
        swing_magic_number = compute_magic_number(
            f"{config.strategy_name}_swing", config.strategy_version
        )
        # Journaled as still open, but deliberately absent from the
        # broker's own reported positions below -- the user manually
        # closed it in the MT5 terminal.
        await TradeRepository(setup_session).add(
            Trade(
                symbol_id=symbol.id,
                direction="buy",
                status="open",
                volume=0.01,
                entry_price=2000.0,
                stop_loss=1990.0,
                initial_stop_loss=1990.0,
                magic_number=swing_magic_number,
                broker_ticket="9700",
            )
        )
        await setup_session.commit()

    mt5 = _RaisesForPrimaryMagicNumberMT5Client(
        failing_magic_number=primary_magic_number,
        raw_candles=_uptrend_raw_candles(5),
        tick=SymbolTick(bid=2007.8, ask=2008.0, timestamp=datetime.now(UTC)),
        positions=[],
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
    telegram = _FakeTelegramNotifier()
    loop = LiveTradingLoop(
        scan_config=config,
        mt5_client=mt5,
        telegram_notifier=telegram,
        technical_agents=[_BullishAgent()],
        classification_model=_bullish_classification_model(),
        regression_model=_bullish_regression_model(),
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        # Only needed so the Swing magic number is included in position
        # monitoring at all (`_run_position_monitoring` only appends it
        # when `self._swing_service is not None`) -- this test's own MT5
        # fixture gives it no qualifying D1/W1 setup, so it never
        # actually opens a new trade.
        swing_service=SwingAnalysisService(technical_agents=[_BullishAgent()]),
    )

    await loop.run_once()

    async with raw_session_factory() as check_session:
        swing_trade = await TradeRepository(check_session).get_by_broker_ticket("9700")
    assert swing_trade is not None
    assert swing_trade.status == "closed"
