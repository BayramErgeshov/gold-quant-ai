"""ORM model for the trade journal (DATABASE.md: `trades`; MT5_ENGINE.md
"ORDER PARAMETERS" / "EXECUTION LOG").

Per MT5_ENGINE.md: "Every order is traceable... Every execution must be
reproducible." One row tracks a single order/position from submission
through close, regardless of which execution gateway (MT5 demo, paper,
future live) placed it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TRADE_DIRECTIONS: tuple[str, ...] = ("buy", "sell")
TRADE_STATUSES: tuple[str, ...] = ("pending", "open", "closed", "rejected", "cancelled")


class Trade(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single order/position tracked from submission through close.

    Attributes:
        symbol_id: Owning `Symbol`.
        direction: One of `TRADE_DIRECTIONS`.
        status: One of `TRADE_STATUSES`.
        volume: Order/position size, in the broker's lot/unit convention.
        entry_price: Requested (or filled) entry price.
        stop_loss: Current protective stop price (MT5_ENGINE.md: every
            order requires one). Mutated in place as the Trade Monitoring
            Workflow moves it to break-even/trails it.
        initial_stop_loss: The stop distance as originally computed at
            entry, preserved so break-even/trailing logic always measures
            its R-multiple against the trade's real invalidation
            distance rather than a stop that may have already moved.
        breakeven_moved: Whether the Trade Monitoring Workflow has already
            moved this position's stop to break-even (idempotency guard).
        take_profit: Target price, if set.
        magic_number: Strategy identifier attached to every order
            (MT5_ENGINE.md "Magic Number").
        comment: Broker-visible order comment.
        strategy_version: Version tag of the strategy that generated this trade.
        journal_reference: Free-form reference to the originating Chief AI
            decision/journal entry (DECISION_ENGINE.md "Journal ID").
        broker_ticket: Broker-assigned order/position ticket, once filled.
        account: Broker account identifier the trade was placed on.
        exit_price: Realized exit price, once closed.
        opened_at: When the position was actually opened (broker-reported).
        closed_at: When the position was actually closed (broker-reported).
        spread: Spread at execution time.
        slippage: Realized slippage (entry_price - requested price).
        commission: Broker commission charged.
        swap: Broker swap/rollover charged.
        realized_pnl: Realized profit/loss once closed.
        error_message: Broker/gateway error, if the order was rejected.
        department_votes: Snapshot of each department's `bias`/`confidence`
            at the moment this trade's decision was made — e.g.
            `{"technical": {"bias": "bullish", "confidence": 0.8}, ...}`.
            Populated once, at signal time, never mutated afterward;
            enables `src.engines.learning_engine.department_performance`
            to later measure each department's realized accuracy without
            needing to replay the original decision. Null for trades
            journaled before this field existed.
        quality_score: The Trade Quality Engine's 0-100 score at signal
            time (`src.engines.chief_ai.trade_quality`). Null for trades
            journaled before this field existed.
        risk_score: The Trade Quality Engine's 0-100 risk score at signal
            time. Null for trades journaled before this field existed.
        market_regime: The classified market regime at signal time (e.g.
            "bull_trend", "range"), for the "Profit by Market Regime"
            performance breakdown. Null for trades journaled before this
            field existed, or when regime was not yet classified.
        confidence_pct: Chief AI's overall decision confidence (0-100) at
            signal time, for the "Profit by Confidence Range" performance
            breakdown -- distinct from `quality_score`, which blends
            confidence with confluence/reliability/books support. Null
            for trades journaled before this field existed.
        post_mortem: The persisted "Post Trade Learning" verdict, once
            computed (`src.engines.learning_engine.post_mortem.
            PostMortemReport`, serialized) -- `would_repeat`,
            `should_have_been_skipped`, `disagreeing_departments`,
            `missing_departments`, `department_correctness`, `factors`.
            Populated once, right after the trade closes, never mutated
            afterward. Null for trades not yet reviewed (or journaled
            before this field existed).
        reasons: `ChiefAIDecision.reasons` at signal time -- why this
            direction was chosen, for the "Strategy Explanation"
            production requirement's per-trade "Reasons" display. Null
            for trades journaled before this field existed.
        scenario_plan: `src.engines.chief_ai.scenarios.ScenarioPlan` at
            signal time, serialized -- `primary_scenario`
            ("Expected Scenario"), `alternative_scenario`, `invalidation`,
            `expected_volatility`. Null for trades journaled before this
            field existed.
        similarity_summary: `src.engines.historical_engine.similarity.
            SimilarityDisplayStats` at signal time, serialized -- how many
            similar historical situations were found, how many were
            profitable/failed, average RR, average holding time, average
            drawdown (the "Trade Similarity Engine" production
            requirement's "Display this information before every trade").
            Null for Shakky trades (that engine's own spec forbids
            Historical Pattern Matching) or trades journaled before this
            field existed.
        max_favorable_excursion: The largest unrealized profit (in price
            distance, in the trade's favor) observed while the position
            was open, updated each monitoring cycle
            (`src.workflows.execution.position_monitor`). Null until the
            first monitoring cycle after entry, or for trades journaled
            before this field existed.
        max_adverse_excursion: The largest unrealized loss (in price
            distance, against the trade) observed while open, same
            update cadence as `max_favorable_excursion`.
        entry_trend_confidence_score: The Shakky Trend Confidence Engine's
            0-100 score (`src.engines.shakky_engine.trend_confidence`) at
            entry time. Null for non-Shakky trades (that score doesn't
            apply to the other engines) or Shakky trades journaled before
            this field existed.
        scale_events: Every Position Scaling add-on for this trade, as
            `[{"price": ..., "volume": ..., "at": "<ISO timestamp>"}, ...]`
            (`src.engines.shakky_engine.position_scaling`). Empty/null
            means no scale-in has happened yet.
        shakky_learning: The Shakky-specific post-trade learning verdict
            (`src.engines.learning_engine.shakky_trade_review.
            ShakkyLearningVerdict`, serialized), separate from the
            general `post_mortem` every strategy gets -- Shakky's own
            questions ("was TP too small," "should scaling have
            happened") don't apply to the other engines. Null for
            non-Shakky trades or trades not yet reviewed.
        micro_scalping_learning: The Micro Scalping-specific post-trade
            learning verdict (`src.engines.learning_engine.
            micro_scalping_trade_review.MicroScalpingLearningVerdict`,
            serialized) -- its own questions ("was profit taken too
            early/late," "would holding longer have helped") don't apply
            to the other engines. Null for non-Micro-Scalping trades or
            trades not yet reviewed.
    """

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(f"direction IN {TRADE_DIRECTIONS}", name="ck_trades_direction_valid"),
        CheckConstraint(f"status IN {TRADE_STATUSES}", name="ck_trades_status_valid"),
    )

    symbol_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False, index=True)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    initial_stop_loss: Mapped[float | None] = mapped_column(Float)
    breakeven_moved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    take_profit: Mapped[float | None] = mapped_column(Float)
    magic_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(String(200))
    strategy_version: Mapped[str | None] = mapped_column(String(50))
    journal_reference: Mapped[str | None] = mapped_column(String(200))
    broker_ticket: Mapped[str | None] = mapped_column(String(50), index=True)
    account: Mapped[str | None] = mapped_column(String(50))
    exit_price: Mapped[float | None] = mapped_column(Float)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spread: Mapped[float | None] = mapped_column(Float)
    slippage: Mapped[float | None] = mapped_column(Float)
    commission: Mapped[float | None] = mapped_column(Float)
    swap: Mapped[float | None] = mapped_column(Float)
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(String(500))
    department_votes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality_score: Mapped[float | None] = mapped_column(Float)
    risk_score: Mapped[float | None] = mapped_column(Float)
    market_regime: Mapped[str | None] = mapped_column(String(30))
    confidence_pct: Mapped[float | None] = mapped_column(Float)
    post_mortem: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reasons: Mapped[list[Any] | None] = mapped_column(JSON)
    scenario_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    similarity_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    max_favorable_excursion: Mapped[float | None] = mapped_column(Float)
    max_adverse_excursion: Mapped[float | None] = mapped_column(Float)
    entry_trend_confidence_score: Mapped[float | None] = mapped_column(Float)
    scale_events: Mapped[list[Any] | None] = mapped_column(JSON)
    shakky_learning: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    micro_scalping_learning: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    def __repr__(self) -> str:
        return f"Trade(direction={self.direction!r}, status={self.status!r})"
