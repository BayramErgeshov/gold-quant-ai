"""ORM model for user-adjustable runtime settings (DATABASE.md: `runtime_settings`).

Per the "User Interface" production requirement: "Settings: Lot Size,
Auto Trading, Confidence Threshold, Strategy Selection, Risk Mode" must
be changeable from the interface. A single row (id `"default"`) holds the
platform's current overrides; `LiveTradingLoop` re-reads it every cycle
so a change takes effect on the very next scan, without a restart.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin

RISK_MODES: tuple[str, ...] = ("conservative", "normal", "aggressive")

DEFAULT_RUNTIME_SETTINGS_ID = "default"


class RuntimeSettings(Base, TimestampMixin):
    """The platform's single, live-editable runtime settings row.

    Attributes:
        id: Always `DEFAULT_RUNTIME_SETTINGS_ID` -- this table intentionally
            holds exactly one row (application-enforced, not a DB constraint,
            per YAGNI: multi-profile settings are not a current requirement).
        fixed_lot_size: Overrides `MarketScanConfig.fixed_lot_size` when
            set. None means "use the script's own configured default."
        auto_trading_enabled: When False, the loop still scans and
            analyzes every cycle but never places an order -- a master
            kill-switch, not a pause of analysis.
        confidence_threshold: Overrides `MarketScanConfig.confidence_threshold`
            (the primary/Intraday engine's own threshold) when set.
        intraday_enabled: When False, disables the primary (Intraday)
            engine for this cycle. Per the "User Configuration" production
            requirement's strategy-combination picker (e.g. "Scalping
            only" must be able to exclude Intraday too) -- unlike earlier
            revisions of this platform, the primary engine is no longer
            unconditionally mandatory.
        scalping_enabled: When False, disables the independent Scalping
            Engine for this cycle even if the script wired one in.
        swing_enabled: When False, disables the independent Swing Engine
            for this cycle even if the script wired one in.
        scalping_confidence_threshold: Overrides the Scalping Engine's own
            confidence threshold when set (independent of the Intraday
            engine's `confidence_threshold`). None uses the Scalping
            Engine's own constructed default.
        swing_confidence_threshold: Overrides the Swing Engine's own
            confidence threshold when set, independently of the other two
            engines. None uses the Swing Engine's own constructed default.
        risk_mode: One of `RISK_MODES`; scales `risk_per_trade_pct`
            (0.5x conservative, 1x normal, 1.5x aggressive) -- a real,
            defensible behavior, not a cosmetic label.
        max_positions: Overrides the maximum number of simultaneously
            open journaled positions `LiveTradingLoop` allows before
            suppressing a new signal. None means "no count limit beyond
            the Risk Engine's own percentage-based exposure limits."
        books_folder: Overrides the folder `BooksFolderWatcher` polls for
            new documents. None means "use the script's own configured
            default" (`scripts/run_books_watcher.py`'s `books/`).
        paused: Per the "Live Control" production requirement's PAUSE
            button -- when True, the live loop still monitors already-open
            positions and sends the "Before Market Close" report each
            cycle, but skips new market scans and signal execution
            entirely. Softer than STOP, which the web UI implements by
            terminating the process outright
            (`src.interfaces.web.process_control`).
        intraday_profile_name: The `StrategyProfile.name` currently
            assigned to the primary (Intraday) engine, if any. None means
            every module stays at its current default (enabled, weight
            1.0) -- unchanged behavior, per the "Complete Strategy
            Builder" production requirement's own default philosophy.
        scalping_profile_name: Same, for the independent Scalping Engine.
        swing_profile_name: Same, for the independent Swing Engine.
        min_trade_quality_score: Overrides every strategy's own minimum
            Trade Quality Score (0-100) required to open a trade when
            set. None uses `config/risk.yaml`'s own configured default
            (`RiskConfig.quality.minimum_trade_quality_score`). Per the
            "Trade Quality Engine" production requirement: the score is
            the primary decision metric, not just a displayed number.
        demo_learning_mode_enabled: Per the "Demo Learning Mode"
            production requirement: when True, `LiveTradingLoop` skips
            the optional portfolio-wide position cap
            (`max_positions`) and applies a bounded discount to every
            strategy's own confidence/quality thresholds -- "allow
            parallel trades, aggressive experimentation, prioritize
            learning over capital preservation." Defaults False, which
            preserves every existing behavior unchanged; this relaxed
            behavior applies only while the flag is True.
        shakky_enabled: When False, disables the independent Shakky
            ("Classic M5 Strategy") engine for this cycle even if the
            script wired one in -- same opt-out convention as
            `scalping_enabled`/`swing_enabled`.
        shakky_dynamic_tp_enabled: When False, Shakky's open positions
            keep today's fixed take-profit behavior regardless of Trend
            Confidence at entry -- lets the user disable
            `src.engines.shakky_engine.exit_management` independently of
            disabling Shakky entirely. Defaults True.
        shakky_scaling_enabled: When False, Shakky never adds to an
            already-open position (`src.engines.shakky_engine.
            position_scaling`), independently of disabling Shakky
            entirely. Defaults True.
        micro_scalping_enabled: When False, disables the independent
            Micro Scalping Engine for this cycle even if the script
            wired one in -- same opt-out convention as the other engines.
        micro_scalping_min_confidence: Overrides the Micro Scalping
            Engine's own minimum confidence to enter when set. None uses
            the engine's own constructed default.
        micro_scalping_max_holding_minutes: Overrides the maximum time a
            Micro Scalping position may stay open before being closed
            unconditionally, regardless of profit. None uses the
            engine's own constructed default -- per its own spec, "never
            hold trades for hours."
        micro_scalping_dynamic_profit_target_enabled: When False, Micro
            Scalping always closes at its flat profit target rather than
            ever switching to a trailing stop on strong momentum.
            Defaults True.
        micro_scalping_trailing_stop_enabled: When False, Micro Scalping
            never trails an open position -- it only ever closes flat at
            the profit target. Defaults True.
        micro_scalping_lot_mode: "manual" (fixed lot,
            `micro_scalping_fixed_lot_size`) or "auto" (risk-based,
            `src.engines.risk_engine.position_sizing.compute_position_size`).
            Defaults "manual", matching every other engine's default
            fixed-sizing convention.
        micro_scalping_fixed_lot_size: The fixed lot size used when
            `micro_scalping_lot_mode == "manual"`. None uses the engine's
            own small constructed default.
        micro_scalping_max_spread_points: Overrides the Micro Scalping
            Engine's own maximum acceptable spread (in points) to enter
            when set. None uses the engine's own constructed default --
            exposed here (unlike a hardcoded constant) so a future shift
            in this account's real observed spread can be corrected from
            Settings without a code change.
    """

    __tablename__ = "runtime_settings"
    __table_args__ = (
        CheckConstraint(f"risk_mode IN {RISK_MODES}", name="ck_runtime_settings_risk_mode_valid"),
        CheckConstraint(
            "micro_scalping_lot_mode IN ('auto', 'manual')",
            name="ck_runtime_settings_micro_scalping_lot_mode_valid",
        ),
    )

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    fixed_lot_size: Mapped[float | None] = mapped_column(Float)
    auto_trading_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confidence_threshold: Mapped[float | None] = mapped_column(Float)
    intraday_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scalping_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    swing_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scalping_confidence_threshold: Mapped[float | None] = mapped_column(Float)
    swing_confidence_threshold: Mapped[float | None] = mapped_column(Float)
    risk_mode: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    max_positions: Mapped[int | None] = mapped_column(Integer)
    books_folder: Mapped[str | None] = mapped_column(String(500))
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    intraday_profile_name: Mapped[str | None] = mapped_column(String(100))
    scalping_profile_name: Mapped[str | None] = mapped_column(String(100))
    swing_profile_name: Mapped[str | None] = mapped_column(String(100))
    min_trade_quality_score: Mapped[float | None] = mapped_column(Float)
    demo_learning_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shakky_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    shakky_dynamic_tp_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    shakky_scaling_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    micro_scalping_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    micro_scalping_min_confidence: Mapped[float | None] = mapped_column(Float)
    micro_scalping_max_holding_minutes: Mapped[float | None] = mapped_column(Float)
    micro_scalping_dynamic_profit_target_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    micro_scalping_trailing_stop_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    micro_scalping_lot_mode: Mapped[str] = mapped_column(
        String(10), default="manual", nullable=False
    )
    micro_scalping_fixed_lot_size: Mapped[float | None] = mapped_column(Float)
    micro_scalping_max_spread_points: Mapped[float | None] = mapped_column(Float)

    def __repr__(self) -> str:
        return f"RuntimeSettings(id={self.id!r}, auto_trading_enabled={self.auto_trading_enabled})"
