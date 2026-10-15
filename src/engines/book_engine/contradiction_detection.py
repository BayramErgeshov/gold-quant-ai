"""Contradiction/agreement detection between extracted book claims.

Per the Institutional Knowledge Research System spec: "Create links
between books, detect contradictions/agreement." Two claims are only
comparable once grouped by topic (BOOK_RAG.md taxonomy) and directional
lean (`claim_direction.classify_claim_direction`) — claims with no
detectable direction are excluded rather than guessed into a group.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from src.engines.book_engine.claim_direction import classify_claim_direction
from src.models.book_claim import BookClaim

_MIN_CLAIMS_FOR_AGREEMENT = 2


@dataclass(frozen=True, slots=True)
class ClaimAgreement:
    """Two or more claims sharing a topic and directional lean.

    Attributes:
        topic: The shared `BookClaim.topic`.
        direction: The shared directional lean ("bullish" or "bearish").
        claim_ids: Every agreeing claim's id.
    """

    topic: str
    direction: str
    claim_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ClaimContradiction:
    """Claims sharing a topic but disagreeing on directional lean.

    Attributes:
        topic: The shared `BookClaim.topic`.
        bullish_claim_ids: Claim ids leaning bullish on this topic.
        bearish_claim_ids: Claim ids leaning bearish on this topic.
    """

    topic: str
    bullish_claim_ids: list[uuid.UUID] = field(default_factory=list)
    bearish_claim_ids: list[uuid.UUID] = field(default_factory=list)


def _group_by_topic_and_direction(
    claims: list[BookClaim],
) -> dict[str, dict[str, list[uuid.UUID]]]:
    grouped: dict[str, dict[str, list[uuid.UUID]]] = defaultdict(lambda: defaultdict(list))
    for claim in claims:
        if claim.topic is None:
            continue
        direction = classify_claim_direction(claim.statement)
        if direction == "neutral":
            continue
        grouped[claim.topic][direction].append(claim.id)
    return grouped


def find_agreements(claims: list[BookClaim]) -> list[ClaimAgreement]:
    """Find claim groups sharing a topic and a directional lean.

    Args:
        claims: Extracted claims to compare (typically all claims for a
            given topic, or across the whole knowledge base).

    Returns:
        One `ClaimAgreement` per (topic, direction) pair with at least
        `_MIN_CLAIMS_FOR_AGREEMENT` claims. Empty if nothing qualifies.
    """
    grouped = _group_by_topic_and_direction(claims)
    return [
        ClaimAgreement(topic=topic, direction=direction, claim_ids=claim_ids)
        for topic, by_direction in grouped.items()
        for direction, claim_ids in by_direction.items()
        if len(claim_ids) >= _MIN_CLAIMS_FOR_AGREEMENT
    ]


def find_contradictions(claims: list[BookClaim]) -> list[ClaimContradiction]:
    """Find topics where claims disagree on directional lean.

    Args:
        claims: Extracted claims to compare.

    Returns:
        One `ClaimContradiction` per topic where both a bullish and a
        bearish claim exist. Empty if nothing qualifies.
    """
    grouped = _group_by_topic_and_direction(claims)
    return [
        ClaimContradiction(
            topic=topic,
            bullish_claim_ids=by_direction["bullish"],
            bearish_claim_ids=by_direction["bearish"],
        )
        for topic, by_direction in grouped.items()
        if by_direction.get("bullish") and by_direction.get("bearish")
    ]
