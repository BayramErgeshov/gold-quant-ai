"""Trade Monitoring Workflow (WORKFLOW_ENGINE.md "Trade Monitoring Workflow").

Manages already-open positions: moves the stop to break-even once a
position has moved a dynamically-computed multiple of its original risk
distance (`Trade.initial_stop_loss`) in its favor, then continues
trailing the stop as price moves further favorably. Per the "Position
Management" production requirement: "Trailing Stop and Break-Even must
never follow fixed rules -- must be adjusted dynamically according to
volatility, liquidity, order flow, higher timeframe trend, market regime,
support/resistance, news risk" — both the break-even trigger and the
trailing distance are computed by
`src.engines.risk_engine.dynamic_stop` from this cycle's real signals
when the caller supplies `DynamicStopInputs`; without them, a fixed
R-multiple applies (documented fallback, not the default production path).

Also reconciles positions the broker has already closed (SL/TP hit, or
manually closed outside this platform) against the journal, so the "Post
Trade Learning" post-mortem actually fires automatically instead of
requiring a separate manual step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.common.logging import get_logger
from src.core.execution.mt5_client import MT5Client, OpenPosition
from src.core.notifications.formatting import (
    PositionEventData,
    format_position_event_message,
    format_post_mortem_message,
)
from src.core.notifications.telegram_client import TelegramNotifier
from src.engines.learning_engine.micro_scalping_trade_review import review_micro_scalping_trade
from src.engines.learning_engine.post_mortem import PostMortemService
from src.engines.learning_engine.shakky_trade_review import (
    other_strategy_average_r_multiple,
    review_shakky_trade,
)
from src.engines.risk_engine.dynamic_stop import (
    DynamicStopInputs,
    compute_dynamic_breakeven_trigger_r_multiple,
    compute_trailing_stop_price,
)
from src.models.trade import Trade
from src.repositories.trade_repository import TradeRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PositionMonitorResult:
    """Outcome of one Trade Monitoring Workflow cycle.

    Attributes:
        checked: Number of open positions examined.
        moved_to_breakeven: Broker tickets whose stop was moved this cycle.
        trailed: Broker tickets whose stop was trailed further this cycle
            (only possible after break-even has already been reached).
        closed_trades: Journaled trades reconciled as closed this cycle
            (no longer present among the broker's open positions).
        errors: Broker-ticket-prefixed error messages for failed modifications.
    """

    checked: int
    moved_to_breakeven: list[str] = field(default_factory=list)
    trailed: list[str] = field(default_factory=list)
    closed_trades: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PositionMonitor:
    """Moves open positions to break-even once they've earned it."""

    def __init__(
        self,
        *,
        mt5_client: MT5Client,
        trade_repository: TradeRepository,
        breakeven_trigger_r_multiple: float = 1.0,
        telegram_notifier: TelegramNotifier | None = None,
        telegram_chat_id: str | None = None,
        post_mortem_service: PostMortemService | None = None,
        shakky_magic_number: int | None = None,
        micro_scalping_magic_number: int | None = None,
    ) -> None:
        """Initialize the monitor (constructor injection).

        Args:
            mt5_client: Execution gateway.
            trade_repository: Source of truth for each position's
                original entry/stop and break-even state.
            breakeven_trigger_r_multiple: How many multiples of the
                original risk distance the position must have moved in
                its favor before its stop is moved to entry. Defaults to
                1.0 (a conservative, commonly used placeholder pending a
                configured value).
            telegram_notifier: If given (alongside `telegram_chat_id`),
                sends a "BREAK-EVEN"/"POST-MORTEM" notification per the
                spec's "During the trade send: ... Break-even" and "Post
                Trade Learning" requirements. Both must be provided to
                enable notifications; either alone is treated as disabled.
            telegram_chat_id: Chat to notify, if `telegram_notifier` is given.
            post_mortem_service: If given, runs the automatic post-mortem
                (`src.engines.learning_engine.post_mortem`) for every
                position this cycle reconciles as closed. Optional so
                callers that don't need reconciliation (e.g. existing
                breakeven-only tests) are unaffected.
            shakky_magic_number: If given, a closed trade with this
                magic number also gets the Shakky-specific learning
                verdict (`src.engines.learning_engine.shakky_trade_review`)
                persisted onto `Trade.shakky_learning` -- Shakky's own
                `department_votes` shape makes the generic post-mortem's
                department-agreement analysis meaningless for it.
            micro_scalping_magic_number: If given, a closed trade with
                this magic number also gets the Micro Scalping-specific
                learning verdict (`src.engines.learning_engine
                .micro_scalping_trade_review`) persisted onto
                `Trade.micro_scalping_learning` -- same reasoning as
                `shakky_magic_number` (its own `department_votes` shape
                and lack of a broker-side take-profit make the generic
                post-mortem meaningless for it).
        """
        self._mt5 = mt5_client
        self._trades = trade_repository
        self._trigger_r = breakeven_trigger_r_multiple
        self._telegram = telegram_notifier
        self._telegram_chat_id = telegram_chat_id
        self._post_mortem = post_mortem_service
        self._shakky_magic_number = shakky_magic_number
        self._micro_scalping_magic_number = micro_scalping_magic_number

    async def run_cycle(
        self,
        *,
        mt5_symbol: str,
        magic_number: int,
        dynamic_stop_inputs: DynamicStopInputs | None = None,
    ) -> PositionMonitorResult:
        """Check every open position for this strategy and move eligible stops.

        Args:
            mt5_symbol: Broker symbol name to filter positions by.
            magic_number: Only positions opened by this strategy are managed.
            dynamic_stop_inputs: This cycle's real volatility/order-flow/
                trend/regime/support-resistance/news signals
                (`src.engines.risk_engine.dynamic_stop`). When given, both
                the break-even trigger and the post-break-even trailing
                distance are computed dynamically from them. When None,
                the constructor's fixed `breakeven_trigger_r_multiple`
                applies and no further trailing happens after break-even
                (the pre-Position-Management-requirement behavior).

        Returns:
            A `PositionMonitorResult` summarizing what happened this cycle.
        """
        open_positions = await self._mt5.get_open_positions(
            symbol=mt5_symbol, magic_number=magic_number
        )
        moved: list[str] = []
        trailed: list[str] = []
        errors: list[str] = []

        for position in open_positions:
            trade = await self._trades.get_by_broker_ticket(position.ticket)
            if trade is None or trade.initial_stop_loss is None or trade.entry_price is None:
                continue

            risk_distance = abs(trade.entry_price - trade.initial_stop_loss)
            if risk_distance <= 0:
                continue

            if trade.breakeven_moved:
                if dynamic_stop_inputs is not None and await self._trail_stop(
                    trade, position, risk_distance, dynamic_stop_inputs
                ):
                    trailed.append(position.ticket)
                continue

            favorable_move = (
                position.current_price - trade.entry_price
                if position.direction == "buy"
                else trade.entry_price - position.current_price
            )
            trigger_r = (
                compute_dynamic_breakeven_trigger_r_multiple(
                    dynamic_stop_inputs, position.direction
                )
                if dynamic_stop_inputs is not None
                else self._trigger_r
            )
            if favorable_move < risk_distance * trigger_r:
                continue

            breakeven_price = trade.entry_price
            modify_result = await self._mt5.modify_order(position.ticket, stop_loss=breakeven_price)
            if not modify_result.success:
                error_detail = modify_result.error_message or "modify_failed"
                errors.append(f"{position.ticket}: {error_detail}")
                continue

            trade.stop_loss = breakeven_price
            trade.breakeven_moved = True
            await self._trades.add(trade)
            moved.append(position.ticket)
            logger.info(
                "position_moved_to_breakeven",
                ticket=position.ticket,
                breakeven_price=breakeven_price,
                trigger_r_multiple=trigger_r,
            )
            await self._notify_breakeven(trade, position, breakeven_price)

        closed = await self._reconcile_closed_positions(
            open_positions, mt5_symbol=mt5_symbol, magic_number=magic_number
        )

        return PositionMonitorResult(
            checked=len(open_positions),
            moved_to_breakeven=moved,
            trailed=trailed,
            closed_trades=closed,
            errors=errors,
        )

    async def _trail_stop(
        self,
        trade: Trade,
        position: OpenPosition,
        risk_distance: float,
        dynamic_stop_inputs: DynamicStopInputs,
    ) -> bool:
        """Trail an already-break-even position's stop further, if favorable.

        A trailing stop only ever tightens (moves in the position's
        favor) — this never loosens an existing stop even if the dynamic
        computation would otherwise suggest a wider one this cycle.

        Returns:
            True if the stop was moved this cycle.
        """
        new_stop = compute_trailing_stop_price(
            dynamic_stop_inputs,
            position_direction=position.direction,
            current_price=position.current_price,
            risk_distance=risk_distance,
        )
        is_more_favorable = (
            new_stop > trade.stop_loss
            if position.direction == "buy"
            else new_stop < trade.stop_loss
        )
        if not is_more_favorable:
            return False

        modify_result = await self._mt5.modify_order(position.ticket, stop_loss=new_stop)
        if not modify_result.success:
            return False

        trade.stop_loss = new_stop
        await self._trades.add(trade)
        logger.info("position_stop_trailed", ticket=position.ticket, new_stop=new_stop)
        await self._notify_sl_moved(trade, position, new_stop)
        return True

    async def _notify_sl_moved(self, trade: Trade, position: OpenPosition, new_stop: float) -> None:
        """Send an "SL MOVED" Telegram notification for a trailing-stop update, if configured."""
        if self._telegram is None or self._telegram_chat_id is None:
            return
        message = format_position_event_message(
            PositionEventData(
                event="sl_moved",
                trade_id=str(trade.id),
                market=position.symbol,
                reason="Стоп скорректирован под волатильность и тренд",
                new_stop_loss=new_stop,
                current_price=position.current_price,
            )
        )
        await self._telegram.send_message(self._telegram_chat_id, message)

    async def _reconcile_closed_positions(
        self, open_positions: list[OpenPosition], *, mt5_symbol: str, magic_number: int
    ) -> list[str]:
        """Detect journaled trades the broker no longer reports as open and close them.

        The broker is the source of truth for whether a position is still
        open (it may have closed via SL/TP, or manually, outside this
        platform). This platform does not yet query MT5 deal history, so
        the exit price is approximated from a fresh tick at reconciliation
        time rather than the actual fill price — a documented, honest
        approximation (MT5_ENGINE.md "Market Data" tick storage is a
        follow-up that would make this exact).

        Args:
            open_positions: This cycle's broker-reported open positions.
            mt5_symbol: Broker symbol name.
            magic_number: Only this strategy's journaled trades are reconciled.

        Returns:
            Trade ids closed this cycle.
        """
        broker_tickets = {position.ticket for position in open_positions}
        journaled_open = [
            trade
            for trade in await self._trades.list_open()
            if trade.magic_number == magic_number
            and trade.broker_ticket is not None
            and trade.broker_ticket not in broker_tickets
        ]
        if not journaled_open:
            return []

        # Production incident: a position that genuinely stayed open on
        # the broker got journaled as "closed" after roughly a minute,
        # over and over -- a single transient MT5 read returning fewer
        # positions than actually exist (the same documented IPC
        # flakiness `RealMT5Client` retries for elsewhere) is
        # indistinguishable, from here, from a real close. Unlike a
        # `None` response (already retried inside `get_open_positions`
        # itself), a transient *empty-but-non-None* list was trusted
        # immediately. Re-querying right here before acting catches a
        # one-cycle glitch without waiting a full extra cycle (during
        # which `_strategy_has_open_position` would have already let
        # this same strategy open a second, duplicate position).
        reconfirmed_positions = await self._mt5.get_open_positions(
            symbol=mt5_symbol, magic_number=magic_number
        )
        reconfirmed_tickets = {position.ticket for position in reconfirmed_positions}
        journaled_open = [
            trade for trade in journaled_open if trade.broker_ticket not in reconfirmed_tickets
        ]
        if not journaled_open:
            return []

        tick = await self._mt5.get_symbol_tick(mt5_symbol)
        closed_ids: list[str] = []

        for trade in journaled_open:
            if trade.entry_price is None:
                continue
            exit_price = tick.bid if trade.direction == "buy" else tick.ask
            direction_sign = 1.0 if trade.direction == "buy" else -1.0
            trade.status = "closed"
            trade.exit_price = exit_price
            trade.realized_pnl = (exit_price - trade.entry_price) * direction_sign * trade.volume
            trade.closed_at = datetime.now(UTC)
            await self._trades.add(trade)
            closed_ids.append(str(trade.id))
            logger.info(
                "position_reconciled_as_closed",
                trade_id=str(trade.id),
                broker_ticket=trade.broker_ticket,
                exit_price=exit_price,
                realized_pnl=trade.realized_pnl,
            )
            await self._run_post_mortem(trade, mt5_symbol=mt5_symbol)

        return closed_ids

    async def _run_post_mortem(self, trade: Trade, *, mt5_symbol: str) -> None:
        """Run the automatic post-trade analysis for a newly-closed trade, if configured.

        Per the "Post Trade Analysis" production requirement, this runs
        for every closed trade -- win or loss. The verdict is persisted
        onto `Trade.post_mortem` so it survives beyond the one-shot
        Telegram notification, for later dashboard/analytics use.

        Never raises: a post-mortem or notification failure must not undo
        the trade's already-persisted closed status.
        """
        if self._post_mortem is None:
            return
        report = await self._post_mortem.run_for_closed_trade(trade)
        trade.post_mortem = {
            "would_repeat": report.would_repeat,
            "should_have_been_skipped": report.should_have_been_skipped,
            "disagreeing_departments": report.disagreeing_departments,
            "missing_departments": report.missing_departments,
            "department_correctness": report.department_correctness,
            "factors": [{"name": f.name, "detail": f.detail} for f in report.factors],
        }
        if (
            self._shakky_magic_number is not None
            and trade.magic_number == self._shakky_magic_number
        ):
            await self._run_shakky_learning(trade)
        if (
            self._micro_scalping_magic_number is not None
            and trade.magic_number == self._micro_scalping_magic_number
        ):
            await self._run_micro_scalping_learning(trade)
        await self._trades.add(trade)
        if self._telegram is None or self._telegram_chat_id is None:
            return
        message = format_post_mortem_message(report, market=mt5_symbol)
        await self._telegram.send_message(self._telegram_chat_id, message)

    async def _run_shakky_learning(self, trade: Trade) -> None:
        """Persist the Shakky-specific learning verdict onto `Trade.shakky_learning`.

        Never raises: a learning-verdict failure must not undo the
        already-computed generic post-mortem or the trade's closed status.
        """
        try:
            closed_trades = await self._trades.list_by_status("closed", limit=1000)
            comparison = other_strategy_average_r_multiple(closed_trades)
            verdict = review_shakky_trade(trade, other_strategy_average_r_multiple=comparison)
        except Exception:
            logger.exception("shakky_learning_verdict_failed", trade_id=str(trade.id))
            return
        trade.shakky_learning = {
            "tp_too_small": verdict.tp_too_small,
            "tp_too_large": verdict.tp_too_large,
            "should_have_scaled": verdict.should_have_scaled,
            "better_strategy": verdict.better_strategy,
            "reasons": verdict.reasons,
        }

    async def _run_micro_scalping_learning(self, trade: Trade) -> None:
        """Persist the Micro Scalping learning verdict onto `Trade.micro_scalping_learning`.

        Never raises: a learning-verdict failure must not undo the
        already-computed generic post-mortem or the trade's closed status.
        """
        try:
            verdict = review_micro_scalping_trade(trade)
        except Exception:
            logger.exception("micro_scalping_learning_verdict_failed", trade_id=str(trade.id))
            return
        trade.micro_scalping_learning = {
            "closed_too_early": verdict.closed_too_early,
            "gave_back_profit": verdict.gave_back_profit,
            "held_too_long": verdict.held_too_long,
            "reasons": verdict.reasons,
        }

    async def _notify_breakeven(
        self, trade: Trade, position: OpenPosition, breakeven_price: float
    ) -> None:
        """Send a "BREAK-EVEN" Telegram notification, if configured.

        Never raises: a notification failure must not undo the stop move
        that already succeeded on the broker (the same class of bug
        already found and fixed once for `SignalWorkflow`'s own Telegram
        call — `TelegramNotifier.send_message` itself never raises, so
        this is a defense-in-depth guard, not a workaround for a known gap).
        """
        if self._telegram is None or self._telegram_chat_id is None:
            return
        message = format_position_event_message(
            PositionEventData(
                event="breakeven",
                trade_id=str(trade.id),
                market=position.symbol,
                reason=f"Цена прошла {self._trigger_r:.1f}R, стоп переведён в безубыток",
                new_stop_loss=breakeven_price,
                current_price=position.current_price,
            )
        )
        await self._telegram.send_message(self._telegram_chat_id, message)
