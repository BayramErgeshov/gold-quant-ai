"""Environment-variable-backed settings.

Per CODING_STANDARDS.md and SECURITY_ARCHITECTURE.md: secrets, credentials and
connection details are never hardcoded and never stored in YAML. They are read
exclusively from environment variables (populated locally via `.env`, and via
the deployment secret manager elsewhere).
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresEnvSettings(BaseSettings):
    """PostgreSQL connection settings sourced from the environment."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    db: str = "gold_quant_ai"
    user: str = "gold_quant_ai"
    password: SecretStr = SecretStr("")
    pool_min_size: int = 5
    pool_max_size: int = 20

    @property
    def dsn(self) -> str:
        """Build an asyncpg-compatible SQLAlchemy DSN without leaking the password in repr."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RedisEnvSettings(BaseSettings):
    """Redis connection settings sourced from the environment."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr = SecretStr("")

    @property
    def url(self) -> str:
        """Build a redis:// connection URL."""
        auth = f":{self.password.get_secret_value()}@" if self.password.get_secret_value() else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class QdrantEnvSettings(BaseSettings):
    """Qdrant connection settings sourced from the environment."""

    model_config = SettingsConfigDict(env_prefix="QDRANT_", extra="ignore")

    host: str = "localhost"
    port: int = 6333
    api_key: SecretStr = SecretStr("")


class TelegramEnvSettings(BaseSettings):
    """Telegram bot credentials sourced from the environment."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", extra="ignore")

    bot_token: SecretStr = SecretStr("")
    admin_chat_ids: str = ""
    trading_group_id: str = ""
    research_group_id: str = ""

    @property
    def admin_chat_id_list(self) -> list[int]:
        """Parse the comma-separated admin chat id list into integers."""
        return [int(value) for value in self.admin_chat_ids.split(",") if value.strip()]


class MT5EnvSettings(BaseSettings):
    """MetaTrader 5 account credentials sourced from the environment.

    Per MT5_ENGINE.md, `account_type` must default to demo. Live trading
    requires a separate, explicitly approved configuration.
    """

    model_config = SettingsConfigDict(env_prefix="MT5_", extra="ignore")

    login: str = ""
    password: SecretStr = SecretStr("")
    server: str = ""
    terminal_path: str = ""
    account_type: str = "demo"


class SecurityEnvSettings(BaseSettings):
    """Application secrets sourced from the environment."""

    model_config = SettingsConfigDict(extra="ignore")

    secret_key: SecretStr = Field(default=SecretStr(""), alias="SECRET_KEY")
    encryption_key: SecretStr = Field(default=SecretStr(""), alias="ENCRYPTION_KEY")


class DataProviderEnvSettings(BaseSettings):
    """Third-party data provider API keys sourced from the environment."""

    model_config = SettingsConfigDict(extra="ignore")

    fred_api_key: SecretStr = Field(default=SecretStr(""), alias="FRED_API_KEY")
    tradingeconomics_api_key: SecretStr = Field(
        default=SecretStr(""), alias="TRADINGECONOMICS_API_KEY"
    )
    alphavantage_api_key: SecretStr = Field(default=SecretStr(""), alias="ALPHAVANTAGE_API_KEY")
    twelvedata_api_key: SecretStr = Field(default=SecretStr(""), alias="TWELVEDATA_API_KEY")
    polygon_api_key: SecretStr = Field(default=SecretStr(""), alias="POLYGON_API_KEY")
    finnhub_api_key: SecretStr = Field(default=SecretStr(""), alias="FINNHUB_API_KEY")
    newsapi_api_key: SecretStr = Field(default=SecretStr(""), alias="NEWSAPI_API_KEY")
    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")


class MonitoringEnvSettings(BaseSettings):
    """Monitoring stack connection settings sourced from the environment."""

    model_config = SettingsConfigDict(extra="ignore")

    prometheus_port: int = Field(default=9090, alias="PROMETHEUS_PORT")
    grafana_port: int = Field(default=3000, alias="GRAFANA_PORT")
    grafana_admin_password: SecretStr = Field(default=SecretStr(""), alias="GRAFANA_ADMIN_PASSWORD")
