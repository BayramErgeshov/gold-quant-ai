"""EMERGENCY CLOSE handling for the "Live Control" production requirement.

Per the spec: EMERGENCY CLOSE closes every open position immediately and
disables auto-trading. Unlike every other web UI module, this one *does*
connect to MT5 directly (a deliberate, explicit exception to
`dashboard_service`/`settings_service`'s "never touch MT5" rule) --
closing real broker positions cannot wait for the live loop's own next
cycle, and the live loop process may not even be running when this is
triggered (e.g. right after STOP).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.logging import get_logger
from src.core.execution.mt5_client import MT5Client
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.trade_repository import TradeRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EmergencyCloseResult:
    """Outcome of one EMERGENCY CLOSE action.

    Attributes:
        mt5_connected: Whether the connection to MT5 succeeded at all.
        closed_tickets: Broker tickets successfully closed.
        failed_tickets: Broker tickets MT5 rejected the close request for.
    """

    mt5_connected: bool
    closed_tickets: list[str] = field(default_factory=list)
    failed_tickets: list[str] = field(default_factory=list)


async def emergency_close_all_positions(
    session: AsyncSession, mt5: MT5Client
) -> EmergencyCloseResult:
    """Close every open journaled position immediately and disable auto-trading.

    Args:
        session: The active database session.
        mt5: An `MT5Client` to connect and issue close orders through
            (`src.interfaces.web.app` supplies a real `RealMT5Client`;
            tests supply a fake).

    Returns:
        The `EmergencyCloseResult` summarizing what happened.
    """
    settings_repository = RuntimeSettingsRepository(session)
    runtime_settings = await settings_repository.get_or_create_default()
    runtime_settings.auto_trading_enabled = False
    await settings_repository.add(runtime_settings)

    connected = await mt5.connect()
    if not connected:
        logger.error("emergency_close_mt5_connect_failed")
        return EmergencyCloseResult(mt5_connected=False)

    trade_repository = TradeRepository(session)
    closed_tickets: list[str] = []
    failed_tickets: list[str] = []
    for trade in await trade_repository.list_open():
        if trade.broker_ticket is None:
            continue
        result = await mt5.close_position(trade.broker_ticket)
        if not result.success:
            failed_tickets.append(trade.broker_ticket)
            logger.error(
                "emergency_close_position_failed",
                broker_ticket=trade.broker_ticket,
                error=result.error_message,
            )
            continue

        trade.status = "closed"
        trade.exit_price = result.filled_price
        if trade.entry_price is not None and result.filled_price is not None:
            direction_sign = 1.0 if trade.direction == "buy" else -1.0
            trade.realized_pnl = (
                (result.filled_price - trade.entry_price) * direction_sign * trade.volume
            )
        trade.closed_at = datetime.now(UTC)
        await trade_repository.add(trade)
        closed_tickets.append(trade.broker_ticket)
        logger.info("emergency_close_position_closed", broker_ticket=trade.broker_ticket)

    return EmergencyCloseResult(
        mt5_connected=True, closed_tickets=closed_tickets, failed_tickets=failed_tickets
    )
