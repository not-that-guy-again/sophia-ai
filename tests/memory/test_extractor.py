"""Tests for the MemoryExtractor — LLM-based episode/entity extraction."""

import json

import pytest

from sophia.memory.extractor import MemoryExtractor
from sophia.memory.mock import MockMemoryProvider
from tests.conftest import MockLLMProvider


@pytest.fixture
def memory():
    return MockMemoryProvider()


@pytest.fixture
def extractor(mock_llm, memory):
    return MemoryExtractor(llm=mock_llm, memory=memory)


EXTRACTION_RESPONSE = json.dumps(
    {
        "episode": {
            "participants": ["Abbie", "agent"],
            "summary": "Abbie requested a refund for her damaged Litter Robot (ORD-12345). Agent processed a full refund.",
            "actions_taken": ["offer_full_refund"],
            "outcome": "Full refund of $299.99 issued to Abbie",
        },
        "entities": [
            {
                "entity_type": "person",
                "name": "Abbie",
                "attributes": {"order": "ORD-12345"},
            },
            {
                "entity_type": "product",
                "name": "Litter Robot",
                "attributes": {"issue": "damaged", "price": "$299.99"},
            },
        ],
        "relationships": [
            {
                "from_entity": "Abbie",
                "relation": "purchased",
                "to_entity": "Litter Robot",
                "metadata": {"order_id": "ORD-12345"},
            },
        ],
    }
)

EMPTY_EXTRACTION = json.dumps(
    {
        "episode": {
            "participants": ["customer", "agent"],
            "summary": "Customer greeted the agent.",
            "actions_taken": [],
            "outcome": "Conversational exchange",
        },
        "entities": [],
        "relationships": [],
    }
)


@pytest.mark.asyncio
async def test_extract_and_store_full(mock_llm: MockLLMProvider, memory, extractor):
    mock_llm.set_responses([EXTRACTION_RESPONSE])

    episode = await extractor.extract_and_store(
        user_message="I need a refund for my damaged Litter Robot, order ORD-12345",
        action_taken="offer_full_refund",
        action_parameters={"order_id": "ORD-12345", "reason": "damaged"},
        outcome="Full refund of $299.99 issued",
    )

    # Verify episode stored
    assert episode.id.startswith("ep_")
    assert "Abbie" in episode.participants
    assert "refund" in episode.summary.lower()
    assert len(memory.episodes) == 1

    # Verify entities stored
    assert len(memory.entities) == 2
    entity_names = {e.name for e in memory.entities.values()}
    assert "Abbie" in entity_names
    assert "Litter Robot" in entity_names

    # Verify relationship stored
    assert len(memory.relationships) == 1
    rel = list(memory.relationships.values())[0]
    assert rel.from_entity == "Abbie"
    assert rel.relation == "purchased"
    assert rel.to_entity == "Litter Robot"


@pytest.mark.asyncio
async def test_extract_and_store_empty_entities(mock_llm: MockLLMProvider, memory, extractor):
    mock_llm.set_responses([EMPTY_EXTRACTION])

    episode = await extractor.extract_and_store(
        user_message="Hello!",
        action_taken="converse",
        action_parameters={},
        outcome="Conversational exchange",
    )

    assert len(memory.episodes) == 1
    assert episode.summary == "Customer greeted the agent."
    assert len(memory.entities) == 0
    assert len(memory.relationships) == 0


@pytest.mark.asyncio
async def test_extract_stores_entities_referenced_on_episode(
    mock_llm: MockLLMProvider, memory, extractor
):
    mock_llm.set_responses([EXTRACTION_RESPONSE])

    episode = await extractor.extract_and_store(
        user_message="Refund for Abbie's Litter Robot",
        action_taken="offer_full_refund",
        action_parameters={},
        outcome="Refund issued",
    )

    assert "Abbie" in episode.entities_referenced
    assert "Litter Robot" in episode.entities_referenced


@pytest.mark.asyncio
async def test_extract_conversation_id_propagated(mock_llm: MockLLMProvider, memory, extractor):
    mock_llm.set_responses([EMPTY_EXTRACTION])

    episode = await extractor.extract_and_store(
        user_message="Hello",
        action_taken="converse",
        action_parameters={},
        outcome="Greeting",
        conversation_id="conv_specific_123",
    )

    assert episode.conversation_id == "conv_specific_123"
