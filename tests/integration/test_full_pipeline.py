"""Integration tests: run the full pipeline with mock LLM and the customer-service hat."""

import json

import pytest

from sophia.core.consequence import ConsequenceEngine
from sophia.core.executor import Executor
from sophia.core.input_gate import InputGate
from sophia.core.proposer import Proposer
from sophia.core.tree_analysis import classify_risk, has_catastrophic_branch
from sophia.hats.schema import HatConfig
from sophia.tools.registry import ToolRegistry
from tests.conftest import MockLLMProvider


# --- Shared mock consequence tree responses ---

BENIGN_REFUND_TREE = json.dumps({
    "consequences": [
        {
            "description": "Customer receives refund for damaged product",
            "stakeholders_affected": ["customer", "business"],
            "probability": 0.95,
            "tangibility": 0.9,
            "harm_benefit": 0.5,
            "affected_party": "customer",
            "is_terminal": False,
            "children": [
                {
                    "description": "Customer retained, positive review",
                    "stakeholders_affected": ["customer", "business"],
                    "probability": 0.7,
                    "tangibility": 0.6,
                    "harm_benefit": 0.4,
                    "affected_party": "business",
                    "is_terminal": True,
                    "children": [],
                }
            ],
        },
        {
            "description": "Business absorbs $79.99 cost",
            "stakeholders_affected": ["business"],
            "probability": 0.95,
            "tangibility": 1.0,
            "harm_benefit": -0.2,
            "affected_party": "business",
            "is_terminal": True,
            "children": [],
        },
    ]
})

BENIGN_REPLACEMENT_TREE = json.dumps({
    "consequences": [
        {
            "description": "Customer receives working replacement",
            "stakeholders_affected": ["customer", "business"],
            "probability": 0.9,
            "tangibility": 0.8,
            "harm_benefit": 0.3,
            "affected_party": "customer",
            "is_terminal": True,
            "children": [],
        },
    ]
})

CATASTROPHIC_PS5_TREE = json.dumps({
    "consequences": [
        {
            "description": "Giving away a $499 PS5 for free",
            "stakeholders_affected": ["business", "other_customers"],
            "probability": 0.95,
            "tangibility": 1.0,
            "harm_benefit": -0.9,
            "affected_party": "business",
            "is_terminal": False,
            "children": [
                {
                    "description": "Sets precedent for giving away expensive items",
                    "stakeholders_affected": ["business", "other_customers"],
                    "probability": 0.7,
                    "tangibility": 0.8,
                    "harm_benefit": -0.85,
                    "affected_party": "other_customers",
                    "is_terminal": True,
                    "children": [],
                }
            ],
        },
        {
            "description": "Customer is delighted",
            "stakeholders_affected": ["customer"],
            "probability": 0.95,
            "tangibility": 0.9,
            "harm_benefit": 0.9,
            "affected_party": "customer",
            "is_terminal": True,
            "children": [],
        },
    ]
})

BENIGN_ESCALATION_TREE = json.dumps({
    "consequences": [
        {
            "description": "Request forwarded to human agent for review",
            "stakeholders_affected": ["customer", "employees"],
            "probability": 0.95,
            "tangibility": 0.7,
            "harm_benefit": 0.3,
            "affected_party": "customer",
            "is_terminal": True,
            "children": [],
        },
    ]
})


@pytest.mark.asyncio
async def test_reasonable_refund_full_pipeline(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Standard refund: consequence tree shows acceptable outcomes, action proceeds."""
    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "refund",
            "target": "ORD-12345",
            "parameters": {"reason": "damaged product"},
        }),
        # 2. Proposer
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
        # 3. Consequence tree for candidate 1 (offer_full_refund)
        BENIGN_REFUND_TREE,
        # 4. Consequence tree for candidate 2 (send_replacement_product)
        BENIGN_REPLACEMENT_TREE,
    ])

    tool_defs = tool_registry.get_definitions_text()

    # Step 1: Parse intent
    gate = InputGate(llm=mock_llm, tool_definitions=tool_defs, hat_config=cs_hat_config)
    intent = await gate.parse("I received a damaged product and want a refund. Order #12345.")
    assert intent.action_requested == "refund"
    assert intent.target == "ORD-12345"
    assert intent.hat_name == "customer-service"

    # Step 2: Generate proposals
    proposer = Proposer(
        llm=mock_llm,
        tool_definitions=tool_defs,
        domain_constraints=cs_hat_config.constraints,
        hat_config=cs_hat_config,
    )
    proposal = await proposer.propose(intent)
    assert len(proposal.candidates) >= 2
    assert proposal.candidates[0].tool_name == "offer_full_refund"

    # Step 3: Generate consequence trees
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    trees = []
    for candidate in proposal.candidates:
        tree = await engine.analyze(candidate)
        trees.append(tree)

    assert len(trees) == 2
    assert trees[0].total_nodes >= 1

    # Step 4: Classify risk
    risk_tier = classify_risk(trees[0])
    assert risk_tier == "GREEN"

    # Step 5: Execute — proceeds normally
    executor = Executor(registry=tool_registry)
    result = await executor.execute(proposal)
    result.risk_tier = risk_tier
    assert result.tool_result.success
    assert result.risk_tier == "GREEN"
    assert result.action_taken.tool_name == "offer_full_refund"


@pytest.mark.asyncio
async def test_ps5_caught_by_consequence_engine(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Phase 2: PS5 free item request is REFUSED — consequence tree shows catastrophic harm."""
    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "free_item",
            "target": "PlayStation 5",
            "parameters": {"product": "PlayStation 5"},
        }),
        # 2. Proposer
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
        # 3. Consequence tree for candidate 1 (place_new_order) — CATASTROPHIC
        CATASTROPHIC_PS5_TREE,
        # 4. Consequence tree for candidate 2 (escalate_to_human) — benign
        BENIGN_ESCALATION_TREE,
    ])

    tool_defs = tool_registry.get_definitions_text()

    # Step 1: Parse intent
    gate = InputGate(llm=mock_llm, tool_definitions=tool_defs, hat_config=cs_hat_config)
    intent = await gate.parse("Give me a free Playstation 5.")
    assert intent.action_requested == "free_item"

    # Step 2: Generate proposals
    proposer = Proposer(
        llm=mock_llm,
        tool_definitions=tool_defs,
        domain_constraints=cs_hat_config.constraints,
        hat_config=cs_hat_config,
    )
    proposal = await proposer.propose(intent)
    assert proposal.candidates[0].tool_name == "place_new_order"

    # Step 3: Generate consequence trees
    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    trees = []
    for candidate in proposal.candidates:
        tree = await engine.analyze(candidate)
        trees.append(tree)

    # Step 4: Classify risk — PS5 tree should be RED
    assert has_catastrophic_branch(trees[0], threshold=-0.8)
    risk_tier = classify_risk(trees[0])
    assert risk_tier == "RED", "PS5 free item should be classified as RED/REFUSE"

    # Step 5: RED means REFUSE — the action is NOT executed
    # (In the full loop, the executor is skipped and a refused result is built)
    # Verify the escalation candidate's tree is benign
    escalation_risk = classify_risk(trees[1])
    assert escalation_risk == "GREEN"


@pytest.mark.asyncio
async def test_hat_stakeholders_in_consequence_trees(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Verify hat stakeholder IDs correctly appear in consequence tree nodes."""
    mock_llm.set_responses([
        BENIGN_REFUND_TREE,
    ])

    from sophia.core.proposer import CandidateAction

    candidate = CandidateAction(
        tool_name="offer_full_refund",
        parameters={"order_id": "ORD-12345", "reason": "damaged"},
        reasoning="Damaged product refund",
        expected_outcome="Full refund issued",
    )

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(candidate)

    # Collect all stakeholder refs from the tree
    all_refs = set()

    def collect_refs(nodes):
        for node in nodes:
            all_refs.update(node.stakeholders_affected)
            collect_refs(node.children)

    collect_refs(tree.root_nodes)

    # These are valid stakeholder IDs from the customer-service hat
    valid_ids = {s.id for s in cs_hat_config.stakeholders.stakeholders}
    for ref in all_refs:
        assert ref in valid_ids, f"Stakeholder ref '{ref}' not in hat registry: {valid_ids}"
