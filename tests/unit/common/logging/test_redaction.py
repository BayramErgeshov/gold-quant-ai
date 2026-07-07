"""Unit tests for `src.common.logging.redaction`."""

from __future__ import annotations

import pytest

from src.common.logging.redaction import redact_sensitive_fields

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "user_password",
        "api_key",
        "apiKey",
        "secret_token",
        "PRIVATE_KEY",
        "broker_credential",
        "Authorization",
        "session_id",
    ],
)
def test_redacts_known_sensitive_keys(key: str) -> None:
    event = {key: "super-sensitive-value", "safe_field": "ok"}

    result = redact_sensitive_fields(None, "info", event)

    assert result[key] == "***REDACTED***"
    assert result["safe_field"] == "ok"


def test_leaves_non_sensitive_fields_untouched() -> None:
    event = {"symbol": "XAUUSD", "confidence": 83.5}

    result = redact_sensitive_fields(None, "info", dict(event))

    assert result == event


def test_returns_same_dict_instance() -> None:
    event = {"password": "x"}

    result = redact_sensitive_fields(None, "info", event)

    assert result is event
