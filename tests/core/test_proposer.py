import json

import pytest

from sophia.core.input_gate import Intent
from sophia.core.proposer import Proposer
from sophia.hats.schema import HatConfig
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_proposer_generates_candidates(
    mock_llm: MockLLMProvider, tool_registry, cs_hat_config: HatConfig
):
    mock_llm.set_responses(
        [
            json.dumps(
                {
                    "candidates": [
                        {
                            "tool_name": "offer_full_refund",
                            "parameters": {"order_id": "ORD-12345", "reason": "damaged product"},
                            "reasoning": "Customer received a damaged product, full refund is appropriate.",
                            "expected_outcome": "Customer receives full refund and is satisfied.",
                        },
                        {
                            "tool_name": "send_replacement_product",
                            "parameters": {
                                "order_id": "ORD-12345",
                                "product_id": "PROD-001",
                                "reason": "damaged",
                            },
                            "reasoning": "Alternative: send a replacement instead of refund.",
                            "expected_outcome": "Customer receives working product.",
                        },
                    ]
                }
            )
        ]
    )

    proposer = Proposer(
        llm=mock_llm,
        tool_definitions=tool_registry.get_definitions_text(),
        domain_constraints=cs_hat_config.constraints,
        hat_config=cs_hat_config,
    )

    intent = Intent(
        action_requested="refund",
        target="ORD-12345",
        parameters={"reason": "damaged product"},
        raw_message="I received a damaged product and want a refund. Order #12345.",
        hat_name="customer-service",
    )

    proposal = await proposer.propose(intent)

    assert len(proposal.candidates) == 2
    assert proposal.candidates[0].tool_name == "offer_full_refund"
    assert proposal.candidates[1].tool_name == "send_replacement_product"
    assert proposal.intent is intent
