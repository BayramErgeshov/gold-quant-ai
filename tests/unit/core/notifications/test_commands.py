"""Unit tests for the Telegram command registry."""

from __future__ import annotations

import pytest

from src.core.notifications.commands import CommandRegistry

pytestmark = pytest.mark.unit


async def _dashboard_handler() -> str:
    return "Dashboard: all systems nominal."


def test_register_rejects_unknown_command() -> None:
    registry = CommandRegistry()

    with pytest.raises(ValueError, match="Unknown command"):
        registry.register("not_a_real_command", _dashboard_handler)


async def test_dispatch_invokes_registered_handler() -> None:
    registry = CommandRegistry()
    registry.register("dashboard", _dashboard_handler)

    response = await registry.dispatch("dashboard")

    assert response == "Dashboard: all systems nominal."


async def test_dispatch_raises_for_unregistered_command() -> None:
    registry = CommandRegistry()

    with pytest.raises(KeyError, match="No handler registered"):
        await registry.dispatch("dashboard")


def test_registered_commands_lists_sorted_names() -> None:
    registry = CommandRegistry()
    registry.register("status", _dashboard_handler)
    registry.register("dashboard", _dashboard_handler)

    assert registry.registered_commands() == ["dashboard", "status"]
