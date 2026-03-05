"""Integration test: parameter gate catches placeholders (ADR-019).

Mirrors the exact scenario from the 2026-03-03 audit: customer asks about an
order without providing an order number. The proposer generates
check_order_status(order_id="UNKNOWN") as candidate #1 and converse as #2.
The gate catches the placeholder and promotes converse.

After ADR-032 amendment: promoted converse on a non-general_inquiry intent
triggers situation evaluation instead of bypass.
"""

import json

import pytest

from sophia.core.loop import CONVERSE_TOOL_NAME, AgentLoop
from sophia.memory.mock import MockMemoryProvider
from tests.conftest import MockLLMProvider


# Shared helper for situation eval mock responses (order_status → GREEN)
def _situation_eval_responses():
    """Return mock responses for situation consequence tree + 4 evaluators."""
    return [
        # Situation consequence tree
        json.dumps(
            {
                "consequences": [
                    {
                        "description": "Customer order status is checked",
                        "stakeholders_affected": ["customer"],
                        "probability": 0.95,
                        "tangibility": 0.8,
                        "harm_benefit": 0.3,
                        "affected_party": "customer",
                        "is_terminal": True,
                        "children": [],
                    }
                ]
            }
        ),
        # Four evaluators — all benign (order lookup is harmless)
        json.dumps(
            {
                "score": 0.2,
                "confidence": 0.8,
                "flags": [],
                "reasoning": "Order status check is routine",
                "key_concerns": [],
            }
        ),
        json.dumps(
            {
                "score": 0.2,
                "confidence": 0.8,
                "flags": [],
                "reasoning": "No tribal harm",
                "key_concerns": [],
            }
        ),
        json.dumps(
            {
                "score": 0.2,
                "confidence": 0.8,
                "flags": [],
                "reasoning": "Standard request",
                "key_concerns": [],
            }
        ),
        json.dumps(
            {
                "score": 0.2,
                "confidence": 0.8,
                "flags": [],
                "reasoning": "Within authority",
                "key_concerns": [],
            }
        ),
    ]


@pytest.mark.asyncio
async def test_parameter_gate_shortcircuits_placeholder_order_id(
    mock_llm: MockLLMProvider, cs_hat_config
):
    """When proposer returns check_order_status(order_id='UNKNOWN') + converse,
    the parameter gate promotes converse. Since intent is order_status (not
    general_inquiry), situation evaluation runs (ADR-032 amendment)."""
    mock_llm.set_responses(
        [
            # 1. Input gate
            json.dumps(
                {
                    "action_requested": "order_status",
                    "target": None,
                    "parameters": {},
                }
            ),
            # 2. Proposer — check_order_status with placeholder, then converse
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "check_order_status",
                            "parameters": {"order_id": "UNKNOWN"},
                            "reasoning": "Customer wants order status but we need the order ID first",
                            "expected_outcome": "Look up order status",
                        },
                        {
                            "tool_name": "converse",
                            "parameters": {},
                            "reasoning": "We don't yet have the order ID, which is required to look up any order details",
                            "expected_outcome": "Ask the customer for their order number",
                        },
                    ]
                }
            ),
            # 3-7. Situation evaluation (consequence tree + 4 evaluators)
            *_situation_eval_responses(),
            # 8. Response generator (converse path with situation tier)
            "I'd be happy to help you check on your order! Could you please provide me with your order number so I can look that up for you?",
            # 9. Memory extractor
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Customer asked about order status without providing order number.",
                        "actions_taken": [],
                        "outcome": "Agent asked for order number",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    from sophia.config import Settings
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry
    from pathlib import Path

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
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("Where is my order? It hasn't arrived yet.")

    # Situation evaluation ran — not bypassed (ADR-032 amendment)
    assert result.bypassed is False
    assert result.situation_tree is not None
    assert result.situation_risk_classification is not None

    # Response is conversational (asks for order number)
    assert "order" in result.response.lower()

    # Execution used converse
    assert result.execution.action_taken.tool_name == CONVERSE_TOOL_NAME

    # Metadata contains parameter gate results
    assert "parameter_gate" in result.metadata
    gate_data = result.metadata["parameter_gate"]
    assert len(gate_data) == 2

    # check_order_status failed validation
    cos_validation = next(v for v in gate_data if v["tool_name"] == "check_order_status")
    assert cos_validation["passed"] is False
    assert len(cos_validation["failures"]) > 0
    assert any("UNKNOWN" in f for f in cos_validation["failures"])

    # converse passed validation
    converse_validation = next(v for v in gate_data if v["tool_name"] == "converse")
    assert converse_validation["passed"] is True

    # 9 LLM calls: input gate, proposer, consequence tree, 4 evaluators, response gen, memory
    assert len(mock_llm.calls) == 9


@pytest.mark.asyncio
async def test_parameter_gate_synthesizes_converse_when_no_converse_candidate(
    mock_llm: MockLLMProvider, cs_hat_config
):
    """When ALL candidates fail and no converse candidate exists,
    the gate synthesizes one. Situation evaluation runs for non-general_inquiry."""
    mock_llm.set_responses(
        [
            # 1. Input gate
            json.dumps(
                {
                    "action_requested": "order_status",
                    "target": None,
                    "parameters": {},
                }
            ),
            # 2. Proposer — only check_order_status with placeholder, NO converse
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "check_order_status",
                            "parameters": {"order_id": "UNKNOWN"},
                            "reasoning": "Customer wants order status but we need the order ID first",
                            "expected_outcome": "Look up order status",
                        },
                    ]
                }
            ),
            # 3-7. Situation evaluation (consequence tree + 4 evaluators)
            *_situation_eval_responses(),
            # 8. Response generator (converse path)
            "Could you please share your order number? I'll look into the status for you right away.",
            # 9. Memory extractor
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Customer asked about order without providing number.",
                        "actions_taken": [],
                        "outcome": "Agent requested order number",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    from sophia.config import Settings
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry
    from pathlib import Path

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
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("What's my order status?")

    # Situation evaluation ran (ADR-032 amendment)
    assert result.bypassed is False
    assert result.situation_tree is not None
    assert result.execution.action_taken.tool_name == CONVERSE_TOOL_NAME

    # Gate metadata shows the failure
    assert "parameter_gate" in result.metadata
    gate_data = result.metadata["parameter_gate"]
    cos_validation = next(v for v in gate_data if v["tool_name"] == "check_order_status")
    assert cos_validation["passed"] is False

    # 9 LLM calls: input gate, proposer, consequence tree, 4 evaluators, response gen, memory
    assert len(mock_llm.calls) == 9


@pytest.mark.asyncio
async def test_parameter_gate_passes_valid_candidates_through(
    mock_llm: MockLLMProvider, cs_hat_config
):
    """When candidates have valid parameters, the gate passes them through
    and the full pipeline runs normally."""
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
            # 2. Proposer — valid order ID
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "check_order_status",
                            "parameters": {"order_id": "ORD-12345"},
                            "reasoning": "Looking up order ORD-12345",
                            "expected_outcome": "Order status returned",
                        },
                    ]
                }
            ),
            # 3. Consequence tree
            json.dumps(
                {
                    "consequences": [
                        {
                            "description": "Customer sees order status",
                            "stakeholders_affected": ["customer"],
                            "probability": 0.95,
                            "tangibility": 0.8,
                            "harm_benefit": 0.3,
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
                    "score": 0.2,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "ok",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.2,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "ok",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.2,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "ok",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": 0.2,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "ok",
                    "key_concerns": [],
                }
            ),
            # 8. Response generator
            "Your order ORD-12345 has been shipped and is on its way!",
            # 9. Memory extractor
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Customer checked order status.",
                        "actions_taken": ["check_order_status"],
                        "outcome": "Status shown",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    from sophia.config import Settings
    from sophia.tools.registry import ToolRegistry
    from sophia.hats.registry import HatRegistry
    from pathlib import Path

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
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("What's the status of order ORD-12345?")

    # Pipeline ran fully — NOT bypassed
    assert result.bypassed is False
    assert len(result.consequence_trees) > 0
    assert len(result.evaluation_results) > 0

    # Gate metadata is present and shows pass
    assert "parameter_gate" in result.metadata
    gate_data = result.metadata["parameter_gate"]
    assert all(v["passed"] for v in gate_data)

    # 8 LLM calls: gate, proposer, consequence tree, 4 evaluators, memory
    # (hat min_tier="ORANGE" floors GREEN → ORANGE, skipping response generator)
    assert len(mock_llm.calls) == 8
