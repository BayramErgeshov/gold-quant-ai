"""Integration tests for `RuntimeSettingsRepository`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.runtime_settings import DEFAULT_RUNTIME_SETTINGS_ID, RuntimeSettings
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository


async def test_get_or_create_default_creates_defaults_when_absent(
    session: AsyncSession,
) -> None:
    repo = RuntimeSettingsRepository(session)

    settings = await repo.get_or_create_default()

    assert settings.id == DEFAULT_RUNTIME_SETTINGS_ID
    assert settings.auto_trading_enabled is True
    assert settings.fixed_lot_size is None
    assert settings.confidence_threshold is None
    assert settings.scalping_enabled is True
    assert settings.risk_mode == "normal"


async def test_get_or_create_default_returns_the_existing_row(session: AsyncSession) -> None:
    repo = RuntimeSettingsRepository(session)
    await repo.add(
        RuntimeSettings(
            id=DEFAULT_RUNTIME_SETTINGS_ID, auto_trading_enabled=False, risk_mode="aggressive"
        )
    )

    settings = await repo.get_or_create_default()

    assert settings.auto_trading_enabled is False
    assert settings.risk_mode == "aggressive"


async def test_settings_can_be_updated_and_persisted(session: AsyncSession) -> None:
    repo = RuntimeSettingsRepository(session)
    settings = await repo.get_or_create_default()

    settings.fixed_lot_size = 0.5
    settings.confidence_threshold = 80.0
    await repo.add(settings)

    reloaded = await repo.get_or_create_default()
    assert reloaded.fixed_lot_size == 0.5
    assert reloaded.confidence_threshold == 80.0
