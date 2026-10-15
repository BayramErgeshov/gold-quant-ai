"""Micro Scalping's own additional entry gates, layered on top of Shakky's signal.

Per the engine's own spec: "Reuse the existing Shakky confirmation
logic... Do NOT invent a new strategy. The difference is only trade
management." These gates run only *after* Shakky itself has already
found a qualifying signal (>= 3 confirmations, its own baseline "strong
confirmation" bar) -- they narrow that signal down further to the
specific conditions this engine's many-small-trades approach needs
(low spread, real session liquidity, a fresh momentum burst, no
just-published high-impact news), never loosen or replace Shakky's own
entry logic.

Every gate is a small, independently testable, deterministic function
returning an honest pass/fail plus its own reason -- no fabricated
"confidence" score. Reuses `src.engines.scalping_engine.microstructure`
(session classification, momentum-burst detection) rather than
duplicating that logic, matching this platform's "never invent a second
implementation" convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.core.execution.mt5_client import SymbolTick
from src.engines.scalping_engine.microstructure import (
    Session,
    classify_session,
    detect_momentum_burst,
)
from src.models.candle import Candle
from src.models.news_article import NewsArticle

# London/New York/their overlap only -- Asia and closed-market hours have
# thinner liquidity, which makes the fast, small-target exits this engine
# relies on less reliable.
_LIQUID_SESSIONS: frozenset[Session] = frozenset({"london", "new_york", "london_new_york_overlap"})

# Same XAUUSD point-size convention as
# `src.workflows.market_update.pipeline._POINT_SIZE`, duplicated locally
# (not imported) so this engine's own gates stay independent of that
# module, matching how Shakky's own DXY-proxy code already does this.
# Production incident: this was originally set to 5.0, an arbitrary
# "sounds tight" guess never checked against this broker/account's
# actual quoted spread. Live logs showed this account's real XAUUSD
# spread sitting at a stable ~36 points every single cycle (never
# below it), so every entry was silently rejected -- the engine never
# once qualified a trade. 60.0 sits comfortably above that observed
# baseline while still meaningfully rejecting a genuinely blown-out
# spread (e.g. a news-driven widening), and is overridable per-cycle
# via `RuntimeSettings.micro_scalping_max_spread_points` so a future
# shift in the account's real spread can be corrected from Settings
# without another code change.
_POINT_SIZE = 0.01
_DEFAULT_MAX_SPREAD_POINTS = 60.0
# How recently a high-importance article must have published to count as
# "active news risk right now" -- an honest read of the best data this
# platform actually has (retrospective news ingestion), not a fabricated
# forward-looking economic calendar the platform does not maintain.
_NEWS_BLACKOUT_MINUTES = 15.0
_MIN_NEWS_IMPORTANCE = 0.7


@dataclass(frozen=True, slots=True)
class EntryGateResult:
    """One gate's pass/fail verdict, with its own reason if it blocked.

    Attributes:
        passed: Whether this gate allows the trade to proceed.
        reasons: Human-readable detail (empty when passed silently).
    """

    passed: bool
    reasons: list[str] = field(default_factory=list)


def check_spread(
    tick: SymbolTick, *, max_spread_points: float = _DEFAULT_MAX_SPREAD_POINTS
) -> EntryGateResult:
    """Require a tight spread -- a wide spread alone can exceed this engine's whole profit target.

    Args:
        tick: Current bid/ask quote.
        max_spread_points: Maximum acceptable spread, in price points.

    Returns:
        An `EntryGateResult`.
    """
    spread_points = (tick.ask - tick.bid) / _POINT_SIZE
    if spread_points > max_spread_points:
        return EntryGateResult(
            passed=False,
            reasons=[f"spread_too_wide:{spread_points:.1f}pts>{max_spread_points:.1f}pts"],
        )
    return EntryGateResult(passed=True)


def check_liquidity(tick: SymbolTick) -> EntryGateResult:
    """Require a real-liquidity trading session (London/New York/overlap).

    Args:
        tick: Current quote, used only for its timestamp.

    Returns:
        An `EntryGateResult`. Asia and closed-market hours are excluded
        -- thinner liquidity makes the fast, small-target exits this
        engine relies on less reliable.
    """
    session = classify_session(tick.timestamp)
    if session not in _LIQUID_SESSIONS:
        return EntryGateResult(passed=False, reasons=[f"insufficient_liquidity_session:{session}"])
    return EntryGateResult(passed=True, reasons=[f"liquid_session:{session}"])


def check_momentum(m1_candles: list[Candle]) -> EntryGateResult:
    """Require a fresh, measurable momentum burst on the fastest primary timeframe.

    Args:
        m1_candles: M1 candles, ordered by timestamp ascending.

    Returns:
        An `EntryGateResult`.
    """
    burst = detect_momentum_burst(m1_candles)
    if burst is None:
        return EntryGateResult(passed=False, reasons=["no_momentum_burst"])
    return EntryGateResult(
        passed=True, reasons=[f"momentum_burst_{burst.direction}:{burst.atr_multiple:.1f}x_atr"]
    )


def check_recent_high_impact_news(
    recent_high_importance_articles: list[NewsArticle],
    *,
    now: datetime,
    blackout_minutes: float = _NEWS_BLACKOUT_MINUTES,
) -> EntryGateResult:
    """Block entry if a high-importance article just published (active news-driven volatility risk).

    Args:
        recent_high_importance_articles: Recent articles with
            `importance_score >= _MIN_NEWS_IMPORTANCE`, most recent
            first (`NewsArticleRepository.list_high_importance`).
        now: Current time (UTC).
        blackout_minutes: How recently an article must have published
            to still count as active risk.

    Returns:
        An `EntryGateResult`. Passes honestly (never blocks) when no
        high-importance news data exists at all -- this platform has no
        forward-looking economic calendar, so this can only ever detect
        news that has *already* published, not predict upcoming
        releases; an empty list means "no data," not "no risk."
    """
    if not recent_high_importance_articles:
        return EntryGateResult(passed=True)
    most_recent = recent_high_importance_articles[0]
    published_at = most_recent.published_at
    # Some drivers (e.g. this platform's own faster SQLite-backed unit
    # tests) return naive datetimes even for a `DateTime(timezone=True)`
    # column; every timestamp in this platform is UTC internally.
    aware_published_at = (
        published_at if published_at.tzinfo is not None else published_at.replace(tzinfo=UTC)
    )
    age = now - aware_published_at
    if age <= timedelta(minutes=blackout_minutes):
        return EntryGateResult(
            passed=False,
            reasons=[f"recent_high_impact_news:{most_recent.title[:60]!r}"],
        )
    return EntryGateResult(passed=True)
