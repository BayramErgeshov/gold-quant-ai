"""News deduplication via content hashing.

Per NEWS_ENGINE.md ("Never analyze the same news twice"): the same story
is frequently republished by multiple sources or re-fetched minutes apart
with a slightly different timestamp. `NewsArticle.content_hash` carries a
unique constraint on this hash, so ingestion can cheaply detect and skip
duplicates via `NewsArticleRepository.get_by_content_hash`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime


def compute_content_hash(*, title: str, source: str, published_at: datetime) -> str:
    """Compute a stable deduplication hash for an article.

    Args:
        title: Article title (case/whitespace normalized before hashing).
        source: Publisher name (case normalized before hashing).
        published_at: Publication timestamp. Only the date component is
            used, since the same story is often republished minutes apart
            with a slightly different timestamp.

    Returns:
        A 64-character hex SHA-256 digest.
    """
    normalized_title = " ".join(title.strip().lower().split())
    normalized_source = source.strip().lower()
    key = f"{normalized_source}|{published_at.date().isoformat()}|{normalized_title}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
