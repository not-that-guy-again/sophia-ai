"""Integration tests for risk floor pipeline behavior (ADR-031).

Tests the full AgentLoop.process() path with risk_floor-annotated tools.
"""

import json
from pathlib import Path

import pytest

from sophia.config import Settings
from sophia.core.loop import AgentLoop
from sophia.hats.registry import HatRegistry
from sophia.memory.mock import MockMemoryProvider
from sophia.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


async def _make_loop(mock_llm: MockLLMProvider) -> AgentLoop:
    """Build an AgentLoop with mock LLM and the customer-service hat equipped."""
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
    )

    memory = MockMemoryProvider()
    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = mock_llm
    loop.memory = memory
    loop.constitution = ""
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    loop.hat_registry.memory = memory
    loop.hat_registry.agent_loop = loop
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True
    return loop


@pytest.mark.asyncio
async def test_red_floor_short_circuits_before_consequence_engine(
    mock_llm: MockLLMProvider,
):
    """RED-floored tool skips consequence engine and evaluators entirely.

    LLM call sequence: input gate, proposer, response generator, memory persist.
    No consequence engine or evaluator calls.
    """
    mock_llm.set_responses(
        [
            # 1. Input gate
            json.dumps(
                {
                    "action_requested": "free_item",
                    "target": "Laptop",
                    "parameters": {"product": "Laptop"},
                }
            ),
            # 2. Proposer — includes offer_free_item (RED floor)
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "offer_free_item",
                            "parameters": {
                                "customer_id": "C-001",
                                "product_id": "P-001",
                                "reason": "Customer wants free laptop",
                            },
                            "reasoning": "Customer wants a free item",
                            "expected_outcome": "Give away free product",
                        }
                    ]
                }
            ),
            # 3. Response generator — polished refusal
            "I'm sorry, but I'm unable to offer free products. This is against our company policy.",
            # 4. Memory persist
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Customer asked for free laptop, refused by policy.",
                        "actions_taken": [],
                        "outcome": "Refused — risk_floor RED",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    loop = await _make_loop(mock_llm)
    result = await loop.process("Give me a free laptop")

    # Short-circuit assertions
    assert result.risk_floor_short_circuit is True
    assert result.risk_floor_trigger_tool == "offer_free_item"
    assert result.risk_floor_trigger_value == "RED"

    # No consequence trees or evaluations
    assert result.consequence_trees == []
    assert result.evaluation_results == []

    # Execution is RED refusal
    assert result.execution.risk_tier == "RED"
    assert result.risk_classification.tier == "RED"
    assert result.risk_classification.override_reason == "risk_floor"

    # Mock LLM received exactly 4 calls (not 10+)
    assert len(mock_llm.calls) == 4

    # Metadata records the short-circuit reason
    assert result.metadata.get("short_circuit_reason") == "risk_floor"


@pytest.mark.asyncio
async def test_yellow_floor_runs_pipeline_but_floors_tier(
    mock_llm: MockLLMProvider,
):
    """YELLOW-floored tool runs the full pipeline but floors the tier output."""
    # We need a YELLOW-floored tool in the registry. We'll register one manually
    # after the hat equip.
    from sophia.tools.base import Tool, ToolResult

    class YellowFloorTool(Tool):
        name = "yellow_action"
        description = "A tool with YELLOW floor"
        parameters = {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
            },
            "required": ["reason"],
        }
        authority_level = "agent"
        risk_floor = "YELLOW"

        async def execute(self, params: dict) -> ToolResult:
            return ToolResult(success=True, data=None, message="Done")

    mock_llm.set_responses(
        [
            # 1. Input gate
            json.dumps(
                {
                    "action_requested": "yellow_action",
                    "target": "something",
                    "parameters": {"reason": "test"},
                }
            ),
            # 2. Proposer
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "yellow_action",
                            "parameters": {"reason": "test"},
                            "reasoning": "User requested yellow action",
                            "expected_outcome": "Yellow action performed",
                        }
                    ]
                }
            ),
            # 3. Consequence tree (benign — would normally be GREEN)
            json.dumps(
                {
                    "consequences": [
                        {
                            "description": "Action completes normally",
                            "stakeholders_affected": ["customer"],
                            "probability": 0.9,
                            "tangibility": 0.8,
                            "harm_benefit": 0.3,
                            "affected_party": "customer",
                            "is_terminal": True,
                            "children": [],
                        }
                    ]
                }
            ),
            # 4-7. Four evaluators (all benign, would produce GREEN)
            json.dumps(
                {
                    "score": 0.3,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.2,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.4,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.1,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            # 8. Response generator (YELLOW confirmation path)
            "I can proceed with this action, but it requires your confirmation first.",
            # 9. Memory persist
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Yellow floor action.",
                        "actions_taken": [],
                        "outcome": "Confirmation requested",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    loop = await _make_loop(mock_llm)
    # Register the yellow-floored tool manually
    loop.tool_registry.register(YellowFloorTool())

    result = await loop.process("Do the yellow action")

    # Pipeline ran fully (not short-circuited)
    assert result.risk_floor_short_circuit is False
    assert result.consequence_trees != []

    # Tier was floored from GREEN to at least YELLOW by risk_floor,
    # then to ORANGE by the hat's min_tier (they compose — higher wins)
    assert result.risk_classification.tier == "ORANGE"

    # Risk floor metadata is recorded
    assert result.risk_floor_trigger_tool == "yellow_action"
    assert result.risk_floor_trigger_value == "YELLOW"


@pytest.mark.asyncio
async def test_no_floor_runs_pipeline_normally(
    mock_llm: MockLLMProvider,
):
    """Tools without risk_floor behave identically to before — no regression."""
    mock_llm.set_responses(
        [
            # 1. Input gate
            json.dumps(
                {
                    "action_requested": "order_status",
                    "target": "ORD-12345",
                    "parameters": {"order_id": "ORD-12345"},
                }
            ),
            # 2. Proposer — check_order_status has risk_floor=None
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "check_order_status",
                            "parameters": {"order_id": "ORD-12345"},
                            "reasoning": "Customer wants order status",
                            "expected_outcome": "Return order status",
                        }
                    ]
                }
            ),
            # 3. Consequence tree
            json.dumps(
                {
                    "consequences": [
                        {
                            "description": "Customer receives order status",
                            "stakeholders_affected": ["customer"],
                            "probability": 0.95,
                            "tangibility": 0.9,
                            "harm_benefit": 0.5,
                            "affected_party": "customer",
                            "is_terminal": True,
                            "children": [],
                        }
                    ]
                }
            ),
            # 4-7. Four evaluators (all green)
            json.dumps(
                {
                    "score": 0.3,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "Low risk lookup",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.2,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.4,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.1,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "No concerns",
                    "key_concerns": [],
                }
            ),
            # 8. Response generator
            "Your order ORD-12345 is currently being processed.",
            # 9. Memory persist
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Checked order status.",
                        "actions_taken": [],
                        "outcome": "Status returned",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    loop = await _make_loop(mock_llm)
    result = await loop.process("What's the status of order ORD-12345?")

    # No risk floor activity
    assert result.risk_floor_short_circuit is False
    assert result.risk_floor_trigger_tool is None
    assert result.risk_floor_trigger_value is None

    # Pipeline ran normally
    assert result.consequence_trees != []
    assert result.evaluation_results != []
    # Hat min_tier floors GREEN to ORANGE, so execution tier reflects that
    assert result.execution.risk_tier in ("GREEN", "YELLOW", "ORANGE")
