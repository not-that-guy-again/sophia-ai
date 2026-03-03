"""Tests for audit ORM models and database creation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sophia.audit.models import (
    Base,
    Decision,
    DecisionEvaluation,
    DecisionOutcome,
    DecisionProposal,
    DecisionTree,
    Feedback,
    HatConfigSnapshot,
)


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_decision(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="I need a refund",
        intent={"action_requested": "refund", "target": "ORD-12345"},
        risk_tier="GREEN",
        action_taken="offer_full_refund",
        response="Your refund has been processed.",
    )
    db_session.add(decision)
    await db_session.commit()

    assert decision.id is not None
    assert decision.id > 0
    assert decision.hat_name == "customer-service"


@pytest.mark.asyncio
async def test_create_decision_with_proposals(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="I need a refund",
        intent={"action_requested": "refund"},
        risk_tier="GREEN",
        action_taken="offer_full_refund",
        response="Refund processed.",
    )
    db_session.add(decision)
    await db_session.flush()

    proposal = DecisionProposal(
        decision_id=decision.id,
        rank=0,
        tool_name="offer_full_refund",
        parameters={"order_id": "ORD-12345"},
        reasoning="Valid refund request",
        expected_outcome="Full refund issued",
    )
    db_session.add(proposal)
    await db_session.commit()

    assert proposal.id is not None
    assert proposal.decision_id == decision.id


@pytest.mark.asyncio
async def test_create_decision_with_evaluations(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="test",
        intent={},
        risk_tier="GREEN",
        action_taken="test",
        response="test",
    )
    db_session.add(decision)
    await db_session.flush()

    evaluation = DecisionEvaluation(
        decision_id=decision.id,
        evaluator_name="tribal",
        score=0.3,
        confidence=0.8,
        flags=[],
        reasoning="Action is acceptable",
        key_concerns=[],
    )
    db_session.add(evaluation)
    await db_session.commit()

    assert evaluation.id is not None
    assert evaluation.score == 0.3


@pytest.mark.asyncio
async def test_create_decision_with_tree(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="test",
        intent={},
        risk_tier="GREEN",
        action_taken="test",
        response="test",
    )
    db_session.add(decision)
    await db_session.flush()

    tree = DecisionTree(
        decision_id=decision.id,
        candidate_tool_name="offer_full_refund",
        tree_data={"root_nodes": []},
        total_nodes=3,
        worst_harm=-0.2,
        best_benefit=0.5,
    )
    db_session.add(tree)
    await db_session.commit()

    assert tree.id is not None
    assert tree.total_nodes == 3


@pytest.mark.asyncio
async def test_create_outcome(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="test",
        intent={},
        risk_tier="GREEN",
        action_taken="test",
        response="test",
    )
    db_session.add(decision)
    await db_session.flush()

    outcome = DecisionOutcome(
        decision_id=decision.id,
        actual_outcome="Refund was successfully processed, customer satisfied",
        outcome_matches_prediction=True,
        notes="Customer left positive review",
    )
    db_session.add(outcome)
    await db_session.commit()

    assert outcome.id is not None
    assert outcome.outcome_matches_prediction is True


@pytest.mark.asyncio
async def test_create_feedback(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="test",
        intent={},
        risk_tier="YELLOW",
        action_taken="test",
        response="test",
    )
    db_session.add(decision)
    await db_session.flush()

    feedback = Feedback(
        decision_id=decision.id,
        feedback_type="override",
        original_tier="YELLOW",
        override_action="offer_full_refund",
        reason="Customer is a VIP, override approved by manager",
    )
    db_session.add(feedback)
    await db_session.commit()

    assert feedback.id is not None
    assert feedback.feedback_type == "override"


@pytest.mark.asyncio
async def test_create_hat_config_snapshot(db_session: AsyncSession):
    decision = Decision(
        hat_name="customer-service",
        input_message="test",
        intent={},
        risk_tier="GREEN",
        action_taken="test",
        response="test",
    )
    db_session.add(decision)
    await db_session.flush()

    snapshot = HatConfigSnapshot(
        decision_id=decision.id,
        hat_name="customer-service",
        hat_version="0.1.0",
        constraints={"max_refund": 100},
        stakeholders={"stakeholders": []},
        evaluator_config={"weight_overrides": {}},
    )
    db_session.add(snapshot)
    await db_session.commit()

    assert snapshot.id is not None
    assert snapshot.constraints["max_refund"] == 100
