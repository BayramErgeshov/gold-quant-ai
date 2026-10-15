"""Market Replay Mode session management for the local web UI.

Per the "Market Replay Mode" production requirement: "Complete replay
mode allowing replaying any historical period candle-by-candle,
simulating the market exactly as if live... Allow Pause/Resume/Speed
Control/Step Forward/Step Back." A session is an in-memory, per-process
cursor over an already-loaded chronological candle range -- deliberately
not persisted to the database, since a replay session is a disposable
research tool, not durable trading data (matching this project's
"never fabricate a value" ethos: nothing here is ever written to the
real trade journal or `historical_similarities` table).

Pause/Resume/Speed Control are client-side concerns: the browser decides
how often to call the `step` endpoint (or not at all, i.e. "paused") --
this keeps the server a single, simple `step forward/backward` primitive,
matching this platform's "fastest, extremely minimalistic" web UI
philosophy applied elsewhere (`src.interfaces.web.dashboard_service`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.technical_analysis.agent_registry import default_technical_agents
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.explanation import DecisionExplanation
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.replay_engine.decision import ReplayDecisionStep, compute_replay_decision
from src.models.candle import Candle
from src.models.market_regime import REGIME_TYPES, MarketRegime
from src.repositories.candle_repository import CandleRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.market_regime_repository import MarketRegimeRepository
from src.repositories.news_article_repository import NewsArticleRepository
from src.repositories.symbol_repository import SymbolRepository

_DEFAULT_WINDOW_SIZE = 20
# A generous cap on one replay session's candle range -- large enough for
# any realistic manual research session, small enough to keep the whole
# range comfortably in memory for the life of the (single-operator,
# local) web process.
_MAX_CANDLES_PER_SESSION = 20_000


class ReplaySessionNotFoundError(Exception):
    """Raised when a replay session id does not exist (or was never started)."""


class ReplayInsufficientHistoryError(Exception):
    """Raised when a requested replay range has fewer than `window_size` candles."""


@dataclass(frozen=True, slots=True)
class ReplayCandleView:
    """A serializable projection of one `Candle`, for the replay API."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@dataclass(frozen=True, slots=True)
class ReplayStepView:
    """A serializable projection of one `ReplayDecisionStep`."""

    candle: ReplayCandleView
    decision: ChiefAIDecision
    explanation: DecisionExplanation
    market_regime: str
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None


@dataclass(frozen=True, slots=True)
class ReplaySessionView:
    """Everything the replay UI needs after starting or stepping a session.

    Attributes:
        session_id: Opaque id for subsequent `step` calls.
        total_candles: Total candles loaded for this session's range.
        window_size: Candles considered per decision.
        current_index: Index (into the loaded range) of the candle the
            current `step` decided on. -1 before the first step.
        can_step_forward: Whether another candle is available ahead.
        can_step_backward: Whether a prior candle is available behind.
        step: The current step's decision, if at least one has been made.
    """

    session_id: str
    total_candles: int
    window_size: int
    current_index: int
    can_step_forward: bool
    can_step_backward: bool
    step: ReplayStepView | None = None


@dataclass(frozen=True, slots=True)
class ReplayCandidateWindow:
    """One suggested historical period to replay.

    Attributes:
        label: Human-readable description, e.g. an article title or
            "bull_trend (2020-03-01 to 2020-03-15)".
        start: Suggested replay range start (padded before the event/regime).
        end: Suggested replay range end (padded after the event/regime).
    """

    label: str
    start: datetime
    end: datetime


@dataclass
class _ReplaySession:
    symbol_id: uuid.UUID
    timeframe: str
    candles: list[ReplayCandleView]
    window_size: int
    current_index: int = -1
    steps: dict[int, ReplayDecisionStep] = field(default_factory=dict)


# Per-process session store. Deliberately not persisted -- see module docstring.
_SESSIONS: dict[str, _ReplaySession] = {}


def _to_candle_view(candle: Candle) -> ReplayCandleView:
    return ReplayCandleView(
        timestamp=candle.timestamp,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )


def _to_step_view(step: ReplayDecisionStep) -> ReplayStepView:
    return ReplayStepView(
        candle=_to_candle_view(step.candle),
        decision=step.decision,
        explanation=step.explanation,
        market_regime=step.market_regime,
        entry_price=step.entry_price,
        stop_loss=step.stop_loss,
        take_profit=step.take_profit,
    )


def _session_view(session_id: str, session_data: _ReplaySession) -> ReplaySessionView:
    current_step = session_data.steps.get(session_data.current_index)
    return ReplaySessionView(
        session_id=session_id,
        total_candles=len(session_data.candles),
        window_size=session_data.window_size,
        current_index=session_data.current_index,
        can_step_forward=session_data.current_index + 1 < len(session_data.candles),
        can_step_backward=session_data.current_index - 1 >= session_data.window_size,
        step=_to_step_view(current_step) if current_step is not None else None,
    )


async def _decide_at(
    db_session: AsyncSession, session_data: _ReplaySession, index: int
) -> ReplayDecisionStep:
    cached = session_data.steps.get(index)
    if cached is not None:
        return cached

    window = _candle_views_to_candles(
        session_data.candles[index - session_data.window_size : index],
        symbol_id=session_data.symbol_id,
        timeframe=session_data.timeframe,
    )
    next_candle = _candle_views_to_candles(
        [session_data.candles[index]],
        symbol_id=session_data.symbol_id,
        timeframe=session_data.timeframe,
    )[0]
    step = await compute_replay_decision(
        symbol_id=session_data.symbol_id,
        timeframe=session_data.timeframe,
        window=window,
        next_candle=next_candle,
        technical_agents=default_technical_agents(),
        similarity_service=HistoricalSimilarityService(
            candle_repository=CandleRepository(db_session),
            similarity_repository=HistoricalSimilarityRepository(db_session),
        ),
    )
    session_data.steps[index] = step
    return step


def _candle_views_to_candles(
    views: list[ReplayCandleView], *, symbol_id: uuid.UUID, timeframe: str
) -> list[Candle]:
    """Adapt cached `ReplayCandleView`s back into (unpersisted) `Candle` instances.

    Session state stores the lightweight, serializable view (so it can
    outlive any single DB session/request) rather than SQLAlchemy
    instances, which risk `DetachedInstanceError` once their owning
    session closes. These `Candle` objects are constructed loosely
    (never added to a session), exactly like this codebase's own test
    fixtures build candles -- never persisted, purely in-memory inputs
    for `compute_replay_decision` and the technical agents.
    """
    return [
        Candle(
            symbol_id=symbol_id,
            timeframe=timeframe,
            timestamp=view.timestamp,
            open=view.open,
            high=view.high,
            low=view.low,
            close=view.close,
            volume=view.volume,
            source="replay",
        )
        for view in views
    ]


async def start_replay_session(
    db_session: AsyncSession,
    *,
    symbol_name: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    window_size: int = _DEFAULT_WINDOW_SIZE,
) -> ReplaySessionView:
    """Start a new Market Replay Mode session over a historical candle range.

    Args:
        db_session: The active database session (used only to load
            candles and compute the first step; not held open by the
            session afterward).
        symbol_name: The platform `Symbol` name, e.g. "XAUUSD".
        timeframe: One of `src.models.candle.TIMEFRAMES`.
        start: Inclusive range start.
        end: Inclusive range end.
        window_size: Candles considered per decision.

    Returns:
        A `ReplaySessionView` with the first step already decided, if
        the range has enough history.

    Raises:
        ReplayInsufficientHistoryError: If the range has fewer than
            `window_size + 1` candles (not enough to decide even one step).
    """
    symbol = await SymbolRepository(db_session).get_by_name(symbol_name)
    if symbol is None:
        raise ReplayInsufficientHistoryError(f"unknown_symbol:{symbol_name}")

    candles = await CandleRepository(db_session).list_range(
        symbol.id, timeframe, start=start, end=end, limit=_MAX_CANDLES_PER_SESSION
    )
    if len(candles) <= window_size:
        raise ReplayInsufficientHistoryError(
            f"need_more_than_{window_size}_candles_got_{len(candles)}"
        )

    session_id = uuid.uuid4().hex
    session_data = _ReplaySession(
        symbol_id=symbol.id,
        timeframe=timeframe,
        candles=[_to_candle_view(candle) for candle in candles],
        window_size=window_size,
    )
    _SESSIONS[session_id] = session_data

    session_data.current_index = window_size
    await _decide_at(db_session, session_data, window_size)
    return _session_view(session_id, session_data)


async def step_replay_session(
    db_session: AsyncSession, session_id: str, *, direction: str
) -> ReplaySessionView:
    """Advance or retreat a replay session by one candle.

    Args:
        db_session: The active database session.
        session_id: The session to step.
        direction: "forward" or "backward".

    Returns:
        The updated `ReplaySessionView`.

    Raises:
        ReplaySessionNotFoundError: If no such session exists.
    """
    session_data = _SESSIONS.get(session_id)
    if session_data is None:
        raise ReplaySessionNotFoundError(session_id)

    if direction == "forward" and session_data.current_index + 1 < len(session_data.candles):
        session_data.current_index += 1
        await _decide_at(db_session, session_data, session_data.current_index)
    elif direction == "backward" and session_data.current_index - 1 >= session_data.window_size:
        session_data.current_index -= 1

    return _session_view(session_id, session_data)


def get_replay_session(session_id: str) -> ReplaySessionView:
    """Fetch a replay session's current state without stepping it.

    Args:
        session_id: The session to look up.

    Returns:
        The current `ReplaySessionView`.

    Raises:
        ReplaySessionNotFoundError: If no such session exists.
    """
    session_data = _SESSIONS.get(session_id)
    if session_data is None:
        raise ReplaySessionNotFoundError(session_id)
    return _session_view(session_id, session_data)


async def find_high_impact_news_windows(
    db_session: AsyncSession, *, min_importance: float = 0.7, padding_hours: int = 6
) -> list[ReplayCandidateWindow]:
    """Suggest replay windows around major news events.

    Per the "Market Replay Mode" production requirement: "Allow replay
    of Major News Events (CPI/NFP/FOMC)."

    Args:
        db_session: The active database session.
        min_importance: Minimum `NewsArticle.importance_score` to suggest.
        padding_hours: Hours of context to include before/after the
            article's `published_at`.

    Returns:
        One `ReplayCandidateWindow` per matching article, most recent first.
    """
    articles = await NewsArticleRepository(db_session).list_high_importance(
        min_importance=min_importance
    )
    padding = timedelta(hours=padding_hours)
    return [
        ReplayCandidateWindow(
            label=article.title,
            start=article.published_at - padding,
            end=article.published_at + padding,
        )
        for article in articles
    ]


async def find_regime_windows(
    db_session: AsyncSession, *, symbol_name: str, timeframe: str, regime_type: str
) -> list[ReplayCandidateWindow]:
    """Suggest replay windows covering a given market regime.

    Per the "Market Replay Mode" production requirement: "Allow replay
    of ... Trending Markets, Ranging Markets."

    Args:
        db_session: The active database session.
        symbol_name: The platform `Symbol` name, e.g. "XAUUSD".
        timeframe: One of `src.models.candle.TIMEFRAMES`.
        regime_type: One of `src.models.market_regime.REGIME_TYPES`.

    Returns:
        One `ReplayCandidateWindow` per historical period classified as
        `regime_type`, most recent first. Empty if the symbol is unknown
        or `regime_type` is not a recognized regime -- never a fabricated
        window.
    """
    if regime_type not in REGIME_TYPES:
        return []

    symbol = await SymbolRepository(db_session).get_by_name(symbol_name)
    if symbol is None:
        return []

    periods = await MarketRegimeRepository(db_session).list_by_symbol(symbol.id, timeframe)
    matching = [period for period in periods if period.regime == regime_type]

    def _label(period: MarketRegime) -> str:
        return f"{regime_type} ({period.start_timestamp.date()} to {period.end_timestamp.date()})"

    return [
        ReplayCandidateWindow(
            label=_label(period), start=period.start_timestamp, end=period.end_timestamp
        )
        for period in reversed(matching)
    ]
