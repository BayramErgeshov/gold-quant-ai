"""Typed schema for the merged YAML platform configuration.

Business-critical sections (global toggles, risk, execution, database,
logging, monitoring, books) are fully typed. Sections owned by engines that
ship in later roadmap phases (agents, ml, research, news, macro, telegram,
mt5) are validated as dictionaries so their detailed schema can be introduced
alongside the engine that consumes it, per CODING_STANDARDS.md YAGNI guidance.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SymbolsConfig(BaseModel):
    """Tradable and reserved-for-future-expansion symbols (CONFIGURATION.md)."""

    primary: str
    enabled: list[str]
    reserved: list[str] = Field(default_factory=list)


class TimeframesConfig(BaseModel):
    """Enabled timeframes and their roles (CONFIGURATION.md)."""

    enabled: list[str]
    default_execution: str
    default_context: str
    primary_structure: str


class AnalysisFrequencyConfig(BaseModel):
    """Update cadence per timeframe (CONFIGURATION.md)."""

    tick: str
    m1_seconds: int
    m5_seconds: int
    m15_seconds: int
    h1_seconds: int
    daily_utc_hour: int
    weekly_day: str
    monthly_day: int


class DepartmentsEnabledConfig(BaseModel):
    """Feature toggles for each AI department (CONFIGURATION.md)."""

    chief_ai: bool
    technical: bool
    macro: bool
    news: bool
    risk: bool
    execution: bool
    historical: bool
    book: bool
    machine_learning: bool
    learning: bool
    statistics: bool
    workflow: bool
    monitoring: bool
    database: bool
    telegram: bool
    mt5: bool


class DataSourcesEnabledConfig(BaseModel):
    """Feature toggles for external data sources (CONFIGURATION.md)."""

    market_data: bool
    news: bool
    macro: bool
    books: bool
    historical: bool
    machine_learning: bool
    research: bool


class ExecutionToggleConfig(BaseModel):
    """Execution feature toggles (CONFIGURATION.md, MT5_ENGINE.md).

    `live_enabled` must remain False outside of an explicitly approved live
    deployment; see FAILSAFE_PROTOCOL.md.
    """

    execution_enabled: bool
    demo_only: bool
    live_enabled: bool
    pending_orders_enabled: bool
    market_orders_enabled: bool
    partial_close_enabled: bool
    trailing_enabled: bool
    break_even_enabled: bool


class ConfidenceThresholds(BaseModel):
    """Confidence bands that gate trade approval (RISK_ENGINE.md)."""

    reject_below: float
    observation_only_below: float
    setup_requires_confirmation_below: float
    high_quality_below: float
    institutional_grade: float


class QualityThresholds(BaseModel):
    """Minimum acceptable quality grades (RISK_ENGINE.md, DECISION_ENGINE.md)."""

    minimum_grade: str
    maximum_risk_grade: str
    minimum_historical_similarity: float
    minimum_data_quality_grade: str
    minimum_trade_quality_score: float


class ExposureLimits(BaseModel):
    """Portfolio exposure limits (RISK_ENGINE.md)."""

    max_total_exposure_pct: float
    max_gold_exposure_pct: float
    max_correlated_exposure_pct: float
    max_daily_exposure_pct: float
    max_weekly_exposure_pct: float
    max_simultaneous_positions: int


class PositionSizingConfig(BaseModel):
    """Dynamic position sizing parameters (RISK_ENGINE.md)."""

    mode: Literal["dynamic"]
    risk_per_trade_pct: float
    max_risk_per_trade_pct: float
    atr_multiplier_for_stop: float


class DrawdownLimits(BaseModel):
    """Drawdown circuit breakers (RISK_ENGINE.md)."""

    max_daily_drawdown_pct: float
    max_weekly_drawdown_pct: float
    max_monthly_drawdown_pct: float
    action_on_breach: str


class RiskFilters(BaseModel):
    """Trade filter toggles (RISK_ENGINE.md, CONFIGURATION.md)."""

    trend_alignment_enabled: bool
    liquidity_enabled: bool
    macro_enabled: bool
    news_enabled: bool
    historical_similarity_enabled: bool
    machine_learning_enabled: bool
    book_validation_enabled: bool
    correlation_filter_enabled: bool
    volatility_filter_enabled: bool
    session_filter_enabled: bool


class NewsProtectionConfig(BaseModel):
    """News blackout windows around high-impact events (RISK_ENGINE.md)."""

    minutes_before_high_impact_no_new_entries: int
    minutes_after_high_impact_no_new_entries: int


class TradeManagementConfig(BaseModel):
    """Allowed trade management methods (RISK_ENGINE.md, EXECUTION_ENGINE.md)."""

    break_even_requires_structure_confirmation: bool
    trailing_methods_allowed: list[str]
    partial_close_options_pct: list[float]


class SessionScheduleConfig(BaseModel):
    """Trading-session close schedule for the "Before Market Close" report.

    Attributes:
        daily_close_utc: The connected broker's daily session close time,
            "HH:MM" in UTC. Broker-dependent -- confirm against the
            connected terminal rather than assuming a universal value.
        weekly_close_weekday: The weekday whose daily close is also the
            weekly close (a full weekend ahead) -- its pre-close report
            additionally carries a weekend gap risk note.
        pre_close_warning_minutes: How long before `daily_close_utc` the
            report is sent.
    """

    daily_close_utc: str
    weekly_close_weekday: Literal[
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]
    pre_close_warning_minutes: int


class RiskConfig(BaseModel):
    """Complete Risk Engine configuration (RISK_ENGINE.md)."""

    confidence: ConfidenceThresholds
    quality: QualityThresholds
    exposure: ExposureLimits
    position_sizing: PositionSizingConfig
    drawdown: DrawdownLimits
    filters: RiskFilters
    news_protection: NewsProtectionConfig
    trade_management: TradeManagementConfig
    session_schedule: SessionScheduleConfig


class DatabaseConfig(BaseModel):
    """Database configuration (DATABASE.md).

    Connection secrets live in environment variables; this section holds
    operational tuning and feature toggles only.
    """

    auto_backup: bool
    echo_sql: bool
    postgres: dict[str, Any] = Field(default_factory=dict)
    redis: dict[str, Any] = Field(default_factory=dict)
    qdrant: dict[str, Any] = Field(default_factory=dict)
    backup: dict[str, Any] = Field(default_factory=dict)
    data_retention: dict[str, Any] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    """Logging configuration (OBSERVABILITY_AND_MONITORING.md).

    Mirrors the Python `logging.config.dictConfig` schema, which is already
    validated by the standard library when applied, so extra keys are
    accepted here rather than duplicating that schema field by field.
    """

    model_config = ConfigDict(extra="allow")

    level: str = "INFO"


class MonitoringConfig(BaseModel):
    """Monitoring stack configuration (OBSERVABILITY_AND_MONITORING.md)."""

    prometheus: dict[str, Any]
    healthchecks: dict[str, Any]
    alert_levels: list[str]
    critical_alert_triggers: list[str]
    performance_targets_ms: dict[str, int]
    heartbeat_interval_seconds: int


class LocalEmbeddingConfig(BaseModel):
    """Local sentence-transformers embedding configuration (BOOK_RAG.md).

    `model_candidates` is a fallback chain, not a single choice: the engine
    tries each model in order and uses the first one that loads
    successfully, so a missing/unavailable large model degrades gracefully
    to a smaller one instead of failing outright.
    """

    model_candidates: list[str]
    device: str = "cpu"


class OpenAIEmbeddingConfig(BaseModel):
    """OpenAI embedding configuration, used only when `provider: openai`."""

    model: str
    dimension: int


class EmbeddingConfig(BaseModel):
    """Embedding provider selection (BOOK_RAG.md, CONFIGURATION.md).

    Switching `provider` from "local" to "openai" (or any future provider
    registered in `src.core.embeddings.factory`) requires no code changes.
    """

    provider: Literal["local", "openai"]
    local: LocalEmbeddingConfig
    openai: OpenAIEmbeddingConfig


class BooksConfig(BaseModel):
    """Book Engine configuration (BOOK_RAG.md)."""

    automatic_ocr: bool
    automatic_chunking: bool
    automatic_embeddings: bool
    knowledge_graph_enabled: bool
    validation_required: bool
    chunking: dict[str, int]
    embedding: EmbeddingConfig
    knowledge_priority: dict[int, str]


class PlatformConfig(BaseModel):
    """Root schema for the merged YAML platform configuration."""

    environment: str
    symbols: SymbolsConfig
    timeframes: TimeframesConfig
    analysis_frequency: AnalysisFrequencyConfig
    departments_enabled: DepartmentsEnabledConfig
    data_sources_enabled: DataSourcesEnabledConfig
    execution: ExecutionToggleConfig
    risk: RiskConfig
    database: DatabaseConfig
    logging: LoggingConfig
    monitoring: MonitoringConfig
    books: BooksConfig

    # Domains whose consuming engines are implemented in later roadmap phases.
    telegram: dict[str, Any] = Field(default_factory=dict)
    mt5: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, Any] = Field(default_factory=dict)
    ml: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] = Field(default_factory=dict)
    news: dict[str, Any] = Field(default_factory=dict)
    macro: dict[str, Any] = Field(default_factory=dict)
