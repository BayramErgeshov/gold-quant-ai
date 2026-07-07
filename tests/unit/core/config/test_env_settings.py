"""Unit tests for `src.core.config.env_settings`."""

from __future__ import annotations

import pytest

from src.core.config.env_settings import RedisEnvSettings, TelegramEnvSettings

pytestmark = pytest.mark.unit


def test_redis_url_without_password() -> None:
    settings = RedisEnvSettings(host="localhost", port=6379, db=0, password="")

    assert settings.url == "redis://localhost:6379/0"


def test_redis_url_with_password() -> None:
    settings = RedisEnvSettings(host="localhost", port=6379, db=0, password="hunter2")

    assert settings.url == "redis://:hunter2@localhost:6379/0"


def test_telegram_admin_chat_id_list_parses_csv() -> None:
    settings = TelegramEnvSettings(admin_chat_ids="123, 456,789")

    assert settings.admin_chat_id_list == [123, 456, 789]


def test_telegram_admin_chat_id_list_empty_string_returns_empty_list() -> None:
    settings = TelegramEnvSettings(admin_chat_ids="")

    assert settings.admin_chat_id_list == []
