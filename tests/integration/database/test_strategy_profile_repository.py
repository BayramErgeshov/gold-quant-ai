"""Integration tests for `StrategyProfileRepository`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.strategy_profile import StrategyProfile, StrategyProfileModule
from src.repositories.strategy_profile_repository import StrategyProfileRepository


async def test_get_by_name_returns_none_when_no_profile_exists(session: AsyncSession) -> None:
    repository = StrategyProfileRepository(session)

    assert await repository.get_by_name("Conservative") is None


async def test_add_then_get_by_name_round_trips_modules(session: AsyncSession) -> None:
    repository = StrategyProfileRepository(session)
    profile = await repository.add(StrategyProfile(name="Conservative"))
    await repository.replace_modules(
        profile,
        [
            StrategyProfileModule(module_name="trend", enabled=True, weight=1.5),
            StrategyProfileModule(
                module_name="news", enabled=False, weight=1.0, min_confidence=0.7
            ),
        ],
    )

    fetched = await repository.get_by_name("Conservative")

    assert fetched is not None
    modules_by_name = {module.module_name: module for module in fetched.modules}
    assert modules_by_name["trend"].enabled is True
    assert modules_by_name["trend"].weight == 1.5
    assert modules_by_name["news"].enabled is False
    assert modules_by_name["news"].min_confidence == 0.7


async def test_replace_modules_drops_modules_no_longer_listed(session: AsyncSession) -> None:
    repository = StrategyProfileRepository(session)
    profile = await repository.add(StrategyProfile(name="Aggressive"))
    await repository.replace_modules(
        profile, [StrategyProfileModule(module_name="trend", enabled=True, weight=1.0)]
    )

    await repository.replace_modules(
        profile, [StrategyProfileModule(module_name="momentum", enabled=True, weight=2.0)]
    )

    fetched = await repository.get_by_name("Aggressive")
    assert fetched is not None
    assert [module.module_name for module in fetched.modules] == ["momentum"]


async def test_list_all_orders_profiles_by_name(session: AsyncSession) -> None:
    repository = StrategyProfileRepository(session)
    await repository.add(StrategyProfile(name="Swing"))
    await repository.add(StrategyProfile(name="Conservative"))

    profiles = await repository.list_all()

    assert [profile.name for profile in profiles] == ["Conservative", "Swing"]


async def test_delete_by_name_removes_the_profile_and_its_modules(
    session: AsyncSession,
) -> None:
    repository = StrategyProfileRepository(session)
    profile = await repository.add(StrategyProfile(name="News Trading"))
    await repository.replace_modules(
        profile, [StrategyProfileModule(module_name="news", enabled=True, weight=2.0)]
    )

    deleted = await repository.delete_by_name("News Trading")

    assert deleted is True
    assert await repository.get_by_name("News Trading") is None


async def test_delete_by_name_returns_false_when_no_profile_exists(
    session: AsyncSession,
) -> None:
    repository = StrategyProfileRepository(session)

    assert await repository.delete_by_name("Nonexistent") is False
