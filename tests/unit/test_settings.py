"""Unit tests for `src.settings`."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from src.settings import get_settings

pytestmark = pytest.mark.unit


def test_get_settings_resolves_testing_environment() -> None:
    settings = get_settings()

    assert settings.environment == "testing"
    assert settings.platform.symbols.primary == "XAUUSD"


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_settings()
    second = get_settings()

    assert first is second


def test_get_settings_rejects_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLD_ENVIRONMENT", "not-a-real-environment")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="Invalid GOLD_ENVIRONMENT"):
        get_settings()


def test_postgres_password_is_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "super-secret-value")
    get_settings.cache_clear()

    settings = get_settings()

    assert isinstance(settings.postgres.password, SecretStr)
    assert "super-secret-value" not in repr(settings.postgres.password)
    assert "super-secret-value" not in repr(settings)


def test_postgres_dsn_contains_actual_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "super-secret-value")
    get_settings.cache_clear()

    settings = get_settings()

    assert "super-secret-value" in settings.postgres.dsn


def test_execution_live_trading_disabled_by_default() -> None:
    settings = get_settings()

    assert settings.platform.execution.live_enabled is False
