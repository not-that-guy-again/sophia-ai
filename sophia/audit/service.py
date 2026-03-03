"""Audit service: stores pipeline decisions and queries the audit log.

All writes are append-only. No update or delete operations.
"""

import logging
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sophia.audit.models import (
    Decision,
    DecisionEvaluation,
    DecisionOutcome,
    DecisionProposal,
    DecisionTree,
    Feedback,
    HatConfigSnapshot,
)
from sophia.core.loop import PipelineResult, _tree_to_dict

logger = logging.getLogger(__name__)


async def store_decision(session: AsyncSession, result: PipelineResult, input_message: str) -> int:
    """Store a complete pipeline result as an audit record. Returns the decision ID."""
    hat_name = result.metadata.get("hat", "none")

    decision = Decision(
        hat_name=hat_name,
        input_message=input_message,
        intent=asdict(result.intent),
        risk_tier=result.risk_classification.tier,
        action_taken=result.execution.action_taken.tool_name,
        response=result.response,
        bypassed=result.bypassed,
        metadata_=result.metadata,
    )
    session.add(decision)
    await session.flush()  # Get the ID

    # Store proposals
    for rank, candidate in enumerate(result.proposal.candidates):
        session.add(DecisionProposal(
            decision_id=decision.id,
            rank=rank,
            tool_name=candidate.tool_name,
            parameters=candidate.parameters,
            reasoning=candidate.reasoning,
            expected_outcome=candidate.expected_outcome,
        ))

    # Store consequence trees
    for tree in result.consequence_trees:
        session.add(DecisionTree(
            decision_id=decision.id,
            candidate_tool_name=tree.candidate_action.tool_name,
            tree_data=_tree_to_dict(tree),
            total_nodes=tree.total_nodes,
            worst_harm=tree.worst_terminal.harm_benefit if tree.worst_terminal else None,
            best_benefit=tree.best_terminal.harm_benefit if tree.best_terminal else None,
        ))

    # Store evaluations
    for eval_result in result.evaluation_results:
        session.add(DecisionEvaluation(
            decision_id=decision.id,
            evaluator_name=eval_result.evaluator_name,
            score=eval_result.score,
            confidence=eval_result.confidence,
            flags=eval_result.flags,
            reasoning=eval_result.reasoning,
            key_concerns=eval_result.key_concerns,
        ))

    # Snapshot hat config if available
    if hat_name != "none":
        session.add(HatConfigSnapshot(
            decision_id=decision.id,
            hat_name=hat_name,
            hat_version=result.metadata.get("hat_version", "unknown"),
            constraints=result.intent.parameters if result.intent else {},
            stakeholders={},
            evaluator_config={},
        ))

    await session.commit()
    logger.info("Audit record stored: decision_id=%d hat=%s tier=%s", decision.id, hat_name, decision.risk_tier)
    return decision.id


async def store_decision_with_hat(
    session: AsyncSession,
    result: PipelineResult,
    input_message: str,
    hat_config=None,
) -> int:
    """Store a pipeline result with full hat config snapshot."""
    hat_name = result.metadata.get("hat", "none")

    decision = Decision(
        hat_name=hat_name,
        input_message=input_message,
        intent=asdict(result.intent),
        risk_tier=result.risk_classification.tier,
        action_taken=result.execution.action_taken.tool_name,
        response=result.response,
        bypassed=result.bypassed,
        metadata_=result.metadata,
    )
    session.add(decision)
    await session.flush()

    for rank, candidate in enumerate(result.proposal.candidates):
        session.add(DecisionProposal(
            decision_id=decision.id,
            rank=rank,
            tool_name=candidate.tool_name,
            parameters=candidate.parameters,
            reasoning=candidate.reasoning,
            expected_outcome=candidate.expected_outcome,
        ))

    for tree in result.consequence_trees:
        session.add(DecisionTree(
            decision_id=decision.id,
            candidate_tool_name=tree.candidate_action.tool_name,
            tree_data=_tree_to_dict(tree),
            total_nodes=tree.total_nodes,
            worst_harm=tree.worst_terminal.harm_benefit if tree.worst_terminal else None,
            best_benefit=tree.best_terminal.harm_benefit if tree.best_terminal else None,
        ))

    for eval_result in result.evaluation_results:
        session.add(DecisionEvaluation(
            decision_id=decision.id,
            evaluator_name=eval_result.evaluator_name,
            score=eval_result.score,
            confidence=eval_result.confidence,
            flags=eval_result.flags,
            reasoning=eval_result.reasoning,
            key_concerns=eval_result.key_concerns,
        ))

    if hat_config is not None:
        session.add(HatConfigSnapshot(
            decision_id=decision.id,
            hat_name=hat_config.name,
            hat_version=hat_config.manifest.version,
            constraints=hat_config.constraints,
            stakeholders=hat_config.stakeholders.model_dump(),
            evaluator_config=hat_config.evaluator_config.model_dump(),
        ))

    await session.commit()
    logger.info("Audit record stored: decision_id=%d hat=%s tier=%s", decision.id, hat_name, decision.risk_tier)
    return decision.id


async def store_outcome(
    session: AsyncSession,
    decision_id: int,
    actual_outcome: str,
    outcome_matches_prediction: bool | None = None,
    notes: str = "",
) -> DecisionOutcome:
    """Record the actual outcome for a decision."""
    outcome = DecisionOutcome(
        decision_id=decision_id,
        actual_outcome=actual_outcome,
        outcome_matches_prediction=outcome_matches_prediction,
        notes=notes,
    )
    session.add(outcome)
    await session.commit()
    logger.info("Outcome stored for decision_id=%d", decision_id)
    return outcome


async def store_feedback(
    session: AsyncSession,
    decision_id: int,
    feedback_type: str,
    original_tier: str,
    override_action: str | None = None,
    reason: str = "",
) -> Feedback:
    """Record human feedback or override for a decision."""
    fb = Feedback(
        decision_id=decision_id,
        feedback_type=feedback_type,
        original_tier=original_tier,
        override_action=override_action,
        reason=reason,
    )
    session.add(fb)
    await session.commit()
    logger.info("Feedback stored for decision_id=%d type=%s", decision_id, feedback_type)
    return fb


async def get_decision(session: AsyncSession, decision_id: int) -> Decision | None:
    """Retrieve a single decision with all related data."""
    stmt = (
        select(Decision)
        .where(Decision.id == decision_id)
        .options(
            selectinload(Decision.proposals),
            selectinload(Decision.trees),
            selectinload(Decision.evaluations),
            selectinload(Decision.outcome),
            selectinload(Decision.feedback_entries),
            selectinload(Decision.hat_config_snapshot),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def query_decisions(
    session: AsyncSession,
    hat_name: str | None = None,
    risk_tier: str | None = None,
    tool_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Decision]:
    """Query decisions with optional filters."""
    stmt = (
        select(Decision)
        .options(
            selectinload(Decision.proposals),
            selectinload(Decision.evaluations),
            selectinload(Decision.outcome),
            selectinload(Decision.feedback_entries),
        )
        .order_by(Decision.timestamp.desc())
    )

    if hat_name:
        stmt = stmt.where(Decision.hat_name == hat_name)
    if risk_tier:
        stmt = stmt.where(Decision.risk_tier == risk_tier)
    if tool_name:
        stmt = stmt.where(Decision.action_taken == tool_name)
    if start_date:
        stmt = stmt.where(Decision.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(Decision.timestamp <= end_date)

    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())
