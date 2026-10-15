"""Data assembly for the local web UI's settings page.

Per the "Settings" production requirement: "Auto Trading, Fixed/Auto Lot,
Confidence Threshold, Max Positions, Telegram, Books Folder, News
Providers, Correlation Providers, Risk Mode" must be changeable from the
interface. Every provider credential (Telegram bot token, NewsAPI/FRED
API keys) lives in `.env` and is never exposed or editable here -- only a
read-only "configured" status is shown, matching MT5_ENGINE.md's "never
expose a secret through a UI control" convention.

Demo/Live is deliberately NOT exposed here as a toggle: per
FAILSAFE_PROTOCOL.md, enabling live (real-money) trading is a separate,
explicit decision made in code (`account_type`/`live_trading_approved` in
`scripts/run_live_loop.py`), never a single UI click.

Every independent trading style (Intraday/Scalping/Swing) can be
individually enabled or disabled
(`intraday_enabled`/`scalping_enabled`/`swing_enabled`), letting the user
pick any combination -- "Scalping only", "Intraday + Swing", "All
Strategies", etc. (per the "User Configuration" production requirement).
`auto_trading_enabled` remains the master kill switch for all three at
once. Each engine also has its own independent confidence threshold
(`confidence_threshold` for Intraday, `scalping_confidence_threshold`,
`swing_confidence_threshold`) -- a stricter Swing threshold does not
affect Scalping's, and vice versa. Individual AI department toggles
(Trend, Correlation, Order Flow, etc.) are still NOT exposed: disabling
one department mid-vote would silently change every engine's confluence
math in a way this UI cannot honestly preview before saving.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.runtime_settings import RISK_MODES, RuntimeSettings
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.settings import get_settings

# A per-engine confidence threshold at or above this is, in practice, an
# unreachable bar -- no confidence engine on this platform has ever been
# observed anywhere near 95%, so a value this high silently makes that
# whole engine stop trading without the "disabled" state ever showing up
# anywhere in the UI (found in production: `scalping_confidence_threshold`
# was once set to 100.0, which made Scalping reject every signal for
# weeks before anyone noticed). Wanting a strategy off belongs on its own
# `*_enabled` toggle, not an extreme numeric threshold -- so this is
# rejected outright rather than silently accepted.
_MAX_SANE_CONFIDENCE_THRESHOLD = 95.0


@dataclass(frozen=True, slots=True)
class SettingsView:
    """Everything the settings page needs.

    Attributes:
        fixed_lot_size: The current lot-size override, if set. None means
            "auto lot" (the Risk Engine's own position-sizing calculation).
        auto_trading_enabled: Whether the live loop currently executes trades.
        confidence_threshold: The Intraday engine's own confidence-threshold
            override, if set.
        intraday_enabled: Whether the primary (Intraday) engine is enabled.
        scalping_enabled: Whether the independent Scalping Engine is enabled.
        swing_enabled: Whether the independent Swing Engine is enabled.
        shakky_enabled: Whether the independent Classic M5 Strategy
            ("Shakky") Engine is enabled. Unlike the other three, it has
            no confidence-threshold override -- it is purely rule-based
            and never computes a confidence score.
        shakky_dynamic_tp_enabled: Whether Shakky's Trend Confidence-based
            Dynamic Take Profit is active. When False, Shakky's open
            positions keep the fixed take-profit behavior regardless of
            Trend Confidence at entry.
        shakky_scaling_enabled: Whether Shakky may add volume to an
            already-open, already-profitable position on genuine
            strength (Position Scaling). When False, Shakky never scales in.
        scalping_confidence_threshold: The Scalping Engine's own
            confidence-threshold override, if set.
        swing_confidence_threshold: The Swing Engine's own
            confidence-threshold override, if set.
        risk_mode: One of `RISK_MODES`.
        max_positions: The current max-simultaneous-open-positions override,
            if set. None means "no count limit beyond the Risk Engine's own
            percentage-based exposure limits."
        books_folder: The current books-folder override, if set.
        paused: Whether the "Live Control" PAUSE flag is currently set.
        min_trade_quality_score: The current minimum Trade Quality Score
            (0-100) override, if set. None uses `config/risk.yaml`'s own
            configured default.
        telegram_configured: Whether a Telegram bot token is set (read-only).
        news_configured: Whether a NewsAPI key is set (read-only).
        macro_configured: Whether a FRED API key is set (read-only).
        correlated_instruments_enabled: Count of correlated instruments
            with a real MT5 symbol currently enabled (read-only; see
            `src.database.seed.seed_correlated_instruments`).
        demo_learning_mode_enabled: Whether "Demo Learning Mode" is
            currently active -- when True, the optional portfolio-wide
            position cap is skipped and every strategy's own configured
            confidence/quality thresholds are discounted, to maximize
            statistically useful demo trading experience.
        micro_scalping_enabled: Whether the independent Micro Scalping
            Engine is enabled.
        micro_scalping_min_confidence: The Micro Scalping Engine's own
            minimum Trend Confidence override to enter, if set. None uses
            the engine's own constructed default.
        micro_scalping_max_holding_minutes: The maximum time a Micro
            Scalping position may stay open before being closed
            unconditionally, if set. None uses the engine's own
            constructed default.
        micro_scalping_dynamic_profit_target_enabled: Whether Micro
            Scalping may ever extend past its flat profit target on
            strong momentum. When False, it always closes flat at target.
        micro_scalping_trailing_stop_enabled: Whether Micro Scalping may
            trail its stop once its profit target is reached and momentum
            still supports holding. When False, it only ever closes flat.
        micro_scalping_lot_mode: "auto" (risk-based sizing) or "manual"
            (fixed lot, `micro_scalping_fixed_lot_size`).
        micro_scalping_fixed_lot_size: The fixed lot size used when
            `micro_scalping_lot_mode == "manual"`, if set. None uses the
            engine's own small constructed default.
        micro_scalping_max_spread_points: The Micro Scalping Engine's own
            maximum acceptable spread override (in points), if set. None
            uses the engine's own constructed default.
    """

    fixed_lot_size: float | None
    auto_trading_enabled: bool
    confidence_threshold: float | None
    intraday_enabled: bool
    scalping_enabled: bool
    swing_enabled: bool
    shakky_enabled: bool
    shakky_dynamic_tp_enabled: bool
    shakky_scaling_enabled: bool
    scalping_confidence_threshold: float | None
    swing_confidence_threshold: float | None
    risk_mode: str
    max_positions: int | None
    books_folder: str | None
    paused: bool
    min_trade_quality_score: float | None
    telegram_configured: bool
    news_configured: bool
    macro_configured: bool
    correlated_instruments_enabled: int
    demo_learning_mode_enabled: bool
    micro_scalping_enabled: bool
    micro_scalping_min_confidence: float | None
    micro_scalping_max_holding_minutes: float | None
    micro_scalping_dynamic_profit_target_enabled: bool
    micro_scalping_trailing_stop_enabled: bool
    micro_scalping_lot_mode: str
    micro_scalping_fixed_lot_size: float | None
    micro_scalping_max_spread_points: float | None


@dataclass(frozen=True, slots=True)
class SettingsUpdate:
    """User-submitted settings changes; every field is optional (partial update)."""

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


async def _view_from_row(session: AsyncSession, row: RuntimeSettings) -> SettingsView:
    data_providers = get_settings().data_providers
    enabled_instruments = await CorrelatedInstrumentRepository(
        session
    ).list_enabled_with_mt5_symbol()
    return SettingsView(
        fixed_lot_size=row.fixed_lot_size,
        auto_trading_enabled=row.auto_trading_enabled,
        confidence_threshold=row.confidence_threshold,
        intraday_enabled=row.intraday_enabled,
        scalping_enabled=row.scalping_enabled,
        swing_enabled=row.swing_enabled,
        shakky_enabled=row.shakky_enabled,
        shakky_dynamic_tp_enabled=row.shakky_dynamic_tp_enabled,
        shakky_scaling_enabled=row.shakky_scaling_enabled,
        scalping_confidence_threshold=row.scalping_confidence_threshold,
        swing_confidence_threshold=row.swing_confidence_threshold,
        risk_mode=row.risk_mode,
        max_positions=row.max_positions,
        books_folder=row.books_folder,
        paused=row.paused,
        min_trade_quality_score=row.min_trade_quality_score,
        telegram_configured=bool(get_settings().telegram_env.bot_token.get_secret_value()),
        news_configured=bool(data_providers.newsapi_api_key.get_secret_value()),
        macro_configured=bool(data_providers.fred_api_key.get_secret_value()),
        correlated_instruments_enabled=len(enabled_instruments),
        demo_learning_mode_enabled=row.demo_learning_mode_enabled,
        micro_scalping_enabled=row.micro_scalping_enabled,
        micro_scalping_min_confidence=row.micro_scalping_min_confidence,
        micro_scalping_max_holding_minutes=row.micro_scalping_max_holding_minutes,
        micro_scalping_dynamic_profit_target_enabled=(
            row.micro_scalping_dynamic_profit_target_enabled
        ),
        micro_scalping_trailing_stop_enabled=row.micro_scalping_trailing_stop_enabled,
        micro_scalping_lot_mode=row.micro_scalping_lot_mode,
        micro_scalping_fixed_lot_size=row.micro_scalping_fixed_lot_size,
        micro_scalping_max_spread_points=row.micro_scalping_max_spread_points,
    )


async def get_current_settings(session: AsyncSession) -> SettingsView:
    """Fetch the current settings for display.

    Args:
        session: The active database session.

    Returns:
        The current `SettingsView`.
    """
    row = await RuntimeSettingsRepository(session).get_or_create_default()
    return await _view_from_row(session, row)


async def update_settings(session: AsyncSession, update: SettingsUpdate) -> SettingsView:
    """Apply a partial settings update.

    Args:
        session: The active database session.
        update: The fields to change; unset fields are left as-is.

    Returns:
        The resulting `SettingsView`.

    Raises:
        ValueError: If `update.risk_mode` is set to an unrecognized value,
            `update.max_positions` is set below 1,
            `update.min_trade_quality_score` is outside [0, 100], or any
            confidence threshold is outside [0, `_MAX_SANE_CONFIDENCE_THRESHOLD`].
    """
    if update.risk_mode is not None and update.risk_mode not in RISK_MODES:
        raise ValueError(f"risk_mode must be one of {RISK_MODES}, got {update.risk_mode!r}")
    if update.max_positions is not None and update.max_positions < 1:
        raise ValueError(f"max_positions must be at least 1, got {update.max_positions!r}")
    if update.min_trade_quality_score is not None and not (
        0.0 <= update.min_trade_quality_score <= 100.0
    ):
        raise ValueError(
            f"min_trade_quality_score must be in [0, 100], got {update.min_trade_quality_score!r}"
        )
    for field_name, value in (
        ("confidence_threshold", update.confidence_threshold),
        ("scalping_confidence_threshold", update.scalping_confidence_threshold),
        ("swing_confidence_threshold", update.swing_confidence_threshold),
        ("micro_scalping_min_confidence", update.micro_scalping_min_confidence),
    ):
        if value is not None and not (0.0 <= value <= _MAX_SANE_CONFIDENCE_THRESHOLD):
            raise ValueError(
                f"{field_name} must be in [0, {_MAX_SANE_CONFIDENCE_THRESHOLD}], got {value!r} "
                "-- to disable a strategy, use its own *_enabled toggle instead"
            )
    if (
        update.micro_scalping_max_holding_minutes is not None
        and update.micro_scalping_max_holding_minutes <= 0
    ):
        raise ValueError(
            "micro_scalping_max_holding_minutes must be positive, got "
            f"{update.micro_scalping_max_holding_minutes!r}"
        )
    if update.micro_scalping_lot_mode is not None and update.micro_scalping_lot_mode not in (
        "auto",
        "manual",
    ):
        raise ValueError(
            "micro_scalping_lot_mode must be 'auto' or 'manual', got "
            f"{update.micro_scalping_lot_mode!r}"
        )
    if (
        update.micro_scalping_fixed_lot_size is not None
        and update.micro_scalping_fixed_lot_size <= 0
    ):
        raise ValueError(
            f"micro_scalping_fixed_lot_size must be positive, got "
            f"{update.micro_scalping_fixed_lot_size!r}"
        )
    if (
        update.micro_scalping_max_spread_points is not None
        and update.micro_scalping_max_spread_points <= 0
    ):
        raise ValueError(
            "micro_scalping_max_spread_points must be positive, got "
            f"{update.micro_scalping_max_spread_points!r}"
        )

    repository = RuntimeSettingsRepository(session)
    row = await repository.get_or_create_default()

    if update.clear_fixed_lot_size:
        row.fixed_lot_size = None
    elif update.fixed_lot_size is not None:
        row.fixed_lot_size = update.fixed_lot_size

    if update.auto_trading_enabled is not None:
        row.auto_trading_enabled = update.auto_trading_enabled

    if update.clear_confidence_threshold:
        row.confidence_threshold = None
    elif update.confidence_threshold is not None:
        row.confidence_threshold = update.confidence_threshold

    if update.intraday_enabled is not None:
        row.intraday_enabled = update.intraday_enabled

    if update.scalping_enabled is not None:
        row.scalping_enabled = update.scalping_enabled

    if update.swing_enabled is not None:
        row.swing_enabled = update.swing_enabled

    if update.shakky_enabled is not None:
        row.shakky_enabled = update.shakky_enabled

    if update.shakky_dynamic_tp_enabled is not None:
        row.shakky_dynamic_tp_enabled = update.shakky_dynamic_tp_enabled

    if update.shakky_scaling_enabled is not None:
        row.shakky_scaling_enabled = update.shakky_scaling_enabled

    if update.clear_scalping_confidence_threshold:
        row.scalping_confidence_threshold = None
    elif update.scalping_confidence_threshold is not None:
        row.scalping_confidence_threshold = update.scalping_confidence_threshold

    if update.clear_swing_confidence_threshold:
        row.swing_confidence_threshold = None
    elif update.swing_confidence_threshold is not None:
        row.swing_confidence_threshold = update.swing_confidence_threshold

    if update.risk_mode is not None:
        row.risk_mode = update.risk_mode

    if update.clear_max_positions:
        row.max_positions = None
    elif update.max_positions is not None:
        row.max_positions = update.max_positions

    if update.clear_books_folder:
        row.books_folder = None
    elif update.books_folder is not None:
        row.books_folder = update.books_folder

    if update.paused is not None:
        row.paused = update.paused

    if update.clear_min_trade_quality_score:
        row.min_trade_quality_score = None
    elif update.min_trade_quality_score is not None:
        row.min_trade_quality_score = update.min_trade_quality_score

    if update.demo_learning_mode_enabled is not None:
        row.demo_learning_mode_enabled = update.demo_learning_mode_enabled

    if update.micro_scalping_enabled is not None:
        row.micro_scalping_enabled = update.micro_scalping_enabled

    if update.clear_micro_scalping_min_confidence:
        row.micro_scalping_min_confidence = None
    elif update.micro_scalping_min_confidence is not None:
        row.micro_scalping_min_confidence = update.micro_scalping_min_confidence

    if update.clear_micro_scalping_max_holding_minutes:
        row.micro_scalping_max_holding_minutes = None
    elif update.micro_scalping_max_holding_minutes is not None:
        row.micro_scalping_max_holding_minutes = update.micro_scalping_max_holding_minutes

    if update.micro_scalping_dynamic_profit_target_enabled is not None:
        row.micro_scalping_dynamic_profit_target_enabled = (
            update.micro_scalping_dynamic_profit_target_enabled
        )

    if update.micro_scalping_trailing_stop_enabled is not None:
        row.micro_scalping_trailing_stop_enabled = update.micro_scalping_trailing_stop_enabled

    if update.micro_scalping_lot_mode is not None:
        row.micro_scalping_lot_mode = update.micro_scalping_lot_mode

    if update.clear_micro_scalping_fixed_lot_size:
        row.micro_scalping_fixed_lot_size = None
    elif update.micro_scalping_fixed_lot_size is not None:
        row.micro_scalping_fixed_lot_size = update.micro_scalping_fixed_lot_size

    if update.clear_micro_scalping_max_spread_points:
        row.micro_scalping_max_spread_points = None
    elif update.micro_scalping_max_spread_points is not None:
        row.micro_scalping_max_spread_points = update.micro_scalping_max_spread_points

    await repository.add(row)
    return await _view_from_row(session, row)
