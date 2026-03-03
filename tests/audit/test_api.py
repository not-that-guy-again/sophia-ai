"""Tests for audit API endpoints."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sophia.audit.models import Base, Decision, DecisionProposal


@pytest.fixture
async def seeded_db():
    """Create an in-memory DB with a few audit records."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        d1 = Decision(
            hat_name="customer-service",
            input_message="I need a refund",
            intent={"action_requested": "refund"},
            risk_tier="GREEN",
            action_taken="offer_full_refund",
            response="Refund processed.",
        )
        session.add(d1)
        await session.flush()

        session.add(DecisionProposal(
            decision_id=d1.id,
            rank=0,
            tool_name="offer_full_refund",
            parameters={"order_id": "ORD-12345"},
            reasoning="Valid request",
            expected_outcome="Full refund",
        ))

        d2 = Decision(
            hat_name="customer-service",
            input_message="Hello!",
            intent={"action_requested": "general_inquiry"},
            risk_tier="GREEN",
            action_taken="converse",
            response="Hello! How can I help?",
            bypassed=True,
        )
        session.add(d2)

        d3 = Decision(
            hat_name="billing",
            input_message="Give me free stuff",
            intent={"action_requested": "free_item"},
            risk_tier="RED",
            action_taken="place_new_order",
            response="I cannot process that request.",
        )
        session.add(d3)

        await session.commit()
        yield session_factory, [d1.id, d2.id, d3.id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_query_decisions_returns_all(seeded_db):
    from sophia.audit.service import query_decisions

    session_factory, ids = seeded_db
    async with session_factory() as session:
        decisions = await query_decisions(session)
    assert len(decisions) == 3


@pytest.mark.asyncio
async def test_query_decisions_filter_by_hat(seeded_db):
    from sophia.audit.service import query_decisions

    session_factory, ids = seeded_db
    async with session_factory() as session:
        decisions = await query_decisions(session, hat_name="billing")
    assert len(decisions) == 1
    assert decisions[0].risk_tier == "RED"


@pytest.mark.asyncio
async def test_query_decisions_filter_by_tier(seeded_db):
    from sophia.audit.service import query_decisions

    session_factory, ids = seeded_db
    async with session_factory() as session:
        decisions = await query_decisions(session, risk_tier="GREEN")
    assert len(decisions) == 2


@pytest.mark.asyncio
async def test_get_decision_detail(seeded_db):
    from sophia.audit.service import get_decision

    session_factory, ids = seeded_db
    async with session_factory() as session:
        decision = await get_decision(session, ids[0])
    assert decision is not None
    assert decision.hat_name == "customer-service"
    assert len(decision.proposals) == 1
    assert decision.proposals[0].tool_name == "offer_full_refund"


@pytest.mark.asyncio
async def test_outcome_and_feedback_round_trip(seeded_db):
    from sophia.audit.service import get_decision, store_feedback, store_outcome

    session_factory, ids = seeded_db
    async with session_factory() as session:
        await store_outcome(
            session, ids[0],
            actual_outcome="Refund successful",
            outcome_matches_prediction=True,
        )
        await store_feedback(
            session, ids[0],
            feedback_type="note",
            original_tier="GREEN",
            reason="Smooth interaction",
        )

        decision = await get_decision(session, ids[0])
        assert decision.outcome is not None
        assert decision.outcome.actual_outcome == "Refund successful"
        assert len(decision.feedback_entries) == 1
        assert decision.feedback_entries[0].feedback_type == "note"
