"""Unit tests for the `CURRENT_STATE.md` generator."""

from __future__ import annotations

import pytest
from scripts.generate_current_state import generate_current_state_markdown

pytestmark = pytest.mark.unit


def test_generate_current_state_markdown_includes_every_required_section() -> None:
    content = generate_current_state_markdown()

    required_sections = (
        "## Current Architecture",
        "## Implemented AI Departments",
        "## Implemented Strategies",
        "## Implemented Indicators / Technical Agents",
        "## Implemented News Sources",
        "## Implemented Correlation Sources",
        "## Implemented ML Models",
        "## Books Intelligence",
        "## Execution Engine",
        "## Telegram Integration",
        "## Web/Desktop Interface",
        "## Database Structure",
        "## Qdrant Structure",
        "## Current Limitations",
        "## Known Issues",
        "## Production Readiness",
        "## Roadmap",
        "## Future Improvements",
    )
    for section in required_sections:
        assert section in content


def test_generate_current_state_markdown_lists_real_departments_and_tables() -> None:
    content = generate_current_state_markdown()

    assert "`technical`" in content
    assert "`scalping_engine`" in content
    assert "`trades`" in content
    assert "`weight_recommendations`" in content


def test_generate_current_state_markdown_is_deterministic() -> None:
    first = generate_current_state_markdown()
    second = generate_current_state_markdown()

    assert first == second


def test_generate_current_state_markdown_excludes_infra_routes() -> None:
    content = generate_current_state_markdown()

    assert "/openapi.json" not in content
