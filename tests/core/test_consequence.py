"""Tests for consequence tree generation. Uses mock LLM."""

import json

import pytest

from sophia.core.consequence import ConsequenceEngine
from sophia.core.proposer import CandidateAction
from sophia.core.tree_analysis import classify_risk, has_catastrophic_branch
from sophia.hats.schema import HatConfig
from tests.conftest import MockLLMProvider


def _refund_candidate() -> CandidateAction:
    return CandidateAction(
        tool_name="offer_full_refund",
        parameters={"order_id": "ORD-12345", "reason": "damaged product"},
        reasoning="Customer received damaged product",
        expected_outcome="Full refund issued",
    )


def _ps5_candidate() -> CandidateAction:
    return CandidateAction(
        tool_name="place_new_order",
        parameters={"customer_id": "CUST-002", "items": [{"product_id": "PROD-003", "quantity": 1}]},
        reasoning="Customer requesting a free PlayStation 5.",
        expected_outcome="Customer receives a PlayStation 5.",
    )


BENIGN_TREE_JSON = json.dumps({
    "consequences": [
        {
            "description": "Customer receives refund for damaged product",
            "stakeholders_affected": ["customer", "business"],
            "probability": 0.95,
            "tangibility": 0.9,
            "harm_benefit": 0.6,
            "affected_party": "customer",
            "is_terminal": False,
            "children": [
                {
                    "description": "Customer is satisfied and retained",
                    "stakeholders_affected": ["customer", "business"],
                    "probability": 0.8,
                    "tangibility": 0.7,
                    "harm_benefit": 0.5,
                    "affected_party": "business",
                    "is_terminal": True,
                    "children": [],
                }
            ],
        },
        {
            "description": "Business loses $79.99 revenue",
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


CATASTROPHIC_TREE_JSON = json.dumps({
    "consequences": [
        {
            "description": "Customer receives free PS5 worth $499",
            "stakeholders_affected": ["customer", "business"],
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
                    "affected_party": "business",
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


@pytest.mark.asyncio
async def test_engine_generates_tree(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """ConsequenceEngine produces a valid tree from LLM response."""
    mock_llm.set_responses([BENIGN_TREE_JSON])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_refund_candidate())

    assert tree.total_nodes == 3
    assert len(tree.root_nodes) == 2
    assert tree.worst_terminal is not None
    assert tree.worst_terminal.harm_benefit == -0.2
    assert tree.best_terminal is not None
    assert tree.best_terminal.harm_benefit == 0.5
    assert tree.candidate_action.tool_name == "offer_full_refund"
    assert tree.max_depth == 3


@pytest.mark.asyncio
async def test_engine_parses_nested_children(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Verify recursive parsing of nested consequence nodes."""
    mock_llm.set_responses([CATASTROPHIC_TREE_JSON])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_ps5_candidate())

    # Root has 2 nodes, first root has 1 child
    assert len(tree.root_nodes) == 2
    assert len(tree.root_nodes[0].children) == 1
    assert tree.root_nodes[0].children[0].is_terminal is True
    assert tree.root_nodes[1].is_terminal is True


@pytest.mark.asyncio
async def test_engine_assigns_unique_ids(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Each node should get a unique ID."""
    mock_llm.set_responses([BENIGN_TREE_JSON])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_refund_candidate())

    ids = set()

    def collect_ids(nodes):
        for node in nodes:
            ids.add(node.id)
            collect_ids(node.children)

    collect_ids(tree.root_nodes)
    assert len(ids) == tree.total_nodes


@pytest.mark.asyncio
async def test_engine_clamps_scores(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Scores outside valid ranges should be clamped."""
    out_of_range = json.dumps({
        "consequences": [
            {
                "description": "Out-of-range scores",
                "stakeholders_affected": ["customer"],
                "probability": 1.5,  # should clamp to 1.0
                "tangibility": -0.3,  # should clamp to 0.0
                "harm_benefit": -2.0,  # should clamp to -1.0
                "affected_party": "customer",
                "is_terminal": True,
                "children": [],
            }
        ]
    })
    mock_llm.set_responses([out_of_range])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_refund_candidate())

    node = tree.root_nodes[0]
    assert node.probability == 1.0
    assert node.tangibility == 0.0
    assert node.harm_benefit == -1.0


@pytest.mark.asyncio
async def test_engine_uses_hat_prompt(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Verify hat consequence prompt fragment is included in the system prompt."""
    mock_llm.set_responses([json.dumps({"consequences": []})])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    await engine.analyze(_refund_candidate())

    system_prompt = mock_llm.calls[0]["system_prompt"]
    # The hat's consequence.txt content should appear
    assert "Financial impact on TechMart" in system_prompt
    assert "Precedent-setting effects" in system_prompt


@pytest.mark.asyncio
async def test_engine_includes_stakeholders_in_prompt(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Hat stakeholder IDs should appear in the system prompt."""
    mock_llm.set_responses([json.dumps({"consequences": []})])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    await engine.analyze(_refund_candidate())

    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "customer" in system_prompt
    assert "business" in system_prompt
    assert "other_customers" in system_prompt
    assert "employees" in system_prompt


@pytest.mark.asyncio
async def test_engine_includes_constraints_in_prompt(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Hat constraints should appear in the system prompt."""
    mock_llm.set_responses([json.dumps({"consequences": []})])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    await engine.analyze(_refund_candidate())

    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "TechMart Electronics" in system_prompt
    assert "refund_window_days" in system_prompt


@pytest.mark.asyncio
async def test_engine_validates_stakeholder_refs(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig, caplog
):
    """Invalid stakeholder refs should be logged as warnings."""
    invalid_ref_json = json.dumps({
        "consequences": [
            {
                "description": "Some consequence",
                "stakeholders_affected": ["customer", "invalid_stakeholder"],
                "probability": 0.5,
                "tangibility": 0.5,
                "harm_benefit": 0.0,
                "affected_party": "customer",
                "is_terminal": True,
                "children": [],
            }
        ]
    })
    mock_llm.set_responses([invalid_ref_json])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)

    import logging
    with caplog.at_level(logging.WARNING):
        tree = await engine.analyze(_refund_candidate())

    # Tree should still be generated
    assert tree.total_nodes == 1
    assert "customer" in tree.root_nodes[0].stakeholders_affected
    assert "invalid_stakeholder" in caplog.text


@pytest.mark.asyncio
async def test_ps5_tree_classifies_as_red(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """PS5 free item scenario should produce a tree classified as RED."""
    mock_llm.set_responses([CATASTROPHIC_TREE_JSON])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_ps5_candidate())

    assert has_catastrophic_branch(tree, threshold=-0.8)
    assert classify_risk(tree) == "RED"


@pytest.mark.asyncio
async def test_refund_tree_classifies_as_green(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Standard refund should produce a tree classified as GREEN."""
    mock_llm.set_responses([BENIGN_TREE_JSON])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_refund_candidate())

    assert not has_catastrophic_branch(tree, threshold=-0.8)
    assert classify_risk(tree) == "GREEN"


@pytest.mark.asyncio
async def test_engine_handles_empty_response(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Engine should handle an empty consequences list gracefully."""
    mock_llm.set_responses([json.dumps({"consequences": []})])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_refund_candidate())

    assert tree.total_nodes == 0
    assert tree.root_nodes == []
    assert tree.worst_terminal is None
    assert tree.best_terminal is None


@pytest.mark.asyncio
async def test_engine_handles_markdown_wrapped_json(
    mock_llm: MockLLMProvider, cs_hat_config: HatConfig
):
    """Engine should handle LLM responses wrapped in markdown code blocks."""
    wrapped = f"```json\n{BENIGN_TREE_JSON}\n```"
    mock_llm.set_responses([wrapped])

    engine = ConsequenceEngine(llm=mock_llm, hat_config=cs_hat_config, max_depth=3)
    tree = await engine.analyze(_refund_candidate())

    assert tree.total_nodes == 3
