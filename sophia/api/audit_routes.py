"""Audit API routes — read-only query endpoints + outcome/feedback submission."""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from sophia.api.schemas import (
    AuditDecisionDetail,
    AuditDecisionSummary,
    AuditEvaluationResponse,
    AuditFeedbackCreate,
    AuditFeedbackResponse,
    AuditHatConfigResponse,
    AuditOutcomeCreate,
    AuditOutcomeResponse,
    AuditProposalResponse,
    AuditTreeResponse,
)
from sophia.audit.database import get_session
from sophia.audit.service import (
    get_decision,
    query_decisions,
    store_feedback,
    store_outcome,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


def _decision_to_summary(d) -> AuditDecisionSummary:
    return AuditDecisionSummary(
        id=d.id,
        timestamp=d.timestamp.isoformat(),
        hat_name=d.hat_name,
        input_message=d.input_message,
        risk_tier=d.risk_tier,
        action_taken=d.action_taken,
        response=d.response,
        bypassed=d.bypassed,
        proposal_count=len(d.proposals) if d.proposals else 0,
        evaluation_count=len(d.evaluations) if d.evaluations else 0,
        has_outcome=d.outcome is not None,
        feedback_count=len(d.feedback_entries) if d.feedback_entries else 0,
    )


def _decision_to_detail(d) -> AuditDecisionDetail:
    proposals = [
        AuditProposalResponse(
            rank=p.rank,
            tool_name=p.tool_name,
            parameters=p.parameters,
            reasoning=p.reasoning,
            expected_outcome=p.expected_outcome,
        )
        for p in (d.proposals or [])
    ]

    trees = [
        AuditTreeResponse(
            candidate_tool_name=t.candidate_tool_name,
            tree_data=t.tree_data,
            total_nodes=t.total_nodes,
            worst_harm=t.worst_harm,
            best_benefit=t.best_benefit,
        )
        for t in (d.trees or [])
    ]

    evaluations = [
        AuditEvaluationResponse(
            evaluator_name=e.evaluator_name,
            score=e.score,
            confidence=e.confidence,
            flags=e.flags,
            reasoning=e.reasoning,
            key_concerns=e.key_concerns,
        )
        for e in (d.evaluations or [])
    ]

    outcome = None
    if d.outcome:
        outcome = AuditOutcomeResponse(
            actual_outcome=d.outcome.actual_outcome,
            outcome_matches_prediction=d.outcome.outcome_matches_prediction,
            notes=d.outcome.notes,
            timestamp=d.outcome.timestamp.isoformat(),
        )

    feedback = [
        AuditFeedbackResponse(
            feedback_type=f.feedback_type,
            original_tier=f.original_tier,
            override_action=f.override_action,
            reason=f.reason,
            timestamp=f.timestamp.isoformat(),
        )
        for f in (d.feedback_entries or [])
    ]

    hat_config = None
    if d.hat_config_snapshot:
        hat_config = AuditHatConfigResponse(
            hat_name=d.hat_config_snapshot.hat_name,
            hat_version=d.hat_config_snapshot.hat_version,
            constraints=d.hat_config_snapshot.constraints,
            stakeholders=d.hat_config_snapshot.stakeholders,
            evaluator_config=d.hat_config_snapshot.evaluator_config,
        )

    return AuditDecisionDetail(
        id=d.id,
        timestamp=d.timestamp.isoformat(),
        hat_name=d.hat_name,
        input_message=d.input_message,
        intent=d.intent,
        risk_tier=d.risk_tier,
        action_taken=d.action_taken,
        response=d.response,
        bypassed=d.bypassed,
        metadata=d.metadata_,
        proposals=proposals,
        trees=trees,
        evaluations=evaluations,
        outcome=outcome,
        feedback=feedback,
        hat_config=hat_config,
    )


@router.get("/decisions", response_model=list[AuditDecisionSummary])
async def list_decisions(
    hat: str | None = Query(None, description="Filter by hat name"),
    tier: str | None = Query(None, description="Filter by risk tier (GREEN/YELLOW/ORANGE/RED)"),
    tool: str | None = Query(None, description="Filter by tool name"),
    start: str | None = Query(None, description="Start date (ISO format)"),
    end: str | None = Query(None, description="End date (ISO format)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Query the audit log with optional filters."""
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None

    async with get_session() as session:
        decisions = await query_decisions(
            session,
            hat_name=hat,
            risk_tier=tier,
            tool_name=tool,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return [_decision_to_summary(d) for d in decisions]


@router.get("/decisions/{decision_id}", response_model=AuditDecisionDetail)
async def get_decision_detail(decision_id: int):
    """Get full detail for a single audit record."""
    async with get_session() as session:
        decision = await get_decision(session, decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
        return _decision_to_detail(decision)


@router.post("/decisions/{decision_id}/outcome", response_model=AuditOutcomeResponse)
async def report_outcome(decision_id: int, body: AuditOutcomeCreate):
    """Report the actual outcome for a decision."""
    async with get_session() as session:
        decision = await get_decision(session, decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
        if decision.outcome is not None:
            raise HTTPException(status_code=409, detail="Outcome already recorded for this decision")

        outcome = await store_outcome(
            session,
            decision_id=decision_id,
            actual_outcome=body.actual_outcome,
            outcome_matches_prediction=body.outcome_matches_prediction,
            notes=body.notes,
        )
        return AuditOutcomeResponse(
            actual_outcome=outcome.actual_outcome,
            outcome_matches_prediction=outcome.outcome_matches_prediction,
            notes=outcome.notes,
            timestamp=outcome.timestamp.isoformat(),
        )


@router.post("/decisions/{decision_id}/feedback", response_model=AuditFeedbackResponse)
async def submit_feedback(decision_id: int, body: AuditFeedbackCreate):
    """Submit human feedback or override for a decision."""
    async with get_session() as session:
        decision = await get_decision(session, decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

        fb = await store_feedback(
            session,
            decision_id=decision_id,
            feedback_type=body.feedback_type,
            original_tier=body.original_tier,
            override_action=body.override_action,
            reason=body.reason,
        )
        return AuditFeedbackResponse(
            feedback_type=fb.feedback_type,
            original_tier=fb.original_tier,
            override_action=fb.override_action,
            reason=fb.reason,
            timestamp=fb.timestamp.isoformat(),
        )
