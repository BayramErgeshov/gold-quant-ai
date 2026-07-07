"""Text cleaning for raw collected news articles (NEWS_ENGINE.md pipeline step).

NewsAPI (and similar aggregators) truncate long article bodies with a
suffix like "... [+1234 chars]" and often carry irregular whitespace from
the source HTML. Neither is meaningful content, so both are stripped
before classification/entity-extraction/storage.
"""

from __future__ import annotations

import re

_TRUNCATION_SUFFIX = re.compile(r"\s*[\[(]\+\d+\s*chars[\])]\s*$")
_WHITESPACE_RUN = re.compile(r"\s+")


def clean_article_text(text: str) -> str:
    """Normalize a raw article title/summary/content field.

    Args:
        text: Raw text as returned by the news provider.

    Returns:
        Text with the truncation marker removed and whitespace collapsed,
        leading/trailing whitespace stripped.
    """
    without_truncation_marker = _TRUNCATION_SUFFIX.sub("", text)
    return _WHITESPACE_RUN.sub(" ", without_truncation_marker).strip()
