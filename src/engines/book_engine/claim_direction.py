"""Keyword-based directional-lean classification for extracted claims.

Per the Institutional Knowledge Research System spec: "detect
contradictions/agreement" between books. Two claims on the same topic can
only meaningfully be compared once each has a directional lean; this is
the same deliberately explainable keyword-scoring approach as
`topic_classification.py` (BOOK_RAG.md "Machine Learning Department may
replace this with a trained classifier once validated training data
exists"). A claim with no directional keywords at all is "neutral" —
never guessed.
"""

from __future__ import annotations

from src.core.agents.report import Bias
from src.utils.keyword_classifier import score_keywords

_DIRECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bullish": (
        "bullish",
        "buy",
        "long position",
        "goes up",
        "moves higher",
        "upward",
        "increases the probability of a reversal upward",
        "accumulation",
        "higher high",
        "higher low",
        "upside",
    ),
    "bearish": (
        "bearish",
        "sell",
        "short position",
        "goes down",
        "moves lower",
        "downward",
        "distribution",
        "lower high",
        "lower low",
        "downside",
        "reversal downward",
    ),
}


def classify_claim_direction(statement: str) -> Bias:
    """Classify a claim's directional lean from its own wording.

    Args:
        statement: The extracted claim text.

    Returns:
        "bullish" or "bearish" if one side's keywords strictly dominate,
        otherwise "neutral" (includes no keywords at all, or an even tie
        — never a guessed direction).
    """
    scores = score_keywords(statement, _DIRECTION_KEYWORDS, max_categories=2)
    if not scores:
        return "neutral"
    if len(scores) > 1 and scores[0].score == scores[1].score:
        return "neutral"
    return "bullish" if scores[0].category == "bullish" else "bearish"
