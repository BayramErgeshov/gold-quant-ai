"""Unit tests for `src.common.logging.setup`."""

from __future__ import annotations

import pytest

from src.common.logging import setup as logging_setup
from src.common.logging.setup import _build_dict_config, configure_logging, get_logger
from src.settings import get_settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_configured_flag() -> None:
    logging_setup._configured = False


def test_build_dict_config_applies_platform_level() -> None:
    settings = get_settings()

    dict_config = _build_dict_config(settings)

    assert dict_config["root"]["level"] == settings.platform.logging.level
    assert "level" not in dict_config


def test_configure_logging_is_idempotent() -> None:
    settings = get_settings()

    configure_logging(settings)
    assert logging_setup._configured is True
    configure_logging(settings)  # second call must be a no-op, not re-raise

    assert logging_setup._configured is True


def test_get_logger_returns_usable_bound_logger() -> None:
    settings = get_settings()
    configure_logging(settings)

    logger = get_logger(__name__)
    logger.info("unit_test_event", ok=True)  # must not raise
