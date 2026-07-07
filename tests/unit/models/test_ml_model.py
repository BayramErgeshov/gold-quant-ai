"""Unit tests for the `MLModel` ORM model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.ml_model import MLModel

pytestmark = pytest.mark.unit


def test_repr_includes_name_version_and_status() -> None:
    model = MLModel(
        name="xauusd_direction_classifier",
        version=1,
        model_type="classification",
        status="training",
        trained_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert repr(model) == (
        "MLModel(name='xauusd_direction_classifier', version=1, status='training')"
    )
