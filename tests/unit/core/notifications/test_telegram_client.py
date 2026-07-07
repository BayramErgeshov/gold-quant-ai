"""Unit tests for the Telegram notification gateway.

`telegram` is installed, but no bot token is available in this
environment, so `RealTelegramNotifier` is exercised against a fake
`telegram.Bot` injected into `sys.modules` — the same technique used for
`MetaTrader5` in `tests/unit/core/execution/test_mt5_client.py`.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.notifications.telegram_client import RealTelegramNotifier, TelegramNotifier
from src.settings import get_settings

pytestmark = pytest.mark.unit


class _FakeBot:
    def __init__(self, *, sent_message: object | None = SimpleNamespace(message_id=1)) -> None:
        self.sent_message = sent_message
        self.last_call: dict[str, object] | None = None

    async def send_message(self, **kwargs: object) -> object | None:
        self.last_call = kwargs
        return self.sent_message


class _FakeTelegramModule:
    def __init__(self, bot: _FakeBot) -> None:
        self._bot = bot

    def Bot(self, *, token: str) -> _FakeBot:  # noqa: N802 - matches telegram.Bot's own casing
        self._bot.last_call = {"token": token}
        return self._bot


def test_telegram_notifier_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        TelegramNotifier()  # type: ignore[abstract]


async def test_send_message_returns_true_on_success() -> None:
    fake_bot = _FakeBot()
    with patch.dict(sys.modules, {"telegram": _FakeTelegramModule(fake_bot)}):
        notifier = RealTelegramNotifier(get_settings())
        result = await notifier.send_message("12345", "hello")

    assert result is True
    assert fake_bot.last_call is not None
    assert fake_bot.last_call["chat_id"] == "12345"
    assert fake_bot.last_call["text"] == "hello"


async def test_send_message_returns_false_when_bot_returns_none() -> None:
    fake_bot = _FakeBot(sent_message=None)
    with patch.dict(sys.modules, {"telegram": _FakeTelegramModule(fake_bot)}):
        notifier = RealTelegramNotifier(get_settings())
        result = await notifier.send_message("12345", "hello")

    assert result is False
