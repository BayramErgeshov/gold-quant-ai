"""Phase 20 Live Loop entrypoint — Live Demo Trading Mode.

Continuously scans XAUUSD on the connected MT5 account using every
currently-wired engine (Technical, Historical, Machine Learning,
Correlation, Order Flow, and the independent Scalping and Swing Engines —
Macro/News are unconfigured, so every decision is flagged
`reduced_confidence`), generates signals via `MarketScanner`, and
executes/journals/notifies through `LiveTradingLoop`, which also
reconciles broker-closed positions each cycle and automatically runs the
"Post Trade Learning" post-mortem
(`src.engines.learning_engine.post_mortem`) for every losing trade,
sending a "POST-MORTEM" Telegram notification. It also sends a "Before
Market Close" report for every open position
(`config/risk.yaml` `session_schedule`) ahead of the daily session close,
with an added weekend gap risk note on the configured weekly close day.

Per the "Multi Strategy" production requirement: the primary (Intraday,
M15) engine, the Scalping Engine (M1/H1), and the Swing Engine (D1/W1)
are each evaluated independently every cycle and executed if they
individually qualify -- never limited to picking only one.

Per the "Position Management" production requirement, every position's
break-even trigger and post-break-even trailing stop are computed
dynamically each cycle (`src.engines.risk_engine.dynamic_stop`) from that
cycle's own real volatility/order-flow/trend/regime/support-resistance
signals — never a fixed R-multiple rule.

Per the "Live Demo Trading Mode" production requirement: once Chief AI's
overall confidence reaches `config/risk.yaml`
`confidence.setup_requires_confirmation_below` (70% by default), the
loop may automatically execute on the connected MT5 **demo** account —
there is no requirement to wait for another position to close; multiple
simultaneous positions are allowed whenever the Risk Engine's own
exposure-limit check (`src.engines.risk_engine.exposure`, cumulative
across every open position, not a fixed position count) still finds the
combined exposure acceptable.

Demo-account-only: `live_trading_approved` is hardcoded `False` here
regardless of `config/*.yaml`, per this platform's explicit operating
instructions and FAILSAFE_PROTOCOL.md — enabling *live* (real-money)
trading is a separate, explicit decision this script never makes on its
own. This gate has no effect on demo accounts (it only applies when
`account_type == "live"`), so it does not block the automatic demo
trading described above.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/run_live_loop.py
"""

from __future__ import annotations

import asyncio
import sys

from src.common.logging import configure_logging, get_logger
from src.common.process_lock import acquire_single_instance_lock
from src.core.config.yaml_loader import PROJECT_ROOT
from src.core.execution.mt5_client import RealMT5Client, configure_event_loop_policy
from src.core.notifications.telegram_client import RealTelegramNotifier
from src.core.technical_analysis.agent_registry import default_technical_agents
from src.database.postgres.session import get_session
from src.engines.micro_scalping_engine.service import MicroScalpingAnalysisService
from src.engines.ml_engine.training import TrainingService
from src.engines.order_flow_engine.service import OrderFlowAnalysisService
from src.engines.risk_engine.exposure import ExposureLimits
from src.engines.risk_engine.session_schedule import parse_session_schedule
from src.engines.scalping_engine.service import ScalpingAnalysisService
from src.engines.shakky_engine.service import ShakkyAnalysisService
from src.engines.swing_engine.service import SwingAnalysisService
from src.repositories.candle_repository import CandleRepository
from src.repositories.ml_model_repository import MLModelRepository
from src.repositories.symbol_repository import SymbolRepository
from src.services.scheduler.live_loop import LiveTradingLoop
from src.settings import get_settings
from src.workflows.market_update.pipeline import MarketScanConfig

logger = get_logger(__name__)

_TIMEFRAME = "M15"
_WINDOW_SIZE = 20
# Technical Department agents get their own, larger window -- decoupled
# from `_WINDOW_SIZE` (the ML model's trained feature-vector length,
# which must stay fixed for a given trained model). 250 covers EMA200
# (the longest single indicator any agent computes) with a small buffer.
_TECHNICAL_WINDOW_SIZE = 250
_FORWARD_BARS = 8
_SCAN_INTERVAL_SECONDS = 60
# Scalping Engine confidence bar (Phase 22) -- deliberately a separate,
# independent threshold from the primary engine's `confidence_threshold`
# above (config-driven), since the Scalping Engine has its own risk
# profile and evidence base.
_SCALPING_CONFIDENCE_THRESHOLD = 0.6
# Swing Engine confidence bar (Phase 26) -- higher than scalping's since a
# swing position holds far longer and each entry is far more consequential.
_SWING_CONFIDENCE_THRESHOLD = 0.65


_PID_FILE = PROJECT_ROOT / "logs" / "live_loop.pid"


async def main() -> int:
    configure_event_loop_policy()
    settings = get_settings()
    configure_logging(settings)

    if not acquire_single_instance_lock(_PID_FILE):
        logger.error("live_loop_startup_failed", reason="already_running")
        return 1

    mt5_client = RealMT5Client(settings)
    if not await mt5_client.connect():
        logger.error("live_loop_startup_failed", reason="mt5_connect_failed")
        return 1

    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name(settings.platform.symbols.primary)
        if symbol is None:
            logger.error("live_loop_startup_failed", reason="symbol_not_seeded")
            return 1

        model_name = f"xauusd_{_TIMEFRAME.lower()}_live"
        training_result = await TrainingService(
            candle_repository=CandleRepository(session),
            model_repository=MLModelRepository(session),
        ).train(
            symbol.id,
            _TIMEFRAME,
            model_name=model_name,
            window_size=_WINDOW_SIZE,
            forward_bars=_FORWARD_BARS,
        )

    risk_config = settings.platform.risk
    execution_validation = settings.platform.mt5.get("execution_validation", {})
    scan_config = MarketScanConfig(
        symbol_id=symbol.id,
        mt5_symbol=settings.platform.symbols.primary,
        timeframe=_TIMEFRAME,
        window_size=_WINDOW_SIZE,
        technical_window_size=_TECHNICAL_WINDOW_SIZE,
        risk_per_trade_pct=risk_config.position_sizing.risk_per_trade_pct,
        atr_multiplier_for_stop=risk_config.position_sizing.atr_multiplier_for_stop,
        max_spread_points=float(execution_validation.get("max_spread_points", 350)),
        confidence_threshold=risk_config.confidence.setup_requires_confirmation_below,
        exposure_limits=ExposureLimits(
            max_total_exposure_pct=risk_config.exposure.max_total_exposure_pct,
            max_instrument_exposure_pct=risk_config.exposure.max_gold_exposure_pct,
            max_correlated_exposure_pct=risk_config.exposure.max_correlated_exposure_pct,
            max_session_exposure_pct=risk_config.exposure.max_daily_exposure_pct,
            max_daily_exposure_pct=risk_config.exposure.max_daily_exposure_pct,
        ),
        account_type=settings.mt5_env.account_type,
        expected_account=settings.mt5_env.login or None,
        live_trading_approved=False,
        strategy_name=model_name,
        strategy_version="1.0.0",
        telegram_chat_id=settings.telegram_env.trading_group_id,
        min_trade_quality_score=risk_config.quality.minimum_trade_quality_score,
    )

    session_schedule = parse_session_schedule(
        daily_close_utc=risk_config.session_schedule.daily_close_utc,
        weekly_close_weekday=risk_config.session_schedule.weekly_close_weekday,
        pre_close_warning_minutes=risk_config.session_schedule.pre_close_warning_minutes,
    )
    shakky_service = ShakkyAnalysisService()
    loop = LiveTradingLoop(
        scan_config=scan_config,
        mt5_client=mt5_client,
        telegram_notifier=RealTelegramNotifier(settings),
        technical_agents=default_technical_agents(),
        classification_model=training_result.classification_model,
        regression_model=training_result.regression_model,
        session_factory=get_session,
        interval_seconds=_SCAN_INTERVAL_SECONDS,
        scalping_service=ScalpingAnalysisService(
            order_flow_service=OrderFlowAnalysisService(mt5_client=mt5_client),
            confidence_threshold=_SCALPING_CONFIDENCE_THRESHOLD,
        ),
        swing_service=SwingAnalysisService(
            technical_agents=default_technical_agents(),
            confidence_threshold=_SWING_CONFIDENCE_THRESHOLD,
        ),
        shakky_service=shakky_service,
        micro_scalping_service=MicroScalpingAnalysisService(shakky_service=shakky_service),
        session_schedule=session_schedule,
    )
    logger.info(
        "live_loop_started",
        symbol=scan_config.mt5_symbol,
        timeframe=_TIMEFRAME,
        interval_seconds=_SCAN_INTERVAL_SECONDS,
        account_type=scan_config.account_type,
        confidence_threshold=scan_config.confidence_threshold,
        scalping_enabled=True,
        swing_enabled=True,
        shakky_enabled=True,
        micro_scalping_enabled=True,
        live_trading_approved=scan_config.live_trading_approved,
        daily_close_utc=risk_config.session_schedule.daily_close_utc,
        weekly_close_weekday=risk_config.session_schedule.weekly_close_weekday,
    )
    await loop.run_forever()
    return 0  # pragma: no cover - unreachable: run_forever() loops until killed


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
