"""Telegram notification gateway abstraction.

Per TELEGRAM.md: "Telegram is the primary communication interface between
the user and GOLD QUANT AI." This module never decides *what* to say —
callers build message text via `src.core.notifications.formatting`; it
only sends it.

`RealTelegramNotifier` wraps the `python-telegram-bot` package and
activates automatically once `TELEGRAM_BOT_TOKEN` is set in `.env`
(`src.core.config.env_settings.TelegramEnvSettings`), mirroring the Data
Collection Engine's provider-activation pattern (DATA_COLLECTION_ENGINE.md).
Verified against a live bot token and chat during Phase 20 (`getMe` and a
real `sendMessage` both succeeded); unit tests still exercise it against a
fake `telegram.Bot` for determinism. The `telegram` package is imported
lazily so this module remains importable and testable without it installed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.settings import Settings, get_settings


class TelegramNotifier(ABC):
    """Notification gateway interface (TELEGRAM.md "Telegram Components")."""

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> bool:
        """Send a message to a chat.

        Args:
            chat_id: Target chat/channel id.
            text: Message body (Markdown-formatted).

        Returns:
            True if the message was accepted.
        """


class RealTelegramNotifier(TelegramNotifier):
    """Wraps `telegram.Bot.send_message`. See module docstring."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the notifier.

        Args:
            settings: Application settings. Defaults to `get_settings()`.
        """
        self._settings = settings or get_settings()

    async def send_message(self, chat_id: str, text: str) -> bool:
        """Send a message via the Telegram Bot API.

        Args:
            chat_id: Target chat/channel id.
            text: Message body (Markdown-formatted).

        Returns:
            True if Telegram accepted the message.
        """
        import telegram

        bot = telegram.Bot(token=self._settings.telegram_env.bot_token.get_secret_value())
        message = await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        return message is not None

    async def verify_connection(self) -> str:
        """Verify the bot token is valid via `getMe` (MT5_ENGINE.md-style
        "Connection Validation", applied to Telegram).

        Returns:
            The bot's `@username`, confirming the token is valid.
        """
        import telegram

        bot = telegram.Bot(token=self._settings.telegram_env.bot_token.get_secret_value())
        me = await bot.get_me()
        return f"@{me.username}"
