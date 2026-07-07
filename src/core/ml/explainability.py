"""Prediction explainability for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Explainability": every prediction must
disclose its top contributing features. For the linear models used here
(`src.core.ml.model`), a feature's contribution to the raw model score is
exactly `coefficient * feature_value` — an exact decomposition, not an
approximation like SHAP/permutation importance
(`src.core.ml.feature_importance`), which remain reserved for future
non-linear model types.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ml.model import ClassificationModel, RegressionModel


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    """One feature's signed contribution to a prediction, most influential first."""

    feature_name: str
    value: float
    contribution: float


def _rank_contributions(
    feature_names: tuple[str, ...], features: dict[str, float], coefficients: list[float]
) -> list[FeatureContribution]:
    contributions = [
        FeatureContribution(
            feature_name=name, value=features[name], contribution=coefficient * features[name]
        )
        for name, coefficient in zip(feature_names, coefficients, strict=True)
    ]
    contributions.sort(key=lambda item: abs(item.contribution), reverse=True)
    return contributions


def explain_regression(
    model: RegressionModel, features: dict[str, float]
) -> list[FeatureContribution]:
    """Decompose a `RegressionModel` prediction into per-feature contributions.

    Args:
        model: A fitted `RegressionModel`.
        features: The feature vector the prediction was made from.

    Returns:
        One `FeatureContribution` per feature, ranked by absolute
        contribution descending.

    Raises:
        RuntimeError: If `model` has not been fit yet.
    """
    if model.trained_at is None:
        raise RuntimeError("RegressionModel must be fit before explaining a prediction")
    coefficients = list(model._estimator.coef_)
    return _rank_contributions(model.feature_names, features, coefficients)


def explain_classification(
    model: ClassificationModel, features: dict[str, float], label: str
) -> list[FeatureContribution]:
    """Decompose a `ClassificationModel` prediction into per-feature contributions.

    Args:
        model: A fitted `ClassificationModel`.
        features: The feature vector the prediction was made from.
        label: Which class's decision function to explain.

    Returns:
        One `FeatureContribution` per feature toward `label`'s decision
        function, ranked by absolute contribution descending.

    Raises:
        RuntimeError: If `model` has not been fit yet.
        ValueError: If `label` was not one of the classes the model was trained on.
    """
    if model.trained_at is None:
        raise RuntimeError("ClassificationModel must be fit before explaining a prediction")

    classes = list(model._estimator.classes_)
    if label not in classes:
        raise ValueError(f"Unknown label {label!r}; model classes are {classes}")

    coef_matrix = model._estimator.coef_
    if len(classes) == 2:
        raw_coefficients = list(coef_matrix[0])
        coefficients = raw_coefficients if label == classes[1] else [-c for c in raw_coefficients]
    else:
        coefficients = list(coef_matrix[classes.index(label)])

    return _rank_contributions(model.feature_names, features, coefficients)
