"""Unit tests for prediction explainability."""

from __future__ import annotations

import pytest

from src.core.ml.explainability import explain_classification, explain_regression
from src.core.ml.model import ClassificationModel, RegressionModel
from src.engines.ml_engine.dataset import Sample

pytestmark = pytest.mark.unit

_FEATURE_NAMES = ("momentum_pct", "trend_slope_pct")


def _samples() -> list[Sample]:
    return [
        Sample(
            features={"momentum_pct": 5.0, "trend_slope_pct": 0.5},
            forward_return_pct=2.0,
            label="bullish",
        ),
        Sample(
            features={"momentum_pct": 4.5, "trend_slope_pct": 0.4},
            forward_return_pct=1.8,
            label="bullish",
        ),
        Sample(
            features={"momentum_pct": -5.0, "trend_slope_pct": -0.5},
            forward_return_pct=-2.0,
            label="bearish",
        ),
        Sample(
            features={"momentum_pct": -4.5, "trend_slope_pct": -0.4},
            forward_return_pct=-1.8,
            label="bearish",
        ),
    ]


def test_explain_regression_raises_before_fit() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError, match="must be fit"):
        explain_regression(model, {"momentum_pct": 1.0, "trend_slope_pct": 1.0})


def test_explain_regression_ranks_features_by_absolute_contribution() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    contributions = explain_regression(model, {"momentum_pct": 5.0, "trend_slope_pct": 0.5})

    assert {item.feature_name for item in contributions} == set(_FEATURE_NAMES)
    assert contributions[0].contribution >= contributions[1].contribution


def test_explain_classification_raises_before_fit() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError, match="must be fit"):
        explain_classification(
            model, {"momentum_pct": 1.0, "trend_slope_pct": 1.0}, "bullish"
        )


def test_explain_classification_raises_for_unknown_label() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    with pytest.raises(ValueError, match="Unknown label"):
        explain_classification(
            model, {"momentum_pct": 1.0, "trend_slope_pct": 1.0}, "sideways"
        )


def test_explain_classification_bullish_contribution_is_positive_for_bullish_features() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    contributions = explain_classification(
        model, {"momentum_pct": 5.0, "trend_slope_pct": 0.5}, "bullish"
    )

    assert sum(item.contribution for item in contributions) > 0


def test_explain_classification_bearish_contribution_is_negative_for_bullish_features() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    bullish = explain_classification(
        model, {"momentum_pct": 5.0, "trend_slope_pct": 0.5}, "bullish"
    )
    bearish = explain_classification(
        model, {"momentum_pct": 5.0, "trend_slope_pct": 0.5}, "bearish"
    )

    bullish_total = sum(item.contribution for item in bullish)
    bearish_total = sum(item.contribution for item in bearish)
    assert bullish_total == pytest.approx(-bearish_total)


def test_explain_classification_handles_more_than_two_classes() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    model.fit(
        [
            *_samples(),
            Sample(
                features={"momentum_pct": 0.0, "trend_slope_pct": 0.0},
                forward_return_pct=0.0,
                label="neutral",
            ),
            Sample(
                features={"momentum_pct": 0.1, "trend_slope_pct": -0.1},
                forward_return_pct=0.05,
                label="neutral",
            ),
        ]
    )

    contributions = explain_classification(
        model, {"momentum_pct": 0.0, "trend_slope_pct": 0.0}, "neutral"
    )

    assert {item.feature_name for item in contributions} == set(_FEATURE_NAMES)
