"""Tests for MockMemoryProvider — validates all MemoryProvider operations."""

from datetime import UTC, datetime, timedelta

import pytest

from sophia.memory.mock import MockMemoryProvider
from sophia.memory.models import Entity, Episode, Relationship


@pytest.fixture
def memory():
    return MockMemoryProvider()


# --- Episode storage and recall ---


@pytest.mark.asyncio
async def test_store_and_recall_episode(memory):
    ep = Episode(
        summary="Customer asked about order status",
        participants=["customer", "agent"],
        entities_referenced=["Abbie", "ORD-12345"],
        hat_name="customer-service",
    )
    ep_id = await memory.store_episode(ep)
    assert ep_id.startswith("ep_")
    assert ep.id == ep_id

    # Recall by entity reference
    results = await memory.recall_by_entity("person", "Abbie")
    assert len(results) == 1
    assert results[0].summary == "Customer asked about order status"


@pytest.mark.asyncio
async def test_recall_by_entity_returns_empty_for_unknown(memory):
    results = await memory.recall_by_entity("person", "unknown")
    assert results == []


@pytest.mark.asyncio
async def test_recall_by_timerange(memory):
    now = datetime.now(UTC)
    old = Episode(
        summary="Old conversation",
        timestamp=now - timedelta(days=30),
    )
    recent = Episode(
        summary="Recent conversation",
        timestamp=now - timedelta(hours=1),
    )
    await memory.store_episode(old)
    await memory.store_episode(recent)

    results = await memory.recall_by_timerange(
        start=now - timedelta(days=1),
        end=now,
    )
    assert len(results) == 1
    assert results[0].summary == "Recent conversation"


@pytest.mark.asyncio
async def test_recall_similar_returns_most_recent(memory):
    for i in range(5):
        ep = Episode(
            summary=f"Conversation {i}",
            timestamp=datetime.now(UTC) + timedelta(seconds=i),
        )
        await memory.store_episode(ep)

    results = await memory.recall_similar(query_embedding=[0.1, 0.2], limit=3)
    assert len(results) == 3
    # Most recent first
    assert results[0].summary == "Conversation 4"


@pytest.mark.asyncio
async def test_recall_respects_limit(memory):
    for i in range(10):
        await memory.store_episode(Episode(
            summary=f"Conversation {i}",
            entities_referenced=["Abbie"],
        ))

    results = await memory.recall_by_entity("person", "Abbie", limit=3)
    assert len(results) == 3


# --- Entity storage and lookup ---


@pytest.mark.asyncio
async def test_store_and_get_entity(memory):
    ent = Entity(
        entity_type="person",
        name="Abbie",
        attributes={"email": "abbie@example.com"},
    )
    ent_id = await memory.store_entity(ent)
    assert ent_id.startswith("ent_")

    retrieved = await memory.get_entity(ent_id)
    assert retrieved is not None
    assert retrieved.name == "Abbie"
    assert retrieved.attributes["email"] == "abbie@example.com"


@pytest.mark.asyncio
async def test_get_entity_returns_none_for_unknown(memory):
    result = await memory.get_entity("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_search_entities_by_name(memory):
    await memory.store_entity(Entity(entity_type="person", name="Abbie"))
    await memory.store_entity(Entity(entity_type="person", name="Bob"))
    await memory.store_entity(Entity(entity_type="product", name="Litter Robot"))

    results = await memory.search_entities("abbie")
    assert len(results) == 1
    assert results[0].name == "Abbie"


@pytest.mark.asyncio
async def test_search_entities_by_attribute(memory):
    await memory.store_entity(Entity(
        entity_type="person",
        name="Abbie",
        attributes={"email": "abbie@example.com"},
    ))

    results = await memory.search_entities("abbie@example.com")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_entities_case_insensitive(memory):
    await memory.store_entity(Entity(entity_type="person", name="Abbie"))

    results = await memory.search_entities("ABBIE")
    assert len(results) == 1


# --- Relationship storage and traversal ---


@pytest.mark.asyncio
async def test_store_and_get_relationships(memory):
    ent1_id = await memory.store_entity(Entity(entity_type="person", name="Abbie"))
    ent2_id = await memory.store_entity(Entity(entity_type="product", name="Litter Robot"))

    rel = Relationship(
        from_entity=ent1_id,
        relation="purchased",
        to_entity=ent2_id,
        metadata={"order_id": "ORD-12345"},
    )
    rel_id = await memory.store_relationship(rel)
    assert rel_id.startswith("rel_")

    # Get relationships for entity 1
    rels = await memory.get_relationships(ent1_id)
    assert len(rels) == 1
    assert rels[0].relation == "purchased"
    assert rels[0].to_entity == ent2_id


@pytest.mark.asyncio
async def test_get_relationships_filtered_by_type(memory):
    ent1_id = await memory.store_entity(Entity(entity_type="person", name="Abbie"))
    ent2_id = await memory.store_entity(Entity(entity_type="product", name="Litter Robot"))
    ent3_id = await memory.store_entity(Entity(entity_type="issue", name="Motor defect"))

    await memory.store_relationship(Relationship(
        from_entity=ent1_id, relation="purchased", to_entity=ent2_id,
    ))
    await memory.store_relationship(Relationship(
        from_entity=ent1_id, relation="reported_issue", to_entity=ent3_id,
    ))

    purchased = await memory.get_relationships(ent1_id, relation_type="purchased")
    assert len(purchased) == 1
    assert purchased[0].to_entity == ent2_id

    all_rels = await memory.get_relationships(ent1_id)
    assert len(all_rels) == 2


@pytest.mark.asyncio
async def test_get_relationships_returns_empty_for_unknown(memory):
    rels = await memory.get_relationships("nonexistent")
    assert rels == []


# --- Hat independence (ADR-012) ---


@pytest.mark.asyncio
async def test_memory_persists_across_hat_context():
    """Memory stored under one hat is accessible without any hat context.
    This validates ADR-012: memory is independent from hats.
    """
    memory = MockMemoryProvider()

    # Store under customer-service context
    ep = Episode(
        summary="Abbie called about her Litter Robot",
        entities_referenced=["Abbie"],
        hat_name="customer-service",
    )
    await memory.store_episode(ep)

    await memory.store_entity(Entity(
        entity_type="person",
        name="Abbie",
        attributes={"issue": "motor defect"},
    ))

    # Recall without any hat context — memory is not hat-scoped
    results = await memory.recall_by_entity("person", "Abbie")
    assert len(results) == 1
    assert results[0].hat_name == "customer-service"

    entities = await memory.search_entities("Abbie")
    assert len(entities) == 1
    assert entities[0].attributes["issue"] == "motor defect"
