"""Cross-department confidence aggregation for the Statistics Engine.

Per DECISION_ENGINE.md "Confidence Calculation": combines every
department/input's confidence into one overall score, "weighted
dynamically according to historical reliability" — the reliability weight
is a pluggable input here rather than hardcoded, since measuring each
department's actual historical reliability requires the Self-Learning
Engine (a later roadmap phase) to track outcomes over time.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_RELIABILITY = 1.0


@dataclass(frozen=True, slots=True)
class ConfidenceInput:
    """One department/input's confidence contribution.

    Attributes:
        name: Input name, e.g. "technical", "macro", "data_quality".
        confidence: That input's own confidence/score, in [0.0, 1.0].
        historical_reliability: How reliable this input has been
            historically, in [0.0, 1.0]. Defaults to 1.0 (no adjustment)
            until the Self-Learning Engine supplies a measured value.
    """

    name: str
    confidence: float
    historical_reliability: float = _DEFAULT_RELIABILITY


def compute_overall_confidence(inputs: list[ConfidenceInput]) -> float:
    """Combine every input's confidence into one overall score.

    Args:
        inputs: Every department/input's `ConfidenceInput`.

    Returns:
        The historical-reliability-weighted average confidence, in
        [0.0, 1.0]. 0.0 if `inputs` is empty or every reliability is 0 —
        never a fabricated non-zero confidence with no supporting inputs.
    """
    total_weight = sum(item.historical_reliability for item in inputs)
    if total_weight <= 0:
        return 0.0
    return sum(item.confidence * item.historical_reliability for item in inputs) / total_weight
