import json

import pytest

from sophia.core.input_gate import InputGate
from sophia.hats.schema import HatConfig
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_input_gate_parses_refund_intent(mock_llm: MockLLMProvider, tool_registry, cs_hat_config: HatConfig):
    mock_llm.set_responses([
        json.dumps({
            "action_requested": "refund",
            "target": "ORD-12345",
            "parameters": {"reason": "damaged product"},
        })
    ])

    gate = InputGate(
        llm=mock_llm,
        tool_definitions=tool_registry.get_definitions_text(),
        hat_config=cs_hat_config,
    )
    intent = await gate.parse("I received a damaged product and want a refund. Order #12345.")

    assert intent.action_requested == "refund"
    assert intent.target == "ORD-12345"
    assert intent.raw_message == "I received a damaged product and want a refund. Order #12345."
    assert intent.hat_name == "customer-service"
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_input_gate_handles_code_blocks(mock_llm: MockLLMProvider, tool_registry, cs_hat_config):
    mock_llm.set_responses([
        '```json\n{"action_requested": "order_status", "target": "ORD-11111", "parameters": {}}\n```'
    ])

    gate = InputGate(
        llm=mock_llm,
        tool_definitions=tool_registry.get_definitions_text(),
        hat_config=cs_hat_config,
    )
    intent = await gate.parse("Where is my order ORD-11111?")

    assert intent.action_requested == "order_status"
    assert intent.target == "ORD-11111"


@pytest.mark.asyncio
async def test_input_gate_general_inquiry(mock_llm: MockLLMProvider, tool_registry, cs_hat_config):
    mock_llm.set_responses([
        json.dumps({
            "action_requested": "general_inquiry",
            "target": None,
            "parameters": {},
        })
    ])

    gate = InputGate(
        llm=mock_llm,
        tool_definitions=tool_registry.get_definitions_text(),
        hat_config=cs_hat_config,
    )
    intent = await gate.parse("What are your store hours?")

    assert intent.action_requested == "general_inquiry"
    assert intent.target is None


@pytest.mark.asyncio
async def test_input_gate_includes_hat_prompt(mock_llm: MockLLMProvider, tool_registry, cs_hat_config):
    """Verify that the hat's system prompt fragment is included."""
    mock_llm.set_responses([
        json.dumps({"action_requested": "general_inquiry", "target": None, "parameters": {}})
    ])

    gate = InputGate(
        llm=mock_llm,
        tool_definitions=tool_registry.get_definitions_text(),
        hat_config=cs_hat_config,
    )
    await gate.parse("Hello")

    # The system prompt should include hat-specific context
    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "Customer Service" in system_prompt
    assert "TechMart" in system_prompt
