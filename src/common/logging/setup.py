"""Structured JSON logging setup for GOLD QUANT AI.

Per CODING_STANDARDS.md: no module may call `print()` or configure its own
logging. Every module obtains a logger via `get_logger(__name__)` after
`configure_logging()` has run once at process startup (see bootstrap.py).

Logging is two-layered:

1. Standard library `logging` handles output — console plus rotating file
   handlers for `logs/application/` and `logs/errors/` — configured from
   `config/logging.yaml` (PROJECT_STRUCTURE.md: `logs/` layout).
2. `structlog` produces structured, redacted, JSON-rendered log events on
   top of the standard library handlers.
"""

from __future__ import annotations

import logging
import logging.config
from typing import Any, cast

import structlog

from src.common.logging.redaction import redact_sensitive_fields
from src.core.config.yaml_loader import PROJECT_ROOT
from src.settings import Settings

_LOG_DIRECTORIES: tuple[str, ...] = ("logs/application", "logs/errors")
_configured: bool = False


def _ensure_log_directories_exist() -> None:
    """Create the log directories declared in PROJECT_STRUCTURE.md if missing."""
    for relative_path in _LOG_DIRECTORIES:
        (PROJECT_ROOT / relative_path).mkdir(parents=True, exist_ok=True)


def _build_dict_config(settings: Settings) -> dict[str, Any]:
    """Translate the validated `LoggingConfig` into a stdlib `dictConfig` payload.

    Args:
        settings: Resolved application settings.

    Returns:
        A dictionary suitable for `logging.config.dictConfig`, with the
        platform-level `level` override applied to the root logger.
    """
    raw = settings.platform.logging.model_dump(exclude={"level"})
    raw.setdefault("version", 1)
    raw.setdefault("disable_existing_loggers", False)
    root = raw.setdefault("root", {})
    root["level"] = settings.platform.logging.level
    return raw


def configure_logging(settings: Settings) -> None:
    """Configure stdlib logging and structlog exactly once per process.

    Args:
        settings: Resolved application settings (see `src.settings.get_settings`).
    """
    global _configured
    if _configured:
        return

    _ensure_log_directories_exist()
    logging.config.dictConfig(_build_dict_config(settings))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive_fields,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    for handler in logging.getLogger().handlers:
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(processor=structlog.processors.JSONRenderer())
        )

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger bound to the given module name.

    Args:
        name: Typically `__name__` of the calling module.

    Returns:
        A structlog bound logger that writes through the stdlib handlers
        configured by `configure_logging`.
    """
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


__all__ = ["configure_logging", "get_logger"]
