"""Market Update Workflow (WORKFLOW_ENGINE.md "Market Update Workflow").

Per the spec: "Tick Received -> Update Database -> ... -> Trigger Technical
Analysis -> Trigger Historical Similarity -> Trigger ML -> Trigger Chief
AI." This module is the per-cycle orchestrator that runs one scan: it
ingests fresh candles, runs every enabled department (Technical,
Historical, ML) independently, builds the Risk Engine's Trade Approval
Decision, and calls Chief AI's `evaluate()` — nothing here re-implements a
department's own logic, it only sequences already-built outputs, exactly
like `src.workflows.trade.pipeline.SignalWorkflow` does for execution.

Macro and News departments are intentionally absent from
`department_votes` in the platform's current "reduced mode" (no FRED/
NewsAPI keys configured yet) — every decision is instead flagged
`reduced_confidence` via `ChiefAIInput.optional_reports`, per
`src.engines.chief_ai.decision`. Market Correlation and Order Flow
(Phase 21) follow the identical pattern: both are always run when a
service is injected, but are treated as optional confirmation only —
"These signals must never force a trade. They only increase or decrease
confidence" — and are simply absent (also reduced-confidence) when no
service is configured, exactly like an unconfigured Macro/News provider.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from src.core.agents.confluence import CombinedVote, grade_from_confidence
from src.core.execution.mt5_client import MT5Client, OpenPosition
from src.core.execution.order_validation import ExecutionValidationRequest
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
from src.engines.chief_ai.multi_timeframe import (
    combine_timeframe_confirmations,
    confirm_timeframe,
)
from src.engines.correlation_engine.analysis import (
    CorrelationAnalysisResult,
    CorrelationAnalysisService,
)
from src.engines.historical_engine.mt5_ingestion import MT5HistoricalIngestionService
from src.engines.historical_engine.regime_detection import classify_regime
from src.engines.historical_engine.similarity import (
    OutcomeStatistics,
    SimilarityDisplayStats,
    summarize_matches_for_direction,
)
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.order_flow_engine.service import OrderFlowAnalysisService, OrderFlowResult
from src.engines.risk_engine.approval import TradeApprovalRequest, evaluate_trade
from src.engines.risk_engine.exposure import ExposureLimits, ExposureState, check_exposure_limits
from src.engines.risk_engine.position_sizing import (
    PositionSizeResult,
    compute_fixed_lot_position_size,
    compute_position_size,
)
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.engines.technical_engine.confluence import TechnicalConfluence
from src.repositories.candle_repository import CandleRepository

_OPTIONAL_REPORTS: frozenset[str] = frozenset({"macro", "news", "correlation", "order_flow"})
_ALWAYS_PRESENT_REPORTS: tuple[str, ...] = ("statistics", "risk", "execution")
# XAUUSD is quoted with 2 decimal digits by this platform's broker
# (MT5_ENGINE.md "Symbol Specification"); one point is therefore $0.01.
_POINT_SIZE = 0.01
# How many bars ahead each historical analogue's outcome is measured over
# -- shared between the `HistoricalSimilarityService.search()` call and
# `summarize_matches_for_direction()` so "Average holding time" reflects
# the same horizon the outcomes were actually measured over.
_SIMILARITY_FORWARD_BARS = 10
MIN_REWARD_RISK_RATIO = 1.5
# A floor on the ATR-based stop distance, as a percent of entry price, so
# an unusually quiet window never collapses the stop toward zero and
# implies an unboundedly large position size.
MIN_STOP_DISTANCE_PCT = 0.05
# Per the "Complete Multi-Timeframe Analysis" production requirement's
# Intraday role ("Primary: H4 + H1, Confirmation: M15, Entry: M5"): the
# scan's own M15 decision window (`MarketScanConfig.timeframe`) is left
# unchanged (same reasoning as the Swing Engine's D1 primary staying
# untouched), and H4/H1/M5 are added as independent confirmation layers
# against the Technical department's own directional lean.
_INTRADAY_MTF_CANDLE_COUNT = 60
_INTRADAY_MTF_TIMEFRAMES: tuple[str, ...] = ("H4", "H1", "M5")


@dataclass(frozen=True, slots=True)
class MarketScanConfig:
    """Every tunable input one scan cycle needs beyond live market data.

    Attributes:
        symbol_id: The platform `Symbol` id being scanned.
        mt5_symbol: The MT5 broker symbol name, e.g. "XAUUSD".
        timeframe: The decision timeframe, one of `src.models.candle.TIMEFRAMES`.
        window_size: Candles considered per agent/feature/regime computation.
        risk_per_trade_pct: Baseline risk-per-trade (RISK_ENGINE.md "Position Sizing").
            Ignored when `fixed_lot_size` is set.
        atr_multiplier_for_stop: Volatility multiplier for the ATR-based
            stop distance (RISK_ENGINE.md: "never a fixed pip/point distance").
        max_spread_points: Maximum acceptable spread, in price points.
        confidence_threshold: Minimum overall confidence to BUY/SELL
            (RISK_ENGINE.md "Confidence Levels").
        exposure_limits: Configured maximum exposure percentages.
        account_type: One of "demo"/"paper"/"forward_test"/"live".
        expected_account: The account number the platform expects to trade on.
        live_trading_approved: Whether Live Mode has been explicitly enabled.
        strategy_name: Strategy identifier for the magic number/journal.
        strategy_version: Strategy version tag.
        telegram_chat_id: Chat to preview signals to.
        fixed_lot_size: If set, every position this cycle uses exactly
            this size (in the same unit as `entry_price`, e.g. ounces for
            XAUUSD) instead of the risk-based `compute_position_size`
            formula — per this platform's explicit operating
            instructions: "Use fixed position sizing chosen by the
            user... Never increase lot size because of confidence
            alone." None (the default) preserves risk-based sizing.
        technical_window_size: Candles considered by the Technical
            Department agents specifically. Decoupled from `window_size`
            (the ML model's trained feature-vector length, which must
            never change independently of retraining) because some
            technical indicators need much longer history than the ML
            feature window -- e.g. EMA200 needs 200+ candles. None (the
            default) reuses `window_size` for technical agents too,
            preserving the original single-window behavior.
        min_trade_quality_score: Minimum Trade Quality Score (0-100)
            required to BUY/SELL, forwarded to `ChiefAIInput`. Per the
            "Trade Quality Engine" production requirement: the score is
            the primary decision metric, not just a displayed number.
        demo_learning_mode: Per the "Demo Learning Mode" production
            requirement: forwarded to `TradeApprovalRequest`, widening
            the Risk Engine's own executable confidence-tier floor
            (independent of, and normally stricter than,
            `confidence_threshold` above) to also include "possible_setup"
            (61-75%). False (the default) preserves the standard floor.
    """

    symbol_id: uuid.UUID
    mt5_symbol: str
    timeframe: str
    window_size: int
    risk_per_trade_pct: float
    atr_multiplier_for_stop: float
    max_spread_points: float
    confidence_threshold: float
    exposure_limits: ExposureLimits
    account_type: str
    expected_account: str | None
    live_trading_approved: bool
    strategy_name: str
    strategy_version: str
    telegram_chat_id: str
    fixed_lot_size: float | None = None
    technical_window_size: int | None = None
    min_trade_quality_score: float = 0.0
    demo_learning_mode: bool = False


@dataclass(frozen=True, slots=True)
class MarketScanResult:
    """Outcome of one Market Update Workflow scan cycle.

    Attributes:
        decision: The Chief AI decision for this cycle.
        entry_price: Planned entry price, only set for an actionable decision.
        stop_loss: Protective stop price, only set for an actionable decision.
        take_profit: Target price, only set for an actionable decision.
        position_size: Risk Engine's computed size, only set for an
            actionable decision with a non-zero size.
        execution_request: Pre-execution safety-gate inputs, only set for
            an actionable decision.
        market_regime: The classified regime this cycle, if enough history
            was available.
        blocked_reasons: Why no trade parameters were computed, if the
            decision was not actionable or data was insufficient.
        department_votes: Every department vote this cycle's decision was
            built from, keyed by name — for `SignalWorkflow` to snapshot
            onto the journaled `Trade`
            (`src.engines.learning_engine.department_performance`).
        multi_timeframe_reasons: Per the "Complete Multi-Timeframe
            Analysis" production requirement: H4/H1/M5 confirmation tags
            against the Technical department's own directional lean (e.g.
            "H4_confirms:bull_trend", "M5_counter_trend:bear_trend"),
            for display alongside `department_votes` — empty when the
            Technical department reached no directional lean this cycle.
        similarity_summary: Per the "Trade Similarity Engine" production
            requirement: how many historical analogues were found for
            this cycle's situation, evaluated against the actual chosen
            direction ("How many became profitable. How many failed.
            Average RR. Average holding time. Average drawdown"), for
            display before the trade executes. None when the decision was
            not actionable (WAIT) or blocked before a direction was chosen.
    """

    decision: ChiefAIDecision
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    position_size: PositionSizeResult | None = None
    execution_request: ExecutionValidationRequest | None = None
    market_regime: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    department_votes: dict[str, CombinedVote] = field(default_factory=dict)
    multi_timeframe_reasons: list[str] = field(default_factory=list)
    similarity_summary: SimilarityDisplayStats | None = None


def historical_vote_from_outcome(outcome: OutcomeStatistics) -> CombinedVote:
    """Build a department vote from the Historical Research Engine's outcome stats.

    Confidence reflects both how far the win rate is from a coin flip and
    how many analogues it is based on — a small sample is never treated
    as confidently as a large one.
    """
    if outcome.sample_size == 0:
        return CombinedVote(
            bullish_probability=0.0,
            bearish_probability=0.0,
            neutral_probability=1.0,
            confidence=0.0,
            quality_grade="C",
            strongest_supporting_factors=[],
            strongest_opposing_factors=["no_historical_analogues_found"],
        )

    edge = abs(outcome.win_rate - 0.5) * 2
    sample_reliability = min(1.0, outcome.sample_size / 100)
    confidence = edge * sample_reliability
    factor = (
        f"historical_win_rate:{outcome.win_rate:.1%} "
        f"avg_return:{outcome.average_return_pct:+.2f}% "
        f"n={outcome.sample_size}"
    )
    return CombinedVote(
        bullish_probability=outcome.win_rate,
        bearish_probability=1.0 - outcome.win_rate,
        neutral_probability=0.0,
        confidence=confidence,
        quality_grade=grade_from_confidence(confidence),
        strongest_supporting_factors=[factor] if outcome.win_rate >= 0.5 else [],
        strongest_opposing_factors=[factor] if outcome.win_rate < 0.5 else [],
    )


def ml_vote_from_prediction(
    class_probabilities: dict[str, float], forward_return_pct: float
) -> CombinedVote:
    """Build a department vote from the ML Engine's classifier + regressor output."""
    bullish_probability = class_probabilities.get("bullish", 0.0) + class_probabilities.get(
        "strong_bullish", 0.0
    )
    bearish_probability = class_probabilities.get("bearish", 0.0) + class_probabilities.get(
        "strong_bearish", 0.0
    )
    neutral_probability = class_probabilities.get("neutral", 0.0)
    confidence = max(class_probabilities.values()) if class_probabilities else 0.0
    factor = f"ml_predicted_forward_return:{forward_return_pct:+.2f}%"
    return CombinedVote(
        bullish_probability=bullish_probability,
        bearish_probability=bearish_probability,
        neutral_probability=neutral_probability,
        confidence=confidence,
        quality_grade=grade_from_confidence(confidence),
        strongest_supporting_factors=[factor] if forward_return_pct >= 0 else [],
        strongest_opposing_factors=[factor] if forward_return_pct < 0 else [],
    )


def _correlation_vote_from_result(result: CorrelationAnalysisResult) -> CombinedVote:
    """Build a department vote from the Market Correlation Engine's output.

    Uses only the single most currently-predictive instrument (highest
    `feature_importance_score`) — "dynamic feature importance" means
    different instruments lead at different times, so voting with every
    instrument equally would dilute whichever one is actually informative
    right now. A correlation coefficient has no direction of its own, so
    the implied XAUUSD direction is `sign(correlation) * sign(instrument's
    own recent return)`.
    """
    if not result.instruments:
        return CombinedVote(
            bullish_probability=0.0,
            bearish_probability=0.0,
            neutral_probability=1.0,
            confidence=0.0,
            quality_grade="C",
            strongest_supporting_factors=[],
            strongest_opposing_factors=["no_correlated_instruments_configured"],
        )

    top = result.instruments[0]
    implied_direction = (
        1.0
        if (top.rolling_correlation.correlation * top.recent_return_pct) > 0
        else -1.0
        if (top.rolling_correlation.correlation * top.recent_return_pct) < 0
        else 0.0
    )
    confidence = min(1.0, top.feature_importance_score)
    factor = (
        f"{top.instrument_name} correlation={top.rolling_correlation.correlation:+.2f} "
        f"recent_return={top.recent_return_pct:+.2f}% (lead/lag={top.lead_lag.best_lag})"
    )
    return CombinedVote(
        bullish_probability=confidence if implied_direction > 0 else 0.0,
        bearish_probability=confidence if implied_direction < 0 else 0.0,
        neutral_probability=1.0 - confidence,
        confidence=confidence,
        quality_grade=grade_from_confidence(confidence),
        strongest_supporting_factors=[factor] if implied_direction != 0 else [],
        strongest_opposing_factors=[],
    )


def _order_flow_vote_from_result(result: OrderFlowResult) -> CombinedVote:
    """Build a department vote from the Order Flow Engine's output (real or synthetic)."""
    neutral_probability = max(0.0, 1.0 - result.bullish_probability - result.bearish_probability)
    return CombinedVote(
        bullish_probability=result.bullish_probability,
        bearish_probability=result.bearish_probability,
        neutral_probability=neutral_probability,
        confidence=result.confidence,
        quality_grade=grade_from_confidence(result.confidence),
        strongest_supporting_factors=[
            f"order_flow[{result.source}]: {note}" for note in result.supporting_evidence
        ],
        strongest_opposing_factors=[
            f"order_flow[{result.source}]: {note}" for note in result.opposing_evidence
        ],
    )


def exposure_state_from_positions(positions: list[OpenPosition], equity: float) -> ExposureState:
    """Build the pre-trade `ExposureState` from currently open positions.

    "Exposure" here means capital actually at risk (each position's
    volume times its stop distance), matching RISK_ENGINE.md's own
    "Position Sizing" formula (`src.engines.risk_engine.position_sizing.
    compute_position_size`) — not notional/leveraged position value, which
    for a correctly risk-sized forex/CFD trade routinely exceeds equity
    many times over and would make any single-digit exposure limit
    meaningless. Single-symbol scope (XAUUSD only): instrument exposure
    equals total exposure. Correlated/session exposure are not yet
    independently tracked (no other instruments are traded by this
    platform), so they are conservatively left at zero rather than fabricated.
    """
    if equity <= 0:
        return ExposureState()
    risk_amount = sum(
        position.volume * abs(position.entry_price - position.stop_loss) for position in positions
    )
    exposure_pct = risk_amount / equity * 100
    return ExposureState(total_exposure_pct=exposure_pct, instrument_exposure_pct=exposure_pct)


class MarketScanner:
    """Runs one Market Update Workflow cycle end to end."""

    def __init__(
        self,
        *,
        config: MarketScanConfig,
        mt5_client: MT5Client,
        candle_repository: CandleRepository,
        historical_ingestion: MT5HistoricalIngestionService,
        similarity_service: HistoricalSimilarityService,
        technical_agents: list[TechnicalAgent],
        classification_model: ClassificationModel,
        regression_model: RegressionModel,
        correlation_service: CorrelationAnalysisService | None = None,
        order_flow_service: OrderFlowAnalysisService | None = None,
        department_reliability: dict[str, float] | None = None,
        books_confluence: float = 0.0,
        technical_agent_weights: dict[str, float] | None = None,
    ) -> None:
        """Initialize the scanner (constructor injection).

        Args:
            config: Every tunable input for this cycle.
            mt5_client: Market data + account gateway.
            candle_repository: Stored OHLCV candles.
            historical_ingestion: Keeps stored candles current from MT5.
            similarity_service: Historical Research Engine's similarity search.
            technical_agents: Every independent Technical Department agent.
            classification_model: Trained direction classifier (in-memory;
                see `src.engines.ml_engine.training.TrainingService`).
            regression_model: Trained forward-return regressor (in-memory).
            correlation_service: Market Correlation Engine (Phase 21), if
                configured. None means "correlation" is an absent/optional
                report this cycle, exactly like an unconfigured Macro/News
                provider — never fabricated.
            order_flow_service: Order Flow Engine (Phase 21), if
                configured. Should be constructed once and reused across
                cycles (see that service's own docstring) — never rebuilt
                per scan.
            department_reliability: Each department's measured historical
                accuracy (`src.engines.learning_engine.department_performance`),
                recomputed once per cycle by the caller from recent closed
                trades. Forwarded to `ChiefAIInput.department_reliability`
                for calibrated-weight combination -- "Trade Quality Engine"
                production requirement.
            books_confluence: How much validated book knowledge supports
                this cycle's setup, in [0.0, 1.0]. Forwarded to
                `ChiefAIInput.books_confluence`.
            technical_agent_weights: Optional per-agent weight override,
                keyed by `TechnicalAgent.name`, forwarded to
                `TechnicalConfluence(weights=...)`. Per the "Complete
                Strategy Builder" production requirement's per-module
                weight; None applies the confluence's own default (every
                agent weight 1.0).
        """
        self._config = config
        self._mt5 = mt5_client
        self._candles = candle_repository
        self._ingestion = historical_ingestion
        self._similarity = similarity_service
        self._technical_agents = technical_agents
        self._classification_model = classification_model
        self._regression_model = regression_model
        self._correlation_service = correlation_service
        self._order_flow_service = order_flow_service
        self._department_reliability = department_reliability or {}
        self._books_confluence = books_confluence
        self._technical_agent_weights = technical_agent_weights

    async def scan(self) -> MarketScanResult:
        """Run one full scan cycle and return the Chief AI decision + trade params."""
        config = self._config
        technical_window_size = config.technical_window_size or config.window_size
        fetch_count = max(config.window_size, technical_window_size) + 50
        await self._ingestion.ingest(
            config.symbol_id,
            mt5_symbol=config.mt5_symbol,
            timeframe=config.timeframe,
            count=fetch_count,
        )
        candles = await self._candles.list_most_recent(
            config.symbol_id, config.timeframe, count=fetch_count
        )
        if len(candles) < config.window_size:
            return MarketScanResult(
                decision=_insufficient_data_decision(),
                blocked_reasons=["insufficient_candle_history"],
            )
        window = candles[-config.window_size :]
        # Technical agents get their own, independently-sized window --
        # some indicators (e.g. EMA200) need far more history than the ML
        # model's trained feature-vector length, and the two must never
        # be conflated (see `MarketScanConfig.technical_window_size`).
        technical_window = candles[-technical_window_size:]

        agent_reports = [agent.analyze(technical_window) for agent in self._technical_agents]
        similarity_result = await self._similarity.search(
            config.symbol_id,
            config.timeframe,
            window_size=config.window_size,
            forward_bars=_SIMILARITY_FORWARD_BARS,
        )
        technical_report = TechnicalConfluence(weights=self._technical_agent_weights).combine(
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

        features = build_feature_vector(window)
        class_probabilities = self._classification_model.predict_proba(features)
        forward_return_pct = self._regression_model.predict(features)
        ml_vote = ml_vote_from_prediction(class_probabilities, forward_return_pct)

        department_votes = {
            "technical": technical_vote,
            "historical": historical_vote,
            "ml": ml_vote,
        }
        reports_present = dict.fromkeys(REQUIRED_REPORTS, True)
        # Macro/News have no configured provider yet in this platform's
        # current reduced mode (no FRED/NewsAPI keys) — always absent.
        reports_present["macro"] = False
        reports_present["news"] = False

        if self._correlation_service is not None:
            correlation_result = await self._correlation_service.analyze(
                config.symbol_id, timeframe=config.timeframe
            )
            if correlation_result.instruments:
                department_votes["correlation"] = _correlation_vote_from_result(correlation_result)
            else:
                # No enabled instrument has any data yet — functionally the
                # same as "no provider configured" (nothing to vote with),
                # not a confident zero-signal read that should still drag
                # down the overall confidence average.
                reports_present["correlation"] = False
        else:
            reports_present["correlation"] = False

        if self._order_flow_service is not None:
            order_flow_result = await self._order_flow_service.analyze(config.mt5_symbol, window)
            department_votes["order_flow"] = _order_flow_vote_from_result(order_flow_result)
        else:
            reports_present["order_flow"] = False

        regime = classify_regime(window)
        reduced_confidence_factors = [
            f"reduced_confidence:{name}_unavailable"
            for name in sorted(_OPTIONAL_REPORTS)
            if not reports_present[name]
        ]
        pre_confidence_pct = compute_department_confidence(
            department_votes,
            reduced_confidence_factors=reduced_confidence_factors,
            department_reliability=self._department_reliability,
        )

        multi_timeframe_reasons: list[str] = []
        if technical_vote.bullish_probability != technical_vote.bearish_probability:
            technical_lean: Literal["buy", "sell"] = (
                "buy"
                if technical_vote.bullish_probability > technical_vote.bearish_probability
                else "sell"
            )
            confirmations = []
            for mtf_timeframe in _INTRADAY_MTF_TIMEFRAMES:
                await self._ingestion.ingest(
                    config.symbol_id,
                    mt5_symbol=config.mt5_symbol,
                    timeframe=mtf_timeframe,
                    count=_INTRADAY_MTF_CANDLE_COUNT + 50,
                )
                mtf_candles = await self._candles.list_most_recent(
                    config.symbol_id, mtf_timeframe, count=_INTRADAY_MTF_CANDLE_COUNT
                )
                confirmations.append(confirm_timeframe(mtf_timeframe, mtf_candles, technical_lean))
            mtf_result = combine_timeframe_confirmations(confirmations)
            pre_confidence_pct *= mtf_result.confidence_multiplier
            multi_timeframe_reasons = mtf_result.reasons

        account = await self._mt5.get_account_info()
        tick = await self._mt5.get_symbol_tick(config.mt5_symbol)
        open_positions = await self._mt5.get_open_positions(symbol=config.mt5_symbol)
        spread_points = (tick.ask - tick.bid) / _POINT_SIZE

        risk_request = TradeApprovalRequest(
            confidence_pct=pre_confidence_pct,
            spread_pips=spread_points,
            max_spread_pips=config.max_spread_points,
            is_market_open=True,
            historical_edge_pct=abs(similarity_result.outcome_statistics.average_return_pct),
            min_historical_edge_pct=0.0,
            critical_news_imminent=False,
            data_complete=True,
            system_health_ok=True,
            demo_learning_mode=config.demo_learning_mode,
        )
        risk_decision = evaluate_trade(risk_request)

        chief_input = ChiefAIInput(
            department_votes=department_votes,
            reports_present=reports_present,
            risk_decision=risk_decision,
            confidence_threshold=config.confidence_threshold,
            market_regime=regime.regime,
            critical_news_imminent=False,
            optional_reports=_OPTIONAL_REPORTS,
            department_reliability=self._department_reliability,
            books_confluence=self._books_confluence,
            min_trade_quality_score=config.min_trade_quality_score,
        )
        decision = evaluate(chief_input)

        if decision.state not in ("BUY", "SELL"):
            return MarketScanResult(
                decision=decision,
                market_regime=regime.regime,
                blocked_reasons=[f"decision_not_actionable:{decision.state}"],
                department_votes=department_votes,
                multi_timeframe_reasons=multi_timeframe_reasons,
            )

        direction_is_buy = decision.state == "BUY"
        # Per the "Trade Similarity Engine" production requirement:
        # "Display this information before every trade" -- now that a
        # direction has actually been chosen, the same matches Chief AI
        # already used as evidence (`historical_vote`) are re-evaluated
        # against THIS trade's own direction.
        similarity_summary = summarize_matches_for_direction(
            similarity_result.matches,
            "buy" if direction_is_buy else "sell",
            forward_bars=_SIMILARITY_FORWARD_BARS,
            timeframe=config.timeframe,
        )
        entry_price = tick.ask if direction_is_buy else tick.bid
        # A near-flat window can measure volatility_pct arbitrarily close
        # to zero, which would otherwise collapse the stop distance and
        # make `compute_position_size` return an unbounded, unsafe size
        # (RISK_ENGINE.md "never a fixed pip/point distance" governs the
        # *shape* of the stop, not a floor on it) — a minimum distance
        # keeps every stop meaningful regardless of how quiet the market is.
        volatility_stop_distance = (
            entry_price * (regime.features.volatility_pct / 100) * config.atr_multiplier_for_stop
        )
        stop_distance = max(volatility_stop_distance, entry_price * MIN_STOP_DISTANCE_PCT / 100)
        if stop_distance <= 0:
            return MarketScanResult(
                decision=decision,
                market_regime=regime.regime,
                blocked_reasons=["undefined_stop_distance"],
                department_votes=department_votes,
                multi_timeframe_reasons=multi_timeframe_reasons,
            )
        stop_loss = entry_price - stop_distance if direction_is_buy else entry_price + stop_distance

        target_distance = max(
            stop_distance * MIN_REWARD_RISK_RATIO,
            entry_price * abs(similarity_result.outcome_statistics.average_return_pct) / 100,
        )
        take_profit = (
            entry_price + target_distance if direction_is_buy else entry_price - target_distance
        )

        if config.fixed_lot_size is not None:
            position_size = compute_fixed_lot_position_size(
                fixed_lot_size=config.fixed_lot_size,
                account_equity=account.equity,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
            )
        else:
            position_size = compute_position_size(
                account_equity=account.equity,
                risk_per_trade_pct=config.risk_per_trade_pct,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
            )

        new_trade_exposure_pct = position_size.effective_risk_pct
        exposure_state = exposure_state_from_positions(open_positions, account.equity)
        exposure_breaches = check_exposure_limits(
            exposure_state, new_trade_exposure_pct, config.exposure_limits
        )
        if exposure_breaches or position_size.position_size_units <= 0:
            blocked = list(exposure_breaches)
            if position_size.position_size_units <= 0:
                blocked.append("zero_position_size")
            return MarketScanResult(
                decision=decision,
                market_regime=regime.regime,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                blocked_reasons=blocked,
                department_votes=department_votes,
                multi_timeframe_reasons=multi_timeframe_reasons,
                similarity_summary=similarity_summary,
            )

        execution_request = ExecutionValidationRequest(
            expected_symbol=config.mt5_symbol,
            order_symbol=config.mt5_symbol,
            expected_account=config.expected_account,
            actual_account=str(account.login),
            account_type=config.account_type,
            live_trading_approved=config.live_trading_approved,
            is_terminal_connected=await self._mt5.is_connected(),
            is_market_open=True,
            risk_approved=risk_decision.approved,
            chief_ai_approved=True,
        )

        return MarketScanResult(
            decision=decision,
            market_regime=regime.regime,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            execution_request=execution_request,
            department_votes=department_votes,
            multi_timeframe_reasons=multi_timeframe_reasons,
            similarity_summary=similarity_summary,
        )


def _insufficient_data_decision() -> ChiefAIDecision:
    """A `WAIT` decision for cycles with too little candle history to analyze."""
    return ChiefAIDecision(
        state="WAIT",
        probability=ProbabilityEstimate(
            bullish_probability=0.0, bearish_probability=0.0, neutral_probability=1.0
        ),
        confidence_pct=0.0,
        uncertainty_factors=["insufficient_candle_history"],
        reasons=["insufficient_candle_history"],
    )
