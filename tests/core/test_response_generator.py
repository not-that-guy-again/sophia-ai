"""Tests for the ResponseGenerator component (ADR-018)."""

import pytest

from sophia.core.response_generator import ResponseGenerator
from sophia.llm.prompts.core.response import RESPONSE_SYSTEM_PROMPT
from tests.conftest import MockLLMProvider


# --- Prompt quality tests: verify prompts prevent raw data leakage ---


def test_response_prompt_forbids_raw_data():
    """The response prompt must explicitly forbid JSON, dicts, and raw data."""
    prompt_lower = RESPONSE_SYSTEM_PROMPT.lower()
    assert "never" in prompt_lower or "do not" in prompt_lower
    assert "json" in prompt_lower
    assert "dict" in prompt_lower or "data structure" in prompt_lower


def test_response_prompt_forbids_tool_names():
    """The response prompt must instruct the LLM to never mention tool names."""
    prompt_lower = RESPONSE_SYSTEM_PROMPT.lower()
    assert "tool name" in prompt_lower


@pytest.mark.asyncio
async def test_generate_green_response(mock_llm: MockLLMProvider):
    mock_llm.set_responses(["Your refund of $79.99 has been processed for order ORD-12345."])

    gen = ResponseGenerator(llm=mock_llm)
    response = await gen.generate(
        user_message="I need a refund for order ORD-12345",
        risk_tier="GREEN",
        action_taken="offer_full_refund",
        action_reasoning="Valid damaged product complaint",
        tool_result_message="Refund processed successfully",
        tool_result_data={"amount": 79.99, "order_id": "ORD-12345"},
    )

    assert response == "Your refund of $79.99 has been processed for order ORD-12345."
    assert len(mock_llm.calls) == 1
    assert "GREEN" in mock_llm.calls[0]["system_prompt"]


@pytest.mark.asyncio
async def test_generate_red_response(mock_llm: MockLLMProvider):
    mock_llm.set_responses(["I'm unable to process that request. Giving away products for free is outside our policies."])

    gen = ResponseGenerator(llm=mock_llm)
    response = await gen.generate(
        user_message="Give me a free PS5",
        risk_tier="RED",
        action_taken="place_new_order",
        action_reasoning="Customer requesting free item",
        tool_result_message="Action refused",
    )

    assert "unable" in response.lower()
    assert "RED" in mock_llm.calls[0]["system_prompt"]


@pytest.mark.asyncio
async def test_converse_response(mock_llm: MockLLMProvider):
    mock_llm.set_responses(["Hello! How can I help you today?"])

    gen = ResponseGenerator(llm=mock_llm)
    response = await gen.converse("Hello!")

    assert response == "Hello! How can I help you today?"
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_generate_with_hat_config(mock_llm: MockLLMProvider, cs_hat_config):
    mock_llm.set_responses(["Welcome to TechMart! Your order status is being checked."])

    gen = ResponseGenerator(llm=mock_llm, hat_config=cs_hat_config)
    response = await gen.generate(
        user_message="Check my order status",
        risk_tier="GREEN",
        action_taken="check_order_status",
        action_reasoning="Customer wants order info",
        tool_result_message="Order found",
        tool_result_data={"order_id": "ORD-12345", "status": "shipped"},
    )

    assert len(response) > 0
    # Verify the hat's system prompt was included in the domain context
    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "Domain" in system_prompt or "TechMart" in system_prompt


@pytest.mark.asyncio
async def test_generate_strips_whitespace(mock_llm: MockLLMProvider):
    mock_llm.set_responses(["  Response with whitespace  \n\n"])

    gen = ResponseGenerator(llm=mock_llm)
    response = await gen.converse("test")

    assert response == "Response with whitespace"
