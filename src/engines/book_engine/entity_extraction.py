"""Rule-based entity extraction for book chunks.

Per BOOK_RAG.md "Entity Extraction". A lightweight, fully explainable v1:
matches known currencies, institutions, countries and macro indicators
against curated word lists. Full named-entity recognition (people,
companies, arbitrary strategy names) requires a trained NER model and is
deferred to the Machine Learning Engine (a later roadmap phase) rather
than approximated here.
"""

from __future__ import annotations

import re

_CURRENCIES: tuple[str, ...] = (
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
    "CNY",
    "XAU",
    "XAG",
    "AUD",
    "CAD",
    "NZD",
)
_INSTITUTIONS: tuple[str, ...] = (
    "Federal Reserve",
    "FOMC",
    "European Central Bank",
    "ECB",
    "Bank of Japan",
    "BOJ",
    "People's Bank of China",
    "PBOC",
    "Bank of England",
    "BOE",
    "IMF",
    "World Bank",
    "BIS",
    "CFTC",
    "SEC",
    "World Gold Council",
)
_COUNTRIES: tuple[str, ...] = (
    "United States",
    "China",
    "Japan",
    "United Kingdom",
    "Eurozone",
    "Germany",
    "Switzerland",
    "Australia",
    "Canada",
)
_INDICATORS: tuple[str, ...] = (
    "CPI",
    "PPI",
    "PCE",
    "GDP",
    "PMI",
    "NFP",
    "Non-Farm Payrolls",
    "Retail Sales",
    "Unemployment Rate",
    "Interest Rate",
    "Federal Funds Rate",
)

_CATEGORY_WORD_LISTS: dict[str, tuple[str, ...]] = {
    "currencies": _CURRENCIES,
    "institutions": _INSTITUTIONS,
    "countries": _COUNTRIES,
    "indicators": _INDICATORS,
}


def _contains_word(text: str, phrase: str) -> bool:
    pattern = r"\b" + re.escape(phrase) + r"\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract known entities from text, grouped by category.

    Args:
        text: Chunk text to scan.

    Returns:
        A dict mapping category name to the distinct matched entity
        strings (original casing from the word list), in list order.
        Categories with no matches are omitted entirely.
    """
    result: dict[str, list[str]] = {}

    for category, entities in _CATEGORY_WORD_LISTS.items():
        matches = [entity for entity in entities if _contains_word(text, entity)]
        if matches:
            result[category] = matches

    return result
