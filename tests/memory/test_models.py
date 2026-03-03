"""Tests for memory data models (Episode, Entity, Relationship)."""

from datetime import datetime

from sophia.memory.models import Entity, Episode, Relationship


def test_episode_defaults():
    ep = Episode()
    assert ep.id == ""
    assert ep.summary == ""
    assert ep.participants == []
    assert ep.actions_taken == []
    assert ep.entities_referenced == []
    assert ep.embedding == []
    assert isinstance(ep.timestamp, datetime)


def test_episode_with_data():
    ep = Episode(
        id="ep_abc123",
        conversation_id="conv_001",
        participants=["customer", "agent"],
        summary="Customer asked about order status",
        actions_taken=["check_order_status"],
        outcome="Order found and status provided",
        entities_referenced=["Abbie", "ORD-12345"],
        hat_name="customer-service",
    )
    assert ep.id == "ep_abc123"
    assert len(ep.participants) == 2
    assert "Abbie" in ep.entities_referenced


def test_entity_defaults():
    ent = Entity()
    assert ent.id == ""
    assert ent.entity_type == ""
    assert ent.name == ""
    assert ent.attributes == {}
    assert ent.embedding == []


def test_entity_with_data():
    ent = Entity(
        id="ent_abc123",
        entity_type="person",
        name="Abbie",
        attributes={"email": "abbie@example.com", "tier": "gold"},
    )
    assert ent.entity_type == "person"
    assert ent.attributes["tier"] == "gold"


def test_relationship_defaults():
    rel = Relationship()
    assert rel.id == ""
    assert rel.from_entity == ""
    assert rel.relation == ""
    assert rel.to_entity == ""
    assert rel.metadata == {}


def test_relationship_with_data():
    rel = Relationship(
        id="rel_abc123",
        from_entity="Abbie",
        relation="purchased",
        to_entity="Litter Robot",
        metadata={"order_id": "ORD-12345"},
    )
    assert rel.relation == "purchased"
    assert rel.metadata["order_id"] == "ORD-12345"
