"""Integration tests for the pipeline bug fix (ADR-032 amendment to ADR-030).

Verifies that promoted converse on policy-constrained requests now runs
situation evaluation, while general_inquiry still bypasses.
"""

import json

import pytest

from sophia.core.loop import AgentLoop
from sophia.memory.mock import MockMemoryProvider
from tests.conftest import MockLLMProvider


def _build_loop(mock_llm, settings):
    """Build an AgentLoop with mock LLM using __new__ + direct injection."""
    from pathlib import Path

    from sophia.hats.registry import HatRegistry
    from sophia.tools.registry import ToolRegistry

    loop = AgentLoop.__new__(AgentLoop)
    loop.settings = settings
    loop.llm = mock_llm
    loop.memory = MockMemoryProvider()
    loop.tool_registry = ToolRegistry()
    loop.hat_registry = HatRegistry(
        hats_dir=Path(settings.hats_dir),
        tool_registry=loop.tool_registry,
    )
    return loop


@pytest.mark.asyncio
async def test_synthesized_converse_on_policy_request_runs_situation_eval(
    mock_llm: MockLLMProvider, cs_hat_config
):
    """Discount request with no order context → parameter gate synthesizes converse →
    situation evaluation runs → risk tier is not GREEN."""
    mock_llm.set_responses(
        [
            # 1. Input gate — discount intent (policy-constrained)
            json.dumps(
                {
                    "action_requested": "discount",
                    "target": None,
                    "parameters": {},
                }
            ),
            # 2. Proposer — discount tool with missing params, then converse
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "offer_discount",
                            "parameters": {
                                "customer_id": "UNKNOWN",
                                "discount_percent": 20,
                                "reason": "Customer request",
                            },
                            "reasoning": "Customer wants a discount",
                            "expected_outcome": "Apply discount to order",
                        },
                        {
                            "tool_name": "converse",
                            "parameters": {},
                            "reasoning": "Need customer details before applying discount",
                            "expected_outcome": "Ask for customer info",
                        },
                    ]
                }
            ),
            # 3. Situation consequence tree — discount has negative consequences
            json.dumps(
                {
                    "consequences": [
                        {
                            "description": "Customer receives unauthorized discount",
                            "stakeholders_affected": ["business"],
                            "probability": 0.9,
                            "tangibility": 0.9,
                            "harm_benefit": -0.7,
                            "affected_party": "business",
                            "is_terminal": True,
                            "children": [],
                        }
                    ]
                }
            ),
            # 4-7. Four evaluators — negative scores for unauthorized discount
            json.dumps(
                {
                    "score": -0.6,
                    "confidence": 0.85,
                    "flags": ["unauthorized_discount"],
                    "reasoning": "Discount without verification",
                    "key_concerns": ["no order context"],
                }
            ),
            json.dumps(
                {
                    "score": -0.5,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "Policy violation",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": -0.4,
                    "confidence": 0.8,
                    "flags": [],
                    "reasoning": "Requires order verification",
                    "key_concerns": [],
                }
            ),
            json.dumps(
                {
                    "score": -0.3,
                    "confidence": 0.75,
                    "flags": [],
                    "reasoning": "Agent authority concerns",
                    "key_concerns": [],
                }
            ),
            # 8. Response generator (converse with situation tier)
            "I understand you'd like a discount. Could you please provide your order number so I can look into this for you?",
            # 9. Memory extractor
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Customer requested discount without order context.",
                        "actions_taken": [],
                        "outcome": "Agent asked for order details",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    from sophia.config import Settings

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
    )

    loop = _build_loop(mock_llm, settings)
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("Can I get a discount on my next order?")

    # Situation evaluation ran — not bypassed
    assert result.bypassed is False
    assert result.situation_tree is not None
    assert result.situation_risk_classification is not None

    # Risk tier should not be GREEN (discount without context is risky)
    assert result.risk_classification.tier != "GREEN"


@pytest.mark.asyncio
async def test_synthesized_converse_on_general_inquiry_still_bypasses(
    mock_llm: MockLLMProvider, cs_hat_config
):
    """'What are your store hours?' → general_inquiry → bypassed, no situation tree."""
    mock_llm.set_responses(
        [
            # 1. Input gate — general_inquiry
            json.dumps(
                {
                    "action_requested": "general_inquiry",
                    "target": None,
                    "parameters": {},
                }
            ),
            # 2. Proposer — converse
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "converse",
                            "parameters": {},
                            "reasoning": "General question about store hours",
                            "expected_outcome": "Provide store hours information",
                        }
                    ]
                }
            ),
            # 3. Response generator (converse path — bypass)
            "Our store hours are Monday through Friday, 9 AM to 6 PM, and Saturday 10 AM to 4 PM.",
            # 4. Memory extractor
            json.dumps(
                {
                    "episode": {
                        "participants": ["customer", "agent"],
                        "summary": "Customer asked about store hours.",
                        "actions_taken": [],
                        "outcome": "Provided store hours",
                    },
                    "entities": [],
                    "relationships": [],
                }
            ),
        ]
    )

    from sophia.config import Settings

    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="test",
        default_hat="customer-service",
        memory_provider="mock",
    )

    loop = _build_loop(mock_llm, settings)
    await loop.hat_registry.equip(settings.default_hat)
    loop._rebuild_pipeline()
    loop._hat_equipped = True

    result = await loop.process("What are your store hours?")

    # Genuinely bypassed — no situation evaluation
    assert result.bypassed is True
    assert result.situation_tree is None
    assert result.situation_risk_classification is None

    # Only 4 LLM calls: input gate, proposer, response gen, memory
    assert len(mock_llm.calls) == 4
