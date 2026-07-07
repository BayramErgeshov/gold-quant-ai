"""Expected value calculation for the Statistics Engine.

Per DECISION_ENGINE.md "Decision Score" and MACHINE_LEARNING_ENGINE.md
"Objectives" ("Expected Move"): the classic institutional trade-quality
formula, blending win probability with the size of wins vs. losses.
"""

from __future__ import annotations


def compute_expected_value(
    *, win_probability: float, average_win_pct: float, average_loss_pct: float
) -> float:
    """Compute the expected value of a trade setup.

    Args:
        win_probability: Probability the trade wins, in [0.0, 1.0].
        average_win_pct: Average return of winning trades, in percent
            (a positive magnitude).
        average_loss_pct: Average return of losing trades, in percent
            (a positive magnitude — the loss size, not a negative number).

    Returns:
        `win_probability * average_win_pct - (1 - win_probability) *
        average_loss_pct`, in percent. Positive means the setup is
        favorable on average.
    """
    loss_probability = 1.0 - win_probability
    return win_probability * average_win_pct - loss_probability * average_loss_pct
