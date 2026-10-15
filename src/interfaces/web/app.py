"""Minimalistic local web UI (production "User Interface" requirement).

"Fastest possible interface... Extremely minimalistic. Main page:
Current Market, Confidence, Active Strategy, Open Positions, Today's
PnL, AI Explanation. Settings: Lot Size, Auto Trading, Confidence
Threshold, Telegram, Strategy Selection, Risk Mode." Runs as its own
process, independent of `LiveTradingLoop` -- reads/writes only durable,
already-persisted data (the trade journal, `SystemLog` scan snapshots,
`RuntimeSettings`), never a direct MT5 connection.

Binds to localhost only (see `scripts/run_web_ui.py`); no authentication
is implemented, matching the "fastest possible, extremely minimalistic"
requirement for a single-operator local tool -- do not expose this
process's port to an untrusted network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.execution.mt5_client import RealMT5Client
from src.database.postgres.session import get_session
from src.interfaces.web.books_service import BooksPageView, get_books_page
from src.interfaces.web.books_template import render_books_html
from src.interfaces.web.chart_service import ChartData, get_chart_data
from src.interfaces.web.chart_template import render_chart_html
from src.interfaces.web.dashboard_service import DashboardStatus, get_dashboard_status
from src.interfaces.web.emergency_close import EmergencyCloseResult, emergency_close_all_positions
from src.interfaces.web.performance_service import PerformancePageView, get_performance_page
from src.interfaces.web.process_control import (
    is_live_loop_running,
    restart_live_loop,
    start_live_loop,
    stop_live_loop,
)
from src.interfaces.web.replay_service import (
    ReplayCandidateWindow,
    ReplayInsufficientHistoryError,
    ReplaySessionNotFoundError,
    ReplaySessionView,
    find_high_impact_news_windows,
    find_regime_windows,
    get_replay_session,
    start_replay_session,
    step_replay_session,
)
from src.interfaces.web.settings_service import (
    SettingsUpdate,
    SettingsView,
    get_current_settings,
    update_settings,
)
from src.interfaces.web.strategy_performance_service import (
    StrategyPerformanceView,
    get_strategy_performance,
)
from src.interfaces.web.strategy_profile_service import (
    ModuleUpdate,
    ProfileNotFoundError,
    StrategyProfilesView,
    StrategyProfileView,
    UnknownModuleError,
    UnknownStrategyError,
    assign_strategy_profile,
    delete_strategy_profile,
    get_strategy_profiles,
    save_strategy_profile,
)
from src.interfaces.web.templates import (
    render_dashboard_html,
    render_settings_html,
    render_strategy_builder_html,
    render_strategy_comparison_html,
)
from src.interfaces.web.weight_recommendation_service import (
    WeightRecommendationAlreadyDecidedError,
    WeightRecommendationNotFoundError,
    WeightRecommendationsView,
    WeightRecommendationView,
    approve_weight_recommendation,
    get_weight_recommendations,
    reject_weight_recommendation,
    to_view,
)
from src.repositories.symbol_repository import SymbolRepository
from src.settings import get_settings

_CHART_TIMEFRAME = "M15"

app = FastAPI(title="GOLD QUANT AI", docs_url=None, redoc_url=None)


async def _get_db() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


class ReplayStartPayload(BaseModel):
    """Request body for `POST /api/replay/start`."""

    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    window_size: int = 20


class ReplayStepPayload(BaseModel):
    """Request body for `POST /api/replay/{session_id}/step`."""

    direction: str


class SettingsPayload(BaseModel):
    """Request body for `POST /api/settings` -- mirrors `SettingsUpdate`."""

    fixed_lot_size: float | None = None
    clear_fixed_lot_size: bool = False
    auto_trading_enabled: bool | None = None
    confidence_threshold: float | None = None
    clear_confidence_threshold: bool = False
    intraday_enabled: bool | None = None
    scalping_enabled: bool | None = None
    swing_enabled: bool | None = None
    shakky_enabled: bool | None = None
    shakky_dynamic_tp_enabled: bool | None = None
    shakky_scaling_enabled: bool | None = None
    scalping_confidence_threshold: float | None = None
    clear_scalping_confidence_threshold: bool = False
    swing_confidence_threshold: float | None = None
    clear_swing_confidence_threshold: bool = False
    risk_mode: str | None = None
    max_positions: int | None = None
    clear_max_positions: bool = False
    books_folder: str | None = None
    clear_books_folder: bool = False
    paused: bool | None = None
    min_trade_quality_score: float | None = None
    clear_min_trade_quality_score: bool = False
    demo_learning_mode_enabled: bool | None = None
    micro_scalping_enabled: bool | None = None
    micro_scalping_min_confidence: float | None = None
    clear_micro_scalping_min_confidence: bool = False
    micro_scalping_max_holding_minutes: float | None = None
    clear_micro_scalping_max_holding_minutes: bool = False
    micro_scalping_dynamic_profit_target_enabled: bool | None = None
    micro_scalping_trailing_stop_enabled: bool | None = None
    micro_scalping_lot_mode: str | None = None
    micro_scalping_fixed_lot_size: float | None = None
    clear_micro_scalping_fixed_lot_size: bool = False
    micro_scalping_max_spread_points: float | None = None
    clear_micro_scalping_max_spread_points: bool = False


class StrategyProfileModulePayload(BaseModel):
    """One module's setting within `StrategyProfileSavePayload`."""

    module_name: str
    enabled: bool = True
    weight: float = 1.0
    min_confidence: float | None = None


class StrategyProfileSavePayload(BaseModel):
    """Request body for `POST /api/strategy-profiles`."""

    name: str
    modules: list[StrategyProfileModulePayload] = []


class StrategyProfileAssignPayload(BaseModel):
    """Request body for `POST /api/strategy-profiles/assign`."""

    strategy: str
    profile_name: str | None = None


@app.get("/", response_class=HTMLResponse)
async def dashboard(session: AsyncSession = Depends(_get_db)) -> str:
    """Serve the main dashboard page."""
    status = await get_dashboard_status(session)
    return render_dashboard_html(status)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(session: AsyncSession = Depends(_get_db)) -> str:
    """Serve the settings page."""
    view = await get_current_settings(session)
    return render_settings_html(view)


@app.get("/books", response_class=HTMLResponse)
async def books_page(session: AsyncSession = Depends(_get_db)) -> str:
    """Serve the Books page (processing progress + hypotheses)."""
    view = await get_books_page(session)
    return render_books_html(view)


@app.get("/strategy-builder", response_class=HTMLResponse)
async def strategy_builder_page(session: AsyncSession = Depends(_get_db)) -> str:
    """Serve the Strategy Builder page."""
    view = await get_strategy_profiles(session)
    return render_strategy_builder_html(view)


@app.get("/strategy-comparison", response_class=HTMLResponse)
async def strategy_comparison_page(session: AsyncSession = Depends(_get_db)) -> str:
    """Serve the "Сравнение стратегий" page."""
    view = await get_strategy_performance(session)
    return render_strategy_comparison_html(view)


@app.get("/chart", response_class=HTMLResponse)
async def chart_page(session: AsyncSession = Depends(_get_db)) -> str:
    """Serve the chart page (candles + Order Blocks/FVG/Liquidity/S&R/BOS/CHOCH/Swing overlays)."""
    market_symbol = get_settings().platform.symbols.primary
    symbol = await SymbolRepository(session).get_by_name(market_symbol)
    data = (
        await get_chart_data(session, symbol_id=symbol.id, timeframe=_CHART_TIMEFRAME)
        if symbol is not None
        else ChartData()
    )
    return render_chart_html(data, market=market_symbol)


@app.get("/api/status")
async def api_status(session: AsyncSession = Depends(_get_db)) -> DashboardStatus:
    """Return the current dashboard status as JSON."""
    return await get_dashboard_status(session)


@app.get("/api/chart")
async def api_chart(session: AsyncSession = Depends(_get_db)) -> ChartData:
    """Return the current chart data as JSON."""
    symbol = await SymbolRepository(session).get_by_name(get_settings().platform.symbols.primary)
    if symbol is None:
        return ChartData()
    return await get_chart_data(session, symbol_id=symbol.id, timeframe=_CHART_TIMEFRAME)


@app.get("/api/books")
async def api_books(session: AsyncSession = Depends(_get_db)) -> BooksPageView:
    """Return the current Books page data as JSON."""
    return await get_books_page(session)


@app.get("/api/performance")
async def api_performance(session: AsyncSession = Depends(_get_db)) -> PerformancePageView:
    """Return the full Performance Validation Framework report as JSON."""
    return await get_performance_page(session)


@app.get("/api/performance/by-strategy")
async def api_performance_by_strategy(
    session: AsyncSession = Depends(_get_db),
) -> StrategyPerformanceView:
    """Return each strategy's own, completely separate performance statistics."""
    return await get_strategy_performance(session)


@app.get("/api/weight-recommendations")
async def api_weight_recommendations(
    session: AsyncSession = Depends(_get_db),
) -> WeightRecommendationsView:
    """Return every AI Weight Optimizer recommendation as JSON."""
    return await get_weight_recommendations(session)


@app.post("/api/weight-recommendations/{recommendation_id}/approve")
async def api_approve_weight_recommendation(
    recommendation_id: str, session: AsyncSession = Depends(_get_db)
) -> WeightRecommendationView:
    """Approve a pending weight recommendation, pinning its suggested weight."""
    try:
        return to_view(await approve_weight_recommendation(session, recommendation_id))
    except WeightRecommendationNotFoundError as error:
        raise HTTPException(status_code=404, detail="recommendation not found") from error
    except WeightRecommendationAlreadyDecidedError as error:
        raise HTTPException(status_code=409, detail="recommendation already decided") from error


@app.post("/api/weight-recommendations/{recommendation_id}/reject")
async def api_reject_weight_recommendation(
    recommendation_id: str, session: AsyncSession = Depends(_get_db)
) -> WeightRecommendationView:
    """Reject a pending weight recommendation -- the live weight is left untouched."""
    try:
        return to_view(await reject_weight_recommendation(session, recommendation_id))
    except WeightRecommendationNotFoundError as error:
        raise HTTPException(status_code=404, detail="recommendation not found") from error
    except WeightRecommendationAlreadyDecidedError as error:
        raise HTTPException(status_code=409, detail="recommendation already decided") from error


@app.post("/api/replay/start")
async def api_replay_start(
    payload: ReplayStartPayload, session: AsyncSession = Depends(_get_db)
) -> ReplaySessionView:
    """Start a new Market Replay Mode session over a historical candle range."""
    try:
        return await start_replay_session(
            session,
            symbol_name=payload.symbol,
            timeframe=payload.timeframe,
            start=payload.start,
            end=payload.end,
            window_size=payload.window_size,
        )
    except ReplayInsufficientHistoryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/replay/{session_id}")
async def api_replay_get(session_id: str) -> ReplaySessionView:
    """Return a replay session's current state without stepping it."""
    try:
        return get_replay_session(session_id)
    except ReplaySessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="replay session not found") from error


@app.post("/api/replay/{session_id}/step")
async def api_replay_step(
    session_id: str, payload: ReplayStepPayload, session: AsyncSession = Depends(_get_db)
) -> ReplaySessionView:
    """Advance or retreat a replay session by one candle (Step Forward/Step Back)."""
    if payload.direction not in ("forward", "backward"):
        raise HTTPException(status_code=400, detail="direction must be forward or backward")
    try:
        return await step_replay_session(session, session_id, direction=payload.direction)
    except ReplaySessionNotFoundError as error:
        raise HTTPException(status_code=404, detail="replay session not found") from error


@app.get("/api/replay/candidates/news")
async def api_replay_candidates_news(
    min_importance: float = 0.7, session: AsyncSession = Depends(_get_db)
) -> list[ReplayCandidateWindow]:
    """Suggest replay windows around major news events."""
    return await find_high_impact_news_windows(session, min_importance=min_importance)


@app.get("/api/replay/candidates/regime")
async def api_replay_candidates_regime(
    regime_type: str, session: AsyncSession = Depends(_get_db)
) -> list[ReplayCandidateWindow]:
    """Suggest replay windows covering a given market regime."""
    return await find_regime_windows(
        session,
        symbol_name=get_settings().platform.symbols.primary,
        timeframe=_CHART_TIMEFRAME,
        regime_type=regime_type,
    )


@app.get("/api/settings")
async def api_get_settings(session: AsyncSession = Depends(_get_db)) -> SettingsView:
    """Return the current settings as JSON."""
    return await get_current_settings(session)


@app.post("/api/settings")
async def api_update_settings(
    payload: SettingsPayload, session: AsyncSession = Depends(_get_db)
) -> SettingsView:
    """Apply a partial settings update."""
    try:
        return await update_settings(session, SettingsUpdate(**payload.model_dump()))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/strategy-profiles")
async def api_strategy_profiles(
    session: AsyncSession = Depends(_get_db),
) -> StrategyProfilesView:
    """Return every saved Strategy Builder profile and current assignments."""
    return await get_strategy_profiles(session)


@app.post("/api/strategy-profiles")
async def api_save_strategy_profile(
    payload: StrategyProfileSavePayload, session: AsyncSession = Depends(_get_db)
) -> StrategyProfileView:
    """Create a new profile, or replace an existing one with the same name."""
    try:
        return await save_strategy_profile(
            session,
            payload.name,
            [
                ModuleUpdate(
                    module_name=module.module_name,
                    enabled=module.enabled,
                    weight=module.weight,
                    min_confidence=module.min_confidence,
                )
                for module in payload.modules
            ],
        )
    except UnknownModuleError as error:
        raise HTTPException(status_code=400, detail=f"unknown module: {error}") from error


@app.delete("/api/strategy-profiles/{name}")
async def api_delete_strategy_profile(
    name: str, session: AsyncSession = Depends(_get_db)
) -> dict[str, bool]:
    """Delete a saved profile by name."""
    deleted = await delete_strategy_profile(session, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="profile not found")
    return {"deleted": True}


@app.post("/api/strategy-profiles/assign")
async def api_assign_strategy_profile(
    payload: StrategyProfileAssignPayload, session: AsyncSession = Depends(_get_db)
) -> StrategyProfilesView:
    """Assign a saved profile to one strategy (or unassign it)."""
    try:
        return await assign_strategy_profile(
            session, strategy=payload.strategy, profile_name=payload.profile_name
        )
    except UnknownStrategyError as error:
        raise HTTPException(status_code=400, detail=f"unknown strategy: {error}") from error
    except ProfileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"profile not found: {error}") from error


@app.get("/api/control/status")
async def api_control_status(session: AsyncSession = Depends(_get_db)) -> dict[str, bool]:
    """Report whether the live loop process is running and whether it is paused."""
    settings = await get_current_settings(session)
    return {"running": is_live_loop_running(), "paused": settings.paused}


@app.post("/api/control/start")
async def api_control_start() -> dict[str, bool]:
    """Start the live loop process (START button), if not already running."""
    return {"started": start_live_loop()}


@app.post("/api/control/stop")
async def api_control_stop() -> dict[str, bool]:
    """Stop the live loop process (STOP button), if currently running."""
    return {"stopped": stop_live_loop()}


@app.post("/api/control/restart")
async def api_control_restart() -> dict[str, bool]:
    """Restart the live loop process (RESTART button)."""
    restart_live_loop()
    return {"running": is_live_loop_running()}


@app.post("/api/control/pause")
async def api_control_pause(session: AsyncSession = Depends(_get_db)) -> SettingsView:
    """Toggle the PAUSE flag (PAUSE button): skip new scans/trades, keep monitoring."""
    current = await get_current_settings(session)
    return await update_settings(session, SettingsUpdate(paused=not current.paused))


@app.post("/api/control/emergency-close")
async def api_control_emergency_close(
    session: AsyncSession = Depends(_get_db),
) -> EmergencyCloseResult:
    """Close every open position immediately and disable auto-trading (EMERGENCY CLOSE)."""
    return await emergency_close_all_positions(session, RealMT5Client(get_settings()))
