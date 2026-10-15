"""Historical statistical validation for extracted book claims.

Per the Institutional Knowledge Research System spec: "Every extracted
hypothesis auto-enters the Research Engine: backtest... only
statistically validated ideas become available to Chief AI, otherwise
marked Rejected/Weak evidence/Needs more data."

Free-text claims cannot be mechanically translated into an arbitrary
backtestable strategy without fabricating an NLP capability this
platform does not have. Instead, this module only validates claims whose
topic already maps to one of this platform's own testable Technical
Department agents (`_TOPIC_AGENTS`) — reusing each agent's own
already-built `analyze()` signal exactly as Chief AI already consumes it
in production, rather than inventing a new rule from the claim's prose.
Claims on every other topic (macro, psychology, risk, ...) honestly stay
"unknown" — BOOK_RAG.md's own rule that "No claim becomes production
knowledge automatically" already covers the case where this platform has
no mechanism to test it yet.

This module only updates `BookClaim.validation_status`; it never feeds a
claim into any live trading decision (BOOK_RAG.md: "Books are NOT
truth... The market has higher priority than any author's opinion" —
still gated behind a later, explicit wiring decision).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.agents.technical.liquidity import LiquidityAgent
from src.agents.technical.market_structure import MarketStructureAgent
from src.agents.technical.price_action import PriceActionAgent
from src.agents.technical.smart_money import SmartMoneyAgent
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.statistics_engine.performance import expectancy_pct, win_rate
from src.models.candle import Candle
from src.repositories.book_claim_repository import BookClaimRepository
from src.utils.statistics import forward_return_pct

# Only topics with a real, already-built directional Technical Department
# agent are testable this way. `volatility` is deliberately excluded: its
# own agent's bias is always "neutral" (VolatilityAgent's own docstring:
# "volatility has no direction"), so it has nothing to backtest.
_TOPIC_AGENTS: dict[str, type[TechnicalAgent]] = {
    "market_structure": MarketStructureAgent,
    "liquidity": LiquidityAgent,
    "smart_money": SmartMoneyAgent,
    "price_action": PriceActionAgent,
}
_WINDOW_SIZE = 30
_FORWARD_BARS = 10
# The classic minimum sample size for a Central-Limit-Theorem-backed
# estimate to be even provisionally meaningful -- not a precisely tuned
# number, a floor below which "insufficient data" is the only honest answer.
_MIN_SIGNAL_OCCURRENCES = 30
_MIN_SIGNAL_CONFIDENCE = 0.6
_MIN_EXPECTANCY_PCT_FOR_ACCEPTANCE = 0.05


@dataclass(frozen=True, slots=True)
class ClaimValidationResult:
    """Outcome of validating a single claim against real price history.

    Attributes:
        claim_id: The validated `BookClaim` id.
        status: "accepted", "rejected", or "unknown" (no testable agent
            for this topic, or too few historical signal occurrences).
        reason: A human-readable explanation, always citing the actual
            sample size/win rate/expectancy computed — never a bare label.
        sample_size: Number of historical signal occurrences used.
        win_rate: Fraction of occurrences followed by a favorable move in
            the claimed direction. 0.0 if `status != "accepted"`.
        expectancy_pct: Average signed forward return, in percent. 0.0 if
            `status != "accepted"`.
    """

    claim_id: uuid.UUID
    status: str
    reason: str
    sample_size: int
    win_rate: float
    expectancy_pct: float


def _collect_signal_returns(agent: TechnicalAgent, candles: list[Candle]) -> list[float]:
    """Walk a rolling window over `candles`, collecting the agent's signed forward returns.

    A bearish signal's "success" is a favorable move in *its* direction
    (price falling), so its raw forward return is sign-flipped before
    being added to the sample — `win_rate`/`expectancy_pct` then treat
    every entry uniformly as "was this signal followed by a favorable move."
    """
    returns: list[float] = []
    for end_index in range(_WINDOW_SIZE, len(candles) - _FORWARD_BARS + 1):
        window = candles[end_index - _WINDOW_SIZE : end_index]
        report = agent.analyze(window)
        if report.bias == "neutral" or report.confidence < _MIN_SIGNAL_CONFIDENCE:
            continue
        entry_price = candles[end_index - 1].close
        exit_price = candles[end_index - 1 + _FORWARD_BARS].close
        raw_return = forward_return_pct(entry_price, exit_price)
        returns.append(raw_return if report.bias == "bullish" else -raw_return)
    return returns


class ClaimValidationService:
    """Runs historical statistical validation for every pending book claim."""

    def __init__(self, *, claim_repository: BookClaimRepository) -> None:
        """Initialize the service (constructor injection).

        Args:
            claim_repository: Persists validation outcomes back onto each `BookClaim`.
        """
        self._claims = claim_repository

    async def validate_pending_claims(
        self, candles: list[Candle], *, limit: int = 100
    ) -> list[ClaimValidationResult]:
        """Validate every pending claim against a candle history and persist the outcome.

        Args:
            candles: Historical candles for the primary symbol, ordered by
                timestamp ascending — the only market this platform has
                deep enough history to test a claim against today.
            limit: Maximum number of pending claims to process this cycle.

        Returns:
            One `ClaimValidationResult` per processed claim.
        """
        pending = await self._claims.list_pending(limit=limit)
        results: list[ClaimValidationResult] = []
        for claim in pending:
            agent_class = _TOPIC_AGENTS.get(claim.topic) if claim.topic else None
            if agent_class is None:
                result = ClaimValidationResult(
                    claim_id=claim.id,
                    status="unknown",
                    reason=f"no_testable_agent_for_topic:{claim.topic!r}",
                    sample_size=0,
                    win_rate=0.0,
                    expectancy_pct=0.0,
                )
            else:
                result = self._validate_against_agent(claim.id, agent_class(), candles)

            claim.validation_status = result.status
            claim.confidence = result.win_rate if result.status == "accepted" else 0.0
            await self._claims.add(claim)
            results.append(result)

        return results

    def _validate_against_agent(
        self, claim_id: uuid.UUID, agent: TechnicalAgent, candles: list[Candle]
    ) -> ClaimValidationResult:
        returns_pct = _collect_signal_returns(agent, candles)
        sample_size = len(returns_pct)
        if sample_size < _MIN_SIGNAL_OCCURRENCES:
            return ClaimValidationResult(
                claim_id=claim_id,
                status="unknown",
                reason=f"insufficient_samples:{sample_size}<{_MIN_SIGNAL_OCCURRENCES}",
                sample_size=sample_size,
                win_rate=0.0,
                expectancy_pct=0.0,
            )

        rate = win_rate(returns_pct)
        expectancy = expectancy_pct(returns_pct)
        accepted = rate > 0.5 and expectancy > _MIN_EXPECTANCY_PCT_FOR_ACCEPTANCE
        reason = (
            f"win_rate={rate:.1%} expectancy={expectancy:.3f}% "
            f"over {sample_size} historical occurrences"
        )
        return ClaimValidationResult(
            claim_id=claim_id,
            status="accepted" if accepted else "rejected",
            reason=reason,
            sample_size=sample_size,
            win_rate=rate,
            expectancy_pct=expectancy,
        )
