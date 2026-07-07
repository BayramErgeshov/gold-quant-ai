"""Feature importance ranking for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Feature Importance": ranks each feature's
practical impact on model performance via permutation importance
(scikit-learn's `sklearn.inspection.permutation_importance`) — shuffle one
feature at a time and measure how much the model's held-out score drops.
SHAP, Gain, Information Value, Mutual Information and Historical Stability
(also listed in that spec section) are reserved for tree/ensemble model
types not yet in use (see `src.core.ml.model`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.inspection import permutation_importance

from src.core.ml.model import ClassificationModel, RegressionModel, to_feature_matrix
from src.engines.ml_engine.dataset import Sample

_DEFAULT_N_REPEATS = 10
_DEFAULT_RANDOM_STATE = 42


@dataclass(frozen=True, slots=True)
class FeatureImportance:
    """One feature's permutation importance, most important first."""

    feature_name: str
    importance_mean: float
    importance_std: float


def _rank(
    feature_names: tuple[str, ...], means: list[float], stds: list[float]
) -> list[FeatureImportance]:
    ranked = [
        FeatureImportance(feature_name=name, importance_mean=mean, importance_std=std)
        for name, mean, std in zip(feature_names, means, stds, strict=True)
    ]
    ranked.sort(key=lambda item: item.importance_mean, reverse=True)
    return ranked


def compute_classification_feature_importance(
    model: ClassificationModel, samples: list[Sample], *, n_repeats: int = _DEFAULT_N_REPEATS
) -> list[FeatureImportance]:
    """Rank features by their impact on classification accuracy.

    Args:
        model: A fitted `ClassificationModel`.
        samples: Held-out samples to evaluate importance on (should not be
            the samples the model was trained on).
        n_repeats: Number of times each feature is independently shuffled.

    Returns:
        One `FeatureImportance` per feature, ranked by mean importance descending.

    Raises:
        RuntimeError: If `model` has not been fit yet.
    """
    if model.trained_at is None:
        raise RuntimeError("ClassificationModel must be fit before computing feature importance")

    x = to_feature_matrix(samples, model.feature_names)
    y = [sample.label for sample in samples]
    result = permutation_importance(
        model._estimator, x, y, n_repeats=n_repeats, random_state=_DEFAULT_RANDOM_STATE
    )
    return _rank(model.feature_names, list(result.importances_mean), list(result.importances_std))


def compute_regression_feature_importance(
    model: RegressionModel, samples: list[Sample], *, n_repeats: int = _DEFAULT_N_REPEATS
) -> list[FeatureImportance]:
    """Rank features by their impact on regression error.

    Args:
        model: A fitted `RegressionModel`.
        samples: Held-out samples to evaluate importance on.
        n_repeats: Number of times each feature is independently shuffled.

    Returns:
        One `FeatureImportance` per feature, ranked by mean importance descending.

    Raises:
        RuntimeError: If `model` has not been fit yet.
    """
    if model.trained_at is None:
        raise RuntimeError("RegressionModel must be fit before computing feature importance")

    x = to_feature_matrix(samples, model.feature_names)
    y = [sample.forward_return_pct for sample in samples]
    result = permutation_importance(
        model._estimator, x, y, n_repeats=n_repeats, random_state=_DEFAULT_RANDOM_STATE
    )
    return _rank(model.feature_names, list(result.importances_mean), list(result.importances_std))
