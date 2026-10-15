"""Pattern-based claim extraction from book chunks (BOOK_RAG.md "Claim Extraction").

Per BOOK_RAG.md: "Every important statement becomes a claim" — trading
ideas, statistical claims, risk-management rules, psychological
observations, and market hypotheses. This is a deliberately explainable
v1, in the same spirit as `topic_classification.py`'s keyword-based
approach: a claim is any sentence containing a checkable-assertion marker
(a causal/frequency/quantitative word, per `_CLAIM_MARKERS`), rather than
an unvalidated "NLP model" placeholder. "Never blindly trust any author" —
extraction only *identifies candidate claims*; it never judges whether
they are true (that is `claim_validation.py`'s job, against real history).
"""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MIN_CLAIM_LENGTH = 20
_MAX_CLAIM_LENGTH = 500

# A checkable assertion typically claims a relationship (cause, frequency,
# comparison, or quantity) rather than merely describing a definition.
_CLAIM_MARKERS: tuple[str, ...] = (
    "tends to",
    "tend to",
    "often",
    "usually",
    "typically",
    "frequently",
    "always",
    "never",
    "increases",
    "increase",
    "decreases",
    "decrease",
    "before",
    "after",
    "precedes",
    "follows",
    "probability",
    "likely",
    "unlikely",
    "should",
    "must",
    "outperform",
    "underperform",
    "reduces",
    "improves",
    "leads to",
    "results in",
    "correlate",
    "correlated",
    "predict",
    "signals",
    "indicates",
    "confirms",
    "%",
)


def extract_claims(text: str) -> list[str]:
    """Extract candidate checkable-claim sentences from a chunk of text.

    Args:
        text: Cleaned chunk text (post `cleaning.clean_text`).

    Returns:
        Sentences containing at least one claim marker, deduplicated,
        trimmed to a sane length range. Empty if nothing qualifies —
        never a fabricated claim.
    """
    normalized = text.replace("\n", " ")
    sentences = _SENTENCE_SPLIT.split(normalized)

    claims: list[str] = []
    seen: set[str] = set()
    for raw_sentence in sentences:
        sentence = raw_sentence.strip()
        if not (_MIN_CLAIM_LENGTH <= len(sentence) <= _MAX_CLAIM_LENGTH):
            continue
        lowered = sentence.lower()
        if not any(marker in lowered for marker in _CLAIM_MARKERS):
            continue
        if sentence in seen:
            continue
        seen.add(sentence)
        claims.append(sentence)

    return claims
