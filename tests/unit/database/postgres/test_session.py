"""Unit tests for `src.database.postgres.session`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.postgres import session as session_module
from src.database.postgres.session import get_engine, get_session, get_session_factory

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_engine_cache() -> None:
    get_engine.cache_clear()
    yield
    get_engine.cache_clear()


def test_get_engine_is_cached() -> None:
    assert get_engine() is get_engine()


def test_get_engine_uses_postgres_dsn() -> None:
    engine = get_engine()

    assert engine.url.drivername == "postgresql+asyncpg"
    assert engine.url.database == "gold_quant_ai"


def test_get_session_factory_binds_to_engine() -> None:
    factory = get_session_factory()

    assert factory.kw["bind"] is get_engine()


async def test_get_session_commits_on_success() -> None:
    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    fake_factory = MagicMock(return_value=fake_session)

    with patch.object(session_module, "get_session_factory", return_value=fake_factory):
        async with get_session() as session:
            assert session is fake_session

    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()


async def test_get_session_rolls_back_on_exception() -> None:
    fake_session = AsyncMock()
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = False
    fake_factory = MagicMock(return_value=fake_session)

    with (
        patch.object(session_module, "get_session_factory", return_value=fake_factory),
        pytest.raises(ValueError, match="boom"),
    ):
        async with get_session():
            raise ValueError("boom")

    fake_session.rollback.assert_awaited_once()
    fake_session.commit.assert_not_awaited()
