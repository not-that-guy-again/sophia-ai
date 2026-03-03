"""Tests for the audit service layer — store and query operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sophia.audit.models import Base
from sophia.audit.service import (
    get_decision,
    query_decisions,
    store_decision_with_hat,
    store_feedback,
    store_outcome,
)
from sophia.core.executor import ExecutionResult
from sophia.core.input_gate import Intent
from sophia.core.loop import PipelineResult
from sophia.core.proposer import CandidateAction, Proposal
from sophia.core.risk_classifier import RiskClassification
from sophia.tools.base import ToolResult


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _make_pipeline_result(
    hat_name="customer-service",
    risk_tier="GREEN",
    tool_name="offer_full_refund",
    message="Refund processed",
    bypassed=False,
) -> PipelineResult:
    intent = Intent(
        action_requested="refund",
        target="ORD-12345",
        parameters={"reason": "damaged"},
        raw_message="I need a refund for order ORD-12345",
        hat_name=hat_name,
    )
    candidate = CandidateAction(
        tool_name=tool_name,
        parameters={"order_id": "ORD-12345"},
        reasoning="Valid refund request",
        expected_outcome="Full refund issued",
    )
    return PipelineResult(
        intent=intent,
        proposal=Proposal(intent=intent, candidates=[candidate]),
        consequence_trees=[],
        evaluation_results=[],
        risk_classification=RiskClassification(
            tier=risk_tier,
            weighted_score=0.0,
            explanation="Test classification",
        ),
        execution=ExecutionResult(
            action_taken=candidate,
            tool_result=ToolResult(success=True, data=None, message=message),
            risk_tier=risk_tier,
        ),
        response=message,
        bypassed=bypassed,
        metadata={"hat": hat_name},
    )


@pytest.mark.asyncio
async def test_store_decision(db_session: AsyncSession):
    result = _make_pipeline_result()
    decision_id = await store_decision_with_hat(
        db_session, result, "I need a refund for order ORD-12345"
    )

    assert decision_id > 0

    decision = await get_decision(db_session, decision_id)
    assert decision is not None
    assert decision.hat_name == "customer-service"
    assert decision.risk_tier == "GREEN"
    assert decision.action_taken == "offer_full_refund"
    assert len(decision.proposals) == 1
    assert decision.proposals[0].tool_name == "offer_full_refund"


@pytest.mark.asyncio
async def test_store_and_retrieve_outcome(db_session: AsyncSession):
    result = _make_pipeline_result()
    decision_id = await store_decision_with_hat(
        db_session, result, "I need a refund"
    )

    outcome = await store_outcome(
        db_session,
        decision_id=decision_id,
        actual_outcome="Customer received refund, left positive review",
        outcome_matches_prediction=True,
        notes="Quick resolution",
    )

    assert outcome.decision_id == decision_id
    assert outcome.outcome_matches_prediction is True

    decision = await get_decision(db_session, decision_id)
    assert decision.outcome is not None
    assert "positive review" in decision.outcome.actual_outcome


@pytest.mark.asyncio
async def test_store_and_retrieve_feedback(db_session: AsyncSession):
    result = _make_pipeline_result(risk_tier="YELLOW")
    decision_id = await store_decision_with_hat(
        db_session, result, "I need a refund"
    )

    fb = await store_feedback(
        db_session,
        decision_id=decision_id,
        feedback_type="override",
        original_tier="YELLOW",
        override_action="offer_full_refund",
        reason="VIP customer, manager approved",
    )

    assert fb.decision_id == decision_id

    decision = await get_decision(db_session, decision_id)
    assert len(decision.feedback_entries) == 1
    assert decision.feedback_entries[0].feedback_type == "override"


@pytest.mark.asyncio
async def test_query_decisions_by_hat(db_session: AsyncSession):
    result1 = _make_pipeline_result(hat_name="customer-service")
    result2 = _make_pipeline_result(hat_name="billing")
    await store_decision_with_hat(db_session, result1, "msg1")
    await store_decision_with_hat(db_session, result2, "msg2")

    cs_decisions = await query_decisions(db_session, hat_name="customer-service")
    assert len(cs_decisions) == 1
    assert cs_decisions[0].hat_name == "customer-service"


@pytest.mark.asyncio
async def test_query_decisions_by_tier(db_session: AsyncSession):
    result_green = _make_pipeline_result(risk_tier="GREEN")
    result_red = _make_pipeline_result(risk_tier="RED")
    await store_decision_with_hat(db_session, result_green, "msg1")
    await store_decision_with_hat(db_session, result_red, "msg2")

    red_decisions = await query_decisions(db_session, risk_tier="RED")
    assert len(red_decisions) == 1
    assert red_decisions[0].risk_tier == "RED"


@pytest.mark.asyncio
async def test_query_decisions_by_tool(db_session: AsyncSession):
    result1 = _make_pipeline_result(tool_name="offer_full_refund")
    result2 = _make_pipeline_result(tool_name="escalate_to_human")
    await store_decision_with_hat(db_session, result1, "msg1")
    await store_decision_with_hat(db_session, result2, "msg2")

    refund_decisions = await query_decisions(db_session, tool_name="offer_full_refund")
    assert len(refund_decisions) == 1


@pytest.mark.asyncio
async def test_query_decisions_with_limit_and_offset(db_session: AsyncSession):
    for i in range(5):
        result = _make_pipeline_result()
        await store_decision_with_hat(db_session, result, f"msg{i}")

    page1 = await query_decisions(db_session, limit=2, offset=0)
    assert len(page1) == 2

    page2 = await query_decisions(db_session, limit=2, offset=2)
    assert len(page2) == 2

    page3 = await query_decisions(db_session, limit=2, offset=4)
    assert len(page3) == 1


@pytest.mark.asyncio
async def test_get_decision_returns_none_for_missing(db_session: AsyncSession):
    result = await get_decision(db_session, 9999)
    assert result is None


@pytest.mark.asyncio
async def test_store_bypassed_decision(db_session: AsyncSession):
    result = _make_pipeline_result(bypassed=True, tool_name="converse")
    decision_id = await store_decision_with_hat(
        db_session, result, "Hello!"
    )

    decision = await get_decision(db_session, decision_id)
    assert decision.bypassed is True
    assert decision.action_taken == "converse"


@pytest.mark.asyncio
async def test_store_decision_with_hat_config(db_session: AsyncSession, cs_hat_config):
    result = _make_pipeline_result()
    decision_id = await store_decision_with_hat(
        db_session, result, "test", hat_config=cs_hat_config,
    )

    decision = await get_decision(db_session, decision_id)
    assert decision.hat_config_snapshot is not None
    assert decision.hat_config_snapshot.hat_name == "customer-service"
    assert decision.hat_config_snapshot.hat_version == "0.1.0"
    assert isinstance(decision.hat_config_snapshot.constraints, dict)
