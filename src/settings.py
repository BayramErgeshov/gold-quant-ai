"""Application settings entrypoint for GOLD QUANT AI.

Combines environment-variable-backed secrets/connection settings with
versioned YAML business configuration into one validated, cached `Settings`
object. This is the single source of configuration truth for the whole
platform — no module may read `os.environ` or a YAML file directly.
See CONFIGURATION.md.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from src.core.config.env_settings import (
    DataProviderEnvSettings,
    MonitoringEnvSettings,
    MT5EnvSettings,
    PostgresEnvSettings,
    QdrantEnvSettings,
    RedisEnvSettings,
    SecurityEnvSettings,
    TelegramEnvSettings,
)
from src.core.config.platform_config import PlatformConfig
from src.core.config.yaml_loader import load_platform_config

_VALID_ENVIRONMENTS: tuple[str, ...] = ("development", "testing", "demo", "production")
_DEFAULT_ENVIRONMENT = "development"


class Settings(BaseModel):
    """Fully resolved, validated application settings.

    Attributes:
        environment: Active deployment environment.
        postgres: PostgreSQL connection settings (from environment variables).
        redis: Redis connection settings (from environment variables).
        qdrant: Qdrant connection settings (from environment variables).
        telegram_env: Telegram bot credentials (from environment variables).
        mt5_env: MetaTrader 5 credentials (from environment variables).
        security: Application secrets (from environment variables).
        data_providers: Third-party API keys (from environment variables).
        monitoring_env: Monitoring stack connection settings.
        platform: Business configuration merged from YAML files.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    environment: str
    postgres: PostgresEnvSettings
    redis: RedisEnvSettings
    qdrant: QdrantEnvSettings
    telegram_env: TelegramEnvSettings
    mt5_env: MT5EnvSettings
    security: SecurityEnvSettings
    data_providers: DataProviderEnvSettings
    monitoring_env: MonitoringEnvSettings
    platform: PlatformConfig


def _resolve_environment() -> str:
    """Resolve the active environment name from `GOLD_ENVIRONMENT`.

    Returns:
        A validated environment name.

    Raises:
        ValueError: If `GOLD_ENVIRONMENT` is set to an unrecognized value.
    """
    environment = os.environ.get("GOLD_ENVIRONMENT", _DEFAULT_ENVIRONMENT).lower()
    if environment not in _VALID_ENVIRONMENTS:
        raise ValueError(
            f"Invalid GOLD_ENVIRONMENT={environment!r}; expected one of {_VALID_ENVIRONMENTS}"
        )
    return environment


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build (and cache) the fully validated application settings.

    Returns:
        The process-wide `Settings` singleton.
    """
    # Containers get `.env` via docker-compose's own `env_file:` directive;
    # a script run directly against the venv (as every script under
    # `scripts/` is) has no such mechanism, so `.env` is loaded here too.
    # Never overrides a variable already present in the real environment.
    load_dotenv(override=False)
    environment = _resolve_environment()
    raw_platform_config = load_platform_config(environment)

    return Settings(
        environment=environment,
        postgres=PostgresEnvSettings(),
        redis=RedisEnvSettings(),
        qdrant=QdrantEnvSettings(),
        telegram_env=TelegramEnvSettings(),
        mt5_env=MT5EnvSettings(),
        security=SecurityEnvSettings(),
        data_providers=DataProviderEnvSettings(),
        monitoring_env=MonitoringEnvSettings(),
        platform=PlatformConfig.model_validate(raw_platform_config),
    )
