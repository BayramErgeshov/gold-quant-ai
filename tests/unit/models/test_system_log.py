"""Unit tests for the `SystemLog` ORM model."""

from __future__ import annotations

import pytest

from src.models.system_log import SystemLog

pytestmark = pytest.mark.unit


def test_repr_includes_level_source_and_event() -> None:
    entry = SystemLog(level="ERROR", source="bootstrap", event="startup_check")

    assert repr(entry) == "SystemLog(level='ERROR', source='bootstrap', event='startup_check')"
