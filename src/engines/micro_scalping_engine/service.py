"""Micro Scalping Engine -- entry orchestration.

Per the engine's own spec: "Reuse the existing Shakky confirmation
logic... Do NOT invent a new strategy. The difference is only trade
management." This module's `analyze()` delegates entry-signal-finding
entirely to `ShakkyAnalysisService.analyze()` (identical confirmation
modules, identical ATR-based stop-loss -- "never a fixed stop"), then
layers this engine's own additional gates
(`src.engines.micro_scalping_engine.entry_filters`) and its own Trend
Confidence-based confidence read on top, narrowing Shakky's own signal
down further rather than replacing any part of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.core.execution.mt5_client import SymbolTick
from src.engines.micro_scalping_engine.entry_filters import (
    check_liquidity,
    check_momentum,
    check_recent_high_impact_news,
    check_spread,
)
from src.engines.shakky_engine.confirmations import Confirmation
from src.engines.shakky_engine.service import ShakkyAnalysisService
from src.engines.shakky_engine.trend_confidence import assess_trend_confidence
from src.models.candle import Candle
from src.models.news_article import NewsArticle

Direction = Literal["buy", "sell"]

_DEFAULT_MIN_CONFIDENCE = 60.0
# See `entry_filters._DEFAULT_MAX_SPREAD_POINTS` for why this is 60.0,
# not the originally-guessed 5.0 (which silently blocked every trade
# against this account's real ~36-point XAUUSD spread).
_DEFAULT_MAX_SPREAD_POINTS = 60.0


@dataclass(frozen=True, slots=True)
class MicroScalpingSignal:
    """A single actionable Micro Scalping opportunity.

    Attributes:
        direction: "buy" or "sell".
        entry_price: Planned entry price (current tick), from Shakky's own signal.
        stop_loss: Protective stop, from Shakky's own ATR/candle-based
            sizing -- never a fixed distance.
        confirmations: Every confirmation that agreed with `direction`
            (Shakky's own confirmation objects, unmodified).
        dominant_family: Which entry-logic family Shakky's stop-loss rule used.
        reasons: Human-readable detail from Shakky's own confirmations
            plus every one of this engine's own additional gates.
    """

    direction: Direction
    entry_price: float
    stop_loss: float
    confirmations: list[Confirmation]
    dominant_family: str
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MicroScalpingAnalysisOutcome:
    """Micro Scalping's outcome for one cycle -- always returned, win or no-trade.

    Attributes:
        signal: The actionable signal, if every gate passed. None otherwise.
        direction: Shakky's own directional read this cycle, even when no signal resulted.
        confirmation_count: How many of Shakky's confirmations agreed with `direction`.
        trend_confidence_score: The Trend Confidence Engine's 0-100 score
            for this direction, if computed (only once Shakky's own
            signal and the spread/liquidity/momentum/news gates already
            passed) -- used both as the "high confidence" entry gate and
            persisted for later learning.
        reasons: Every contributing/blocking reason, in the order evaluated.
    """

    signal: MicroScalpingSignal | None
    direction: Direction | None
    confirmation_count: int
    trend_confidence_score: float | None
    reasons: list[str] = field(default_factory=list)


class MicroScalpingAnalysisService:
    """Runs Micro Scalping's full analysis cycle."""

    def __init__(self, *, shakky_service: ShakkyAnalysisService) -> None:
        """Initialize the service (constructor injection).

        Args:
            shakky_service: The exact same confirmation/pattern logic
                this engine reuses for entry -- never a second, parallel
                implementation.
        """
        self._shakky = shakky_service

    async def analyze(
        self,
        *,
        m1_candles: list[Candle],
        m5_candles: list[Candle],
        m15_candles: list[Candle] | None,
        h1_candles: list[Candle] | None,
        dxy_candles: list[Candle] | None,
        tick: SymbolTick,
        recent_high_importance_news: list[NewsArticle],
        min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
        max_spread_points: float = _DEFAULT_MAX_SPREAD_POINTS,
    ) -> MicroScalpingAnalysisOutcome:
        """Run one Micro Scalping analysis cycle.

        Args:
            m1_candles: Primary M1 candles, ordered by timestamp
                ascending -- used only for this engine's own momentum-burst gate.
            m5_candles: Primary M5 candles, passed through to Shakky
                unchanged (Shakky's own primary timeframe).
            m15_candles: Confirmation M15 candles, if available.
            h1_candles: Confirmation H1 candles, if available. Per this
                engine's own narrower timeframe spec (M1/M5 primary,
                M15/H1 confirmation only), H4/D1 are never passed to
                Shakky here -- Shakky's own confirmation logic simply
                skips whichever timeframes it isn't given.
            dxy_candles: Recent DXY candles, if configured (Shakky's own
                intermarket confirmation family).
            tick: Current bid/ask quote.
            recent_high_importance_news: Recent high-importance articles,
                most recent first (`NewsArticleRepository.list_high_importance`).
            min_confidence: Minimum Trend Confidence score (0-100) to
                enter -- this engine's own "high confidence" requirement.
                Passed per-call (like Scalping/Swing's own
                `confidence_threshold_pct`) so `RuntimeSettings` changes
                apply without restarting the service.
            max_spread_points: Maximum acceptable spread, in price points.

        Returns:
            A `MicroScalpingAnalysisOutcome`.
        """
        outcome = await self._shakky.analyze(
            m5_candles=m5_candles,
            m15_candles=m15_candles,
            h1_candles=h1_candles,
            h4_candles=None,
            d1_candles=None,
            dxy_candles=dxy_candles,
            tick=tick,
        )
        if outcome.signal is None:
            return MicroScalpingAnalysisOutcome(
                signal=None,
                direction=outcome.direction,
                confirmation_count=outcome.confirmation_count,
                trend_confidence_score=None,
                reasons=outcome.reasons,
            )

        shakky_signal = outcome.signal
        reasons = list(shakky_signal.reasons)

        for gate_result in (
            check_spread(tick, max_spread_points=max_spread_points),
            check_liquidity(tick),
            check_momentum(m1_candles),
            check_recent_high_impact_news(recent_high_importance_news, now=tick.timestamp),
        ):
            reasons.extend(gate_result.reasons)
            if not gate_result.passed:
                return MicroScalpingAnalysisOutcome(
                    signal=None,
                    direction=shakky_signal.direction,
                    confirmation_count=outcome.confirmation_count,
                    trend_confidence_score=None,
                    reasons=reasons,
                )

        trend_confidence = assess_trend_confidence(
            direction=shakky_signal.direction,
            entry_price=shakky_signal.entry_price,
            d1_candles=None,
            h4_candles=None,
            h1_candles=h1_candles,
            m15_candles=m15_candles,
            m5_candles=m5_candles,
            dxy_candles=dxy_candles,
        )
        reasons.extend(trend_confidence.reasons)
        if trend_confidence.score < min_confidence:
            reasons.append(
                f"confidence_below_threshold:{trend_confidence.score:.1f}<{min_confidence:.1f}"
            )
            return MicroScalpingAnalysisOutcome(
                signal=None,
                direction=shakky_signal.direction,
                confirmation_count=outcome.confirmation_count,
                trend_confidence_score=trend_confidence.score,
                reasons=reasons,
            )

        return MicroScalpingAnalysisOutcome(
            signal=MicroScalpingSignal(
                direction=shakky_signal.direction,
                entry_price=shakky_signal.entry_price,
                stop_loss=shakky_signal.stop_loss,
                confirmations=list(shakky_signal.confirmations),
                dominant_family=shakky_signal.dominant_family,
                reasons=reasons,
            ),
            direction=shakky_signal.direction,
            confirmation_count=outcome.confirmation_count,
            trend_confidence_score=trend_confidence.score,
            reasons=reasons,
        )


__all__ = [
    "MicroScalpingAnalysisOutcome",
    "MicroScalpingAnalysisService",
    "MicroScalpingSignal",
]
