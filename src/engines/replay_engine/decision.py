"""Market Replay Mode: a step-by-step Chief AI decision from a strictly
historical candle window.

Per the "Market Replay Mode" production requirement: "Chief AI must
decide without seeing future candles." This module reuses the exact
same department-vote builders, Risk Engine gate, and `evaluate()` /
`explain_decision()` the live Market Update Workflow uses
(`src.workflows.market_update.pipeline.MarketScanner`) -- it never
re-implements decision logic, it only assembles the same department
votes from a caller-truncated candle window instead of a live MT5 feed,
so nothing passed in is ever a candle later than the one being decided.

Correlation and Order Flow are always absent here -- neither is
derivable from just the primary symbol's own historical OHLCV without
also replaying every correlated instrument / order-flow feed in lock
step, which is out of scope. Macro/News stay absent exactly as they
already are in this platform's live "reduced mode". ML is present only
if trained models were supplied. Every absence is honest (flagged
`reduced_confidence`), never a fabricated neutral vote.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from src.core.agents.confluence import CombinedVote
from src.core.ml.features import build_feature_vector
from src.core.ml.model import ClassificationModel, RegressionModel
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.chief_ai.decision import (
    REQUIRED_REPORTS,
    ChiefAIDecision,
    ChiefAIInput,
    compute_department_confidence,
    evaluate,
)
from src.engines.chief_ai.explanation import DecisionExplanation, explain_decision
from src.engines.historical_engine.regime_detection import RegimeClassification, classify_regime
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.risk_engine.approval import TradeApprovalRequest, evaluate_trade
from src.engines.technical_engine.confluence import TechnicalConfluence
from src.models.candle import Candle
from src.workflows.market_update.pipeline import (
    MIN_REWARD_RISK_RATIO,
    MIN_STOP_DISTANCE_PCT,
    historical_vote_from_outcome,
    ml_vote_from_prediction,
)

# Every department this replay engine can ever produce a vote for.
# Correlation/order-flow are never reproducible from a single symbol's
# own historical candles; macro/news mirror this platform's live
# "reduced mode" absence.
_ALWAYS_ABSENT_REPORTS: tuple[str, ...] = ("macro", "news", "correlation", "order_flow")


@dataclass(frozen=True, slots=True)
class ReplayDecisionStep:
    """The Chief AI's decision at one historical candle, computed as if live.

    Attributes:
        candle: The candle being decided on -- its `open` is the only
            field of this bar used (as an entry price), matching
            `src.engines.backtesting_engine.simulator`'s own "decide
            before the bar, enter at its open" convention.
        decision: The Chief AI decision, from the exact same `evaluate()`
            the live Market Update Workflow calls.
        explanation: The same structured reasoning shown live
            (`src.engines.chief_ai.explanation.explain_decision`).
        market_regime: The regime classified from the window strictly
            before this candle.
        entry_price: `candle.open`, only set for an actionable decision.
        stop_loss: Protective stop price, only set for an actionable decision.
        take_profit: Target price, only set for an actionable decision.
        department_votes: Every department's own `CombinedVote` this step
            was built from, keyed by name -- so callers (e.g. the Walk-
            Forward Validation Engine) can identify which departments
            agreed/disagreed with `decision` without recomputing votes.
    """

    candle: Candle
    decision: ChiefAIDecision
    explanation: DecisionExplanation
    market_regime: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    department_votes: dict[str, CombinedVote] = field(default_factory=dict)


async def compute_replay_decision(
    *,
    symbol_id: uuid.UUID,
    timeframe: str,
    window: list[Candle],
    next_candle: Candle,
    technical_agents: list[TechnicalAgent],
    similarity_service: HistoricalSimilarityService,
    classification_model: ClassificationModel | None = None,
    regression_model: RegressionModel | None = None,
    confidence_threshold: float = 70.0,
    technical_window_size: int | None = None,
) -> ReplayDecisionStep:
    """Compute the Chief AI decision for one replay step.

    Args:
        symbol_id: The platform `Symbol` id.
        timeframe: One of `src.models.candle.TIMEFRAMES`.
        window: Every candle strictly *before* `next_candle`, ordered by
            timestamp ascending -- the only data this step's decision may
            use ("no future candle leakage").
        next_candle: The candle being decided on. Only its `open` is
            used, as the hypothetical entry price -- its high/low/close
            are never read here.
        technical_agents: Every independent Technical Department agent,
            same as the live Market Update Workflow.
        similarity_service: Historical Research Engine's similarity
            search, called with `as_of_timestamp=window[-1].timestamp`
            and `persist_matches=False` so replay queries never leak
            future outcomes or pollute the live `historical_similarities` table.
        classification_model: Trained direction classifier, if available.
            None means "ml" is an absent (not fabricated) department,
            exactly like an unconfigured Macro/News provider.
        regression_model: Trained forward-return regressor, paired with
            `classification_model`.
        confidence_threshold: Minimum overall confidence (0-100) to BUY/SELL.
        technical_window_size: Candles considered by the Technical
            Department specifically; defaults to the full `window`.

    Returns:
        The `ReplayDecisionStep` for `next_candle`.
    """
    technical_window = (
        window[-technical_window_size:] if technical_window_size is not None else window
    )
    agent_reports = [agent.analyze(technical_window) for agent in technical_agents]

    similarity_result = await similarity_service.search(
        symbol_id,
        timeframe,
        window_size=len(window),
        as_of_timestamp=window[-1].timestamp,
        persist_matches=False,
    )
    technical_report = TechnicalConfluence().combine(
        agent_reports, historical_outcome=similarity_result.outcome_statistics
    )
    technical_vote = CombinedVote(
        bullish_probability=technical_report.bullish_probability,
        bearish_probability=technical_report.bearish_probability,
        neutral_probability=technical_report.neutral_probability,
        confidence=technical_report.technical_confidence,
        quality_grade=technical_report.technical_quality_grade,
        strongest_supporting_factors=technical_report.strongest_supporting_factors,
        strongest_opposing_factors=technical_report.strongest_opposing_factors,
        agent_reports=technical_report.agent_reports,
        historical_win_rate=technical_report.historical_win_rate,
    )
    historical_vote = historical_vote_from_outcome(similarity_result.outcome_statistics)

    department_votes = {"technical": technical_vote, "historical": historical_vote}
    reports_present = dict.fromkeys(REQUIRED_REPORTS, True)
    for name in _ALWAYS_ABSENT_REPORTS:
        reports_present[name] = False

    if classification_model is not None and regression_model is not None:
        features = build_feature_vector(window)
        class_probabilities = classification_model.predict_proba(features)
        forward_return_pct = regression_model.predict(features)
        department_votes["ml"] = ml_vote_from_prediction(class_probabilities, forward_return_pct)
        reports_present["ml"] = True
    else:
        reports_present["ml"] = False

    optional_reports = frozenset(_ALWAYS_ABSENT_REPORTS) | (
        frozenset() if reports_present["ml"] else frozenset({"ml"})
    )
    reduced_confidence_factors = [
        f"reduced_confidence:{name}_unavailable"
        for name in sorted(optional_reports)
        if not reports_present[name]
    ]
    pre_confidence_pct = compute_department_confidence(
        department_votes, reduced_confidence_factors=reduced_confidence_factors
    )

    regime = classify_regime(window)
    risk_request = TradeApprovalRequest(
        confidence_pct=pre_confidence_pct,
        spread_pips=0.0,
        max_spread_pips=float("inf"),
        is_market_open=True,
        historical_edge_pct=abs(similarity_result.outcome_statistics.average_return_pct),
        min_historical_edge_pct=0.0,
        critical_news_imminent=False,
        data_complete=True,
        system_health_ok=True,
    )
    risk_decision = evaluate_trade(risk_request)

    chief_input = ChiefAIInput(
        department_votes=department_votes,
        reports_present=reports_present,
        risk_decision=risk_decision,
        confidence_threshold=confidence_threshold,
        market_regime=regime.regime,
        critical_news_imminent=False,
        optional_reports=optional_reports,
    )
    decision = evaluate(chief_input)
    explanation = explain_decision(decision)

    if decision.state not in ("BUY", "SELL"):
        return ReplayDecisionStep(
            candle=next_candle,
            decision=decision,
            explanation=explanation,
            market_regime=regime.regime,
            department_votes=department_votes,
        )

    return _with_trade_parameters(next_candle, decision, explanation, regime, department_votes)


def _with_trade_parameters(
    next_candle: Candle,
    decision: ChiefAIDecision,
    explanation: DecisionExplanation,
    regime: RegimeClassification,
    department_votes: dict[str, CombinedVote],
) -> ReplayDecisionStep:
    direction_is_buy = decision.state == "BUY"
    entry_price = next_candle.open
    volatility_stop_distance = entry_price * (regime.features.volatility_pct / 100)
    stop_distance = max(volatility_stop_distance, entry_price * MIN_STOP_DISTANCE_PCT / 100)
    stop_loss = entry_price - stop_distance if direction_is_buy else entry_price + stop_distance
    target_distance = stop_distance * MIN_REWARD_RISK_RATIO
    take_profit = (
        entry_price + target_distance if direction_is_buy else entry_price - target_distance
    )

    return ReplayDecisionStep(
        candle=next_candle,
        decision=decision,
        explanation=explanation,
        market_regime=regime.regime,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        department_votes=department_votes,
    )
