"""Walk-forward opportunity recording using the real Chief AI decision pipeline.

Per the "Historical Walk-Forward Validation" production requirement: "Run
full walk-forward validation over the last 1-2 years, replaying
historical candles exactly as if live, Chief AI must not see future
candles. For every historical opportunity record: would a trade have
opened, why, which departments agreed/disagreed, P/L, Maximum Favorable
Excursion, Maximum Adverse Excursion, holding time, Trade Quality Score,
confidence."

Reuses `src.engines.replay_engine.decision.compute_replay_decision` (the
exact same `evaluate()` the live Market Update Workflow calls, already
guaranteed to never see a future candle) rather than re-implementing
decision logic -- this module only adds opportunity recording and, for
actionable decisions, a forward simulation of the resulting trade using
the same "decide before the bar, enter at its open, stop assumed to
trigger before target within the same bar" convention
`src.engines.backtesting_engine.simulator` already documents.

This is an offline, CPU-bound pass over tens of thousands of candles
(`scripts/run_walk_forward_validation.py`), not a web-triggered
synchronous call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from src.core.agents.confluence import CombinedVote
from src.core.ml.model import ClassificationModel, RegressionModel
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.learning_engine.factor_analysis import OPINION_DEPARTMENTS
from src.engines.replay_engine.decision import compute_replay_decision
from src.models.candle import Candle

_DEFAULT_MAX_HOLDING_BARS = 200


@dataclass(frozen=True, slots=True)
class WalkForwardOpportunity:
    """One historical instant's Chief AI decision, recorded for later analysis.

    Attributes:
        timestamp: The candle this opportunity was decided on.
        state: The raw `ChiefAIDecision.state` ("BUY"/"SELL"/"WAIT"/...).
        would_have_traded: Whether `state` was actionable ("BUY"/"SELL").
        direction: "buy"/"sell" when actionable, else None.
        reasons: Why this decision was made.
        confidence_pct: Chief AI's overall confidence, in [0.0, 100.0].
        quality_score: Trade Quality Score, in [0.0, 100.0].
        agreeing_departments: Departments whose vote agreed with `direction`.
        disagreeing_departments: Departments whose vote opposed `direction`.
        missing_departments: Known departments absent this step (e.g.
            Macro/News before a provider is configured).
        entry_price: Planned entry, only set when actionable.
        stop_loss: Planned protective stop, only set when actionable.
        take_profit: Planned target, only set when actionable.
        realized_return_pct: Forward-simulated realized return, in
            percent, only set when actionable and there was at least one
            future candle to simulate against.
        exit_reason: Why the forward simulation closed ("stop_loss",
            "take_profit", "max_holding_bars_reached", "end_of_data").
        holding_bars: Number of bars the simulated position was held.
        mfe_pct: Maximum Favorable Excursion, in percent of entry price.
        mae_pct: Maximum Adverse Excursion, in percent of entry price
            (negative, or zero if price never moved against entry).
    """

    timestamp: datetime
    state: str
    would_have_traded: bool
    direction: Literal["buy", "sell"] | None = None
    reasons: list[str] = field(default_factory=list)
    confidence_pct: float = 0.0
    quality_score: float = 0.0
    agreeing_departments: list[str] = field(default_factory=list)
    disagreeing_departments: list[str] = field(default_factory=list)
    missing_departments: list[str] = field(default_factory=list)
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    realized_return_pct: float | None = None
    exit_reason: str | None = None
    holding_bars: int | None = None
    mfe_pct: float | None = None
    mae_pct: float | None = None


def _department_agreement(
    department_votes: dict[str, CombinedVote], direction: Literal["buy", "sell"] | None
) -> tuple[list[str], list[str], list[str]]:
    """Split departments into agreeing/disagreeing/missing for this direction.

    Mirrors `src.engines.learning_engine.factor_analysis.disagreeing_departments`/
    `missing_departments`'s own "opposing bias" rule, applied to a live
    `dict[str, CombinedVote]` instead of a closed `Trade`'s persisted
    snapshot (there is no `Trade` yet for a walk-forward opportunity).
    """
    missing = [name for name in OPINION_DEPARTMENTS if name not in department_votes]
    if direction is None:
        return [], [], missing

    agreeing: list[str] = []
    disagreeing: list[str] = []
    for name, vote in department_votes.items():
        if vote.bullish_probability == vote.bearish_probability:
            continue
        vote_is_bullish = vote.bullish_probability > vote.bearish_probability
        if vote_is_bullish == (direction == "buy"):
            agreeing.append(name)
        else:
            disagreeing.append(name)
    return sorted(agreeing), sorted(disagreeing), missing


@dataclass(frozen=True, slots=True)
class _ForwardSimulation:
    realized_return_pct: float
    exit_reason: str
    holding_bars: int
    mfe_pct: float
    mae_pct: float


def _simulate_forward(
    candles: list[Candle],
    entry_index: int,
    direction: Literal["buy", "sell"],
    entry_price: float,
    stop_loss: float,
    take_profit: float | None,
    max_holding_bars: int,
) -> _ForwardSimulation | None:
    """Forward-simulate one opportunity's trade using only later candles.

    Never reads a candle at or before `entry_index` -- only the bars a
    real position would actually be held through. When a bar's high and
    low both cross the stop and target, the stop is conservatively
    assumed to trigger first, matching `src.engines.backtesting_engine.
    simulator`'s own documented convention for this platform's bar-replay
    (no tick-level history is collected yet).

    Returns:
        None if there are no candles after `entry_index` to simulate
        against (the opportunity was the last bar in the series).
    """
    is_buy = direction == "buy"
    last_index = min(entry_index + max_holding_bars, len(candles) - 1)
    if last_index <= entry_index:
        return None

    mfe_pct = 0.0
    mae_pct = 0.0
    for offset, index in enumerate(range(entry_index + 1, last_index + 1), start=1):
        bar = candles[index]
        sign = 1 if is_buy else -1
        favorable_price = bar.high if is_buy else bar.low
        adverse_price = bar.low if is_buy else bar.high
        mfe_pct = max(mfe_pct, (favorable_price - entry_price) / entry_price * 100 * sign)
        mae_pct = min(mae_pct, (adverse_price - entry_price) / entry_price * 100 * sign)

        stop_hit = bar.low <= stop_loss if is_buy else bar.high >= stop_loss
        if stop_hit:
            return _ForwardSimulation(
                realized_return_pct=(stop_loss - entry_price) / entry_price * 100 * sign,
                exit_reason="stop_loss",
                holding_bars=offset,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
            )
        target_hit = take_profit is not None and (
            bar.high >= take_profit if is_buy else bar.low <= take_profit
        )
        if target_hit and take_profit is not None:
            return _ForwardSimulation(
                realized_return_pct=(take_profit - entry_price) / entry_price * 100 * sign,
                exit_reason="take_profit",
                holding_bars=offset,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
            )

    final_bar = candles[last_index]
    sign = 1 if is_buy else -1
    exit_reason = "end_of_data" if last_index == len(candles) - 1 else "max_holding_bars_reached"
    return _ForwardSimulation(
        realized_return_pct=(final_bar.close - entry_price) / entry_price * 100 * sign,
        exit_reason=exit_reason,
        holding_bars=last_index - entry_index,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
    )


async def run_chief_ai_walk_forward(
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
    candles: list[Candle],
    technical_agents: list[TechnicalAgent],
    similarity_service: HistoricalSimilarityService,
    classification_model: ClassificationModel | None = None,
    regression_model: RegressionModel | None = None,
    confidence_threshold: float = 70.0,
    window_size: int = 100,
    step: int = 1,
    technical_window_size: int | None = None,
    max_holding_bars: int = _DEFAULT_MAX_HOLDING_BARS,
) -> list[WalkForwardOpportunity]:
    """Walk forward through `candles`, recording every cycle's Chief AI opportunity.

    Args:
        symbol_id: The platform `Symbol` id.
        timeframe: One of `src.models.candle.TIMEFRAMES`.
        candles: The full historical series, ordered by timestamp
            ascending -- typically 1-2 years' worth per the production
            requirement.
        technical_agents: Every independent Technical Department agent,
            same as the live Market Update Workflow.
        similarity_service: Historical Research Engine's similarity
            search (queried with `persist_matches=False` at each step, so
            this offline pass never pollutes the live similarity table).
        classification_model: Trained direction classifier, if available.
        regression_model: Trained forward-return regressor, paired with
            `classification_model`.
        confidence_threshold: Minimum overall confidence (0-100) to BUY/SELL.
        window_size: Candles considered per decision step.
        step: How many candles to advance between decision steps (1 =
            evaluate every candle; larger values trade completeness for
            runtime on long histories).
        technical_window_size: Candles considered by the Technical
            Department specifically; defaults to the full window.
        max_holding_bars: Maximum bars an actionable opportunity's
            forward simulation runs before closing at that bar's close
            regardless of stop/target.

    Returns:
        One `WalkForwardOpportunity` per decision step. The last
        `window_size` candles never produce a step (there is no
        `next_candle` to decide on); the last opportunity may have no
        forward simulation if it falls on the series' final candle.
    """
    opportunities: list[WalkForwardOpportunity] = []
    for index in range(window_size, len(candles), step):
        window = candles[index - window_size : index]
        next_candle = candles[index]
        step_result = await compute_replay_decision(
            symbol_id=symbol_id,
            timeframe=timeframe,
            window=window,
            next_candle=next_candle,
            technical_agents=technical_agents,
            similarity_service=similarity_service,
            classification_model=classification_model,
            regression_model=regression_model,
            confidence_threshold=confidence_threshold,
            technical_window_size=technical_window_size,
        )
        decision = step_result.decision
        would_have_traded = decision.state in ("BUY", "SELL")
        direction: Literal["buy", "sell"] | None = (
            "buy" if decision.state == "BUY" else "sell" if decision.state == "SELL" else None
        )
        agreeing, disagreeing, missing = _department_agreement(
            step_result.department_votes, direction
        )

        forward: _ForwardSimulation | None = None
        if (
            would_have_traded
            and direction is not None
            and step_result.entry_price is not None
            and step_result.stop_loss is not None
        ):
            forward = _simulate_forward(
                candles,
                index,
                direction,
                step_result.entry_price,
                step_result.stop_loss,
                step_result.take_profit,
                max_holding_bars,
            )

        opportunities.append(
            WalkForwardOpportunity(
                timestamp=next_candle.timestamp,
                state=decision.state,
                would_have_traded=would_have_traded,
                direction=direction,
                reasons=list(decision.reasons),
                confidence_pct=decision.confidence_pct,
                quality_score=decision.trade_quality.score,
                agreeing_departments=agreeing,
                disagreeing_departments=disagreeing,
                missing_departments=missing,
                entry_price=step_result.entry_price,
                stop_loss=step_result.stop_loss,
                take_profit=step_result.take_profit,
                realized_return_pct=forward.realized_return_pct if forward else None,
                exit_reason=forward.exit_reason if forward else None,
                holding_bars=forward.holding_bars if forward else None,
                mfe_pct=forward.mfe_pct if forward else None,
                mae_pct=forward.mae_pct if forward else None,
            )
        )

    return opportunities
