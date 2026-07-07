"""Integration tests for `MLModelRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ml_model import MLModel
from src.repositories.ml_model_repository import MLModelRepository

_TRAINED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _model(**overrides: object) -> MLModel:
    defaults: dict[str, object] = {
        "name": "xauusd_direction_classifier",
        "version": 1,
        "model_type": "classification",
        "trained_at": _TRAINED_AT,
    }
    defaults.update(overrides)
    return MLModel(**defaults)  # type: ignore[arg-type]


async def test_next_version_is_one_for_unregistered_name(session: AsyncSession) -> None:
    repo = MLModelRepository(session)

    assert await repo.next_version("brand_new_model") == 1


async def test_next_version_increments_from_latest(session: AsyncSession) -> None:
    repo = MLModelRepository(session)
    await repo.add(_model(version=1))
    await repo.add(_model(version=2))

    assert await repo.next_version("xauusd_direction_classifier") == 3


async def test_get_latest_returns_highest_version(session: AsyncSession) -> None:
    repo = MLModelRepository(session)
    await repo.add(_model(version=1))
    latest = await repo.add(_model(version=2))

    result = await repo.get_latest("xauusd_direction_classifier")

    assert result is not None
    assert result.id == latest.id


async def test_get_latest_returns_none_for_unregistered_name(session: AsyncSession) -> None:
    repo = MLModelRepository(session)

    assert await repo.get_latest("brand_new_model") is None


async def test_get_production_returns_promoted_model(session: AsyncSession) -> None:
    repo = MLModelRepository(session)
    await repo.add(_model(version=1, status="retired"))
    production = await repo.add(_model(version=2, status="production"))

    result = await repo.get_production("xauusd_direction_classifier")

    assert result is not None
    assert result.id == production.id


async def test_get_production_returns_none_when_nothing_promoted(session: AsyncSession) -> None:
    repo = MLModelRepository(session)
    await repo.add(_model(version=1, status="candidate"))

    assert await repo.get_production("xauusd_direction_classifier") is None


async def test_list_versions_orders_most_recent_first(session: AsyncSession) -> None:
    repo = MLModelRepository(session)
    await repo.add(_model(version=1))
    await repo.add(_model(version=2))
    await repo.add(_model(version=3))

    versions = await repo.list_versions("xauusd_direction_classifier")

    assert [model.version for model in versions] == [3, 2, 1]
