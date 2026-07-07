"""Unit tests for training-metric helper functions."""

from __future__ import annotations

import pytest

from src.core.ml.model import ClassificationModel, RegressionModel
from src.engines.ml_engine.training import _classification_metrics, _regression_metrics

pytestmark = pytest.mark.unit

_FEATURE_NAMES = ("momentum_pct", "trend_slope_pct")


def test_classification_metrics_is_empty_for_no_samples() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)

    assert _classification_metrics(model, []) == {}


def test_regression_metrics_is_empty_for_no_samples() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)

    assert _regression_metrics(model, []) == {}
