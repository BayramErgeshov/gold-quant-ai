"""Command registry for the Telegram integration.

Per TELEGRAM.md "Admin Commands": maps each command name to its handler.
Wiring this registry to a live `telegram.ext.Application` (polling/
webhook) requires a running bot connection and is done at platform
startup once `TELEGRAM_BOT_TOKEN` is available; this registry itself is
plain, dependency-free dispatch that can be tested without one.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

CommandHandler = Callable[[], Awaitable[str]]

ADMIN_COMMANDS: tuple[str, ...] = (
    "start",
    "help",
    "dashboard",
    "status",
    "market",
    "open",
    "closed",
    "signals",
    "performance",
    "research",
    "news",
    "books",
    "tasks",
    "learning",
    "agents",
    "restart",
    "shutdown",
    "export",
    "settings",
)


@dataclass(slots=True)
class CommandRegistry:
    """Maps command names to async handlers, and dispatches by name."""

    _handlers: dict[str, CommandHandler] = field(default_factory=dict)

    def register(self, command: str, handler: CommandHandler) -> None:
        """Register a handler for a command.

        Args:
            command: Command name, without the leading "/".
            handler: Async callable returning the response text.

        Raises:
            ValueError: If `command` is not one of `ADMIN_COMMANDS`.
        """
        if command not in ADMIN_COMMANDS:
            raise ValueError(f"Unknown command {command!r}; not in ADMIN_COMMANDS")
        self._handlers[command] = handler

    async def dispatch(self, command: str) -> str:
        """Invoke the handler registered for a command.

        Args:
            command: Command name, without the leading "/".

        Returns:
            The handler's response text.

        Raises:
            KeyError: If no handler is registered for `command`.
        """
        if command not in self._handlers:
            raise KeyError(f"No handler registered for command {command!r}")
        return await self._handlers[command]()

    def registered_commands(self) -> list[str]:
        """List every currently registered command name, sorted."""
        return sorted(self._handlers)
