"""Unit tests for `Concept` and `ConceptRelationship` ORM models."""

from __future__ import annotations

import uuid

import pytest

from src.models.concept import Concept, ConceptRelationship

pytestmark = pytest.mark.unit


def test_concept_repr_includes_name_and_category() -> None:
    concept = Concept(name="Order Block", category="smart_money")

    assert repr(concept) == "Concept(name='Order Block', category='smart_money')"


def test_concept_relationship_repr_includes_edge() -> None:
    from_id = uuid.uuid4()
    to_id = uuid.uuid4()
    relationship = ConceptRelationship(
        from_concept_id=from_id, to_concept_id=to_id, relationship_type="precedes"
    )

    assert repr(relationship) == f"ConceptRelationship({from_id} -precedes-> {to_id})"
