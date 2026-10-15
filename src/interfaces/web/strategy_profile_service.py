"""Data assembly for the local web UI's Strategy Builder page.

Per the "Complete Strategy Builder" production requirement: "Allow
saving/loading profiles (examples: Scalping, Intraday, Swing,
Conservative, Aggressive, News Trading, Smart Money Only)" and assigning
a saved profile to Intraday/Scalping/Swing independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.chief_ai.strategy_profile import MODULE_NAMES
from src.models.runtime_settings import RuntimeSettings
from src.models.strategy_profile import StrategyProfile, StrategyProfileModule
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.strategy_profile_repository import StrategyProfileRepository

_ASSIGNABLE_STRATEGIES: tuple[str, ...] = ("intraday", "scalping", "swing")


@dataclass(frozen=True, slots=True)
class ModuleView:
    """One module's setting within a profile, for display/editing."""

    module_name: str
    enabled: bool
    weight: float
    min_confidence: float | None


@dataclass(frozen=True, slots=True)
class StrategyProfileView:
    """A single saved profile, ready for the Strategy Builder page."""

    name: str
    modules: list[ModuleView] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StrategyProfilesView:
    """Everything the Strategy Builder page needs.

    Attributes:
        module_names: Every module the user can configure, so the UI can
            render a row even for a module a saved profile doesn't list.
        profiles: Every saved profile.
        assignments: The profile currently assigned to each strategy
            ("intraday"/"scalping"/"swing"), None if unassigned (module
            defaults apply).
    """

    module_names: tuple[str, ...]
    profiles: list[StrategyProfileView]
    assignments: dict[str, str | None]


def _to_view(profile: StrategyProfile) -> StrategyProfileView:
    return StrategyProfileView(
        name=profile.name,
        modules=[
            ModuleView(
                module_name=module.module_name,
                enabled=module.enabled,
                weight=module.weight,
                min_confidence=module.min_confidence,
            )
            for module in profile.modules
        ],
    )


def _assignments_from_settings(settings: RuntimeSettings) -> dict[str, str | None]:
    return {
        "intraday": settings.intraday_profile_name,
        "scalping": settings.scalping_profile_name,
        "swing": settings.swing_profile_name,
    }


async def get_strategy_profiles(session: AsyncSession) -> StrategyProfilesView:
    """Assemble the current Strategy Builder view.

    Args:
        session: The active database session.

    Returns:
        A `StrategyProfilesView` computed entirely from persisted rows.
    """
    profiles = await StrategyProfileRepository(session).list_all()
    settings = await RuntimeSettingsRepository(session).get_or_create_default()
    return StrategyProfilesView(
        module_names=MODULE_NAMES,
        profiles=[_to_view(profile) for profile in profiles],
        assignments=_assignments_from_settings(settings),
    )


@dataclass(frozen=True, slots=True)
class ModuleUpdate:
    """One module's desired setting, as submitted from the UI."""

    module_name: str
    enabled: bool = True
    weight: float = 1.0
    min_confidence: float | None = None


class UnknownModuleError(Exception):
    """Raised when a submitted module name is not one of `MODULE_NAMES`."""


async def save_strategy_profile(
    session: AsyncSession, name: str, modules: list[ModuleUpdate]
) -> StrategyProfileView:
    """Create a new profile, or replace an existing one with the same name.

    Args:
        session: The active database session.
        name: The profile's unique name.
        modules: Every module override this profile should store. A
            module not listed here keeps the platform's own default
            (enabled, weight 1.0) when this profile is assigned.

    Returns:
        The saved `StrategyProfileView`.

    Raises:
        UnknownModuleError: If any `modules[i].module_name` is not one of
            `MODULE_NAMES`.
    """
    for update in modules:
        if update.module_name not in MODULE_NAMES:
            raise UnknownModuleError(update.module_name)

    repository = StrategyProfileRepository(session)
    profile = await repository.get_by_name(name)
    if profile is None:
        profile = await repository.add(StrategyProfile(name=name))

    saved = await repository.replace_modules(
        profile,
        [
            StrategyProfileModule(
                module_name=update.module_name,
                enabled=update.enabled,
                weight=update.weight,
                min_confidence=update.min_confidence,
            )
            for update in modules
        ],
    )
    return _to_view(saved)


async def delete_strategy_profile(session: AsyncSession, name: str) -> bool:
    """Delete a saved profile by name.

    Args:
        session: The active database session.
        name: The profile's unique name.

    Returns:
        True if a profile was found and deleted, False otherwise.
    """
    return await StrategyProfileRepository(session).delete_by_name(name)


class UnknownStrategyError(Exception):
    """Raised when `assign_strategy_profile` is given an unrecognized strategy."""


class ProfileNotFoundError(Exception):
    """Raised when `assign_strategy_profile` is given a profile name that does not exist."""


async def assign_strategy_profile(
    session: AsyncSession, *, strategy: str, profile_name: str | None
) -> StrategyProfilesView:
    """Assign a saved profile to one strategy (or unassign it).

    Args:
        session: The active database session.
        strategy: One of "intraday", "scalping", "swing".
        profile_name: The `StrategyProfile.name` to assign, or None to
            unassign (every module reverts to its default behavior).

    Returns:
        The resulting `StrategyProfilesView`.

    Raises:
        UnknownStrategyError: If `strategy` is not one of the three engines.
        ProfileNotFoundError: If `profile_name` does not match a saved profile.
    """
    if strategy not in _ASSIGNABLE_STRATEGIES:
        raise UnknownStrategyError(strategy)
    if (
        profile_name is not None
        and await StrategyProfileRepository(session).get_by_name(profile_name) is None
    ):
        raise ProfileNotFoundError(profile_name)

    settings_repository = RuntimeSettingsRepository(session)
    settings = await settings_repository.get_or_create_default()
    if strategy == "intraday":
        settings.intraday_profile_name = profile_name
    elif strategy == "scalping":
        settings.scalping_profile_name = profile_name
    else:
        settings.swing_profile_name = profile_name
    await settings_repository.add(settings)

    return await get_strategy_profiles(session)
