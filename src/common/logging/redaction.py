"""Structlog processor that redacts sensitive fields before they are logged.

Per SECURITY_ARCHITECTURE.md and CODING_STANDARDS.md: logs must never contain
passwords, tokens, API keys, broker credentials or other secrets, regardless
of which code path produced the log entry.
"""

from __future__ import annotations

from structlog.typing import EventDict, WrappedLogger

_REDACTED_VALUE = "***REDACTED***"

_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "authorization",
    "session_id",
)


def _is_sensitive_key(key: str) -> bool:
    """Check whether a field name looks like it holds sensitive data."""
    normalized = key.lower()
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def redact_sensitive_fields(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Structlog processor: replace sensitive values with a redacted marker.

    Args:
        logger: The bound logger instance (unused, required by structlog's
            processor signature).
        method_name: The log method invoked, e.g. "info" (unused).
        event_dict: The structured log event to sanitize.

    Returns:
        The same dictionary with sensitive values replaced.
    """
    for key in list(event_dict.keys()):
        if _is_sensitive_key(key):
            event_dict[key] = _REDACTED_VALUE
    return event_dict
