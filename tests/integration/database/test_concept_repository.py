"""Integration tests for `ConceptRepository` and `ConceptRelationshipRepository`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.concept_repository import ConceptRelationshipRepository, ConceptRepository


async def test_get_or_create_creates_new_concept(session: AsyncSession) -> None:
    repo = ConceptRepository(session)

    concept = await repo.get_or_create("Order Block", category="smart_money")

    assert concept.name == "Order Block"
    assert concept.category == "smart_money"


async def test_get_or_create_returns_existing_concept(session: AsyncSession) -> None:
    repo = ConceptRepository(session)
    first = await repo.get_or_create("Order Block", category="smart_money")

    second = await repo.get_or_create("Order Block", category="ignored_on_existing")

    assert second.id == first.id
    assert second.category == "smart_money"


async def test_link_creates_relationship(session: AsyncSession) -> None:
    concepts = ConceptRepository(session)
    relationships = ConceptRelationshipRepository(session)
    order_block = await concepts.get_or_create("Order Block")
    liquidity = await concepts.get_or_create("Liquidity")

    relationship = await relationships.link(
        order_block.id, liquidity.id, relationship_type="related_to", weight=0.8
    )

    assert relationship.weight == 0.8


async def test_link_is_idempotent(session: AsyncSession) -> None:
    concepts = ConceptRepository(session)
    relationships = ConceptRelationshipRepository(session)
    order_block = await concepts.get_or_create("Order Block")
    liquidity = await concepts.get_or_create("Liquidity")

    first = await relationships.link(order_block.id, liquidity.id, relationship_type="related_to")
    second = await relationships.link(order_block.id, liquidity.id, relationship_type="related_to")

    assert first.id == second.id


async def test_list_related_finds_incoming_and_outgoing_edges(session: AsyncSession) -> None:
    concepts = ConceptRepository(session)
    relationships = ConceptRelationshipRepository(session)
    order_block = await concepts.get_or_create("Order Block")
    liquidity = await concepts.get_or_create("Liquidity")
    fvg = await concepts.get_or_create("Fair Value Gap")

    await relationships.link(order_block.id, liquidity.id, relationship_type="related_to")
    await relationships.link(fvg.id, order_block.id, relationship_type="precedes")

    related = await relationships.list_related(order_block.id)

    assert len(related) == 2
