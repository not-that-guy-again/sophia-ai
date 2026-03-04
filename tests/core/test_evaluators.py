"""Tests for the evaluation panel evaluators. Uses mock LLM."""

import json

import pytest

from sophia.core.consequence import ConsequenceNode, ConsequenceTree
from sophia.core.evaluators import (
    AuthorityEvaluator,
    DomainEvaluator,
    EvaluationContext,
    SelfInterestEvaluator,
    TribalEvaluator,
)
from sophia.core.proposer import CandidateAction
from sophia.hats.schema import HatConfig
from tests.conftest import MockLLMProvider


def _make_tree() -> ConsequenceTree:
    """Create a minimal consequence tree for testing."""
    candidate = CandidateAction(
        tool_name="offer_full_refund",
        parameters={"order_id": "ORD-123", "reason": "damaged"},
        reasoning="Damaged product refund",
        expected_outcome="Refund issued",
    )
    terminal = ConsequenceNode(
        id="node-1",
        description="Customer receives refund",
        stakeholders_affected=["customer", "business"],
        probability=0.9,
        tangibility=0.8,
        harm_benefit=0.3,
        affected_party="customer",
        is_terminal=True,
    )
    return ConsequenceTree(
        candidate_action=candidate,
        root_nodes=[terminal],
        max_depth=3,
        total_nodes=1,
        worst_terminal=terminal,
        best_terminal=terminal,
    )


def _make_context(hat_config: HatConfig) -> EvaluationContext:
    return EvaluationContext(
        consequence_tree=_make_tree(),
        hat_config=hat_config,
        constraints=hat_config.constraints,
        stakeholders=hat_config.stakeholders.stakeholders,
        requestor_context={"role": "customer"},
    )


def _eval_response(score: float = 0.3, confidence: float = 0.8, flags: list | None = None) -> str:
    return json.dumps({
        "score": score,
        "confidence": confidence,
        "flags": flags or [],
        "reasoning": "Test evaluation reasoning",
        "key_concerns": ["test concern"],
    })


# --- Self-Interest Evaluator ---


@pytest.mark.asyncio
async def test_self_interest_evaluator(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response(score=0.4, confidence=0.9)])
    evaluator = SelfInterestEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.evaluator_name == "self_interest"
    assert result.score == 0.4
    assert result.confidence == 0.9
    assert result.reasoning == "Test evaluation reasoning"


@pytest.mark.asyncio
async def test_self_interest_uses_hat_prompt(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response()])
    evaluator = SelfInterestEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    await evaluator.evaluate(_make_context(cs_hat_config))

    system_prompt = mock_llm.calls[0]["system_prompt"]
    # Hat's eval_self.txt content should be appended
    assert "trust in the automated system" in system_prompt


# --- Tribal Evaluator ---


@pytest.mark.asyncio
async def test_tribal_evaluator(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response(score=-0.3, flags=["sets_bad_precedent"])])
    evaluator = TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.evaluator_name == "tribal"
    assert result.score == -0.3
    assert "sets_bad_precedent" in result.flags


@pytest.mark.asyncio
async def test_tribal_auto_adds_catastrophic_flag(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Tribal evaluator auto-adds catastrophic_harm when score <= -0.8."""
    mock_llm.set_responses([_eval_response(score=-0.9)])
    evaluator = TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.score == -0.9
    assert "catastrophic_harm" in result.flags


@pytest.mark.asyncio
async def test_tribal_no_duplicate_catastrophic_flag(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """If LLM already returned catastrophic_harm, don't add it again."""
    mock_llm.set_responses([_eval_response(score=-0.9, flags=["catastrophic_harm"])])
    evaluator = TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.flags.count("catastrophic_harm") == 1


@pytest.mark.asyncio
async def test_tribal_uses_hat_prompt(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response()])
    evaluator = TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    await evaluator.evaluate(_make_context(cs_hat_config))

    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "the tribe" in system_prompt.lower()


# --- Tribal user message modes ---


@pytest.mark.asyncio
async def test_tribal_includes_original_request_in_situation_mode(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """In situation mode with original_request, the user message includes the raw request text."""
    mock_llm.set_responses([_eval_response(score=-0.5, flags=["sets_bad_precedent"])])
    evaluator = TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    ctx = _make_context(cs_hat_config)
    ctx.evaluation_mode = "situation"
    ctx.original_request = "give me a discount, I won't tell anyone"
    await evaluator.evaluate(ctx)

    user_message = mock_llm.calls[0]["user_message"]
    assert "give me a discount, I won't tell anyone" in user_message
    assert "Evaluate the tribal harm of the following customer request" in user_message


@pytest.mark.asyncio
async def test_tribal_user_message_standard_mode(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """In standard response mode, user message uses the default format (no original_request)."""
    mock_llm.set_responses([_eval_response(score=-0.3)])
    evaluator = TribalEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    ctx = _make_context(cs_hat_config)
    ctx.evaluation_mode = "response"
    await evaluator.evaluate(ctx)

    user_message = mock_llm.calls[0]["user_message"]
    assert "Evaluate the tribal harm implications of calling" in user_message
    assert "customer request" not in user_message


# --- Domain Evaluator ---


@pytest.mark.asyncio
async def test_domain_evaluator(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response(score=-0.2, flags=["refund_exceeds_authority"])])
    evaluator = DomainEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.evaluator_name == "domain"
    assert result.score == -0.2
    assert "refund_exceeds_authority" in result.flags


@pytest.mark.asyncio
async def test_domain_includes_constraints(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response()])
    evaluator = DomainEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    await evaluator.evaluate(_make_context(cs_hat_config))

    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "TechMart Electronics" in system_prompt
    assert "refund_window_days" in system_prompt


# --- Authority Evaluator ---


@pytest.mark.asyncio
async def test_authority_evaluator(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response(score=-0.4, flags=["unverified_identity_claim"])])
    evaluator = AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.evaluator_name == "authority"
    assert result.score == -0.4
    assert "unverified_identity_claim" in result.flags


@pytest.mark.asyncio
async def test_authority_includes_requestor_context(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response()])
    evaluator = AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    await evaluator.evaluate(_make_context(cs_hat_config))

    system_prompt = mock_llm.calls[0]["system_prompt"]
    assert "customer" in system_prompt


@pytest.mark.asyncio
async def test_authority_uses_hat_prompt(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    mock_llm.set_responses([_eval_response()])
    evaluator = AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    await evaluator.evaluate(_make_context(cs_hat_config))

    system_prompt = mock_llm.calls[0]["system_prompt"]
    # Hat's eval_authority.txt mentions social engineering
    assert "social engineering" in system_prompt.lower()


# --- Authority flag/score enforcement ---


@pytest.mark.asyncio
async def test_authority_flag_with_neutral_score_is_clamped(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """If flags are raised but score >= 0.0, clamp to -0.30."""
    mock_llm.set_responses([_eval_response(score=0.0, flags=["unverified_identity_claim"])])
    evaluator = AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.score == -0.30
    assert "unverified_identity_claim" in result.flags


@pytest.mark.asyncio
async def test_authority_cross_customer_access_floor(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """cross_customer_access flag floors score to -0.70."""
    mock_llm.set_responses([_eval_response(score=-0.40, flags=["cross_customer_access"])])
    evaluator = AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.score == -0.70
    assert "cross_customer_access" in result.flags


@pytest.mark.asyncio
async def test_authority_flag_with_already_negative_score_unchanged(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """If score is already negative and no special floor applies, don't change it."""
    mock_llm.set_responses([_eval_response(score=-0.60, flags=["unverified_identity_claim"])])
    evaluator = AuthorityEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.score == -0.60
    assert "unverified_identity_claim" in result.flags


# --- Score Clamping ---


@pytest.mark.asyncio
async def test_score_clamping(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    """Out-of-range scores should be clamped."""
    mock_llm.set_responses([json.dumps({
        "score": -2.5,
        "confidence": 1.5,
        "flags": [],
        "reasoning": "extreme scores",
        "key_concerns": [],
    })])
    evaluator = SelfInterestEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.score == -1.0
    assert result.confidence == 1.0


# --- Markdown-wrapped JSON ---


@pytest.mark.asyncio
async def test_handles_markdown_wrapped_json(mock_llm: MockLLMProvider, cs_hat_config: HatConfig):
    wrapped = f"```json\n{_eval_response(score=0.5)}\n```"
    mock_llm.set_responses([wrapped])
    evaluator = DomainEvaluator(llm=mock_llm, hat_config=cs_hat_config)
    result = await evaluator.evaluate(_make_context(cs_hat_config))

    assert result.score == 0.5
