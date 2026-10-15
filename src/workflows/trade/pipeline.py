"""Signal workflow orchestration.

Per WORKFLOW_ENGINE.md "Signal Workflow": "Chief AI -> Consensus -> Risk
Validation -> Execution Validation -> Telegram Preview -> MT5 Execution ->
Journal -> Learning Queue." Ties together every department already built
(Phases 11-16) into the single end-to-end pipeline that turns a Chief AI
decision into a journaled trade — nothing here re-implements a
department's own logic, it only sequences their already-built outputs and
records the result. "Learning Queue" is Phase 14's `learning_engine`
(trade review runs once the trade is closed, not at signal time).
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from src.core.execution.magic_number import compute_magic_number
from src.core.execution.mt5_client import MT5Client, OrderRequest
from src.core.execution.order_validation import ExecutionValidationRequest, validate_execution
from src.core.notifications.formatting import (
    SignalMessageData,
    build_reason_tags_ru_for_direction,
    format_signal_message,
)
from src.core.notifications.telegram_client import TelegramNotifier
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.scenarios import build_scenario_plan
from src.engines.historical_engine.similarity import SimilarityDisplayStats
from src.engines.risk_engine.position_sizing import PositionSizeResult
from src.models.trade import Trade
from src.repositories.trade_repository import TradeRepository

# MT5's `order_send()` rejects any `comment` of 30+ characters
# (`retcode -2 'Invalid "comment" argument'`) — measured directly against
# a real terminal via a length sweep (29 succeeds, 30 fails), not assumed
# or guessed from documentation. An earlier measurement recorded this
# limit as 31, which was never actually exercised end-to-end by a real
# order until the Scalping Engine's longer strategy name pushed a comment
# past 29 chars and the failure surfaced live. A full trade UUID alone (36
# chars) already exceeds this, so only a short prefix is embeddable in the
# broker-visible comment; the full id is always in the journal, looked up
# by `broker_ticket`.
_MT5_COMMENT_MAX_LENGTH = 29


def _order_comment(strategy_name: str, trade_id: uuid.UUID) -> str:
    """Build an MT5-safe order comment from a strategy name and trade id."""
    short_id = str(trade_id)[:8]
    return f"{strategy_name}:{short_id}"[:_MT5_COMMENT_MAX_LENGTH]


@dataclass(frozen=True, slots=True)
class SignalWorkflowInput:
    """Every input the signal workflow needs beyond the Chief AI decision itself.

    Attributes:
        symbol_id: The platform `Symbol` id this signal is for.
        market_symbol_name: The symbol name as understood by the MT5
            gateway, e.g. "XAUUSD".
        entry_price: Planned entry price.
        stop_loss: Protective stop price.
        take_profit: Target price, if any.
        position_size: Risk Engine's computed position size for this trade.
        execution_request: Pre-execution safety-gate inputs
            (`src.core.execution.order_validation.ExecutionValidationRequest`).
        strategy_name: Strategy identifier for the magic number/journal.
        strategy_version: Strategy version tag.
        telegram_chat_id: Chat to preview the signal to.
        department_votes: Snapshot of each department's bias/confidence at
            decision time, e.g. `{"technical": {"bias": "bullish",
            "confidence": 0.8}}` — persisted on the journaled `Trade` so
            `src.engines.learning_engine.department_performance` can later
            measure each department's realized accuracy. Optional so
            callers that don't yet track per-department votes (e.g. older
            tests) are unaffected. Also drives the richer Telegram signal
            message's "Active engines"/"Correlation"/"Order flow" fields.
        market_regime: The classified regime this cycle, if known — shown
            on the Telegram signal message.
        similarity_summary: Per the "Trade Similarity Engine" production
            requirement: this cycle's historical-analogue summary,
            evaluated against the actual chosen direction
            (`src.engines.historical_engine.similarity.
            summarize_matches_for_direction`), persisted on the journaled
            `Trade` and shown on the Telegram signal message. None for
            engines that don't compute one (e.g. Shakky, whose own spec
            forbids Historical Pattern Matching).
    """

    symbol_id: uuid.UUID
    market_symbol_name: str
    entry_price: float
    stop_loss: float
    take_profit: float | None
    position_size: PositionSizeResult
    execution_request: ExecutionValidationRequest
    strategy_name: str
    strategy_version: str
    telegram_chat_id: str
    department_votes: dict[str, dict[str, float | str]] | None = None
    market_regime: str | None = None
    similarity_summary: SimilarityDisplayStats | None = None


@dataclass(frozen=True, slots=True)
class SignalWorkflowResult:
    """Outcome of running the full signal workflow for one decision cycle.

    Attributes:
        decision: The Chief AI decision this workflow ran for.
        executed: True only if an order was successfully placed.
        trade: The journaled `Trade`, if one was created.
        rejection_reasons: Why the signal did not execute, if it didn't.
        telegram_sent: Whether the Telegram preview was sent.
    """

    decision: ChiefAIDecision
    executed: bool
    trade: Trade | None
    rejection_reasons: list[str] = field(default_factory=list)
    telegram_sent: bool = False


class SignalWorkflow:
    """Runs WORKFLOW_ENGINE.md's "Signal Workflow" end to end."""

    def __init__(
        self,
        *,
        trade_repository: TradeRepository,
        mt5_client: MT5Client,
        telegram_notifier: TelegramNotifier,
    ) -> None:
        """Initialize the workflow (constructor injection).

        Args:
            trade_repository: Persists the resulting journal entry.
            mt5_client: Execution gateway.
            telegram_notifier: Notification gateway for the signal preview.
        """
        self._trades = trade_repository
        self._mt5 = mt5_client
        self._telegram = telegram_notifier

    async def run(
        self, decision: ChiefAIDecision, workflow_input: SignalWorkflowInput
    ) -> SignalWorkflowResult:
        """Run the signal workflow for one Chief AI decision.

        Args:
            decision: The Chief AI's decision for this cycle
                (`src.engines.chief_ai.decision.evaluate`).
            workflow_input: Every remaining input needed to execute and journal it.

        Returns:
            A `SignalWorkflowResult` describing what happened. Non-BUY/SELL
            decisions and execution-validation failures never reach MT5 or
            Telegram — "No trade may bypass" every prior gate
            (RISK_ENGINE.md, MT5_ENGINE.md "Account Safety").
        """
        if decision.state not in ("BUY", "SELL"):
            return SignalWorkflowResult(
                decision=decision,
                executed=False,
                trade=None,
                rejection_reasons=[f"decision_not_actionable: {decision.state}"],
            )

        execution_check = validate_execution(workflow_input.execution_request)
        if not execution_check.approved:
            return SignalWorkflowResult(
                decision=decision,
                executed=False,
                trade=None,
                rejection_reasons=execution_check.rejection_reasons,
            )

        direction: Literal["buy", "sell"] = "buy" if decision.state == "BUY" else "sell"
        magic_number = compute_magic_number(
            workflow_input.strategy_name, workflow_input.strategy_version
        )
        scenario_plan = build_scenario_plan(decision, market_regime=workflow_input.market_regime)

        trade = await self._trades.add(
            Trade(
                symbol_id=workflow_input.symbol_id,
                direction=direction,
                status="pending",
                volume=workflow_input.position_size.position_size_units,
                entry_price=workflow_input.entry_price,
                stop_loss=workflow_input.stop_loss,
                initial_stop_loss=workflow_input.stop_loss,
                take_profit=workflow_input.take_profit,
                magic_number=magic_number,
                strategy_version=workflow_input.strategy_version,
                department_votes=workflow_input.department_votes,
                quality_score=decision.trade_quality.score,
                risk_score=decision.trade_quality.risk_score,
                market_regime=workflow_input.market_regime,
                confidence_pct=decision.confidence_pct,
                reasons=decision.reasons,
                scenario_plan={
                    "primary_scenario": scenario_plan.primary_scenario,
                    "alternative_scenario": scenario_plan.alternative_scenario,
                    "invalidation": scenario_plan.invalidation,
                    "expected_volatility": scenario_plan.expected_volatility,
                },
                similarity_summary=(
                    dataclasses.asdict(workflow_input.similarity_summary)
                    if workflow_input.similarity_summary is not None
                    else None
                ),
            )
        )

        order_result = await self._mt5.place_order(
            OrderRequest(
                symbol=workflow_input.market_symbol_name,
                order_type=direction,
                volume=trade.volume,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                magic_number=magic_number,
                comment=_order_comment(workflow_input.strategy_name, trade.id),
            )
        )

        if not order_result.success:
            trade.status = "rejected"
            trade.error_message = order_result.error_message
            await self._trades.add(trade)
            return SignalWorkflowResult(
                decision=decision,
                executed=False,
                trade=trade,
                rejection_reasons=[order_result.error_message or "order_rejected"],
            )

        trade.status = "open"
        trade.broker_ticket = order_result.broker_ticket
        trade.opened_at = datetime.now(UTC)
        await self._trades.add(trade)

        votes = workflow_input.department_votes or {}
        message_direction: Literal["BUY", "SELL"] = "BUY" if decision.state == "BUY" else "SELL"
        signal_message = format_signal_message(
            SignalMessageData(
                trade_id=str(trade.id),
                market=workflow_input.market_symbol_name,
                direction=message_direction,
                strategy_name=workflow_input.strategy_name,
                entry_price=workflow_input.entry_price,
                stop_loss=workflow_input.stop_loss,
                take_profit=workflow_input.take_profit,
                confidence_pct=decision.confidence_pct,
                quality_score=decision.trade_quality.score,
                reason_tags=build_reason_tags_ru_for_direction(votes, message_direction),
                similarity_summary=workflow_input.similarity_summary,
            )
        )
        telegram_sent = await self._telegram.send_message(
            workflow_input.telegram_chat_id, signal_message
        )

        return SignalWorkflowResult(
            decision=decision, executed=True, trade=trade, telegram_sent=telegram_sent
        )
