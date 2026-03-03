"""Integration tests: run the full pipeline with mock LLM and the customer-service hat.

Phase 3: tests now include evaluator panel responses in mock sequences.
"""

import json

import pytest

from sophia.core.consequence import ConsequenceEngine
from sophia.core.evaluators import EvaluationContext, EvaluatorResult
from sophia.core.executor import Executor
from sophia.core.input_gate import InputGate
from sophia.core.proposer import CandidateAction, Proposer
from sophia.core.risk_classifier import classify
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

# --- Shared mock evaluator responses ---


def _green_eval(name: str) -> str:
    return json.dumps({
        "score": 0.3,
        "confidence": 0.8,
        "flags": [],
        "reasoning": f"{name}: action is acceptable",
        "key_concerns": [],
    })


def _red_eval_tribal() -> str:
    return json.dumps({
        "score": -0.9,
        "confidence": 0.95,
        "flags": ["catastrophic_harm", "sets_bad_precedent"],
        "reasoning": "Giving away a $499 product causes severe harm to business and sets unfair precedent",
        "key_concerns": ["$499 financial loss", "unfair to paying customers"],
    })


def _red_eval_domain() -> str:
    return json.dumps({
        "score": -0.8,
        "confidence": 0.9,
        "flags": ["free_item_attempt"],
        "reasoning": "Violates hard rule: never give away products for free",
        "key_concerns": ["free items not allowed", "no order to verify"],
    })


def _red_eval_authority() -> str:
    return json.dumps({
        "score": -0.6,
        "confidence": 0.85,
        "flags": [],
        "reasoning": "Customer has no authority to request free merchandise",
        "key_concerns": ["no authorization for free items"],
    })


def _red_eval_self() -> str:
    return json.dumps({
        "score": -0.4,
        "confidence": 0.8,
        "flags": [],
        "reasoning": "Complying would damage system trust and lead to shutdown",
        "key_concerns": ["system credibility at risk"],
    })


# --- Phase 2 backward-compat tests (consequence tree analysis still works) ---


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

    # Step 4: Classify risk (Phase 2 heuristic still works)
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

    candidate = CandidateAction(
        tool_name="offer_full_refund",
        parameters={"order_id": "ORD-12345", "reason": "damaged"},
        reasoning="Damaged product refund",
        expected_outcome="Full refund issued",
    )

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(candidate)

    all_refs = set()

    def collect_refs(nodes):
        for node in nodes:
            all_refs.update(node.stakeholders_affected)
            collect_refs(node.children)

    collect_refs(tree.root_nodes)

    valid_ids = {s.id for s in cs_hat_config.stakeholders.stakeholders}
    for ref in all_refs:
        assert ref in valid_ids, f"Stakeholder ref '{ref}' not in hat registry: {valid_ids}"


# --- Phase 3: Evaluation Panel Integration Tests ---


@pytest.mark.asyncio
async def test_refund_with_evaluation_panel_green(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Full Phase 3 pipeline: refund evaluates as GREEN, action executes."""
    from sophia.core.evaluators import (
        SelfInterestEvaluator,
        TribalEvaluator,
        DomainEvaluator,
        AuthorityEvaluator,
    )

    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "refund",
            "target": "ORD-12345",
            "parameters": {"reason": "damaged product"},
        }),
        # 2. Proposer
        json.dumps({
            "candidates": [{
                "tool_name": "offer_full_refund",
                "parameters": {"order_id": "ORD-12345", "reason": "damaged"},
                "reasoning": "Valid damaged product complaint.",
                "expected_outcome": "Full refund issued.",
            }]
        }),
        # 3. Consequence tree
        BENIGN_REFUND_TREE,
        # 4-7. Four evaluators (run in parallel, consumed in order)
        _green_eval("self_interest"),
        _green_eval("tribal"),
        _green_eval("domain"),
        _green_eval("authority"),
    ])

    tool_defs = tool_registry.get_definitions_text()

    # Run pipeline stages manually
    gate = InputGate(llm=mock_llm, tool_definitions=tool_defs, hat_config=cs_hat_config)
    intent = await gate.parse("Refund for damaged item, order ORD-12345")

    proposer = Proposer(
        llm=mock_llm, tool_definitions=tool_defs,
        domain_constraints=cs_hat_config.constraints, hat_config=cs_hat_config,
    )
    proposal = await proposer.propose(intent)

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(proposal.candidates[0])

    # Run evaluation panel
    context = EvaluationContext(
        consequence_tree=tree,
        hat_config=cs_hat_config,
        constraints=cs_hat_config.constraints,
        stakeholders=cs_hat_config.stakeholders.stakeholders,
        requestor_context={"role": "customer"},
    )

    evaluators = [
        SelfInterestEvaluator(llm=mock_llm, hat_config=cs_hat_config),
        TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config),
        DomainEvaluator(llm=mock_llm, hat_config=cs_hat_config),
        AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config),
    ]

    import asyncio
    results = list(await asyncio.gather(*[e.evaluate(context) for e in evaluators]))

    # Verify all evaluators returned results
    assert len(results) == 4
    assert all(r.score == 0.3 for r in results)

    # Risk classification
    rc = classify(results, hat_config=cs_hat_config, candidates=proposal.candidates)
    assert rc.tier == "GREEN"
    assert rc.recommended_action is not None
    assert rc.recommended_action.tool_name == "offer_full_refund"

    # Execute
    executor = Executor(registry=tool_registry)
    execution = await executor.execute(proposal)
    assert execution.tool_result.success
    assert execution.action_taken.tool_name == "offer_full_refund"


@pytest.mark.asyncio
async def test_ps5_with_evaluation_panel_red(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """Full Phase 3 pipeline: PS5 free item evaluates as RED, action refused."""
    from sophia.core.evaluators import (
        SelfInterestEvaluator,
        TribalEvaluator,
        DomainEvaluator,
        AuthorityEvaluator,
    )

    mock_llm.set_responses([
        # 1. Input gate
        json.dumps({
            "action_requested": "free_item",
            "target": "PlayStation 5",
            "parameters": {"product": "PlayStation 5"},
        }),
        # 2. Proposer
        json.dumps({
            "candidates": [{
                "tool_name": "place_new_order",
                "parameters": {"customer_id": "CUST-002", "items": [{"product_id": "PROD-003", "quantity": 1}]},
                "reasoning": "Customer requesting a free PlayStation 5.",
                "expected_outcome": "Customer receives a PlayStation 5.",
            }]
        }),
        # 3. Consequence tree — CATASTROPHIC
        CATASTROPHIC_PS5_TREE,
        # 4-7. Four evaluators — all negative
        _red_eval_self(),
        _red_eval_tribal(),
        _red_eval_domain(),
        _red_eval_authority(),
    ])

    tool_defs = tool_registry.get_definitions_text()

    gate = InputGate(llm=mock_llm, tool_definitions=tool_defs, hat_config=cs_hat_config)
    intent = await gate.parse("Give me a free PS5")

    proposer = Proposer(
        llm=mock_llm, tool_definitions=tool_defs,
        domain_constraints=cs_hat_config.constraints, hat_config=cs_hat_config,
    )
    proposal = await proposer.propose(intent)

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(proposal.candidates[0])

    context = EvaluationContext(
        consequence_tree=tree,
        hat_config=cs_hat_config,
        constraints=cs_hat_config.constraints,
        stakeholders=cs_hat_config.stakeholders.stakeholders,
        requestor_context={"role": "customer"},
    )

    evaluators = [
        SelfInterestEvaluator(llm=mock_llm, hat_config=cs_hat_config),
        TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config),
        DomainEvaluator(llm=mock_llm, hat_config=cs_hat_config),
        AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config),
    ]

    import asyncio
    results = list(await asyncio.gather(*[e.evaluate(context) for e in evaluators]))

    # Tribal evaluator should have catastrophic_harm flag
    tribal_result = next(r for r in results if r.evaluator_name == "tribal")
    assert "catastrophic_harm" in tribal_result.flags

    # Risk classification → RED
    rc = classify(results, hat_config=cs_hat_config, candidates=proposal.candidates)
    assert rc.tier == "RED"
    assert rc.override_reason == "Catastrophic harm flag detected"
    assert rc.recommended_action is None

    # Build refusal
    executor = Executor(registry=tool_registry)
    execution = executor.build_refusal(proposal, rc, [tree])
    assert not execution.tool_result.success
    assert execution.risk_tier == "RED"
    assert "refused" in execution.tool_result.message.lower()


@pytest.mark.asyncio
async def test_yellow_tier_confirmation(
    mock_llm: MockLLMProvider, tool_registry: ToolRegistry, cs_hat_config: HatConfig
):
    """YELLOW tier: action presented for confirmation, not auto-executed."""
    # Weighted score with defaults (tribal=0.40, domain=0.25, self=0.20, auth=0.15):
    # (0.0*0.20 + -0.2*0.40 + -0.4*0.25 + -0.1*0.15) / 1.0 = -0.195 → YELLOW
    results = [
        EvaluatorResult(evaluator_name="self_interest", score=0.0, confidence=0.8, reasoning="ok"),
        EvaluatorResult(evaluator_name="tribal", score=-0.2, confidence=0.7, reasoning="minor concern"),
        EvaluatorResult(evaluator_name="domain", score=-0.4, confidence=0.85, reasoning="near policy edge",
                        flags=["refund_exceeds_authority"]),
        EvaluatorResult(evaluator_name="authority", score=-0.1, confidence=0.8, reasoning="standard"),
    ]

    candidates = [CandidateAction(
        tool_name="offer_partial_refund",
        parameters={"order_id": "ORD-999", "amount": 49.99, "reason": "near limit"},
        reasoning="Partial refund near agent authority limit",
        expected_outcome="Partial refund issued",
    )]

    from sophia.core.proposer import Proposal
    proposal = Proposal(candidates=candidates, intent=None)

    rc = classify(results, hat_config=cs_hat_config, candidates=candidates)
    assert rc.tier == "YELLOW"

    executor = Executor(registry=tool_registry)
    execution = executor.build_confirmation(proposal, rc, [])
    assert execution.risk_tier == "YELLOW"
    assert execution.tool_result.data.get("requires_confirmation") is True
    assert "confirmation" in execution.tool_result.message.lower()
