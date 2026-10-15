"""Controlled infrastructure test trade (Phase 21, Part 4/6 of the user's spec).

Exercises the *real* production Signal Workflow end to end — MT5
connectivity, order placement, journal persistence, and Telegram
notification — using a deliberately synthetic, clearly-labeled "BUY"
decision at the broker's minimum order size, not a real Chief AI signal.

Safety:
    - Aborts immediately if the connected account is not a demo account.
    - Aborts immediately if the terminal reports trading is not allowed
      (AutoTrading disabled).
    - Uses the broker's minimum tradable volume (verified live via
      `symbol_info`, never assumed).
    - Always closes the position before exiting, regardless of P&L.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. POSTGRES_PASSWORD=changeme ./.venv/Scripts/python.exe scripts/mt5_test_trade.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from src.core.execution.magic_number import compute_magic_number
from src.core.execution.mt5_client import RealMT5Client, configure_event_loop_policy
from src.core.execution.order_validation import ExecutionValidationRequest
from src.core.notifications.formatting import format_trade_closed_message
from src.core.notifications.telegram_client import RealTelegramNotifier
from src.database.postgres.session import get_session
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.risk_engine.position_sizing import PositionSizeResult
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository
from src.settings import get_settings
from src.workflows.trade.pipeline import SignalWorkflow, SignalWorkflowInput

_STRATEGY_NAME = "infrastructure_test"
_STRATEGY_VERSION = "test-1"
_STOP_DISTANCE_USD = 3.0  # a modest, realistic distance for XAUUSD; not a signal
_WAIT_BEFORE_CLOSE_SECONDS = 7


def _test_decision() -> ChiefAIDecision:
    """A deliberately synthetic BUY decision — this script tests plumbing, not a signal."""
    return ChiefAIDecision(
        state="BUY",
        probability=ProbabilityEstimate(
            bullish_probability=1.0, bearish_probability=0.0, neutral_probability=0.0
        ),
        confidence_pct=100.0,
        uncertainty_factors=[],
        reasons=["infrastructure_test_forced_buy"],
        supporting_evidence=["This is a controlled infrastructure test, not a trading signal."],
    )


async def main() -> int:
    configure_event_loop_policy()
    settings = get_settings()
    mt5_symbol = settings.platform.symbols.primary

    print("=== Step 1: MT5 connectivity ===")
    mt5_client = RealMT5Client(settings)
    if not await mt5_client.connect():
        print("ABORTED: could not connect to MT5.")
        return 1
    print("Connected.")

    print()
    print("=== Step 2: Account safety checks ===")
    account = await mt5_client.get_account_info()
    print(f"login={account.login} server={account.server} is_demo={account.is_demo}")
    print(f"account.trading_allowed (server-side permission)={account.trading_allowed}")
    if not account.is_demo:
        print("ABORTED: this is not a demo account. Refusing to place any order.")
        return 1
    if not account.trading_allowed:
        print("ABORTED: trading is not allowed on this account (server-side permission).")
        return 1
    print("Demo account confirmed, server-side trading allowed.")

    print()
    print("=== Step 2b: terminal AutoTrading toggle (distinct from account permission) ===")
    import MetaTrader5 as mt5  # noqa: N813 - matches the package's own casing

    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        print("ABORTED: terminal_info() returned None.")
        return 1
    print(f"terminal.trade_allowed (AlgoTrading toggle)={terminal_info.trade_allowed}")
    if not terminal_info.trade_allowed:
        print(
            "ABORTED: AutoTrading is disabled in the MT5 terminal itself "
            "(distinct from the account's server-side permission checked above). "
            "Enable it via the terminal's 'Algo Trading' toolbar button, or "
            "Tools -> Options -> Expert Advisors -> 'Allow algorithmic trading', "
            "then re-run this script."
        )
        return 1
    print("Terminal AutoTrading is enabled.")

    print()
    print("=== Step 3: verify broker minimum volume (never assumed) ===")
    symbol_info = mt5.symbol_info(mt5_symbol)
    if symbol_info is None:
        print(f"ABORTED: symbol_info({mt5_symbol!r}) returned None.")
        return 1
    volume_min_lots = float(symbol_info.volume_min)
    contract_size = float(symbol_info.trade_contract_size)
    minimal_volume_ounces = volume_min_lots * contract_size
    print(
        f"volume_min={volume_min_lots} lots, trade_contract_size={contract_size} "
        f"-> minimal order = {minimal_volume_ounces} oz"
    )

    tick = await mt5_client.get_symbol_tick(mt5_symbol)
    entry_price = tick.ask
    stop_loss = entry_price - _STOP_DISTANCE_USD
    print(f"Current tick: bid={tick.bid} ask={tick.ask} -> entry={entry_price}, sl={stop_loss}")

    print()
    print("=== Step 4: place the minimal TEST order via the real Signal Workflow ===")
    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name(mt5_symbol)
        if symbol is None:
            print(f"ABORTED: symbol {mt5_symbol!r} is not seeded in the database.")
            return 1

        trade_repository = TradeRepository(session)
        telegram_notifier = RealTelegramNotifier(settings)
        workflow = SignalWorkflow(
            trade_repository=trade_repository,
            mt5_client=mt5_client,
            telegram_notifier=telegram_notifier,
        )
        workflow_input = SignalWorkflowInput(
            symbol_id=symbol.id,
            market_symbol_name=mt5_symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=None,
            position_size=PositionSizeResult(
                position_size_units=minimal_volume_ounces,
                risk_amount=minimal_volume_ounces * _STOP_DISTANCE_USD,
                effective_risk_pct=0.0,
            ),
            execution_request=ExecutionValidationRequest(
                expected_symbol=mt5_symbol,
                order_symbol=mt5_symbol,
                expected_account=str(account.login),
                actual_account=str(account.login),
                account_type="demo",
                live_trading_approved=False,
                is_terminal_connected=await mt5_client.is_connected(),
                is_market_open=True,
                risk_approved=True,
                chief_ai_approved=True,
            ),
            strategy_name=_STRATEGY_NAME,
            strategy_version=_STRATEGY_VERSION,
            telegram_chat_id=settings.telegram_env.trading_group_id,
        )

        result = await workflow.run(_test_decision(), workflow_input)
        if not result.executed or result.trade is None or result.trade.broker_ticket is None:
            print(f"ABORTED: order was not accepted. reasons={result.rejection_reasons}")
            return 1

        trade = result.trade
        assert trade.broker_ticket is not None  # narrowed by the guard above
        broker_ticket: str = trade.broker_ticket
        print(f"Order accepted: ticket={broker_ticket} volume={trade.volume}oz")
        print(f"Telegram signal preview sent: {result.telegram_sent}")

        print()
        print(f"=== Step 5: waiting {_WAIT_BEFORE_CLOSE_SECONDS}s before closing ===")
        await asyncio.sleep(_WAIT_BEFORE_CLOSE_SECONDS)

        print()
        print("=== Step 6: closing the test position (regardless of P&L) ===")
        positions_before_close = await mt5_client.get_open_positions(
            symbol=mt5_symbol,
            magic_number=compute_magic_number(_STRATEGY_NAME, _STRATEGY_VERSION),
        )
        matching = [p for p in positions_before_close if p.ticket == broker_ticket]
        floating_pnl = matching[0].profit if matching else None
        current_price = matching[0].current_price if matching else None

        close_result = await mt5_client.close_position(broker_ticket)
        if not close_result.success:
            print(f"ABORTED: failed to close position: {close_result.error_message}")
            print("MANUAL INTERVENTION MAY BE REQUIRED to close this test position.")
            return 1

        trade.status = "closed"
        trade.exit_price = close_result.filled_price or current_price
        trade.closed_at = datetime.now(UTC)
        trade.realized_pnl = floating_pnl
        await trade_repository.add(trade)
        print(f"Closed. exit_price={trade.exit_price} realized_pnl={trade.realized_pnl}")

        print()
        print("=== Step 7: Telegram close notification ===")
        close_message = format_trade_closed_message(trade)
        telegram_sent = await telegram_notifier.send_message(
            settings.telegram_env.trading_group_id, close_message
        )
        print(f"Telegram close notification sent: {telegram_sent}")

        print()
        print("=== Step 8: verify database persistence ===")
        stored = await trade_repository.get_by_broker_ticket(broker_ticket)
        assert stored is not None, "Trade not found in database after close"
        assert stored.status == "closed", f"Expected status=closed, got {stored.status!r}"

    print()
    print("=" * 60)
    print("EXECUTION REPORT")
    print("=" * 60)
    print(f"Account:            {account.login} @ {account.server} (demo={account.is_demo})")
    print(f"Symbol:             {mt5_symbol}")
    print(f"Broker ticket:      {broker_ticket}")
    print(f"Direction:          {trade.direction}")
    print(f"Volume:             {trade.volume} oz ({volume_min_lots} lots)")
    print(f"Entry price:        {trade.entry_price}")
    print(f"Exit price:         {trade.exit_price}")
    print(f"Realized P&L:       {trade.realized_pnl}")
    print(f"Journal (DB) row:   {stored.id}, status={stored.status}")
    print(f"Telegram signal:    sent={result.telegram_sent}")
    print(f"Telegram close:     sent={telegram_sent}")
    print("=" * 60)
    print("TEST TRADE COMPLETED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
