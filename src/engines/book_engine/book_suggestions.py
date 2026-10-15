"""Suggest which knowledge topics the book library covers thinly.

Per the Institutional Knowledge Research System spec: "Suggest additional
books that could improve the platform." This never fabricates specific
book titles or authors it cannot verify exist — an unverifiable
recommendation would itself violate "Never blindly trust any author."
Instead it identifies which topics in this platform's own taxonomy
(`topic_classification.TOPIC_KEYWORDS`) have the fewest ingested chunks,
so the user can decide what to add — an honest, explainable signal
grounded in this platform's own data, not an invented title.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engines.book_engine.topic_classification import TOPIC_KEYWORDS

_DEFAULT_MAX_SUGGESTIONS = 5


@dataclass(frozen=True, slots=True)
class TopicCoverageGap:
    """A topic in this platform's taxonomy with thin book coverage.

    Attributes:
        topic: The topic name (`topic_classification.TOPIC_KEYWORDS` key).
        chunk_count: How many ingested chunks are currently classified
            under this topic. 0 means no book in the library has ever
            touched it.
    """

    topic: str
    chunk_count: int


def suggest_thin_topics(
    topic_chunk_counts: dict[str, int], *, max_suggestions: int = _DEFAULT_MAX_SUGGESTIONS
) -> list[TopicCoverageGap]:
    """Rank this platform's known topics by how thinly the library covers them.

    Args:
        topic_chunk_counts: `{topic: chunk_count}` from
            `BookChunkRepository.count_by_topic()`. A topic absent from
            this dict is treated as having 0 chunks.
        max_suggestions: Maximum number of topics to return.

    Returns:
        Up to `max_suggestions` `TopicCoverageGap`, least-covered first
        (0-chunk topics first, then ascending chunk count) — never a
        fabricated book title, only a topic name from this platform's own
        taxonomy the user could look for a book on.
    """
    gaps = [
        TopicCoverageGap(topic=topic, chunk_count=topic_chunk_counts.get(topic, 0))
        for topic in TOPIC_KEYWORDS
    ]
    gaps.sort(key=lambda gap: gap.chunk_count)
    return gaps[:max_suggestions]
