"""Swing Engine orchestrator.

Per the "Multi Strategy" production requirement: "Run all strategies
simultaneously: Scalping, Intraday, Swing. Chief AI must decide
independently for every opportunity. Do not limit the system to
scalping." Mirrors `src.engines.scalping_engine.service`'s shape
(independent signal, own confidence threshold, own risk-scaled sizing)
but reads D1 candles instead of M1, and reuses this platform's own
generic Technical Department agents
(`src.core.agents.confluence.combine_agent_reports`) for its directional
read instead of scalping-specific microstructure detectors -- pattern
detection tuned for M1 noise (momentum bursts, breakout failures) has no
equivalent meaning at daily-bar scale, whereas trend/support-resistance/
liquidity/momentum agents already work on any timeframe by design.

Reuses already-built engines rather than duplicating them
(CODING_STANDARDS.md): `src.agents.technical.volatility.average_true_range`
for stop/target sizing and `src.engines.historical_engine.regime_detection`
for weekly-trend confirmation, exactly as the Scalping Engine does for its
own higher-timeframe check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.agents.technical.volatility import average_true_range
from src.core.agents.confluence import combine_agent_reports
from src.core.execution.mt5_client import SymbolTick
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.chief_ai.multi_timeframe import (
    combine_timeframe_confirmations,
    confirm_timeframe,
)
from src.engines.historical_engine.regime_detection import classify_regime
from src.models.candle import Candle

_DEFAULT_ATR_PERIOD = 14
_DEFAULT_STOP_ATR_MULTIPLE = 2.0
_DEFAULT_REWARD_RISK_RATIO = 2.0
_DEFAULT_CONFIDENCE_THRESHOLD = 0.65
_MIN_D1_CANDLES = 30
_MIN_W1_CANDLES = 20
# Trading against a strong weekly trend is allowed, but only when the
# daily-bar evidence is unusually strong -- mirrors the Scalping Engine's
# own counter-trend discount against its higher-timeframe check.
_COUNTER_TREND_CONFIDENCE_DISCOUNT = 0.5

_TREND_REGIMES: frozenset[str] = frozenset({"bull_trend", "bear_trend"})


@dataclass(frozen=True, slots=True)
class SwingAnalysisOutcome:
    """The Swing Engine's outcome for one cycle -- always returned.

    Per the "Why No Trade" production requirement: every strategy must
    show "Trade not opened. Reasons. Trade Quality Score. Confidence.
    Missing confirmations" -- even a cycle with no signal at all must
    surface why, not silently return nothing.

    Attributes:
        signal: The actionable signal, if confidence cleared the
            threshold this cycle. None means no trade this cycle.
        direction: The best directional read this cycle, if any evidence
            was measured at all (even below threshold). None when the
            technical agents reached no directional agreement at all --
            never a fabricated direction.
        confidence_pct: The best measured confidence this cycle, in
            [0.0, 100.0]. 0.0 when no evidence was measured at all.
        reasons: The signal's own contributing factors when actionable,
            or the specific reason(s) this cycle did not qualify.
    """

    signal: SwingSignal | None
    direction: Literal["buy", "sell"] | None = None
    confidence_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SwingSignal:
    """A single actionable swing opportunity.

    Attributes:
        direction: "buy" or "sell".
        confidence: Overall confidence in [0.0, 1.0], already discounted
            if the signal runs counter to the weekly trend.
        entry_price: Planned entry price (current tick).
        stop_loss: Protective stop, `_DEFAULT_STOP_ATR_MULTIPLE` times D1
            ATR from entry -- wider than the Scalping Engine's M1-ATR
            stop, matching swing's longer expected holding time.
        take_profit: Target price at `_DEFAULT_REWARD_RISK_RATIO` times
            the stop distance.
        weekly_trend_regime: The W1-classified regime this signal was
            confirmed (or discounted) against.
        reasons: Every contributing technical-agent factor.
        is_counter_trend: Whether this signal opposes `weekly_trend_regime`.
    """

    direction: Literal["buy", "sell"]
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    weekly_trend_regime: str | None
    reasons: list[str] = field(default_factory=list)
    is_counter_trend: bool = False


class SwingAnalysisService:
    """Runs the Swing Engine's full D1 analysis cycle."""

    def __init__(
        self,
        *,
        technical_agents: list[TechnicalAgent],
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        atr_period: int = _DEFAULT_ATR_PERIOD,
        stop_atr_multiple: float = _DEFAULT_STOP_ATR_MULTIPLE,
        reward_risk_ratio: float = _DEFAULT_REWARD_RISK_RATIO,
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            technical_agents: The same generic Technical Department agents
                the primary (Intraday) engine uses, run here against D1
                candles instead -- never a separate/duplicated agent set.
            confidence_threshold: Minimum confidence to produce a signal;
                below this, `analyze()` returns None (skip the trade).
            atr_period: D1 bars to average True Range over.
            stop_atr_multiple: Stop distance as a multiple of D1 ATR.
            reward_risk_ratio: Target distance as a multiple of the stop distance.
        """
        self._technical_agents = technical_agents
        self._confidence_threshold = confidence_threshold
        self._atr_period = atr_period
        self._stop_atr_multiple = stop_atr_multiple
        self._reward_risk_ratio = reward_risk_ratio

    async def analyze(
        self,
        *,
        d1_candles: list[Candle],
        w1_candles: list[Candle],
        tick: SymbolTick,
        confidence_threshold: float | None = None,
        enabled_agent_names: set[str] | None = None,
        agent_weights: dict[str, float] | None = None,
        h4_candles: list[Candle] | None = None,
        m15_candles: list[Candle] | None = None,
    ) -> SwingAnalysisOutcome:
        """Run one full Swing Engine analysis cycle.

        Args:
            d1_candles: Recent D1 candles, ordered by timestamp ascending.
            w1_candles: Recent W1 candles for weekly-trend confirmation,
                ordered by timestamp ascending.
            tick: The current bid/ask quote.
            confidence_threshold: Per-call override of the constructor's
                own `confidence_threshold`, so the "Independent Confidence
                Thresholds" production requirement's live per-strategy
                setting (`RuntimeSettings.swing_confidence_threshold`)
                takes effect every cycle without reconstructing this
                long-lived service. None uses the constructor default.
            enabled_agent_names: Per the "Complete Strategy Builder"
                production requirement's per-module enable/disable: when
                given, only agents whose `.name` is in this set vote this
                cycle. None means every constructor-configured agent votes
                (unchanged behavior).
            agent_weights: Per-agent weight override, keyed by
                `TechnicalAgent.name`, forwarded to `combine_agent_reports`.
                None applies the default (every agent weight 1.0).
            h4_candles: Per the "Complete Multi-Timeframe Analysis"
                production requirement's own Swing role ("Primary: D1 +
                H4"): an intermediate confirmation layer between the D1
                directional read and the weekly W1 context. None skips
                this check entirely (backward compatible).
            m15_candles: Per the same requirement's Swing "Entry: M15 /
                M5" role: a short-term entry-timing confirmation. None
                skips this check entirely.

        Returns:
            A `SwingAnalysisOutcome`, always -- `.signal` is None when
            there is too little history, no directional agreement among
            the technical agents, or confidence falls below the effective
            confidence threshold -- never a fabricated trade, but never a
            silently discarded "why not" either.
        """
        effective_threshold = (
            confidence_threshold if confidence_threshold is not None else self._confidence_threshold
        )
        if len(d1_candles) < _MIN_D1_CANDLES:
            return SwingAnalysisOutcome(signal=None, reasons=["insufficient_d1_history"])

        active_agents = (
            self._technical_agents
            if enabled_agent_names is None
            else [agent for agent in self._technical_agents if agent.name in enabled_agent_names]
        )
        reports = [agent.analyze(d1_candles) for agent in active_agents]
        vote = combine_agent_reports(reports, weights=agent_weights)
        if vote.bullish_probability == vote.bearish_probability:
            return SwingAnalysisOutcome(signal=None, reasons=["no_directional_agreement"])

        direction: Literal["buy", "sell"] = (
            "buy" if vote.bullish_probability > vote.bearish_probability else "sell"
        )
        confidence = vote.confidence
        reasons = list(vote.strongest_supporting_factors)

        weekly_regime = (
            classify_regime(w1_candles).regime if len(w1_candles) >= _MIN_W1_CANDLES else None
        )
        is_counter_trend = weekly_regime in _TREND_REGIMES and (weekly_regime == "bull_trend") != (
            direction == "buy"
        )
        if is_counter_trend:
            confidence *= _COUNTER_TREND_CONFIDENCE_DISCOUNT
            reasons.append(f"counter_trend_discount_applied_against:{weekly_regime}")

        # Per the "Complete Multi-Timeframe Analysis" production
        # requirement: H4 (intermediate confirmation, between the D1
        # primary read and the W1 weekly context) and M15 (entry timing)
        # each independently confirm or discount this candidate direction
        # -- reuses the same discount convention as the W1 check above,
        # generalized across as many additional timeframes as are supplied.
        additional_confirmations = []
        if h4_candles is not None:
            additional_confirmations.append(confirm_timeframe("H4", h4_candles, direction))
        if m15_candles is not None:
            additional_confirmations.append(confirm_timeframe("M15", m15_candles, direction))
        if additional_confirmations:
            mtf_result = combine_timeframe_confirmations(
                additional_confirmations,
                discount_per_disagreement=_COUNTER_TREND_CONFIDENCE_DISCOUNT,
            )
            confidence *= mtf_result.confidence_multiplier
            reasons.extend(mtf_result.reasons)

        if confidence < effective_threshold:
            reasons.append(f"confidence_below_threshold:{confidence:.2f}<{effective_threshold:.2f}")
            return SwingAnalysisOutcome(
                signal=None,
                direction=direction,
                confidence_pct=min(1.0, confidence) * 100,
                reasons=reasons,
            )

        atr = average_true_range(d1_candles, period=self._atr_period)
        if atr is None or atr <= 0:
            reasons.append("undefined_atr")
            return SwingAnalysisOutcome(
                signal=None,
                direction=direction,
                confidence_pct=min(1.0, confidence) * 100,
                reasons=reasons,
            )

        entry_price = tick.ask if direction == "buy" else tick.bid
        stop_distance = atr * self._stop_atr_multiple
        target_distance = stop_distance * self._reward_risk_ratio
        stop_loss = (
            entry_price - stop_distance if direction == "buy" else entry_price + stop_distance
        )
        take_profit = (
            entry_price + target_distance if direction == "buy" else entry_price - target_distance
        )

        signal = SwingSignal(
            direction=direction,
            confidence=min(1.0, confidence),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            weekly_trend_regime=weekly_regime,
            reasons=reasons,
            is_counter_trend=is_counter_trend,
        )
        return SwingAnalysisOutcome(
            signal=signal,
            direction=direction,
            confidence_pct=signal.confidence * 100,
            reasons=reasons,
        )
