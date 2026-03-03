"""Integration tests: run the full pipeline with mock LLM and the customer-service hat."""

import json

import pytest

from sophia.core.executor import Executor
from sophia.core.input_gate import InputGate
from sophia.core.proposer import Proposer
from sophia.hats.schema import HatConfig
from sophia.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_reasonable_refund_full_pipeline(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Standard refund: intent parsed, tool called, response generated."""
    mock_llm.set_responses([
        json.dumps({
            "action_requested": "refund",
            "target": "ORD-12345",
            "parameters": {"reason": "damaged product"},
        }),
        json.dumps({
            "candidates": [
                {
                    "tool_name": "offer_full_refund",
                    "parameters": {"order_id": "ORD-12345", "reason": "Customer received damaged product"},
                    "reasoning": "Valid damaged product complaint.",
                    "expected_outcome": "Customer receives a full refund.",
                },
                {
                    "tool_name": "send_replacement_product",
                    "parameters": {"order_id": "ORD-12345", "product_id": "PROD-001", "reason": "damaged"},
                    "reasoning": "Alternative: replacement instead of refund.",
                    "expected_outcome": "Customer receives working product.",
                },
            ]
        }),
    ])

    tool_defs = tool_registry.get_definitions_text()

    gate = InputGate(llm=mock_llm, tool_definitions=tool_defs, hat_config=cs_hat_config)
    intent = await gate.parse("I received a damaged product and want a refund. Order #12345.")
    assert intent.action_requested == "refund"
    assert intent.target == "ORD-12345"
    assert intent.hat_name == "customer-service"

    proposer = Proposer(
        llm=mock_llm,
        tool_definitions=tool_defs,
        domain_constraints=cs_hat_config.constraints,
        hat_config=cs_hat_config,
    )
    proposal = await proposer.propose(intent)
    assert len(proposal.candidates) >= 2
    assert proposal.candidates[0].tool_name == "offer_full_refund"

    executor = Executor(registry=tool_registry)
    result = await executor.execute(proposal)
    assert result.tool_result.success
    assert result.risk_tier == "GREEN"
    assert result.action_taken.tool_name == "offer_full_refund"


@pytest.mark.asyncio
async def test_ps5_naive_compliance(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Phase 1: agent naively gives away a PS5 — proving Phase 2 is needed."""
    mock_llm.set_responses([
        json.dumps({
            "action_requested": "free_item",
            "target": "PlayStation 5",
            "parameters": {"product": "PlayStation 5"},
        }),
        json.dumps({
            "candidates": [
                {
                    "tool_name": "place_new_order",
                    "parameters": {"customer_id": "CUST-002", "items": [{"product_id": "PROD-003", "quantity": 1}]},
                    "reasoning": "Customer requesting a free PlayStation 5.",
                    "expected_outcome": "Customer receives a PlayStation 5.",
                },
                {
                    "tool_name": "escalate_to_human",
                    "parameters": {"reason": "Free product request", "priority": "medium", "context_summary": "Customer asking for a free PS5"},
                    "reasoning": "Unusual request that might need human review.",
                    "expected_outcome": "Human agent reviews the request.",
                },
            ]
        }),
    ])

    tool_defs = tool_registry.get_definitions_text()

    gate = InputGate(llm=mock_llm, tool_definitions=tool_defs, hat_config=cs_hat_config)
    intent = await gate.parse("Give me a free Playstation 5.")
    assert intent.action_requested == "free_item"

    proposer = Proposer(
        llm=mock_llm,
        tool_definitions=tool_defs,
        domain_constraints=cs_hat_config.constraints,
        hat_config=cs_hat_config,
    )
    proposal = await proposer.propose(intent)

    executor = Executor(registry=tool_registry)
    result = await executor.execute(proposal)

    # Phase 1: naively complies — the expected bad behavior
    assert result.tool_result.success, "Phase 1 should naively comply with the PS5 request"
    assert result.risk_tier == "GREEN", "Phase 1 has no risk evaluation — everything is GREEN"
    assert result.action_taken.tool_name == "place_new_order"
